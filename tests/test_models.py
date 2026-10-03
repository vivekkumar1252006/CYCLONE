"""Model A (parametric impact) and Model B (vulnerability) behaviour."""
import numpy as np
import pytest

from ml.features import FEATURES, build_feature_row, normalize_asset_type
from ml.geo import densify_track, haversine_km, point_in_polygon
from ml.impact_model import ParametricImpactModel, SiteContext
from ml.synthetic_training import generate_training_data
from ml.train import train
from ml.vulnerability_model import VulnerabilityModel, to_frame

TRACK = densify_track([
    dict(lat=17.0, lon=87.4, t_hours=-12, wind_kmh=140, rmw_km=27, roi_km=260, uncertainty_km=0),
    dict(lat=18.0, lon=86.9, t_hours=0, wind_kmh=165, rmw_km=25, roi_km=280, uncertainty_km=0),
    dict(lat=19.8, lon=85.8, t_hours=30, wind_kmh=165, rmw_km=25, roi_km=280, uncertainty_km=75),
    dict(lat=20.8, lon=85.6, t_hours=48, wind_kmh=75, rmw_km=40, roi_km=210, uncertainty_km=120),
])


def test_haversine_known_distance():
    # Bhubaneswar -> Puri ~ 55-60 km
    assert 50 < haversine_km(20.296, 85.824, 19.813, 85.831) < 60


def test_point_in_polygon():
    sq = [(0, 0), (0, 1), (1, 1), (1, 0)]
    assert point_in_polygon(0.5, 0.5, sq) and not point_in_polygon(1.5, 0.5, sq)


def test_wind_decreases_with_distance_from_track():
    m = ParametricImpactModel()
    near, mid, far = m.predict(TRACK, [SiteContext(19.85, 85.85), SiteContext(20.3, 86.6), SiteContext(21.8, 87.8)])
    assert near.peak_wind_kmh > mid.peak_wind_kmh > far.peak_wind_kmh
    assert near.dist_track_km < mid.dist_track_km < far.dist_track_km
    assert near.wind_impact > 0.5 and far.wind_impact < 0.2


def test_flood_probability_higher_for_low_lying_river_sites():
    m = ParametricImpactModel()
    low, high = m.predict(TRACK, [SiteContext(19.9, 85.9, elevation_m=1.5, dist_river_km=1, in_flood_zone=True, slope_deg=0.2),
                                  SiteContext(19.9, 85.9, elevation_m=120, dist_river_km=40, in_flood_zone=False, slope_deg=8)])
    assert low.flood_probability > high.flood_probability + 0.2


def test_surge_only_near_coast():
    m = ParametricImpactModel()
    coast, inland = m.predict(TRACK, [SiteContext(19.82, 85.95, elevation_m=1.5, dist_coast_km=0.5),
                                      SiteContext(19.82, 85.95, elevation_m=30, dist_coast_km=60)])
    assert coast.surge_exposure > 0.2 and inland.surge_exposure < 0.01


def test_impact_outputs_in_valid_ranges():
    res = ParametricImpactModel().predict(TRACK, [SiteContext(20, 86)])[0]
    for k in ("wind_impact", "rainfall_impact", "flood_probability", "surge_exposure"):
        assert 0 <= getattr(res, k) <= 1
    assert res.rainfall_mm >= 0 and res.peak_wind_kmh >= 0


def test_empty_track_rejected():
    with pytest.raises(ValueError):
        ParametricImpactModel().predict([], [SiteContext(20, 86)])


@pytest.fixture(scope="module")
def small_model(tmp_path_factory) -> VulnerabilityModel:
    return train(n_samples=3000, seed=3, out_path=tmp_path_factory.mktemp("m") / "vm.joblib")


def test_training_data_has_both_classes():
    df = generate_training_data(n=2000, seed=1)
    assert set(df["damaged"].unique()) == {0, 1}
    assert list(df.columns[1:-1]) == FEATURES


def test_model_beats_chance_and_persists(small_model, tmp_path):
    assert small_model.metrics["roc_auc"] > 0.8
    path = tmp_path / "copy.joblib"
    small_model.save(path)
    loaded = VulnerabilityModel.load(path)
    X = to_frame([_row(150, 0.5)])
    assert np.allclose(loaded.predict_proba(X), small_model.predict_proba(X))
    assert path.with_suffix(".json").exists()


def _row(wind, flood, atype="power_substation", age=None):
    return build_feature_row(impact={"dist_track_km": 20, "peak_wind_kmh": wind, "rainfall_mm": 200,
                                     "flood_probability": flood, "surge_exposure": 0.1},
                             site={"elevation_m": 3, "dist_coast_km": 5}, asset_type=atype,
                             age_years=age, historical_damage_count=None)


def test_vulnerability_increases_with_hazard(small_model):
    p = small_model.predict_proba(to_frame([_row(60, 0.05), _row(200, 0.9)]))
    assert p[1] > p[0]
    assert ((0 <= p) & (p <= 1)).all()


def test_missing_age_is_handled(small_model):
    row = _row(150, 0.5, age=None)
    assert row["age_missing"] == 1.0
    assert 0 <= small_model.predict_proba(to_frame([row]))[0] <= 1


def test_explanations_and_spread(small_model):
    X = to_frame([_row(200, 0.9), _row(60, 0.05)])
    attr = small_model.explain(X)
    assert len(attr) == 2 and "peak_wind_kmh" in attr[0]
    assert attr[0]["peak_wind_kmh"] > 0  # high wind pushes damage probability up
    spread = small_model.predict_spread(X)
    assert spread.shape == (2,) and (spread >= 0).all()


@pytest.mark.parametrize("raw,expected", [("Substation", "power_substation"), ("cyclone shelter", "emergency_shelter"),
                                          ("Mobile-Tower", "mobile_tower"), ("spaceport", None), ("", None)])
def test_asset_type_normalisation(raw, expected):
    assert normalize_asset_type(raw) == expected
