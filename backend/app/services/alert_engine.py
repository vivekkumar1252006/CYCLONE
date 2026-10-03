"""Rule-based alert engine.

Rules are evaluated per asset on the latest model run. At most one alert is
raised per asset (the most severe matching rule); all matching rules are listed
in ``triggered_rules``. Wording deliberately states that alerts are model-based
estimates, not confirmation of damage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ml.features import ASSET_TYPES
from ml.risk_scoring import RiskConfig

CRITICAL_FACILITIES = {"hospital", "emergency_shelter", "power_substation", "water_facility"}
SEVERITY_ORDER = {"critical": 0, "warning": 1, "advisory": 2}


@dataclass
class Rule:
    key: str
    severity: str
    title: str
    description: str
    condition: Callable[[dict, RiskConfig], bool]


RULES: list[Rule] = [
    Rule("VERY_HIGH_RISK", "critical", "Very High Infrastructure Risk",
         "risk_score > high threshold AND confidence >= minimum confidence",
         lambda p, c: p["risk_score"] > c.threshold_high and p["confidence"] >= c.alert_min_confidence),
    Rule("STORM_SURGE", "critical", "Storm-Surge Exposure Advisory",
         "surge exposure index >= 0.5 AND confidence >= minimum confidence",
         lambda p, c: p["impact"]["surge_exposure"] >= 0.5 and p["confidence"] >= c.alert_min_confidence),
    Rule("CRITICAL_FACILITY_HIGH", "warning", "High Risk to Critical Facility",
         "critical facility type AND risk_score > moderate threshold AND confidence >= minimum confidence",
         lambda p, c: p["asset_type"] in CRITICAL_FACILITIES and p["risk_score"] > c.threshold_moderate
         and p["confidence"] >= c.alert_min_confidence),
    Rule("FLOOD_EXPOSURE", "warning", "Flood Exposure Advisory",
         "flood probability >= 0.7 AND elevation < 5 m",
         lambda p, c: p["impact"]["flood_probability"] >= 0.7 and p["elevation_m"] < 5),
    Rule("VERY_HIGH_LOW_CONFIDENCE", "advisory", "Possible Very High Risk (low confidence)",
         "risk_score > high threshold AND confidence < minimum confidence",
         lambda p, c: p["risk_score"] > c.threshold_high and p["confidence"] < c.alert_min_confidence),
]


def evaluate(pred: dict, cfg: RiskConfig) -> dict | None:
    """``pred`` keys: asset_name, asset_type, district, lat, lon, elevation_m, risk_score,
    risk_category, confidence, main_hazard, impact, recommendations."""
    matched = [r for r in RULES if r.condition(pred, cfg)]
    if not matched:
        return None
    matched.sort(key=lambda r: SEVERITY_ORDER[r.severity])
    top = matched[0]
    label = ASSET_TYPES[pred["asset_type"]]["label"]
    action = pred["recommendations"][0]["action"] if pred["recommendations"] else "Review preparedness plan"
    msg = (f"Model estimates indicate {pred['risk_category'].lower()} risk ({pred['risk_score']:.0f}/100) for "
           f"{pred['asset_name']} ({label}) in {pred['district'] or 'unknown district'}; main hazard: "
           f"{pred['main_hazard'].lower()}. Confidence {pred['confidence']:.0%}. "
           "This is a forecast-based estimate, not a confirmation of damage.")
    return {
        "rule": top.key, "severity": top.severity, "title": top.title, "message": msg,
        "location": f"{pred['district'] or '-'} ({pred['lat']:.3f}, {pred['lon']:.3f})",
        "main_hazard": pred["main_hazard"], "risk_score": pred["risk_score"], "confidence": pred["confidence"],
        "recommended_action": action, "triggered_rules": [r.key for r in matched],
    }


def rules_catalog() -> list[dict]:
    return [{"key": r.key, "severity": r.severity, "title": r.title, "condition": r.description} for r in RULES]
