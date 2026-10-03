"""End-to-end prediction pipeline.

track -> (validation) -> Model A impact -> features -> Model B vulnerability ->
risk scoring -> confidence -> explanations -> recommendations -> alerts ->
hazard grids & district statistics, persisted as one ``ModelRun``.
"""
from __future__ import annotations

import logging
import math
import threading
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ml.features import build_feature_row
from ml.geo import densify_track, haversine_km
from ml.impact_model import ImpactModel, ParametricImpactModel, SiteContext
from ml.risk_scoring import (RiskConfig, compute_risk, confidence_score, explain_factors,
                             format_ml_attributions, main_hazard)
from ml.train import load_or_train
from ml.vulnerability_model import VulnerabilityModel, to_frame

from ..config import get_settings
from ..geodata import region
from ..models import Alert, Cyclone, Infrastructure, ModelRun, RiskPrediction, WeatherObservation, as_utc
from . import alert_engine, recommendations, settings_store

log = logging.getLogger(__name__)
_model_lock = threading.Lock()
_vuln_model: VulnerabilityModel | None = None
_impact_model: ImpactModel = ParametricImpactModel()

GRID_RES_DEG = 0.1
KEEP_RUNS_PER_CYCLONE = 3


def get_vulnerability_model() -> VulnerabilityModel:
    global _vuln_model
    with _model_lock:
        if _vuln_model is None:
            s = get_settings()
            _vuln_model = load_or_train(s.model_path, backend=s.vuln_model_backend)
        return _vuln_model


def get_impact_model() -> ImpactModel:
    return _impact_model


def track_dicts(cyclone: Cyclone) -> list[dict]:
    """Track points with ``t_hours`` relative to the latest observed position (analysis time)."""
    pts = sorted(cyclone.track, key=lambda p: p.timestamp)
    if not pts:
        return []
    observed = [p for p in pts if not p.is_forecast]
    t0 = as_utc((observed[-1] if observed else pts[0]).timestamp)
    return [{
        "lat": p.lat, "lon": p.lon, "t_hours": (as_utc(p.timestamp) - t0).total_seconds() / 3600.0,
        "wind_kmh": p.wind_kmh, "pressure_hpa": p.pressure_hpa or 0.0, "rmw_km": p.rmw_km, "roi_km": p.roi_km,
        "uncertainty_km": p.uncertainty_km, "is_forecast": p.is_forecast, "timestamp": as_utc(p.timestamp),
        "category": p.category,
    } for p in pts]


@lru_cache
def grid_cells() -> list[dict]:
    """Static land grid over the study region with geographic context (cached)."""
    lat_min, lat_max, lon_min, lon_max = region.REGION_BBOX
    cells = []
    for lat in np.arange(lat_min + GRID_RES_DEG / 2, lat_max, GRID_RES_DEG):
        for lon in np.arange(lon_min + GRID_RES_DEG / 2, lon_max, GRID_RES_DEG):
            lat_f, lon_f = round(float(lat), 3), round(float(lon), 3)
            if not region.is_land(lat_f, lon_f):
                continue
            dc = region.dist_coast_km(lat_f, lon_f)
            dr, _ = region.dist_river_km(lat_f, lon_f)
            cells.append({"lat": lat_f, "lon": lon_f, "elevation_m": region.synthetic_elevation_m(lat_f, lon_f),
                          "dist_coast_km": dc, "dist_river_km": dr,
                          "in_flood_zone": region.flood_zone_of(lat_f, lon_f) is not None,
                          "district": region.nearest_district(lat_f, lon_f)})
    return cells


def find_landfall(dense: list[dict]) -> dict | None:
    prev_land = None
    for p in dense:
        land = region.is_land(p["lat"], p["lon"])
        if prev_land is False and land:
            return {"lat": round(p["lat"], 3), "lon": round(p["lon"], 3), "t_hours": round(p["t_hours"], 1),
                    "wind_kmh": round(p.get("wind_kmh", 0), 0), "district": region.nearest_district(p["lat"], p["lon"]),
                    "is_forecast": p["t_hours"] > 0}
        prev_land = land
    return None


def _live_rain_lookup(db: Session, assets: list[Infrastructure]) -> dict[int, float]:
    """Event-total rainfall from LIVE providers (never from simulated stations) within 30 km."""
    obs = db.scalars(select(WeatherObservation).where(WeatherObservation.is_demo.is_(False),
                                                      WeatherObservation.rainfall_mm.is_not(None))).all()
    out: dict[int, float] = {}
    if not obs:
        return out
    for a in assets:
        best = min(obs, key=lambda o: haversine_km(a.lat, a.lon, o.lat, o.lon))
        if haversine_km(a.lat, a.lon, best.lat, best.lon) <= 30:
            out[a.id] = float(best.rainfall_mm)
    return out


def score_assets(dense: list[dict], assets: list[dict], cfg: RiskConfig) -> list[dict]:
    """Pure scoring for a list of asset dicts (used by the pipeline and ad-hoc /api/predict)."""
    if not assets:
        return []
    sites = [SiteContext(lat=a["lat"], lon=a["lon"], elevation_m=a["elevation_m"], dist_coast_km=a["dist_coast_km"],
                         dist_river_km=a["dist_river_km"], in_flood_zone=a["in_flood_zone"],
                         slope_deg=a.get("slope_deg", 1.0), observed_rain_mm=a.get("observed_rain_mm"))
             for a in assets]
    impacts = [r.to_dict() for r in get_impact_model().predict(dense, sites)]
    rows = [build_feature_row(impact=imp, site=a, asset_type=a["asset_type"], age_years=a.get("age_years"),
                              historical_damage_count=a.get("historical_damage_count"))
            for imp, a in zip(impacts, assets)]
    model = get_vulnerability_model()
    X = to_frame(rows)
    vuln = model.predict_proba(X)
    spread = model.predict_spread(X)
    attrs = model.explain(X)
    out = []
    for i, (a, imp) in enumerate(zip(assets, impacts)):
        risk = compute_risk(impact=imp, site=a, asset_type=a["asset_type"], vulnerability=float(vuln[i]), cfg=cfg,
                            criticality_override=a.get("criticality"))
        missing = int(a.get("age_years") is None) + int(a.get("elevation_source", "provided") != "provided") \
            + int(a.get("historical_damage_count") is None)
        conf = confidence_score(dist_track_km=imp["dist_track_km"], track_uncertainty_km=imp["track_uncertainty_km"],
                                lead_hours=imp["closest_approach_hours"],
                                model_spread=float(spread[i]) if spread is not None else None, missing_fields=missing)
        cat = risk["category"]
        out.append({
            "impact": imp, "risk": risk, "vulnerability": round(float(vuln[i]), 4),
            "model_spread": round(float(spread[i]), 4) if spread is not None else None,
            "confidence": conf,
            "score_band": round((1 - conf["value"]) * 20, 1),
            "main_hazard": main_hazard(imp),
            "factors": explain_factors(impact=imp, site=a, asset_type=a["asset_type"], risk=risk,
                                       age_years=a.get("age_years"), historical_damage_count=a.get("historical_damage_count")),
            "ml_attributions": format_ml_attributions(attrs[i]),
            "recommendations": recommendations.generate(a["asset_type"], imp, cat, conf["label"]),
        })
    return out


def asset_to_dict(a: Infrastructure) -> dict:
    return {"id": a.id, "name": a.name, "asset_type": a.asset_type, "lat": a.lat, "lon": a.lon, "district": a.district,
            "elevation_m": a.elevation_m, "elevation_source": a.elevation_source, "slope_deg": a.slope_deg,
            "dist_coast_km": a.dist_coast_km, "dist_river_km": a.dist_river_km, "in_flood_zone": a.in_flood_zone,
            "land_use": a.land_use, "age_years": a.age_years, "historical_damage_count": a.historical_damage_count,
            "criticality": a.criticality, "capacity": a.capacity, "source": a.source, "is_demo": a.is_demo}


def _hazard_grid(dense: list[dict]) -> list[list[float]]:
    cells = grid_cells()
    sites = [SiteContext(lat=c["lat"], lon=c["lon"], elevation_m=c["elevation_m"], dist_coast_km=c["dist_coast_km"],
                         dist_river_km=c["dist_river_km"], in_flood_zone=c["in_flood_zone"], slope_deg=1.0) for c in cells]
    res = get_impact_model().predict(dense, sites)
    out = []
    for c, r in zip(cells, res):
        out.append([c["lat"], c["lon"], round(r.peak_wind_kmh, 1), round(r.rainfall_mm, 1),
                    round(r.flood_probability, 3), round(r.surge_exposure, 3)])
    return out


def _vulnerability_surface(preds: list[tuple[float, float, float]]) -> list[list[float]]:
    """Inverse-distance-weighted surface of asset risk scores (cells within 25 km of an asset)."""
    if not preds:
        return []
    cells = grid_cells()
    clat = np.array([c["lat"] for c in cells])
    clon = np.array([c["lon"] for c in cells])
    plat = np.array([p[0] for p in preds])
    plon = np.array([p[1] for p in preds])
    ps = np.array([p[2] for p in preds])
    dy = (clat[:, None] - plat[None, :]) * 111.2
    dx = (clon[:, None] - plon[None, :]) * 111.2 * np.cos(np.radians(clat[:, None]))
    d = np.hypot(dx, dy)
    w = 1.0 / (d + 3.0) ** 2
    w = np.where(d <= 25.0, w, 0.0)
    wsum = w.sum(axis=1)
    val = np.where(wsum > 0, (w * ps[None, :]).sum(axis=1) / np.maximum(wsum, 1e-12), np.nan)
    return [[float(a), float(b), round(float(v), 1)] for a, b, v in zip(clat, clon, val) if not math.isnan(v)]


def _district_summary(db: Session, grid: list[list[float]], cfg: RiskConfig,
                      preds: list[tuple[Infrastructure, dict]]) -> list[dict]:
    from ..models import District
    districts = {d.name: d for d in db.scalars(select(District)).all()}
    cells = grid_cells()
    per: dict[str, dict] = {}
    for c, g in zip(cells, grid):
        s = per.setdefault(c["district"], {"cells": 0, "gale": 0, "severe": 0, "flood": 0})
        s["cells"] += 1
        s["gale"] += g[2] >= 62
        s["severe"] += g[2] >= 89
        s["flood"] += g[4] >= 0.5
    out = []
    for name, d in districts.items():
        s = per.get(name, {"cells": 0, "gale": 0, "severe": 0, "flood": 0})
        dp = [p for a, p in preds if a.district == name]
        scores = [p["risk"]["score"] for p in dp]
        frac_gale = s["gale"] / s["cells"] if s["cells"] else 0.0
        frac_flood = s["flood"] / s["cells"] if s["cells"] else 0.0
        out.append({
            "district": name, "state": d.state, "population": d.population,
            "assets": len(dp),
            "high_risk_assets": sum(1 for p in dp if p["risk"]["category"] in ("High", "Very High")),
            "very_high_risk_assets": sum(1 for p in dp if p["risk"]["category"] == "Very High"),
            "max_risk": round(max(scores), 1) if scores else 0.0,
            "mean_risk": round(float(np.mean(scores)), 1) if scores else 0.0,
            "area_fraction_gale": round(frac_gale, 3),
            "area_fraction_flood": round(frac_flood, 3),
            "population_exposed_gale": int(d.population * frac_gale),
            "population_exposed_severe": int(d.population * (s["severe"] / s["cells"] if s["cells"] else 0)),
        })
    out.sort(key=lambda r: (-r["high_risk_assets"], -r["population_exposed_gale"]))
    return out


def run_prediction(db: Session, cyclone_id: int) -> ModelRun:
    cy = db.get(Cyclone, cyclone_id)
    if cy is None:
        raise LookupError(f"cyclone {cyclone_id} not found")
    track = track_dicts(cy)
    if len(track) < 2:
        raise ValueError("cyclone track needs at least 2 points")
    cfg = settings_store.get_risk_config(db)
    model = get_vulnerability_model()
    run = ModelRun(cyclone_id=cy.id, impact_model=f"{_impact_model.name}@{_impact_model.version}",
                   vulnerability_model=f"{model.name}@{model.version}", config=cfg.to_dict(), status="running")
    db.add(run)
    db.flush()
    try:
        dense = densify_track(track, 1.0)
        assets = db.scalars(select(Infrastructure).order_by(Infrastructure.id)).all()
        live_rain = _live_rain_lookup(db, assets)
        adicts = []
        for a in assets:
            d = asset_to_dict(a)
            d["observed_rain_mm"] = live_rain.get(a.id)
            adicts.append(d)
        scored = score_assets(dense, adicts, cfg)

        # carry over acknowledgements from the previous run
        acked = {(al.asset_id, al.rule) for al in db.scalars(
            select(Alert).join(ModelRun).where(ModelRun.cyclone_id == cy.id, Alert.acknowledged.is_(True))).all()}

        pairs: list[tuple[Infrastructure, dict]] = []
        for a, s in zip(assets, scored):
            pairs.append((a, s))
            db.add(RiskPrediction(
                model_run_id=run.id, asset_id=a.id, risk_score=s["risk"]["score"], risk_category=s["risk"]["category"],
                confidence=s["confidence"]["value"], confidence_label=s["confidence"]["label"],
                vulnerability=s["vulnerability"], main_hazard=s["main_hazard"], impact=s["impact"],
                components=s["risk"]["components"], contributions=s["risk"]["contributions"],
                confidence_detail={**s["confidence"], "model_spread": s["model_spread"], "score_band": s["score_band"]},
                factors=s["factors"], ml_attributions=s["ml_attributions"], recommendations=s["recommendations"]))
            al = alert_engine.evaluate({
                "asset_name": a.name, "asset_type": a.asset_type, "district": a.district, "lat": a.lat, "lon": a.lon,
                "elevation_m": a.elevation_m, "risk_score": s["risk"]["score"], "risk_category": s["risk"]["category"],
                "confidence": s["confidence"]["value"], "main_hazard": s["main_hazard"], "impact": s["impact"],
                "recommendations": s["recommendations"]}, cfg)
            if al:
                db.add(Alert(model_run_id=run.id, asset_id=a.id, acknowledged=(a.id, al["rule"]) in acked, **al))

        grid = _hazard_grid(dense)
        vuln_surface = _vulnerability_surface([(a.lat, a.lon, s["risk"]["score"]) for a, s in pairs])
        districts = _district_summary(db, grid, cfg, pairs)
        current = [p for p in track if p["t_hours"] <= 0][-1]
        run.grids = {"resolution_deg": GRID_RES_DEG,
                     "hazard_columns": ["lat", "lon", "peak_wind_kmh", "rainfall_mm", "flood_probability", "surge_exposure"],
                     "hazard": grid, "vulnerability_columns": ["lat", "lon", "risk_score"], "vulnerability": vuln_surface}
        run.summary = {
            "landfall": find_landfall(dense),
            "analysis_time": current["timestamp"].isoformat(),
            "max_forecast_wind_kmh": max(p["wind_kmh"] for p in track if p["t_hours"] >= 0),
            "districts": districts,
            "population_exposed_gale": sum(d["population_exposed_gale"] for d in districts),
            "population_exposed_severe": sum(d["population_exposed_severe"] for d in districts),
            "population_note": ("Estimate = district population x share of the schematic district zone forecast to "
                                "experience >= 62 km/h winds (uniform-population assumption)."),
        }
        run.n_assets = len(assets)
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        db.flush()
        # prune old runs (predictions/alerts cascade)
        old = db.scalars(select(ModelRun.id).where(ModelRun.cyclone_id == cy.id)
                         .order_by(ModelRun.id.desc()).offset(KEEP_RUNS_PER_CYCLONE)).all()
        if old:
            db.execute(delete(ModelRun).where(ModelRun.id.in_(old)))
        db.commit()
    except Exception as exc:  # record failure, re-raise for API error handling
        db.rollback()
        log.exception("model run failed")
        failed = ModelRun(cyclone_id=cy.id, impact_model=run.impact_model, vulnerability_model=run.vulnerability_model,
                          config=cfg.to_dict(), status="failed", error=str(exc)[:2000],
                          finished_at=datetime.now(timezone.utc))
        db.add(failed)
        db.commit()
        raise
    return run


def latest_run(db: Session, cyclone_id: int) -> ModelRun | None:
    return db.scalars(select(ModelRun).where(ModelRun.cyclone_id == cyclone_id, ModelRun.status == "completed")
                      .order_by(ModelRun.id.desc()).limit(1)).first()
