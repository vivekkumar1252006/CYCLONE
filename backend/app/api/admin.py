"""Demo mode, settings, model info, data sources and weather endpoints."""
from __future__ import annotations

import json

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ml.risk_scoring import RiskConfig

from ..config import get_settings
from ..database import get_db
from ..models import District, WeatherObservation, as_utc
from ..providers import registry
from ..providers.base import ProviderUnavailable
from ..schemas import DemoGenerateIn, RiskConfigIn
from ..security import require_admin
from ..services import demo_generator, pipeline, settings_store
from .common import DEMO_LABEL, cyclone_status, data_label, resolve_cyclone

router = APIRouter(prefix="/api", tags=["admin"])


# ---------------- demo mode ----------------
@router.get("/demo/scenarios")
def demo_scenarios():
    return [{"key": k, "name": v["name"], "description": v["description"],
             "peak_wind_kmh": max(p[3] for p in v["points"]), "data_mode": DEMO_LABEL}
            for k, v in demo_generator.SCENARIOS.items()]


@router.post("/demo/generate", dependencies=[Depends(require_admin)])
def demo_generate(body: DemoGenerateIn = Body(default_factory=DemoGenerateIn), db: Session = Depends(get_db)):
    """Generate a SIMULATED scenario (track, weather, infrastructure) and run the full pipeline."""
    cy = demo_generator.generate_demo(db, body.scenario, n_assets=body.n_assets, seed=body.seed,
                                      regenerate_assets=body.regenerate_assets)
    settings_store.set_active_cyclone_id(db, cy.id)
    db.commit()
    run = pipeline.run_prediction(db, cy.id)
    return {"cyclone": cyclone_status(db, cy, run), "model_run_id": run.id, "n_assets": run.n_assets,
            "data_mode": DEMO_LABEL}


# ---------------- settings ----------------
@router.get("/settings/risk")
def get_risk_settings(db: Session = Depends(get_db)):
    return {"config": settings_store.get_risk_config(db).to_dict(), "defaults": RiskConfig().to_dict(),
            "note": "Weights, thresholds and gate are configurable prototype assumptions, not validated standards."}


def _apply(db: Session, cfg: RiskConfig) -> dict:
    try:
        settings_store.set_risk_config(db, cfg)
    except ValueError as e:
        raise HTTPException(422, detail=str(e))
    db.commit()
    cid = settings_store.get_active_cyclone_id(db)
    run_id = pipeline.run_prediction(db, cid).id if cid else None
    return {"config": cfg.to_dict(), "model_run_id": run_id}


@router.put("/settings/risk", dependencies=[Depends(require_admin)])
def put_risk_settings(body: RiskConfigIn, db: Session = Depends(get_db)):
    data = body.model_dump()
    if data.get("hazard_subweights") is None:
        data.pop("hazard_subweights", None)
    try:
        cfg = RiskConfig.from_dict(data)
    except ValueError as e:
        raise HTTPException(422, detail=str(e))
    return _apply(db, cfg)


@router.post("/settings/risk/reset", dependencies=[Depends(require_admin)])
def reset_risk_settings(db: Session = Depends(get_db)):
    return _apply(db, RiskConfig())


# ---------------- model + data sources ----------------
@router.get("/model/info")
def model_info():
    m = pipeline.get_vulnerability_model()
    imp = pipeline.get_impact_model()
    meta_path = get_settings().model_path.with_suffix(".json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return {
        "impact_model": {"name": imp.name, "version": imp.version, "type": "parametric / physics-informed",
                         "outputs": ["peak_wind_kmh", "wind_impact", "rainfall_mm", "rainfall_impact",
                                     "flood_probability", "surge_exposure"]},
        "vulnerability_model": {"name": m.name, "version": m.version, "metrics": m.metrics,
                                "feature_importances": m.feature_importances() or meta.get("feature_importances", {}),
                                "training_data_warning": "Trained on SYNTHETIC fragility-curve data. Metrics measure fit to "
                                                         "that synthetic process, not real-world damage prediction skill."},
        "explainability": "Occlusion attribution per feature group + transparent weighted risk components.",
    }


@router.get("/data-sources")
def data_sources():
    return registry.status()


# ---------------- weather ----------------
@router.get("/weather")
def weather(cyclone_id: int | None = None, db: Session = Depends(get_db)):
    cy = resolve_cyclone(db, cyclone_id)
    obs = db.scalars(select(WeatherObservation).where(
        (WeatherObservation.cyclone_id == cy.id) | (WeatherObservation.is_demo.is_(False)))).all()
    return {"cyclone_id": cy.id, **data_label(cy), "items": [{
        "id": o.id, "station_name": o.station_name, "lat": o.lat, "lon": o.lon, "observed_at": as_utc(o.observed_at).isoformat(),
        "rainfall_mm": o.rainfall_mm, "wind_speed_kmh": o.wind_speed_kmh, "wind_direction_deg": o.wind_direction_deg,
        "temperature_c": o.temperature_c, "humidity_pct": o.humidity_pct, "surge_indicator_m": o.surge_indicator_m,
        "source": o.source, "is_demo": o.is_demo} for o in obs]}


@router.post("/weather/refresh", dependencies=[Depends(require_admin)])
def refresh_weather(db: Session = Depends(get_db)):
    """Pull NWP forecast rainfall from the live provider (if configured); otherwise keep simulated readings."""
    prov = registry.weather_provider()
    if prov is None:
        return {"status": "fallback", "mode": "demo",
                "message": "No live weather provider configured (WEATHER_PROVIDER=openmeteo). Using simulated readings."}
    pts = [{"name": d.name, "lat": d.center_lat, "lon": d.center_lon} for d in db.scalars(select(District)).all()]
    try:
        rows = prov.fetch(pts)
    except ProviderUnavailable as e:
        return {"status": "fallback", "mode": "demo", "message": f"{e}. Using simulated readings."}
    db.execute(delete(WeatherObservation).where(WeatherObservation.is_demo.is_(False)))
    for r in rows:
        db.add(WeatherObservation(cyclone_id=None, **r))
    db.commit()
    cid = settings_store.get_active_cyclone_id(db)
    if cid:
        pipeline.run_prediction(db, cid)
    return {"status": "ok", "mode": "live", "provider": prov.name, "stations": len(rows)}
