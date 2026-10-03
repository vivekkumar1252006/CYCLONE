"""Persisted application settings (risk configuration, active cyclone)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ml.risk_scoring import RiskConfig

from ..models import AppSetting, Cyclone


def _get(db: Session, key: str) -> dict | None:
    row = db.get(AppSetting, key)
    return row.value if row else None


def _set(db: Session, key: str, value: dict) -> None:
    row = db.get(AppSetting, key)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.flush()


def get_risk_config(db: Session) -> RiskConfig:
    try:
        return RiskConfig.from_dict(_get(db, "risk_config"))
    except (ValueError, TypeError):
        return RiskConfig()


def set_risk_config(db: Session, cfg: RiskConfig) -> None:
    cfg.validate()
    _set(db, "risk_config", cfg.to_dict())


def get_active_cyclone_id(db: Session) -> int | None:
    v = _get(db, "active_cyclone")
    cid = v.get("id") if v else None
    if cid is not None and db.get(Cyclone, cid) is not None:
        return cid
    latest = db.query(Cyclone).order_by(Cyclone.id.desc()).first()
    return latest.id if latest else None


def set_active_cyclone_id(db: Session, cyclone_id: int) -> None:
    _set(db, "active_cyclone", {"id": cyclone_id})
