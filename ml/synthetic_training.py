"""Synthetic training data for the prototype vulnerability model.

IMPORTANT - PROVENANCE
----------------------
No public, asset-level, labelled cyclone damage dataset for Indian infrastructure
was available for this prototype. Labels are therefore generated from a
documented *synthetic fragility process* (logistic fragility curves per asset
type, loosely inspired by HAZUS-style fragility functions) plus noise.

The trained model therefore learns these assumed relationships - it does NOT
encode real-world damage evidence. For operational use, replace
``generate_training_data`` with historical post-event damage assessments
(e.g. state disaster management damage reports for past cyclones) joined to
hazard footprints.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .features import ASSET_TYPE_KEYS, ASSET_TYPES, FEATURES
from .impact_model import terrain_flood_susceptibility


def fragility_logit(df: pd.DataFrame) -> np.ndarray:
    """Synthetic 'true' damage logit. Shared by data generation and tests."""
    w50 = df["asset_type"].map(lambda t: ASSET_TYPES[t]["fragility_wind50"]).to_numpy(float)
    fs = df["asset_type"].map(lambda t: ASSET_TYPES[t]["flood_sens"]).to_numpy(float)
    ss = df["asset_type"].map(lambda t: ASSET_TYPES[t]["surge_sens"]).to_numpy(float)
    age = df["age_years"].fillna(20.0).to_numpy(float)
    return (
        1.2 * (df["peak_wind_kmh"].to_numpy(float) - w50) / 25.0
        + fs * (2.2 * df["flood_probability"].to_numpy(float) - 1.0)
        + ss * 3.0 * df["surge_exposure"].to_numpy(float)
        + 0.03 * (age - 25.0)
        + 0.5 * df["historical_damage_count"].to_numpy(float)
        + 0.5
    )


def generate_training_data(n: int = 12000, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    asset_type = rng.choice(ASSET_TYPE_KEYS, size=n)
    dist_track = rng.gamma(2.0, 45.0, size=n)                       # km
    vmax = rng.uniform(60, 240, size=n)                              # storm intensity
    rmw = rng.uniform(15, 45, size=n)
    wind = np.where(dist_track <= rmw, vmax * dist_track / rmw * 0.6 + vmax * 0.4,
                    vmax * (rmw / np.maximum(dist_track, 1)) ** 0.6)
    wind = np.clip(wind * rng.normal(1.0, 0.08, size=n), 0, None)
    rain = np.clip((2 + vmax / 15) * np.exp(-np.maximum(dist_track - rmw, 0) / 100) * rng.uniform(6, 24, size=n), 0, None)
    dist_coast = rng.gamma(1.5, 18.0, size=n)
    elevation = np.clip(1.5 + 0.35 * dist_coast + rng.normal(0, 4, size=n), 0, None)
    dist_river = rng.gamma(1.5, 6.0, size=n)
    flood_zone = rng.random(n) < np.exp(-elevation / 10) * 0.6
    slope = np.clip(rng.gamma(1.5, 1.2, size=n), 0, 30)
    rain_imp = np.clip((rain - 25) / 275, 0, 1)
    sus = np.array([terrain_flood_susceptibility(e, d, z, s) for e, d, z, s in zip(elevation, dist_river, flood_zone, slope)])
    flood_p = 1 / (1 + np.exp(-(-5 + 5 * rain_imp + 4 * sus + 3 * rain_imp * sus)))
    surge_int = np.clip((vmax - 62) / 138, 0, 1)
    surge = np.clip(surge_int * np.exp(-np.maximum(dist_track - rmw, 0) / (3 * rmw + 40))
                    * np.exp(-dist_coast / 8) * (0.4 + 0.6 * np.exp(-elevation / 4))
                    * rng.choice([0.5, 1.0], size=n), 0, 1)
    age = rng.uniform(1, 60, size=n)
    age_missing = rng.random(n) < 0.25
    hist = rng.poisson(0.4, size=n)

    df = pd.DataFrame({
        "asset_type": asset_type,
        "dist_track_km": dist_track,
        "peak_wind_kmh": wind,
        "rainfall_mm": rain,
        "elevation_m": elevation,
        "dist_coast_km": dist_coast,
        "flood_probability": flood_p,
        "surge_exposure": surge,
        "age_years": np.where(age_missing, np.nan, age),
        "historical_damage_count": hist,
    })
    logit = fragility_logit(df) + rng.normal(0, 0.6, size=n)
    df["damaged"] = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    # model-ready features
    df["age_missing"] = df["age_years"].isna().astype(float)
    df["age_years"] = df["age_years"].fillna(20.0)
    for t in ASSET_TYPE_KEYS:
        df[f"type_{t}"] = (df["asset_type"] == t).astype(float)
    return df[["asset_type"] + FEATURES + ["damaged"]]
