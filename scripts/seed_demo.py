"""Generate a DEMO / SIMULATED scenario, run the models and optionally export the dataset.

Usage (from repo root):
    python scripts/seed_demo.py --scenario alpha
    python scripts/seed_demo.py --scenario bravo --assets 400 --export data/demo_export
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.database import SessionLocal, init_db  # noqa: E402
from backend.app.models import Infrastructure, RiskPrediction  # noqa: E402
from backend.app.services import demo_generator, pipeline, settings_store  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default="alpha", choices=list(demo_generator.SCENARIOS))
    ap.add_argument("--assets", type=int, default=320)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--export", type=Path, help="directory to write the simulated dataset (CSV/GeoJSON/JSON)")
    a = ap.parse_args()

    init_db()
    with SessionLocal() as db:
        cy = demo_generator.generate_demo(db, a.scenario, n_assets=a.assets, seed=a.seed)
        settings_store.set_active_cyclone_id(db, cy.id)
        db.commit()
        run = pipeline.run_prediction(db, cy.id)
        preds = db.query(RiskPrediction).filter_by(model_run_id=run.id).all()
        print(f"[DEMO / SIMULATED] {cy.name}: {run.n_assets} assets scored, run #{run.id}")
        print("  risk distribution:", dict(Counter(p.risk_category for p in preds)))
        print("  landfall:", (run.summary or {}).get("landfall"))

        if a.export:
            out = a.export
            out.mkdir(parents=True, exist_ok=True)
            assets = db.query(Infrastructure).filter_by(is_demo=True).all()
            fields = ["name", "asset_type", "lat", "lon", "district", "elevation_m", "age_years",
                      "historical_damage_count", "capacity", "dist_coast_km", "dist_river_km", "in_flood_zone"]
            with open(out / "demo_infrastructure.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                for x in assets:
                    w.writerow({k: getattr(x, k) for k in fields})
            (out / "demo_infrastructure.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [x.lon, x.lat]},
                 "properties": {k: getattr(x, k) for k in fields if k not in ("lat", "lon")}} for x in assets]}, indent=1))
            track = [{"time": p["timestamp"].isoformat(), **{k: p[k] for k in ("lat", "lon", "wind_kmh", "pressure_hpa",
                                                                                "category", "is_forecast", "uncertainty_km")}}
                     for p in pipeline.track_dicts(cy)]
            (out / f"demo_track_{a.scenario}.json").write_text(json.dumps({"name": cy.name, "data_mode": "DEMO / SIMULATED",
                                                                            "points": track}, indent=1))
            with open(out / "demo_risk_predictions.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["asset", "type", "district", "risk_score", "risk_category", "confidence", "main_hazard"])
                for p in sorted(preds, key=lambda p: -p.risk_score):
                    w.writerow([p.asset.name, p.asset.asset_type, p.asset.district, p.risk_score, p.risk_category,
                                p.confidence, p.main_hazard])
            print(f"  exported simulated dataset to {out}")


if __name__ == "__main__":
    main()
