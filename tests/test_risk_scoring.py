"""Risk-score engine: transparency, monotonicity, configuration and classification."""
import pytest

from ml.risk_scoring import (RiskConfig, classify, compute_risk, confidence_score, explain_factors,
                             hazard_exposure, main_hazard)

SITE = {"elevation_m": 3.0, "dist_coast_km": 2.0, "dist_river_km": 3.0, "in_flood_zone": True, "slope_deg": 0.5}
HIGH = {"wind_impact": 0.9, "rainfall_impact": 0.8, "flood_probability": 0.85, "surge_exposure": 0.5,
        "peak_wind_kmh": 165.0, "rainfall_mm": 320.0, "dist_track_km": 18.0}
NONE = {"wind_impact": 0.0, "rainfall_impact": 0.0, "flood_probability": 0.01, "surge_exposure": 0.0,
        "peak_wind_kmh": 10.0, "rainfall_mm": 5.0, "dist_track_km": 600.0}


def test_score_is_sum_of_weighted_contributions():
    cfg = RiskConfig()
    r = compute_risk(impact=HIGH, site=SITE, asset_type="power_substation", vulnerability=0.7, cfg=cfg)
    assert 0 <= r["score"] <= 100
    assert r["score"] == pytest.approx(sum(r["contributions"].values()), abs=0.11)
    assert set(r["components"]) >= {"hazard_exposure", "infrastructure_vulnerability", "environmental_exposure", "criticality"}


def test_default_weights_match_specification():
    cfg = RiskConfig()
    assert (cfg.w_hazard, cfg.w_vulnerability, cfg.w_environment, cfg.w_criticality) == (0.4, 0.3, 0.2, 0.1)


def test_high_hazard_scores_higher_than_no_hazard():
    cfg = RiskConfig()
    hi = compute_risk(impact=HIGH, site=SITE, asset_type="hospital", vulnerability=0.6, cfg=cfg)
    lo = compute_risk(impact=NONE, site=SITE, asset_type="hospital", vulnerability=0.01, cfg=cfg)
    assert hi["score"] > 75 >= hi["score"] - 25
    assert lo["category"] == "Low"


def test_hazard_gate_prevents_high_risk_without_hazard():
    """A critical, low-lying asset far from the cyclone must not be scored high."""
    gated = compute_risk(impact=NONE, site=SITE, asset_type="hospital", vulnerability=0.0, cfg=RiskConfig())
    ungated = compute_risk(impact=NONE, site=SITE, asset_type="hospital", vulnerability=0.0, cfg=RiskConfig(hazard_gate=0))
    assert gated["score"] < 5
    assert ungated["score"] > gated["score"]


def test_vulnerability_is_monotonic():
    cfg = RiskConfig()
    scores = [compute_risk(impact=HIGH, site=SITE, asset_type="bridge", vulnerability=v, cfg=cfg)["score"] for v in (0, .3, .6, .9)]
    assert scores == sorted(scores)


def test_weights_change_scores():
    a = compute_risk(impact=HIGH, site=SITE, asset_type="road", vulnerability=0.1, cfg=RiskConfig())
    b = compute_risk(impact=HIGH, site=SITE, asset_type="road", vulnerability=0.1,
                     cfg=RiskConfig(w_hazard=0.1, w_vulnerability=0.9, w_environment=0, w_criticality=0))
    assert b["score"] < a["score"]


@pytest.mark.parametrize("score,expected", [(0, "Low"), (25, "Low"), (26, "Moderate"), (50, "Moderate"),
                                            (51, "High"), (75, "High"), (76, "Very High"), (100, "Very High")])
def test_classification_thresholds(score, expected):
    assert classify(score, RiskConfig()) == expected


def test_custom_thresholds():
    cfg = RiskConfig(threshold_low=10, threshold_moderate=20, threshold_high=30)
    assert classify(31, cfg) == "Very High"


@pytest.mark.parametrize("bad", [
    {"threshold_low": 60, "threshold_moderate": 50},
    {"w_hazard": -1},
    {"w_hazard": 0, "w_vulnerability": 0, "w_environment": 0, "w_criticality": 0},
    {"alert_min_confidence": 2},
])
def test_invalid_config_rejected(bad):
    with pytest.raises(ValueError):
        RiskConfig.from_dict(bad)


def test_hazard_exposure_dominated_by_strongest_hazard():
    single = {**NONE, "surge_exposure": 1.0}
    assert hazard_exposure(single, RiskConfig()) >= 0.6
    assert main_hazard(single) == "Storm surge"


def test_confidence_decreases_with_track_uncertainty():
    sure = confidence_score(dist_track_km=20, track_uncertainty_km=10, lead_hours=6, model_spread=0.05, missing_fields=0)
    unsure = confidence_score(dist_track_km=20, track_uncertainty_km=150, lead_hours=60, model_spread=0.2, missing_fields=2)
    assert sure["value"] > unsure["value"]
    assert sure["label"] in ("High", "Medium") and unsure["label"] in ("Low", "Medium")
    assert 0 <= unsure["value"] <= 1


def test_explanations_mention_key_drivers():
    r = compute_risk(impact=HIGH, site=SITE, asset_type="power_substation", vulnerability=0.7, cfg=RiskConfig())
    f = [x["factor"] for x in explain_factors(impact=HIGH, site=SITE, asset_type="power_substation", risk=r,
                                              age_years=45, historical_damage_count=2)]
    text = " ".join(f)
    assert "18 km from predicted cyclone track" in text
    assert "Low elevation" in text
    assert "Critical infrastructure category" in text
    assert "flood exposure" in text.lower()
