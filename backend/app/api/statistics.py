from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ml.features import ASSET_TYPES

from ..database import get_db
from ..models import Alert, RiskPrediction
from ..services import pipeline
from .common import cyclone_status, data_label, ensure_run, resolve_cyclone

router = APIRouter(prefix="/api", tags=["statistics"])
CATS = ["Low", "Moderate", "High", "Very High"]


@router.get("/statistics")
def statistics(cyclone_id: int | None = None, district: str | None = None, db: Session = Depends(get_db)):
    cy = resolve_cyclone(db, cyclone_id)
    run = ensure_run(db, cy)
    preds = db.scalars(select(RiskPrediction).options(joinedload(RiskPrediction.asset))
                       .where(RiskPrediction.model_run_id == run.id)).all()
    if district:
        preds = [p for p in preds if p.asset.district == district]
    summary = run.summary or {}
    dist_rows = summary.get("districts", [])
    if district:
        dist_rows = [d for d in dist_rows if d["district"] == district]

    dist = Counter(p.risk_category for p in preds)
    by_type: dict[str, Counter] = defaultdict(Counter)
    for p in preds:
        by_type[p.asset.asset_type][p.risk_category] += 1
    top = sorted(preds, key=lambda p: -p.risk_score)[:10]
    hazard_avg = {}
    if preds:
        for k in ("wind_impact", "rainfall_impact", "flood_probability", "surge_exposure"):
            hazard_avg[k] = round(sum(p.impact[k] for p in preds) / len(preds), 3)
    high = [p for p in preds if p.risk_category in ("High", "Very High")]
    affected = [d["district"] for d in dist_rows if d["high_risk_assets"] > 0 or d["population_exposed_gale"] > 0]
    n_alerts = db.query(Alert).filter(Alert.model_run_id == run.id).count()
    track = pipeline.track_dicts(cy)

    return {
        "cyclone_id": cy.id, **data_label(cy), "model_run_id": run.id,
        "cards": {
            "cyclone_status": cyclone_status(db, cy, run),
            "max_wind_kmh": summary.get("max_forecast_wind_kmh"),
            "affected_districts": len(affected), "affected_district_names": affected,
            "high_risk_infrastructure": len(high),
            "very_high_risk_infrastructure": dist.get("Very High", 0),
            "population_exposed": sum(d["population_exposed_gale"] for d in dist_rows),
            "population_note": summary.get("population_note"),
            "total_assets": len(preds), "alerts": n_alerts,
        },
        "risk_distribution": [{"category": c, "count": dist.get(c, 0)} for c in CATS],
        "risk_by_type": [{"asset_type": t, "label": ASSET_TYPES[t]["label"], **{c: by_type[t].get(c, 0) for c in CATS},
                          "total": sum(by_type[t].values())} for t in ASSET_TYPES if by_type.get(t)],
        "hazard_contribution": [{"name": p.asset.name, "asset_id": p.asset_id, "risk_score": p.risk_score,
                                 **p.contributions} for p in top],
        "average_hazard_index": hazard_avg,
        "districts": dist_rows,
        "intensity_timeline": [{"time": p["timestamp"].isoformat(), "t_hours": round(p["t_hours"], 1),
                                "wind_kmh": p["wind_kmh"], "pressure_hpa": p["pressure_hpa"] or None,
                                "category": p["category"], "is_forecast": p["is_forecast"]} for p in track],
    }
