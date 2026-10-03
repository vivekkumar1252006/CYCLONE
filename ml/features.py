"""Feature definitions and infrastructure taxonomy shared by models and API."""
from __future__ import annotations

ASSET_TYPES: dict[str, dict] = {
    # criticality: 0-1 importance for life safety / cascading failures (configurable assumption)
    # fragility_*: parameters of the SYNTHETIC fragility process used for prototype training data
    "power_substation":  {"label": "Power Substation",  "criticality": 0.95, "fragility_wind50": 150, "flood_sens": 2.2, "surge_sens": 1.8},
    "hospital":          {"label": "Hospital",          "criticality": 1.00, "fragility_wind50": 200, "flood_sens": 1.5, "surge_sens": 1.2},
    "bridge":            {"label": "Bridge",            "criticality": 0.85, "fragility_wind50": 220, "flood_sens": 2.5, "surge_sens": 1.5},
    "road":              {"label": "Road Segment",      "criticality": 0.60, "fragility_wind50": 260, "flood_sens": 2.6, "surge_sens": 2.0},
    "school":            {"label": "School",            "criticality": 0.55, "fragility_wind50": 170, "flood_sens": 1.4, "surge_sens": 1.2},
    "mobile_tower":      {"label": "Mobile Tower",      "criticality": 0.75, "fragility_wind50": 140, "flood_sens": 0.8, "surge_sens": 1.0},
    "water_facility":    {"label": "Water Facility",    "criticality": 0.85, "fragility_wind50": 190, "flood_sens": 2.0, "surge_sens": 1.6},
    "emergency_shelter": {"label": "Emergency Shelter", "criticality": 0.90, "fragility_wind50": 210, "flood_sens": 1.0, "surge_sens": 1.0},
    "railway":           {"label": "Railway Infrastructure", "criticality": 0.70, "fragility_wind50": 230, "flood_sens": 2.3, "surge_sens": 1.8},
}

ASSET_TYPE_KEYS = list(ASSET_TYPES.keys())

NUMERIC_FEATURES = [
    "dist_track_km",
    "peak_wind_kmh",
    "rainfall_mm",
    "elevation_m",
    "dist_coast_km",
    "flood_probability",
    "surge_exposure",
    "age_years",
    "age_missing",
    "historical_damage_count",
]

TYPE_FEATURES = [f"type_{t}" for t in ASSET_TYPE_KEYS]
FEATURES = NUMERIC_FEATURES + TYPE_FEATURES

# Feature groups used for explanations (one explanation entry per group)
FEATURE_GROUPS: dict[str, list[str]] = {
    "dist_track_km": ["dist_track_km"],
    "peak_wind_kmh": ["peak_wind_kmh"],
    "rainfall_mm": ["rainfall_mm"],
    "elevation_m": ["elevation_m"],
    "dist_coast_km": ["dist_coast_km"],
    "flood_probability": ["flood_probability"],
    "surge_exposure": ["surge_exposure"],
    "age_years": ["age_years", "age_missing"],
    "historical_damage_count": ["historical_damage_count"],
    "asset_type": TYPE_FEATURES,
}

FEATURE_LABELS = {
    "dist_track_km": "Distance from predicted track",
    "peak_wind_kmh": "Predicted peak wind",
    "rainfall_mm": "Predicted rainfall",
    "elevation_m": "Ground elevation",
    "dist_coast_km": "Distance from coast",
    "flood_probability": "Flood exposure",
    "surge_exposure": "Storm-surge exposure",
    "age_years": "Asset age",
    "historical_damage_count": "Historical damage record",
    "asset_type": "Infrastructure type",
}

DEFAULT_AGE_YEARS = 20.0


def normalize_asset_type(value: str) -> str | None:
    """Map free-text asset types (e.g. from CSV uploads) to a canonical key."""
    if not value:
        return None
    v = value.strip().lower().replace("-", " ").replace("_", " ")
    aliases = {
        "power substation": "power_substation", "substation": "power_substation", "power": "power_substation",
        "hospital": "hospital", "health centre": "hospital", "health center": "hospital", "phc": "hospital",
        "bridge": "bridge",
        "road": "road", "road segment": "road", "highway": "road",
        "school": "school",
        "mobile tower": "mobile_tower", "telecom tower": "mobile_tower", "cell tower": "mobile_tower", "tower": "mobile_tower",
        "water facility": "water_facility", "water": "water_facility", "water treatment": "water_facility", "pumping station": "water_facility",
        "emergency shelter": "emergency_shelter", "shelter": "emergency_shelter", "cyclone shelter": "emergency_shelter",
        "railway": "railway", "railway infrastructure": "railway", "rail": "railway", "railway station": "railway",
    }
    return aliases.get(v)


def build_feature_row(*, impact: dict, site: dict, asset_type: str, age_years: float | None,
                      historical_damage_count: float | None) -> dict[str, float]:
    row = {
        "dist_track_km": float(impact["dist_track_km"]),
        "peak_wind_kmh": float(impact["peak_wind_kmh"]),
        "rainfall_mm": float(impact["rainfall_mm"]),
        "elevation_m": float(site["elevation_m"]),
        "dist_coast_km": float(site["dist_coast_km"]),
        "flood_probability": float(impact["flood_probability"]),
        "surge_exposure": float(impact["surge_exposure"]),
        "age_years": float(age_years) if age_years is not None else DEFAULT_AGE_YEARS,
        "age_missing": 0.0 if age_years is not None else 1.0,
        "historical_damage_count": float(historical_damage_count or 0.0),
    }
    for t in ASSET_TYPE_KEYS:
        row[f"type_{t}"] = 1.0 if t == asset_type else 0.0
    return row
