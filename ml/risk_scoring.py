"""Transparent, configurable risk-scoring engine (0-100).

    Risk = 100 * ( wH*H + wV*V + wE*E*g + wC*C*g ) / (wH + wV + wE + wC)

    H  hazard exposure        - from Model A (wind, rain, flood, surge)
    V  infrastructure vulnerability - Model B probability of significant damage
    E  environmental exposure - terrain flood susceptibility + coastal proximity
    C  criticality            - asset-type importance (or per-asset override)
    g  hazard gate = min(1, H / hazard_gate)  -> an asset far from any hazard
       cannot become "high risk" purely because it is critical or low-lying.
       Set hazard_gate = 0 to disable.

Every weight, threshold and the gate are configuration *assumptions* of the
prototype and are exposed through the settings API.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from .features import ASSET_TYPES, FEATURE_LABELS
from .impact_model import terrain_flood_susceptibility


@dataclass
class RiskConfig:
    w_hazard: float = 0.40
    w_vulnerability: float = 0.30
    w_environment: float = 0.20
    w_criticality: float = 0.10
    hazard_gate: float = 0.25
    # category upper bounds: <=low -> Low, <=moderate -> Moderate, <=high -> High, else Very High
    threshold_low: float = 25.0
    threshold_moderate: float = 50.0
    threshold_high: float = 75.0
    # alert engine
    alert_min_confidence: float = 0.55
    hazard_subweights: dict = field(default_factory=lambda: {"wind": 0.45, "rain": 0.20, "flood": 0.20, "surge": 0.15})

    def validate(self) -> None:
        ws = [self.w_hazard, self.w_vulnerability, self.w_environment, self.w_criticality]
        if any(w < 0 for w in ws) or sum(ws) <= 0:
            raise ValueError("weights must be non-negative and sum to > 0")
        if not (0 <= self.threshold_low < self.threshold_moderate < self.threshold_high <= 100):
            raise ValueError("thresholds must satisfy 0 <= low < moderate < high <= 100")
        if not (0 <= self.alert_min_confidence <= 1):
            raise ValueError("alert_min_confidence must be in [0, 1]")
        if not (0 <= self.hazard_gate <= 1):
            raise ValueError("hazard_gate must be in [0, 1]")
        sw = self.hazard_subweights
        if set(sw) != {"wind", "rain", "flood", "surge"} or any(v < 0 for v in sw.values()) or sum(sw.values()) <= 0:
            raise ValueError("hazard_subweights must define non-negative wind, rain, flood, surge")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "RiskConfig":
        base = cls()
        if not d:
            return base
        known = {k: v for k, v in d.items() if k in base.__dataclass_fields__}
        cfg = cls(**{**asdict(base), **known})
        cfg.validate()
        return cfg


def classify(score: float, cfg: RiskConfig) -> str:
    if score <= cfg.threshold_low:
        return "Low"
    if score <= cfg.threshold_moderate:
        return "Moderate"
    if score <= cfg.threshold_high:
        return "High"
    return "Very High"


def hazard_exposure(impact: dict, cfg: RiskConfig) -> float:
    vals = {"wind": impact["wind_impact"], "rain": impact["rainfall_impact"],
            "flood": impact["flood_probability"], "surge": impact["surge_exposure"]}
    sw = cfg.hazard_subweights
    mean = sum(sw[k] * vals[k] for k in vals) / sum(sw.values())
    # a single extreme hazard should dominate, not be averaged away
    return float(min(1.0, 0.6 * max(vals.values()) + 0.4 * mean))


def environmental_exposure(site: dict) -> float:
    sus = terrain_flood_susceptibility(site["elevation_m"], site["dist_river_km"],
                                       bool(site.get("in_flood_zone")), site.get("slope_deg", 2.0))
    coastal = math.exp(-max(site["dist_coast_km"], 0.0) / 15.0)
    return float(min(1.0, 0.6 * sus + 0.4 * coastal))


def confidence_score(*, dist_track_km: float, track_uncertainty_km: float, lead_hours: float,
                     model_spread: float | None, missing_fields: int) -> dict:
    """Heuristic confidence (0-1) combining track, model and data uncertainty."""
    track_conf = 1.0 - math.exp(-(dist_track_km + 30.0) / (track_uncertainty_km + 1.0))
    model_conf = 1.0 - min(1.0, 2.5 * model_spread) if model_spread is not None else 0.7
    data_conf = max(0.3, 1.0 - 0.15 * missing_fields)
    lead_conf = math.exp(-max(lead_hours, 0.0) / 120.0)
    value = 0.40 * track_conf + 0.25 * model_conf + 0.20 * data_conf + 0.15 * lead_conf
    label = "High" if value >= 0.75 else "Medium" if value >= 0.5 else "Low"
    return {"value": round(value, 3), "label": label,
            "components": {"track": round(track_conf, 3), "model_agreement": round(model_conf, 3),
                           "data_completeness": round(data_conf, 3), "lead_time": round(lead_conf, 3)}}


def compute_risk(*, impact: dict, site: dict, asset_type: str, vulnerability: float,
                 cfg: RiskConfig, criticality_override: float | None = None) -> dict:
    H = hazard_exposure(impact, cfg)
    V = float(min(max(vulnerability, 0.0), 1.0))
    E = environmental_exposure(site)
    C = float(criticality_override if criticality_override is not None else ASSET_TYPES[asset_type]["criticality"])
    g = 1.0 if cfg.hazard_gate <= 0 else min(1.0, H / cfg.hazard_gate)
    wsum = cfg.w_hazard + cfg.w_vulnerability + cfg.w_environment + cfg.w_criticality
    contrib = {
        "hazard_exposure": 100 * cfg.w_hazard * H / wsum,
        "infrastructure_vulnerability": 100 * cfg.w_vulnerability * V / wsum,
        "environmental_exposure": 100 * cfg.w_environment * E * g / wsum,
        "criticality": 100 * cfg.w_criticality * C * g / wsum,
    }
    score = round(sum(contrib.values()), 1)
    return {
        "score": score,
        "category": classify(score, cfg),
        "components": {"hazard_exposure": round(H, 3), "infrastructure_vulnerability": round(V, 3),
                       "environmental_exposure": round(E, 3), "criticality": round(C, 3), "hazard_gate": round(g, 3)},
        "contributions": {k: round(v, 2) for k, v in contrib.items()},
    }


def main_hazard(impact: dict) -> str:
    vals = {"Wind": impact["wind_impact"], "Rainfall": impact["rainfall_impact"],
            "Flooding": impact["flood_probability"], "Storm surge": impact["surge_exposure"]}
    return max(vals, key=vals.get)


def predicted_hazards(impact: dict) -> list[dict]:
    def lvl(x):
        return "High" if x >= 0.6 else "Moderate" if x >= 0.3 else "Low"
    return [
        {"hazard": "Wind", "level": lvl(impact["wind_impact"]), "index": round(impact["wind_impact"], 3),
         "detail": f"Peak sustained wind ~{impact['peak_wind_kmh']:.0f} km/h (model estimate)"},
        {"hazard": "Rainfall", "level": lvl(impact["rainfall_impact"]), "index": round(impact["rainfall_impact"], 3),
         "detail": f"Accumulated rainfall ~{impact['rainfall_mm']:.0f} mm (model estimate)"},
        {"hazard": "Flooding", "level": lvl(impact["flood_probability"]), "index": round(impact["flood_probability"], 3),
         "detail": f"Flooding probability {impact['flood_probability']:.0%}"},
        {"hazard": "Storm surge", "level": lvl(impact["surge_exposure"]), "index": round(impact["surge_exposure"], 3),
         "detail": f"Surge exposure index {impact['surge_exposure']:.2f}"},
    ]


def explain_factors(*, impact: dict, site: dict, asset_type: str, risk: dict,
                    age_years: float | None, historical_damage_count: float | None) -> list[dict]:
    """Human-readable contributing factors, strongest first."""
    f: list[tuple[float, str, str]] = []  # (strength, text, direction)
    d = impact["dist_track_km"]
    if d < 150:
        f.append((1.0 - d / 150, f"{d:.0f} km from predicted cyclone track", "increases"))
    else:
        f.append((0.2, f"{d:.0f} km from predicted cyclone track (relatively distant)", "decreases"))
    w = impact["wind_impact"]
    if w >= 0.25:
        lvl = "High" if w >= 0.6 else "Moderate"
        f.append((w, f"{lvl} predicted wind exposure (~{impact['peak_wind_kmh']:.0f} km/h peak)", "increases"))
    if impact["rainfall_mm"] >= 100:
        f.append((impact["rainfall_impact"], f"Heavy rainfall expected (~{impact['rainfall_mm']:.0f} mm)", "increases"))
    if site["elevation_m"] < 10:
        f.append((1 - site["elevation_m"] / 10, f"Low elevation ({site['elevation_m']:.1f} m)", "increases"))
    fp = impact["flood_probability"]
    if fp >= 0.35:
        f.append((fp, f"{'High' if fp >= 0.6 else 'Moderate'} flood exposure ({fp:.0%} probability)", "increases"))
    if impact["surge_exposure"] >= 0.2:
        f.append((impact["surge_exposure"], f"Storm-surge exposure (index {impact['surge_exposure']:.2f})", "increases"))
    if site["dist_coast_km"] < 10:
        f.append((0.5 * (1 - site["dist_coast_km"] / 10), f"Coastal location ({site['dist_coast_km']:.1f} km from coast)", "increases"))
    if site.get("in_flood_zone"):
        f.append((0.4, "Located in a mapped flood-prone zone", "increases"))
    crit = risk["components"]["criticality"]
    if crit >= 0.85:
        f.append((0.35 + 0.1 * crit, f"Critical infrastructure category ({ASSET_TYPES[asset_type]['label']})", "increases"))
    if age_years is not None and age_years >= 35:
        f.append((min(1.0, age_years / 80), f"Ageing asset ({age_years:.0f} years)", "increases"))
    if historical_damage_count:
        f.append((0.3 + 0.1 * historical_damage_count, f"Historical damage recorded ({int(historical_damage_count)} past events)", "increases"))
    f.sort(key=lambda x: -x[0])
    return [{"factor": t, "direction": dirn, "strength": round(s, 3)} for s, t, dirn in f]


def format_ml_attributions(attr: dict[str, float], top_k: int = 6) -> list[dict]:
    """Occlusion attributions from Model B, largest magnitude first."""
    top = sorted(attr.items(), key=lambda kv: -abs(kv[1]))[:top_k]
    return [{"key": k, "feature": FEATURE_LABELS.get(k, k), "effect": round(v, 4),
             "direction": "increases" if v > 0 else "decreases"} for k, v in top]
