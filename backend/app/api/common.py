"""Shared helpers for route handlers (cyclone resolution, serialisation, labels)."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ml.features import ASSET_TYPES
from ml.geo import bearing_deg, haversine_km

from ..models import Cyclone, ModelRun, RiskPrediction
from ..services import pipeline, settings_store
from ..services.demo_generator import CATEGORY_NAMES

DEMO_LABEL = "DEMO / SIMULATED DATA"
ESTIMATE_NOTE = ("All risk values are model estimates with uncertainty, intended to support preparedness "
                 "decisions. They are not observations and do not guarantee that damage will or will not occur.")


def data_label(cy: Cyclone) -> dict:
    return {"is_demo": cy.is_demo, "data_mode": DEMO_LABEL if cy.is_demo else f"{cy.source.upper()} DATA",
            "source": cy.source, "disclaimer": ESTIMATE_NOTE}


def resolve_cyclone(db: Session, cyclone_id: int | None) -> Cyclone:
    cid = cyclone_id if cyclone_id is not None else settings_store.get_active_cyclone_id(db)
    cy = db.get(Cyclone, cid) if cid is not None else None
    if cy is None:
        raise HTTPException(404, detail="No cyclone loaded. Generate a demo scenario (POST /api/demo/generate) "
                                        "or create a cyclone track (POST /api/cyclones).")
    return cy


def ensure_run(db: Session, cy: Cyclone) -> ModelRun:
    run = pipeline.latest_run(db, cy.id)
    if run is None:
        try:
            run = pipeline.run_prediction(db, cy.id)
        except ValueError as e:
            raise HTTPException(422, detail=str(e))
    return run


def cyclone_status(db: Session, cy: Cyclone, run: ModelRun | None) -> dict:
    track = pipeline.track_dicts(cy)
    observed = [p for p in track if not p["is_forecast"]] or track[:1]
    cur = observed[-1]
    movement = None
    if len(observed) >= 2:
        a, b = observed[-2], observed[-1]
        hrs = max(b["t_hours"] - a["t_hours"], 1e-6)
        movement = {"bearing_deg": round(bearing_deg(a["lat"], a["lon"], b["lat"], b["lon"])),
                    "speed_kmh": round(haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) / hrs, 1)}
    forecast = [p for p in track if p["is_forecast"]]
    return {
        "id": cy.id, "name": cy.name, "description": cy.description, "basin": cy.basin,
        **data_label(cy),
        "analysis_time": cur["timestamp"].isoformat(),
        "position": {"lat": cur["lat"], "lon": cur["lon"]},
        "wind_kmh": cur["wind_kmh"], "pressure_hpa": cur["pressure_hpa"] or None,
        "category": cur["category"], "category_name": CATEGORY_NAMES.get(cur["category"], cur["category"]),
        "movement": movement,
        "max_forecast_wind_kmh": max([p["wind_kmh"] for p in forecast] + [cur["wind_kmh"]]),
        "forecast_hours": round(forecast[-1]["t_hours"]) if forecast else 0,
        "landfall": (run.summary or {}).get("landfall") if run else None,
        "model_run_id": run.id if run else None,
    }


def prediction_summary(p: RiskPrediction) -> dict:
    a = p.asset
    return {
        "asset_id": a.id, "name": a.name, "asset_type": a.asset_type, "asset_type_label": ASSET_TYPES[a.asset_type]["label"],
        "district": a.district, "lat": a.lat, "lon": a.lon,
        "risk_score": p.risk_score, "risk_category": p.risk_category,
        "confidence": p.confidence, "confidence_label": p.confidence_label,
        "main_hazard": p.main_hazard, "dist_track_km": round(p.impact["dist_track_km"], 1),
        "source": a.source, "is_demo": a.is_demo,
    }
