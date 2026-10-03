from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from ml.features import ASSET_TYPES

from ..config import get_settings
from ..database import get_db
from ..models import Infrastructure, RiskPrediction
from ..security import require_admin
from ..services import ingest, pipeline, settings_store

router = APIRouter(prefix="/api/infrastructure", tags=["infrastructure"])

TEMPLATE_CSV = """name,asset_type,lat,lon,district,elevation_m,age_years,historical_damage_count,criticality,capacity
Puri Grid Substation,power_substation,19.812,85.815,Puri,3.5,28,2,,132/33 kV
District Headquarters Hospital Puri,hospital,19.805,85.830,Puri,,35,1,1.0,300 beds
Konark Road Bridge,bridge,19.890,86.050,Puri,4,40,,,
"""


@router.get("")
def list_infrastructure(asset_type: str | None = None, district: str | None = None,
                        q: str | None = Query(default=None, max_length=100),
                        limit: int = Query(default=500, ge=1, le=5000), offset: int = Query(default=0, ge=0),
                        db: Session = Depends(get_db)):
    stmt = select(Infrastructure)
    if asset_type:
        if asset_type not in ASSET_TYPES:
            raise HTTPException(422, detail=f"unknown asset_type; expected one of {', '.join(ASSET_TYPES)}")
        stmt = stmt.where(Infrastructure.asset_type == asset_type)
    if district:
        stmt = stmt.where(Infrastructure.district == district)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Infrastructure.name.ilike(like), Infrastructure.district.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    assets = db.scalars(stmt.order_by(Infrastructure.id).offset(offset).limit(limit)).all()
    # attach latest risk for the active cyclone, if any
    risk = {}
    cid = settings_store.get_active_cyclone_id(db)
    run = pipeline.latest_run(db, cid) if cid else None
    if run and assets:
        for p in db.scalars(select(RiskPrediction).where(RiskPrediction.model_run_id == run.id,
                                                         RiskPrediction.asset_id.in_([a.id for a in assets]))).all():
            risk[p.asset_id] = {"risk_score": p.risk_score, "risk_category": p.risk_category, "confidence": p.confidence}
    return {"total": total, "items": [{**pipeline.asset_to_dict(a), "asset_type_label": ASSET_TYPES[a.asset_type]["label"],
                                       **risk.get(a.id, {})} for a in assets]}


@router.get("/types")
def asset_types():
    return [{"key": k, "label": v["label"], "criticality": v["criticality"]} for k, v in ASSET_TYPES.items()]


@router.get("/template.csv", response_class=PlainTextResponse)
def template_csv():
    return PlainTextResponse(TEMPLATE_CSV, media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=infrastructure_template.csv"})


@router.post("/upload", dependencies=[Depends(require_admin)])
async def upload_infrastructure(file: UploadFile = File(...), mode: Literal["append", "replace"] = "append",
                                db: Session = Depends(get_db)):
    """Upload CSV or GeoJSON. ``replace`` removes ALL existing assets (demo and uploaded) first."""
    max_bytes = int(get_settings().max_upload_mb * 1024 * 1024)
    content = await file.read(max_bytes + 1)
    try:
        result = ingest.parse_upload(file.filename or "", content, max_bytes)
    except ingest.IngestError as e:
        raise HTTPException(422, detail=str(e))
    if not result.accepted:
        raise HTTPException(422, detail={"message": "no valid records found", "rejected": result.rejected[:100]})
    if mode == "replace":
        db.execute(delete(Infrastructure))
    for rec in result.accepted:
        db.add(Infrastructure(**rec, source="upload", is_demo=False))
    db.commit()
    rerun = None
    cid = settings_store.get_active_cyclone_id(db)
    if cid:
        run = pipeline.run_prediction(db, cid)
        rerun = run.id
    return {"accepted": len(result.accepted), "rejected": result.rejected[:200], "rejected_count": len(result.rejected),
            "warnings": result.warnings, "mode": mode, "model_run_id": rerun,
            "derived_fields_note": "Elevation (if missing), slope, coast/river distance and flood-zone flags were derived "
                                   "from the study-region GIS layers (synthetic DEM in demo mode)."}


@router.delete("/uploaded", dependencies=[Depends(require_admin)])
def delete_uploaded(db: Session = Depends(get_db)):
    n = db.execute(delete(Infrastructure).where(Infrastructure.source == "upload")).rowcount
    db.commit()
    cid = settings_store.get_active_cyclone_id(db)
    if cid and db.scalar(select(Infrastructure.id).limit(1)) is not None:
        pipeline.run_prediction(db, cid)
    return {"deleted": n}
