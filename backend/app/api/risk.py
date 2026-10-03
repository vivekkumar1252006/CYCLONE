from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ml.features import ASSET_TYPES
from ml.geo import densify_track
from ml.risk_scoring import predicted_hazards

from ..database import get_db
from ..geodata import region
from ..models import District, Infrastructure, RiskPrediction
from ..schemas import PredictIn
from ..security import require_admin
from ..services import ingest, pipeline, settings_store
from ..services.recommendations import DISCLAIMER
from .common import ESTIMATE_NOTE, data_label, ensure_run, prediction_summary, resolve_cyclone

router = APIRouter(prefix="/api", tags=["risk"])


def _preds(db: Session, run_id: int, district: str | None = None, asset_type: str | None = None):
    stmt = (select(RiskPrediction).join(Infrastructure).options(joinedload(RiskPrediction.asset))
            .where(RiskPrediction.model_run_id == run_id))
    if district:
        stmt = stmt.where(Infrastructure.district == district)
    if asset_type:
        stmt = stmt.where(Infrastructure.asset_type == asset_type)
    return db.scalars(stmt).all()


@router.get("/risk/map")
def risk_map(cyclone_id: int | None = None, district: str | None = None, asset_type: str | None = None,
             db: Session = Depends(get_db)):
    """Everything the map needs: assets with risk, hazard grids, vulnerability surface, reference layers."""
    cy = resolve_cyclone(db, cyclone_id)
    run = ensure_run(db, cy)
    preds = _preds(db, run.id, district, asset_type)
    districts = db.scalars(select(District)).all()
    return {
        "cyclone_id": cy.id, "model_run_id": run.id, **data_label(cy),
        "assets": [prediction_summary(p) for p in preds],
        "grids": run.grids,
        "districts": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": d.boundary,
             "properties": {"name": d.name, "state": d.state, "population": d.population, "note": d.boundary_note}}
            for d in districts]},
        "reference": {
            "coastline": region.line_geojson(region.COASTLINE),
            "rivers": [{"name": k, "geometry": region.line_geojson(v)} for k, v in region.RIVERS.items()],
            "flood_zones": [{"name": k, "geometry": region.polygon_geojson(v)} for k, v in region.FLOOD_ZONES.items()],
            "note": "Simplified reference geometry for the demo study region (not survey-grade).",
        },
        "bbox": region.REGION_BBOX,
        "thresholds": {k: run.config[k] for k in ("threshold_low", "threshold_moderate", "threshold_high")},
    }


@router.get("/risk/priority")
def priority_list(cyclone_id: int | None = None, district: str | None = None, asset_type: str | None = None,
                  limit: int = Query(default=20, ge=1, le=500), db: Session = Depends(get_db)):
    cy = resolve_cyclone(db, cyclone_id)
    run = ensure_run(db, cy)
    preds = sorted(_preds(db, run.id, district, asset_type), key=lambda p: (-p.risk_score, -p.confidence))
    return {"cyclone_id": cy.id, **data_label(cy), "items": [prediction_summary(p) for p in preds[:limit]],
            "ranking": "Sorted by risk score, then confidence"}


@router.get("/risk/{asset_id}")
def asset_risk(asset_id: int, cyclone_id: int | None = None, db: Session = Depends(get_db)):
    cy = resolve_cyclone(db, cyclone_id)
    run = ensure_run(db, cy)
    p = db.scalars(select(RiskPrediction).options(joinedload(RiskPrediction.asset))
                   .where(RiskPrediction.model_run_id == run.id, RiskPrediction.asset_id == asset_id)).first()
    if p is None:
        if db.get(Infrastructure, asset_id) is None:
            raise HTTPException(404, detail=f"asset {asset_id} not found")
        raise HTTPException(404, detail=f"no prediction for asset {asset_id} in the latest model run")
    a = p.asset
    imp = p.impact
    return {
        **data_label(cy), "cyclone_id": cy.id, "cyclone_name": cy.name, "model_run_id": run.id,
        "asset": {**pipeline.asset_to_dict(a), "asset_type_label": ASSET_TYPES[a.asset_type]["label"]},
        "risk_score": p.risk_score, "risk_category": p.risk_category,
        "score_band": p.confidence_detail.get("score_band"),
        "confidence": p.confidence_detail,
        "vulnerability_probability": p.vulnerability,
        "main_hazard": p.main_hazard,
        "predicted_hazards": predicted_hazards(imp),
        "distance_from_track_km": round(imp["dist_track_km"], 1),
        "closest_approach_hours": imp["closest_approach_hours"],
        "track_uncertainty_km": imp["track_uncertainty_km"],
        "right_side_of_track": imp["right_side_of_track"],
        "flood_exposure": imp["flood_probability"], "wind_exposure": imp["wind_impact"],
        "peak_wind_kmh": imp["peak_wind_kmh"], "rainfall_mm": imp["rainfall_mm"], "surge_exposure": imp["surge_exposure"],
        "criticality": p.components["criticality"],
        "components": p.components, "contributions": p.contributions,
        "main_risk_factors": p.factors, "ml_attributions": p.ml_attributions,
        "recommendations": p.recommendations, "recommendations_disclaimer": DISCLAIMER,
        "weights": {k: run.config[k] for k in ("w_hazard", "w_vulnerability", "w_environment", "w_criticality", "hazard_gate")},
        "models": {"impact": run.impact_model, "vulnerability": run.vulnerability_model},
        "note": ESTIMATE_NOTE,
    }


@router.post("/predict")
def predict(body: PredictIn, db: Session = Depends(get_db),
            x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    """Run predictions.

    * Without ``assets``: re-runs the full pipeline for the cyclone and stores a new model run (admin).
    * With ``assets``: scores the supplied ad-hoc assets against the cyclone WITHOUT storing them.
    """
    cy = resolve_cyclone(db, body.cyclone_id)
    if not body.assets:
        require_admin(x_api_key)
        try:
            run = pipeline.run_prediction(db, cy.id)
        except ValueError as e:
            raise HTTPException(422, detail=str(e))
        return {"cyclone_id": cy.id, "model_run_id": run.id, "n_assets": run.n_assets, "status": run.status,
                **data_label(cy)}
    recs, errors = [], []
    for i, a in enumerate(body.assets):
        try:
            recs.append(ingest.validate_record(a.model_dump(), a.lat, a.lon))
        except ingest.IngestError as e:
            errors.append({"index": i, "name": a.name, "error": str(e)})
    if not recs:
        raise HTTPException(422, detail={"message": "no valid assets", "errors": errors})
    cfg = settings_store.get_risk_config(db)
    dense = densify_track(pipeline.track_dicts(cy), 1.0)
    scored = pipeline.score_assets(dense, recs, cfg)
    return {"cyclone_id": cy.id, **data_label(cy), "errors": errors, "results": [
        {"input": {k: r[k] for k in ("name", "asset_type", "lat", "lon", "district", "elevation_m", "elevation_source")},
         "risk_score": s["risk"]["score"], "risk_category": s["risk"]["category"], "score_band": s["score_band"],
         "confidence": s["confidence"], "main_hazard": s["main_hazard"], "impact": s["impact"],
         "components": s["risk"]["components"], "contributions": s["risk"]["contributions"],
         "main_risk_factors": s["factors"], "ml_attributions": s["ml_attributions"],
         "recommendations": s["recommendations"]} for r, s in zip(recs, scored)]}
