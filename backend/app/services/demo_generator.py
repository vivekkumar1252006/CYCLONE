"""DEMO / SIMULATED data generator.

Creates synthetic - but physically plausible - cyclone scenarios, weather
station readings and infrastructure inventories for the demo study region.
Everything produced here is flagged ``is_demo=True`` / ``source='demo'`` and is
labelled as simulated throughout the API and UI. Scenario names are fictional.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ml.features import ASSET_TYPES
from ml.geo import bearing_deg, haversine_km, point_in_polygon

from ..geodata import region
from ..models import Cyclone, CycloneTrackPoint, District, Infrastructure, WeatherObservation

# (t_hours relative to "now", lat, lon, wind_kmh, pressure_hpa). t<=0 observed, t>0 forecast.
SCENARIOS: dict[str, dict] = {
    "alpha": {
        "name": "DEMO Cyclone ALPHA",
        "description": "Simulated very severe cyclonic storm moving NNW, forecast landfall near Puri (~30 h).",
        "points": [(-48, 14.8, 88.6, 65, 994), (-36, 15.6, 88.2, 85, 990), (-24, 16.4, 87.8, 110, 982),
                   (-12, 17.2, 87.3, 140, 972), (0, 17.95, 86.85, 165, 962), (12, 18.7, 86.35, 180, 956),
                   (24, 19.4, 85.95, 175, 958), (30, 19.80, 85.80, 165, 962), (36, 20.15, 85.70, 120, 978),
                   (48, 20.75, 85.60, 75, 990), (60, 21.4, 85.65, 50, 996), (72, 22.0, 85.9, 35, 1000)],
    },
    "bravo": {
        "name": "DEMO Cyclone BRAVO",
        "description": "Simulated severe cyclonic storm moving north, forecast landfall near Dhamra (~30 h), recurving NE.",
        "points": [(-36, 16.0, 87.0, 60, 996), (-24, 16.9, 87.0, 75, 992), (-12, 17.8, 87.0, 95, 986),
                   (0, 18.7, 87.05, 110, 982), (12, 19.5, 87.05, 120, 978), (24, 20.2, 86.98, 115, 980),
                   (30, 20.62, 86.86, 110, 982), (36, 21.1, 86.75, 85, 988), (48, 21.8, 87.1, 60, 994),
                   (60, 22.4, 87.6, 40, 998)],
    },
    "charlie": {
        "name": "DEMO Cyclone CHARLIE",
        "description": "Simulated cyclonic storm moving WNW, forecast landfall near Gopalpur (~20 h).",
        "points": [(-24, 17.3, 86.5, 55, 998), (-12, 17.8, 86.0, 65, 996), (0, 18.3, 85.55, 80, 992),
                   (12, 18.8, 85.15, 88, 990), (20, 19.25, 84.90, 85, 991), (30, 19.6, 84.45, 60, 995),
                   (42, 19.9, 83.95, 40, 999), (54, 20.1, 83.5, 30, 1002)],
    },
}

TYPE_MIX = {"road": 0.20, "school": 0.14, "mobile_tower": 0.13, "power_substation": 0.10, "hospital": 0.08,
            "bridge": 0.09, "water_facility": 0.07, "emergency_shelter": 0.12, "railway": 0.07}


def imd_category(wind_kmh: float) -> str:
    """IMD intensity classes from maximum sustained surface wind (km/h)."""
    for limit, cat in ((31, "L"), (50, "D"), (62, "DD"), (89, "CS"), (118, "SCS"), (167, "VSCS"), (222, "ESCS")):
        if wind_kmh < limit:
            return cat
    return "SuCS"


CATEGORY_NAMES = {"L": "Low pressure area", "D": "Depression", "DD": "Deep Depression", "CS": "Cyclonic Storm",
                  "SCS": "Severe Cyclonic Storm", "VSCS": "Very Severe Cyclonic Storm",
                  "ESCS": "Extremely Severe Cyclonic Storm", "SuCS": "Super Cyclonic Storm"}


def rmw_for(wind: float) -> float:
    return float(np.clip(20 + (200 - wind) / 8, 15, 60))


def roi_for(wind: float) -> float:
    return float(150 + 0.8 * wind)


def cone_radius(t_hours: float) -> float:
    """Forecast-uncertainty radius (km), grows with lead time (typical NIO errors)."""
    return 0.0 if t_hours <= 0 else round(2.6 * t_hours - 0.004 * t_hours ** 2, 1)


def clear_demo_data(db: Session, include_assets: bool = True) -> None:
    """Remove demo cyclones (tracks, weather, runs, predictions, alerts cascade via FKs)."""
    db.execute(delete(Cyclone).where(Cyclone.is_demo.is_(True)))
    if include_assets:
        db.execute(delete(Infrastructure).where(Infrastructure.is_demo.is_(True)))
    db.flush()
    # bulk deletes bypass the ORM; drop stale objects so reused primary keys don't collide
    db.expunge_all()


def ensure_districts(db: Session) -> None:
    if db.scalar(select(District.id).limit(1)) is not None:
        return
    polys = region.district_polygons()
    for d in region.DISTRICTS:
        db.add(District(name=d["name"], state=d["state"], population=d["population"],
                        center_lat=d["center"][0], center_lon=d["center"][1],
                        boundary=region.polygon_geojson(polys[d["name"]]),
                        boundary_note="Schematic zone (Voronoi around HQ, clipped to land) - NOT an official boundary"))
    db.flush()


def create_cyclone(db: Session, scenario: str, now: datetime | None = None) -> Cyclone:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario '{scenario}'. Options: {', '.join(SCENARIOS)}")
    now = (now or datetime.now(timezone.utc)).replace(minute=0, second=0, microsecond=0)
    sc = SCENARIOS[scenario]
    cy = Cyclone(name=sc["name"], scenario_key=scenario, description=sc["description"], source="demo", is_demo=True)
    for t, lat, lon, wind, pres in sc["points"]:
        cy.track.append(CycloneTrackPoint(
            timestamp=now + timedelta(hours=t), lat=lat, lon=lon, wind_kmh=wind, pressure_hpa=pres,
            category=imd_category(wind), rmw_km=rmw_for(wind), roi_km=roi_for(wind),
            is_forecast=t > 0, uncertainty_km=cone_radius(t)))
    db.add(cy)
    db.flush()
    return cy


def _random_point_in(ring, rng, max_tries=400):
    lats = [p[0] for p in ring]
    lons = [p[1] for p in ring]
    for _ in range(max_tries):
        lat = rng.uniform(min(lats), max(lats))
        lon = rng.uniform(min(lons), max(lons))
        if point_in_polygon(lat, lon, ring) and region.is_land(lat, lon) and region.dist_coast_km(lat, lon) > 0.3:
            return lat, lon
    return None


def _snap_near(line, rng, spread_km=2.0):
    i = rng.integers(0, len(line) - 1)
    f = rng.random()
    a, b = line[i], line[i + 1]
    lat = a[0] + f * (b[0] - a[0]) + rng.normal(0, spread_km / 111)
    lon = a[1] + f * (b[1] - a[1]) + rng.normal(0, spread_km / 111)
    return lat, lon


def generate_infrastructure(db: Session, n_assets: int = 320, seed: int = 42) -> list[Infrastructure]:
    rng = np.random.default_rng(seed)
    polys = region.district_polygons()
    # concentrate assets in coastal & plains districts (where cyclones matter most), weighted by population
    weights = {}
    for d in region.DISTRICTS:
        dc = region.dist_coast_km(*d["center"])
        weights[d["name"]] = d["population"] * (1.6 if dc < 40 else 1.0)
    total = sum(weights.values())
    types = list(TYPE_MIX)
    probs = np.array([TYPE_MIX[t] for t in types])
    probs = probs / probs.sum()
    counters: dict[tuple[str, str], int] = {}
    assets: list[Infrastructure] = []
    names = list(weights)
    pdist = np.array([weights[n] / total for n in names])
    attempts = 0
    while len(assets) < n_assets and attempts < n_assets * 20:
        attempts += 1
        atype = str(rng.choice(types, p=probs))
        if atype == "railway":
            pt = _snap_near(region.RAILWAY, rng, 1.0)
        elif atype == "bridge":
            pt = _snap_near(list(region.RIVERS.values())[rng.integers(0, len(region.RIVERS))], rng, 0.8)
        elif atype == "emergency_shelter" and rng.random() < 0.7:
            # multipurpose cyclone shelters are concentrated within ~20 km of the coast
            pt = _snap_near(region.COASTLINE[1:-2], rng, 1.0)
            j = rng.uniform(2, 20) / 111
            pt = (pt[0] + j * 0.7, pt[1] - j * 0.7)
        else:
            dname = str(rng.choice(names, p=pdist))
            pt = _random_point_in(polys[dname], rng)
        if pt is None or not region.in_region(*pt) or not region.is_land(*pt):
            continue
        lat, lon = float(pt[0]), float(pt[1])
        ctx = region.site_context(lat, lon)
        key = (atype, ctx["district"])
        counters[key] = counters.get(key, 0) + 1
        label = ASSET_TYPES[atype]["label"]
        age = None if rng.random() < 0.25 else float(round(rng.uniform(2, 55)))
        hist = float(rng.poisson(0.9 if ctx["dist_coast_km"] < 20 else 0.25))
        capacity = None
        if atype == "hospital":
            capacity = f"{int(rng.choice([30, 50, 100, 250, 500]))} beds"
        elif atype == "emergency_shelter":
            capacity = f"{int(rng.choice([500, 1000, 1500, 2000]))} persons"
        elif atype == "power_substation":
            capacity = str(rng.choice(["33/11 kV", "132/33 kV", "220/132 kV"]))
        a = Infrastructure(
            name=f"{label} - {ctx['district']} #{counters[key]:02d}", asset_type=atype, lat=round(lat, 5), lon=round(lon, 5),
            district=ctx["district"], elevation_m=ctx["elevation_m"], elevation_source="synthetic-dem",
            slope_deg=ctx["slope_deg"], dist_coast_km=ctx["dist_coast_km"], dist_river_km=ctx["dist_river_km"],
            in_flood_zone=ctx["in_flood_zone"], land_use=ctx["land_use"], age_years=age,
            historical_damage_count=hist, capacity=capacity, source="demo", is_demo=True)
        db.add(a)
        assets.append(a)
    db.flush()
    return assets


def generate_weather(db: Session, cyclone: Cyclone, seed: int = 42) -> list[WeatherObservation]:
    """Simulated station readings at district HQs at the current analysis time."""
    from ml.impact_model import ParametricImpactModel, SiteContext
    from .pipeline import track_dicts

    rng = np.random.default_rng(seed + 1)
    track = track_dicts(cyclone)
    observed = [p for p in track if p["t_hours"] <= 0]
    if not observed:
        return []
    now_pt = observed[-1]
    model = ParametricImpactModel()
    obs = []
    for d in region.DISTRICTS:
        lat, lon = d["center"]
        ctx = region.site_context(lat, lon)
        # rainfall so far = model rainfall integrated over the observed part of the track, plus noise
        res = model.predict(observed, [SiteContext(lat, lon, ctx["elevation_m"], ctx["dist_coast_km"], ctx["dist_river_km"],
                                                   ctx["in_flood_zone"], ctx["slope_deg"])])[0]
        r = haversine_km(lat, lon, now_pt["lat"], now_pt["lon"])
        v = max(5.0, now_pt["wind_kmh"] * (now_pt["rmw_km"] / max(r, now_pt["rmw_km"])) ** 0.6 * 0.8 + rng.normal(0, 4))
        # NH cyclonic flow: wind blows counter-clockwise; direction FROM which it blows
        brg_to_center = bearing_deg(lat, lon, now_pt["lat"], now_pt["lon"])
        wind_from = (brg_to_center + 90 + 20) % 360
        surge = None
        if ctx["dist_coast_km"] < 15:
            surge = round(max(0.0, 0.3 + rng.normal(0, 0.1) + 2.5 * math.exp(-r / 80)), 2)
        o = WeatherObservation(
            cyclone_id=cyclone.id, station_name=f"{d['name']} (simulated station)", lat=lat, lon=lon,
            observed_at=now_pt["timestamp"],
            rainfall_mm=round(max(0.0, res.rainfall_mm * rng.uniform(0.75, 1.25)), 1),
            wind_speed_kmh=round(v, 1), wind_direction_deg=round(wind_from, 0),
            temperature_c=round(rng.uniform(24.5, 28.5), 1), humidity_pct=round(rng.uniform(84, 98), 0),
            surge_indicator_m=surge, source="demo", is_demo=True)
        db.add(o)
        obs.append(o)
    db.flush()
    return obs


def generate_demo(db: Session, scenario: str = "alpha", n_assets: int = 320, seed: int = 42,
                  regenerate_assets: bool = True) -> Cyclone:
    """Create a complete demo scenario (does NOT run the models - see pipeline.run_prediction)."""
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario '{scenario}'. Options: {', '.join(SCENARIOS)}")
    has_assets = db.scalar(select(Infrastructure.id).limit(1)) is not None
    new_assets = regenerate_assets or not has_assets
    clear_demo_data(db, include_assets=new_assets)
    ensure_districts(db)
    cy = create_cyclone(db, scenario)
    if new_assets:
        generate_infrastructure(db, n_assets=n_assets, seed=seed)
    generate_weather(db, cy, seed=seed)
    return cy
