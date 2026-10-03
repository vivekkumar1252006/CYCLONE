# Architecture

```
┌──────────────────────────── frontend/ (React + TypeScript + Vite) ────────────────────────────┐
│ Dashboard: scenario bar · KPI cards · Leaflet risk map (layers) · priority list · charts      │
│ Asset detail · Alerts · Data (upload / inventory / weather / sources) · Model · Settings      │
└──────────────── /api (Vite proxy in dev · nginx reverse-proxy in Docker) ─────────────────────┘
                                   │ JSON
┌──────────────────────────── backend/app (FastAPI) ────────────────────────────────────────────┐
│ api/        cyclone · infrastructure · risk · alerts · statistics · admin (demo/settings/...) │
│ schemas.py  strict pydantic validation      security.py  optional X-API-Key (auth-ready)      │
│ services/   pipeline · demo_generator · ingest (CSV/GeoJSON) · alert_engine ·                 │
│             recommendations · settings_store                                                   │
│ providers/  interfaces + adapters: cyclone feed · Open-Meteo weather · GIS · satellite stub   │
│ geodata/    demo study region (coastline, rivers, flood zones, districts, synthetic DEM)      │
│ models.py   SQLAlchemy ORM ─► SQLite (dev) / PostgreSQL + PostGIS (Docker)                   │
└───────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                        │ pure Python
┌──────────────────────────── ml/ (no web/DB dependencies) ─────────────────────────────────────┐
│ geo.py · impact_model.py (Model A) · vulnerability_model.py (Model B) · risk_scoring.py       │
│ features.py · synthetic_training.py · train.py ──► models/vulnerability_model.joblib (+.json) │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Pipeline (one `ModelRun`)

1. Load the cyclone track and set `t = 0` at the latest observed position. Interpolate hourly.
2. Load assets. Attach live NWP rainfall (if configured) within 30 km.
3. **Model A** produces the hazard per asset. **Model B** produces the vulnerability and the per-tree spread. It also computes occlusion attributions.
4. **Risk engine** computes the score, contributions and category. Then come **confidence**, **explanations** and **recommendations**.
5. **Alert engine** applies one alert per asset (the most severe matching rule). Acknowledgements are carried over from earlier runs.
6. **Grids:** a 0.1° land grid gives wind, rain, flood and surge for the map layers. An IDW vulnerability surface is built from asset scores.
7. **District summary:** asset counts, max/mean risk, area share ≥ 62 km/h, flood share, and population exposure (uniform-population assumption).
8. Persist the run, then prune it to the last 3 runs per cyclone.

The run takes about 0.5 s for 320 assets plus about 1,100 grid cells on a laptop. A run is triggered by:

- demo generation
- uploads
- settings changes
- cyclone creation
- `POST /api/predict`

## Database tables

| Table | Purpose |
|---|---|
| `cyclones` | Cyclone metadata, `source` (demo / user / live-feed), `is_demo` |
| `cyclone_tracks` | Observed + forecast points: wind, pressure, IMD category, RMW, radius of influence, uncertainty |
| `weather_observations` | Simulated stations or live NWP forecasts (labelled) |
| `infrastructure` | Assets plus derived geographic features. `source` is demo or upload. |
| `risk_predictions` | Per-asset results for each run: score, components, impact, factors, attributions, recommendations |
| `alerts` | Rule-based alerts per run |
| `districts` | Schematic zones (GeoJSON), Census 2011 population |
| `model_runs` | Model versions, config snapshot, grids, summary, status/error |
| `app_settings` | Risk configuration, active cyclone |

Geometry uses portable `lat`/`lon` columns plus GeoJSON. `docker/postgres/postgis_upgrade.sql` adds PostGIS generated geometry columns and GiST indexes for spatial SQL.

## Security measures

- **Input validation:** strict pydantic schemas (`extra="forbid"`, numeric ranges) and track consistency checks.
- **Upload checks:**
  - extension allow-list
  - size limit (read is capped at the limit + 1 byte)
  - binary sniffing
  - UTF-8 requirement
  - row cap (5,000)
  - per-row validation with study-region and land checks
  - text sanitisation
- **Error responses:** no stack traces or internals are returned to clients.
- **CORS:** allow-list from `CORS_ORIGINS`, with restricted methods and headers.
- **Security headers:** `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`.
- **Secrets:** environment variables only (`.env`, git-ignored). The frontend never contains secrets; the optional admin key is typed at runtime and kept in `sessionStorage`.
- **Auth-ready:** mutating routes depend on `require_admin`. Swap in OAuth2/JWT without changing handlers.
- **Containers:** the Docker backend runs as a non-root user.
