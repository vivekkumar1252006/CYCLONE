# API reference

Base URL (local): `http://localhost:8000`. Interactive OpenAPI docs: **`/docs`** (Swagger UI) and `/redoc`.

All responses about a cyclone include a data label:

```json
{"is_demo": true, "data_mode": "DEMO / SIMULATED DATA", "source": "demo",
 "disclaimer": "All risk values are model estimates with uncertainty ..."}
```

Endpoints marked 🔒 require the header `X-API-Key` **only when** `ADMIN_API_KEY` is set on the server.
Most endpoints take an optional `cyclone_id` query parameter. If it's omitted, they use the active cyclone.

## Cyclone

| Method | Path | Description |
|---|---|---|
| GET | `/api/cyclones` | List cyclones (demo, user-created, live-feed) with `active` flag |
| GET | `/api/cyclone/current` | Status card: category, wind, pressure, movement, max forecast wind, estimated landfall |
| GET | `/api/cyclone/track` | Observed + forecast track points with radius of max wind, radius of influence, uncertainty radius |
| POST 🔒 | `/api/cyclones` | Create a cyclone from a user track (see schema below) and run the models |
| POST 🔒 | `/api/cyclone/{id}/activate` | Make a cyclone active (runs the models if needed) |
| POST 🔒 | `/api/cyclone/import-live` | Import from `CYCLONE_FEED_URL`; returns **503 with a fallback message** if not configured/unavailable |

Track schema (`POST /api/cyclones`, also the live-feed format under `{"cyclones": [...]}`):

```json
{"name": "Example", "points": [
  {"time": "2026-10-01T00:00:00Z", "lat": 16.5, "lon": 87.5, "wind_kmh": 90, "pressure_hpa": 988, "is_forecast": false},
  {"time": "2026-10-02T00:00:00Z", "lat": 18.3, "lon": 86.7, "wind_kmh": 140, "is_forecast": true,
   "rmw_km": 25, "roi_km": 260, "uncertainty_km": 60}
]}
```

Validation:

- Times must be strictly increasing.
- The track needs at least one observed point, and observed points must come before forecast points.
- Value ranges are checked: wind 0–400 km/h and pressure 850–1060 hPa.
- `rmw_km`, `roi_km` and `uncertainty_km` are optional. If omitted, they're derived from intensity and lead time.

## Infrastructure

| Method | Path | Description |
|---|---|---|
| GET | `/api/infrastructure?asset_type=&district=&q=&limit=&offset=` | Inventory with latest risk for the active cyclone |
| GET | `/api/infrastructure/types` | Asset taxonomy + default criticality |
| GET | `/api/infrastructure/template.csv` | CSV template |
| POST 🔒 | `/api/infrastructure/upload?mode=append\|replace` | Multipart `file` (.csv / .geojson / .json, ≤ `MAX_UPLOAD_MB`). Valid rows are accepted and invalid rows are reported with reasons. Then re-scores. |
| DELETE 🔒 | `/api/infrastructure/uploaded` | Remove uploaded (non-demo) assets |

Upload fields:

- **Required:** `name`, `asset_type`, `lat`, `lon`. In GeoJSON, a Point, LineString or Polygon geometry replaces `lat`/`lon`.
- **Optional:** `district`, `elevation_m`, `age_years`, `historical_damage_count`, `criticality` (0–1), `capacity`.

`asset_type` accepts canonical keys (`power_substation, hospital, bridge, road, school, mobile_tower, water_facility, emergency_shelter, railway`) and common aliases ("substation", "cyclone shelter", "cell tower", …).

## Risk & prediction

| Method | Path | Description |
|---|---|---|
| GET | `/api/risk/map?district=&asset_type=` | Assets with scores, hazard grids (wind/rain/flood/surge), vulnerability surface, district zones, reference layers |
| GET | `/api/risk/priority?limit=&district=&asset_type=` | Assets ranked by risk, then confidence |
| GET | `/api/risk/{asset_id}` | Full explainable detail (see below) |
| POST | `/api/predict` | `{"assets": [...]}` → score ad-hoc assets **without storing them** (open). `{}` or `{"cyclone_id": n}` → 🔒 re-run and store a new model run |

`GET /api/risk/{asset_id}` returns:

- **Score:** `risk_score`, `risk_category`, `score_band`.
- **Confidence:** `confidence` (value, label, components: track / model agreement / data completeness / lead time).
- **Hazards and exposure:** `predicted_hazards`, `distance_from_track_km`, `closest_approach_hours`, `track_uncertainty_km`, `wind_exposure`, `flood_exposure`, `surge_exposure`, `criticality`.
- **Score breakdown:** `components` (0–1) and `contributions` (points per component, summing to the score).
- **Explanations:** `main_risk_factors` (plain-language) and `ml_attributions` (Model B occlusion attribution).
- **Actions:** `recommendations` with a disclaimer.

## Alerts, statistics, settings, system

| Method | Path | Description |
|---|---|---|
| GET | `/api/alerts?severity=&district=&include_acknowledged=` | Rule-based alerts for the latest run, with counts |
| GET | `/api/alerts/rules` | Rule catalogue (conditions in plain text) |
| POST 🔒 | `/api/alerts/{id}/acknowledge` | Acknowledge (carried over to later runs) |
| GET | `/api/statistics?district=` | Cards, risk distribution, risk by type, hazard contributions (top 10), district stats, intensity timeline |
| GET | `/api/settings/risk` | Current + default weights/thresholds |
| PUT 🔒 | `/api/settings/risk` | Update weights/thresholds/alert confidence/hazard gate → re-scores |
| POST 🔒 | `/api/settings/risk/reset` | Restore defaults |
| GET | `/api/demo/scenarios` | Demo scenarios |
| POST 🔒 | `/api/demo/generate` | `{"scenario": "alpha\|bravo\|charlie", "n_assets": 320, "seed": 42, "regenerate_assets": true}` |
| GET | `/api/weather` | Weather inputs (simulated stations or live NWP forecasts, labelled) |
| POST 🔒 | `/api/weather/refresh` | Pull Open-Meteo forecasts when `WEATHER_PROVIDER=openmeteo`; otherwise `{"status": "fallback"}` |
| GET | `/api/model/info` | Model names, versions, metrics, feature importances, training-data warning |
| GET | `/api/data-sources` | Provider status (live / demo / unavailable) |
| GET | `/api/health` | Health + whether auth is enabled |

## Errors

| Status | Meaning |
|---|---|
| 401 | Missing/invalid `X-API-Key` (only when auth is enabled) |
| 404 | `{"detail": "..."}`, e.g. no cyclone loaded or unknown asset |
| 422 | `{"detail": "invalid request", "errors": [{"loc": [...], "msg": "..."}]}` or a domain message |
| 503 | Live provider unavailable; the app keeps using demo/existing data |
| 500 | `{"detail": "internal server error"}`. Details are logged server-side, never returned. |
