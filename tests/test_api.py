"""API endpoints, uploads, invalid input, missing data and alert generation."""
import json

import pytest

from backend.app.services import alert_engine
from ml.risk_scoring import RiskConfig


# ---------------- read endpoints ----------------
@pytest.mark.parametrize("path", ["/api/health", "/api/cyclones", "/api/cyclone/current", "/api/cyclone/track",
                                  "/api/infrastructure", "/api/risk/map", "/api/risk/priority", "/api/alerts",
                                  "/api/alerts/rules", "/api/statistics", "/api/demo/scenarios", "/api/settings/risk",
                                  "/api/model/info", "/api/data-sources", "/api/weather", "/api/infrastructure/types"])
def test_get_endpoints_ok(client, path):
    r = client.get(path)
    assert r.status_code == 200, r.text


def test_demo_data_is_labelled(client):
    cur = client.get("/api/cyclone/current").json()
    assert cur["is_demo"] is True and cur["data_mode"] == "DEMO / SIMULATED DATA"
    assert "estimate" in cur["disclaimer"].lower()
    assert all(a["is_demo"] for a in client.get("/api/risk/map").json()["assets"] if a["source"] == "demo")


def test_track_has_observed_and_forecast_with_uncertainty(client):
    t = client.get("/api/cyclone/track").json()
    assert t["observed"] and len(t["forecast"]) > 1
    assert t["forecast"][0] == t["observed"][-1]  # forecast starts at current position
    unc = [p["uncertainty_km"] for p in t["forecast"][1:]]
    assert unc == sorted(unc) and unc[-1] > 0


def test_map_payload(client):
    m = client.get("/api/risk/map").json()
    assert m["assets"] and m["grids"]["hazard"] and m["districts"]["features"]
    a = m["assets"][0]
    assert 0 <= a["risk_score"] <= 100 and a["risk_category"] in ("Low", "Moderate", "High", "Very High")


def test_priority_sorted(client):
    items = client.get("/api/risk/priority?limit=15").json()["items"]
    scores = [i["risk_score"] for i in items]
    assert scores == sorted(scores, reverse=True)


def test_asset_detail_is_explainable(client):
    top = client.get("/api/risk/priority?limit=1").json()["items"][0]
    d = client.get(f"/api/risk/{top['asset_id']}").json()
    for key in ("risk_score", "risk_category", "predicted_hazards", "distance_from_track_km", "flood_exposure",
                "wind_exposure", "criticality", "confidence", "main_risk_factors", "recommendations", "contributions"):
        assert key in d
    assert d["main_risk_factors"] and d["recommendations"] and d["ml_attributions"]
    assert d["confidence"]["label"] in ("Low", "Medium", "High")
    assert sum(d["contributions"].values()) == pytest.approx(d["risk_score"], abs=0.2)
    assert "not" in d["recommendations_disclaimer"].lower()


def test_unknown_asset_404(client):
    assert client.get("/api/risk/99999999").status_code == 404


def test_district_filter(client):
    d = client.get("/api/risk/map?district=Puri").json()
    assert d["assets"] and all(a["district"] == "Puri" for a in d["assets"])


def test_statistics_cards(client):
    s = client.get("/api/statistics").json()
    c = s["cards"]
    assert c["max_wind_kmh"] > 0 and c["total_assets"] > 0
    assert sum(x["count"] for x in s["risk_distribution"]) == c["total_assets"]
    assert s["intensity_timeline"] and s["districts"]


# ---------------- predict ----------------
def test_adhoc_predict_and_invalid_type(client):
    r = client.post("/api/predict", json={"assets": [
        {"asset_type": "hospital", "lat": 19.82, "lon": 85.82},
        {"asset_type": "spaceport", "lat": 19.8, "lon": 85.8}]})
    assert r.status_code == 200
    body = r.json()
    assert len(body["results"]) == 1 and len(body["errors"]) == 1
    res = body["results"][0]
    assert res["input"]["elevation_source"] == "synthetic-dem"  # missing elevation derived and flagged
    assert res["main_risk_factors"]


def test_predict_rerun(client):
    r = client.post("/api/predict", json={})
    assert r.status_code == 200 and r.json()["status"] == "completed"


@pytest.mark.parametrize("payload", [
    {"assets": [{"asset_type": "hospital", "lat": 120, "lon": 85}]},     # invalid latitude
    {"assets": [{"asset_type": "hospital", "lat": 19.8}]},               # missing lon
    {"assets": [{"asset_type": "hospital", "lat": "abc", "lon": 85}]},   # wrong type
    {"unexpected": 1},                                                   # unknown field
])
def test_predict_invalid_input(client, payload):
    assert client.post("/api/predict", json=payload).status_code == 422


def test_predict_all_assets_invalid(client):
    r = client.post("/api/predict", json={"assets": [{"asset_type": "school", "lat": 28.6, "lon": 77.2}]})
    assert r.status_code == 422


# ---------------- uploads ----------------
def test_csv_upload_accepts_valid_rejects_invalid(client, sample_csv):
    r = client.post("/api/infrastructure/upload", files={"file": ("assets.csv", sample_csv, "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] == 7 and body["rejected_count"] == 3
    errors = " ".join(x["error"] for x in body["rejected"])
    assert "unknown asset_type" in errors and "outside" in errors and "not a number" in errors
    assert body["model_run_id"]
    names = [a["name"] for a in client.get("/api/infrastructure?q=SAMPLE").json()["items"]]
    assert "SAMPLE Puri Grid Substation" in names


def test_geojson_upload(client, sample_geojson):
    r = client.post("/api/infrastructure/upload", files={"file": ("a.geojson", sample_geojson, "application/geo+json")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] == 3 and body["rejected_count"] == 1
    items = client.get("/api/infrastructure?q=Marine Drive").json()["items"]
    assert items and items[0]["asset_type"] == "road"


@pytest.mark.parametrize("name,content,fragment", [
    ("evil.exe", b"MZ\x00\x00", "unsupported file type"),
    ("empty.csv", b"", "empty"),
    ("bad.csv", b"foo,bar\n1,2\n", "missing required columns"),
    ("bad.geojson", b"{not json", "invalid GeoJSON"),
    ("wrong.geojson", json.dumps({"type": "Point", "coordinates": [1, 2]}).encode(), "Feature"),
    ("bin.csv", b"name,asset_type,lat,lon\n\x00\x01", "binary"),
])
def test_invalid_uploads_rejected(client, name, content, fragment):
    r = client.post("/api/infrastructure/upload", files={"file": (name, content, "application/octet-stream")})
    assert r.status_code == 422
    assert fragment.lower() in json.dumps(r.json()).lower()


def test_upload_too_large(client, monkeypatch):
    from backend.app.config import get_settings
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0.0001)
    big = b"name,asset_type,lat,lon\n" + b"x,school,20,85\n" * 200
    r = client.post("/api/infrastructure/upload", files={"file": ("big.csv", big, "text/csv")})
    assert r.status_code == 422 and "limit" in r.text


def test_upload_missing_optional_fields(client):
    csv = b"name,asset_type,lat,lon\nMinimal School,school,20.30,85.80\n"
    r = client.post("/api/infrastructure/upload", files={"file": ("m.csv", csv, "text/csv")})
    assert r.status_code == 200 and r.json()["accepted"] == 1
    a = client.get("/api/infrastructure?q=Minimal School").json()["items"][0]
    assert a["age_years"] is None and a["elevation_source"] == "synthetic-dem" and a["district"]
    d = client.get(f"/api/risk/{a['id']}").json()
    assert d["confidence"]["components"]["data_completeness"] < 1


# ---------------- cyclone creation ----------------
def test_create_cyclone_and_validation(client):
    track = json.loads((__import__("pathlib").Path(__file__).parents[1] / "data/samples/sample_cyclone_track.json").read_text())
    r = client.post("/api/cyclones", json=track)
    assert r.status_code == 201, r.text
    assert r.json()["is_demo"] is False
    bad = {**track, "points": list(reversed(track["points"]))}
    assert client.post("/api/cyclones", json=bad).status_code == 422
    one = {**track, "points": track["points"][:1]}
    assert client.post("/api/cyclones", json=one).status_code == 422
    # restore demo as active for later tests
    demo = next(c for c in client.get("/api/cyclones").json() if c["is_demo"])
    assert client.post(f"/api/cyclone/{demo['id']}/activate").status_code == 200


def test_demo_regeneration_in_one_session(client):
    """Regression: bulk deletes + reused SQLite ids must not collide in the ORM identity map."""
    import warnings
    from sqlalchemy.exc import SAWarning
    from backend.app.database import SessionLocal
    from backend.app.services import demo_generator, pipeline
    with warnings.catch_warnings(), SessionLocal() as db:
        warnings.simplefilter("error", SAWarning)
        for sc in ("bravo", "alpha"):
            cy = demo_generator.generate_demo(db, sc, n_assets=60, seed=2)
            db.commit()
            assert pipeline.run_prediction(db, cy.id).status == "completed"
    assert client.post("/api/demo/generate", json={"scenario": "alpha", "n_assets": 120, "seed": 1}).status_code == 200


def test_unknown_scenario_rejected(client):
    assert client.post("/api/demo/generate", json={"scenario": "zulu"}).status_code == 422


def test_live_providers_fall_back_gracefully(client):
    assert client.post("/api/cyclone/import-live").status_code == 503
    assert client.post("/api/weather/refresh").json()["status"] == "fallback"


# ---------------- settings ----------------
def test_settings_update_rescores_and_validates(client):
    cfg = client.get("/api/settings/risk").json()["config"]
    new = {**cfg, "w_hazard": 1.0, "w_vulnerability": 0.0, "w_environment": 0.0, "w_criticality": 0.0}
    r = client.put("/api/settings/risk", json=new)
    assert r.status_code == 200 and r.json()["model_run_id"]
    d = client.get(f"/api/risk/{client.get('/api/risk/priority?limit=1').json()['items'][0]['asset_id']}").json()
    assert d["contributions"]["infrastructure_vulnerability"] == 0
    bad = {**cfg, "threshold_low": 80}
    assert client.put("/api/settings/risk", json=bad).status_code == 422
    assert client.post("/api/settings/risk/reset").status_code == 200


# ---------------- alerts ----------------
def test_alerts_generated_and_acknowledged(client):
    a = client.get("/api/alerts").json()
    assert a["items"], "demo scenario should produce alerts"
    first = a["items"][0]
    assert first["severity"] in ("critical", "warning", "advisory")
    assert "not a confirmation of damage" in first["message"]
    r = client.post(f"/api/alerts/{first['id']}/acknowledge")
    assert r.status_code == 200 and r.json()["acknowledged"]
    open_ids = [x["id"] for x in client.get("/api/alerts?include_acknowledged=false").json()["items"]]
    assert first["id"] not in open_ids


def _pred(score, conf, **kw):
    base = {"asset_name": "X", "asset_type": "power_substation", "district": "Puri", "lat": 19.8, "lon": 85.8,
            "elevation_m": 10, "risk_score": score, "risk_category": "Very High", "confidence": conf,
            "main_hazard": "Wind", "impact": {"surge_exposure": 0.0, "flood_probability": 0.1},
            "recommendations": [{"action": "Inspect"}]}
    base.update(kw)
    return base


def test_alert_rules():
    cfg = RiskConfig()
    assert alert_engine.evaluate(_pred(80, 0.8), cfg)["rule"] == "VERY_HIGH_RISK"
    assert alert_engine.evaluate(_pred(80, 0.3, asset_type="road"), cfg)["rule"] == "VERY_HIGH_LOW_CONFIDENCE"
    assert alert_engine.evaluate(_pred(20, 0.9, risk_category="Low", asset_type="road"), cfg) is None
    flood = alert_engine.evaluate(_pred(40, 0.9, asset_type="road", elevation_m=2,
                                        impact={"surge_exposure": 0, "flood_probability": 0.8}), cfg)
    assert flood["rule"] == "FLOOD_EXPOSURE"


# ---------------- auth ----------------
def test_api_key_required_when_configured(client, monkeypatch):
    from backend.app.config import get_settings
    monkeypatch.setattr(get_settings(), "admin_api_key", "s3cret")
    adhoc = {"assets": [{"asset_type": "hospital", "lat": 19.82, "lon": 85.82}]}
    assert client.post("/api/predict", json=adhoc).status_code == 200          # ad-hoc scoring stays open
    assert client.post("/api/predict", json={}).status_code == 401             # stored re-run needs the key
    assert client.get("/api/risk/map").status_code == 200                      # reads stay open
    assert client.post("/api/settings/risk/reset").status_code == 401
    assert client.post("/api/settings/risk/reset", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.post("/api/settings/risk/reset", headers={"X-API-Key": "s3cret"}).status_code == 200
