from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Cyclone, CycloneTrackPoint
from ..providers.base import ProviderUnavailable
from ..providers import registry
from ..schemas import CycloneIn
from ..security import require_admin
from ..services import pipeline, settings_store
from ..services.demo_generator import cone_radius, imd_category, rmw_for, roi_for
from .common import cyclone_status, data_label, ensure_run, resolve_cyclone

router = APIRouter(prefix="/api", tags=["cyclone"])


@router.get("/cyclones")
def list_cyclones(db: Session = Depends(get_db)):
    active = settings_store.get_active_cyclone_id(db)
    out = []
    for cy in db.scalars(select(Cyclone).order_by(Cyclone.id.desc())).all():
        out.append({"id": cy.id, "name": cy.name, "description": cy.description, "scenario_key": cy.scenario_key,
                    "active": cy.id == active, **data_label(cy)})
    return out


@router.get("/cyclone/current")
def current_cyclone(cyclone_id: int | None = None, db: Session = Depends(get_db)):
    cy = resolve_cyclone(db, cyclone_id)
    return cyclone_status(db, cy, ensure_run(db, cy))


@router.get("/cyclone/track")
def cyclone_track(cyclone_id: int | None = None, db: Session = Depends(get_db)):
    cy = resolve_cyclone(db, cyclone_id)
    pts = [{"time": p["timestamp"].isoformat(), "t_hours": round(p["t_hours"], 1), "lat": p["lat"], "lon": p["lon"],
            "wind_kmh": p["wind_kmh"], "pressure_hpa": p["pressure_hpa"] or None, "category": p["category"],
            "rmw_km": p["rmw_km"], "roi_km": p["roi_km"], "uncertainty_km": p["uncertainty_km"],
            "is_forecast": p["is_forecast"]} for p in pipeline.track_dicts(cy)]
    observed = [p for p in pts if not p["is_forecast"]]
    # forecast line starts at the current (last observed) position
    forecast = observed[-1:] + [p for p in pts if p["is_forecast"]]
    return {"cyclone_id": cy.id, "name": cy.name, **data_label(cy), "points": pts,
            "observed": observed, "forecast": forecast,
            "note": "Forecast positions are model/scenario estimates; circles show the track-uncertainty radius."}


def _store_cyclone(db: Session, name: str, description: str | None, points: list[dict], source: str) -> Cyclone:
    cy = Cyclone(name=name, description=description, source=source, is_demo=False)
    observed = [p for p in points if not p["is_forecast"]]
    t0 = observed[-1]["time"]
    for p in points:
        lead = (p["time"] - t0).total_seconds() / 3600
        w = float(p["wind_kmh"])
        cy.track.append(CycloneTrackPoint(
            timestamp=p["time"], lat=p["lat"], lon=p["lon"], wind_kmh=w, pressure_hpa=p.get("pressure_hpa"),
            category=imd_category(w), rmw_km=p.get("rmw_km") or rmw_for(w), roi_km=p.get("roi_km") or roi_for(w),
            is_forecast=p["is_forecast"],
            uncertainty_km=p.get("uncertainty_km") if p.get("uncertainty_km") is not None else cone_radius(lead)))
    db.add(cy)
    db.flush()
    settings_store.set_active_cyclone_id(db, cy.id)
    db.commit()
    return cy


@router.post("/cyclones", dependencies=[Depends(require_admin)], status_code=201)
def create_cyclone(body: CycloneIn, db: Session = Depends(get_db)):
    """Create a cyclone from a user-supplied observed + forecast track, then run the models."""
    cy = _store_cyclone(db, body.name, body.description, [p.model_dump() for p in body.points], source="user")
    run = pipeline.run_prediction(db, cy.id)
    return cyclone_status(db, cy, run)


@router.post("/cyclone/{cyclone_id}/activate", dependencies=[Depends(require_admin)])
def activate_cyclone(cyclone_id: int, db: Session = Depends(get_db)):
    cy = resolve_cyclone(db, cyclone_id)
    settings_store.set_active_cyclone_id(db, cy.id)
    db.commit()
    return cyclone_status(db, cy, ensure_run(db, cy))


@router.post("/cyclone/import-live", dependencies=[Depends(require_admin)])
def import_live(db: Session = Depends(get_db)):
    """Import tracks from the configured live feed. Falls back (503) to existing/demo data if unavailable."""
    prov = registry.cyclone_provider()
    if prov is None:
        raise HTTPException(503, detail="No live cyclone feed configured (CYCLONE_FEED_URL). Continuing with demo data.")
    try:
        cyclones = prov.fetch_tracks()
    except ProviderUnavailable as e:
        raise HTTPException(503, detail=f"{e}. Continuing with existing/demo data.")
    imported = []
    for c in cyclones:
        try:
            body = CycloneIn(name=str(c.get("name", "Unnamed"))[:120],
                             points=[{"time": p["time"], "lat": p["lat"], "lon": p["lon"], "wind_kmh": p["wind_kmh"],
                                      "pressure_hpa": p.get("pressure_hpa"), "is_forecast": bool(p.get("is_forecast")),
                                      "rmw_km": p.get("rmw_km"), "roi_km": p.get("roi_km"),
                                      "uncertainty_km": p.get("uncertainty_km")} for p in c.get("points", [])])
        except (ValueError, KeyError, TypeError) as e:
            imported.append({"name": c.get("name"), "status": "rejected", "error": str(e)[:300]})
            continue
        cy = _store_cyclone(db, body.name, "Imported from live feed", [p.model_dump() for p in body.points], "live-feed")
        pipeline.run_prediction(db, cy.id)
        imported.append({"name": cy.name, "id": cy.id, "status": "imported"})
    return {"imported": imported}
