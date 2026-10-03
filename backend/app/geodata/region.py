"""Demo study region: Odisha coast (Bay of Bengal), India.

Reference geometry here is SIMPLIFIED and APPROXIMATE, digitised by hand for the
prototype (coarse coastline, main river courses, illustrative flood-prone
polygons). District zones are schematic Voronoi cells around approximate
district headquarters, clipped to land - NOT official administrative
boundaries. District populations are rounded Census of India 2011 figures.

The elevation surface is a SYNTHETIC DEM (smooth function of coast distance,
Eastern Ghats uplift and river valleys). Replace ``GISProvider`` with real
SRTM/Copernicus DEM, OSM/Bhuvan layers etc. for operational use.
"""
from __future__ import annotations

import math
from functools import lru_cache

from ml.geo import clip_polygon_halfplane, point_in_polygon, point_polyline_distance_km

REGION_NAME = "Odisha coast (demo study region)"
# lat_min, lat_max, lon_min, lon_max
REGION_BBOX = (18.2, 22.2, 83.3, 88.2)

COASTLINE: list[tuple[float, float]] = [
    (17.70, 83.30), (18.30, 84.10), (18.75, 84.55), (19.25, 84.92), (19.45, 85.12),
    (19.65, 85.45), (19.80, 85.83), (19.88, 86.10), (20.05, 86.40), (20.26, 86.67),
    (20.55, 86.80), (20.80, 86.97), (21.10, 86.92), (21.45, 87.05), (21.60, 87.40),
    (21.65, 87.60), (21.70, 88.10), (21.80, 88.60),
]

RIVERS: dict[str, list[tuple[float, float]]] = {
    "Mahanadi": [(20.95, 84.60), (20.55, 85.10), (20.48, 85.55), (20.47, 85.88), (20.40, 86.20), (20.30, 86.65)],
    "Kathajodi-Devi": [(20.45, 85.85), (20.20, 86.15), (20.00, 86.35), (19.95, 86.38)],
    "Brahmani": [(21.20, 85.10), (20.95, 85.60), (20.85, 85.95), (20.70, 86.40), (20.75, 86.85)],
    "Baitarani": [(21.30, 85.80), (21.10, 86.10), (20.90, 86.60), (20.80, 86.95)],
    "Rushikulya": [(19.75, 84.30), (19.55, 84.60), (19.45, 84.85), (19.38, 85.05)],
    "Budhabalanga": [(21.80, 86.40), (21.60, 86.65), (21.50, 86.95), (21.46, 87.05)],
    "Subarnarekha": [(22.15, 86.70), (21.90, 87.10), (21.62, 87.35), (21.57, 87.43)],
}

FLOOD_ZONES: dict[str, list[tuple[float, float]]] = {
    "Mahanadi delta": [(20.15, 85.90), (20.55, 85.90), (20.70, 86.55), (20.32, 86.72), (20.02, 86.36)],
    "Chilika fringe": [(19.55, 85.10), (19.85, 85.20), (19.95, 85.55), (19.72, 85.62), (19.60, 85.40)],
    "Brahmani-Baitarani lower basin": [(20.62, 86.30), (21.00, 86.40), (20.96, 86.94), (20.60, 86.84)],
    "Subarnarekha-Budhabalanga lower basin": [(21.42, 86.85), (21.70, 87.05), (21.68, 87.50), (21.55, 87.45)],
}

DISTRICTS: list[dict] = [
    {"name": "Gajapati", "state": "Odisha", "population": 577817, "center": (18.95, 84.15)},
    {"name": "Ganjam", "state": "Odisha", "population": 3529031, "center": (19.38, 84.68)},
    {"name": "Nayagarh", "state": "Odisha", "population": 962789, "center": (20.13, 85.10)},
    {"name": "Puri", "state": "Odisha", "population": 1698730, "center": (19.85, 85.70)},
    {"name": "Khordha", "state": "Odisha", "population": 2251673, "center": (20.20, 85.62)},
    {"name": "Cuttack", "state": "Odisha", "population": 2624470, "center": (20.50, 85.95)},
    {"name": "Jagatsinghpur", "state": "Odisha", "population": 1136971, "center": (20.25, 86.25)},
    {"name": "Kendrapara", "state": "Odisha", "population": 1440361, "center": (20.55, 86.50)},
    {"name": "Jajpur", "state": "Odisha", "population": 1827192, "center": (20.85, 86.15)},
    {"name": "Dhenkanal", "state": "Odisha", "population": 1192811, "center": (20.70, 85.50)},
    {"name": "Bhadrak", "state": "Odisha", "population": 1506337, "center": (21.05, 86.60)},
    {"name": "Kendujhar", "state": "Odisha", "population": 1801733, "center": (21.40, 85.80)},
    {"name": "Balasore", "state": "Odisha", "population": 2320529, "center": (21.45, 86.90)},
    {"name": "Mayurbhanj", "state": "Odisha", "population": 2519738, "center": (21.85, 86.40)},
    {"name": "Srikakulam", "state": "Andhra Pradesh", "population": 2703114, "center": (18.45, 83.90)},
]

# Main railway corridor (Howrah-Chennai line, approximate)
RAILWAY = [(21.49, 86.93), (21.06, 86.50), (20.95, 86.12), (20.47, 85.88), (20.27, 85.84), (20.18, 85.62),
           (19.85, 85.20), (19.31, 84.79), (19.11, 84.69), (18.77, 84.41), (18.30, 83.90)]


def _land_ring() -> list[tuple[float, float]]:
    lat_min, lat_max, lon_min, lon_max = REGION_BBOX
    # coastline (SW->NE) then close via the inland (north-west) side
    return COASTLINE + [(lat_max + 1, COASTLINE[-1][1]), (lat_max + 1, lon_min - 1), (COASTLINE[0][0], lon_min - 1)]


LAND_RING = _land_ring()


def is_land(lat: float, lon: float) -> bool:
    return point_in_polygon(lat, lon, LAND_RING)


def dist_coast_km(lat: float, lon: float) -> float:
    return point_polyline_distance_km((lat, lon), COASTLINE)[0]


def dist_river_km(lat: float, lon: float) -> tuple[float, str]:
    best = (float("inf"), "")
    for name, line in RIVERS.items():
        d = point_polyline_distance_km((lat, lon), line)[0]
        if d < best[0]:
            best = (d, name)
    return best


def flood_zone_of(lat: float, lon: float) -> str | None:
    for name, ring in FLOOD_ZONES.items():
        if point_in_polygon(lat, lon, ring):
            return name
    return None


def synthetic_elevation_m(lat: float, lon: float) -> float:
    """Smooth SYNTHETIC DEM (metres). Not real terrain data."""
    dc = dist_coast_km(lat, lon)
    dr, _ = dist_river_km(lat, lon)
    base = 1.0 + 0.45 * dc ** 0.9
    ghats = 220.0 / (1.0 + math.exp(-(84.9 - lon) * 4.0)) * (1.0 / (1.0 + math.exp(-(dc - 40) / 10)))
    northern_hills = 120.0 / (1.0 + math.exp(-(lat - 21.4) * 5.0)) * (1.0 / (1.0 + math.exp(-(dc - 50) / 12)))
    valley = -min(base * 0.4, 6.0) * math.exp(-dr / 4.0)
    texture = 2.5 * math.sin(lat * 23.0) * math.cos(lon * 19.0) + 1.5 * math.sin((lat + lon) * 41.0)
    return round(max(0.5, base + ghats + northern_hills + valley + texture * min(1.0, dc / 15)), 1)


def synthetic_slope_deg(lat: float, lon: float) -> float:
    h = 0.01  # ~1.1 km
    dzdx = (synthetic_elevation_m(lat, lon + h) - synthetic_elevation_m(lat, lon - h)) / (2 * h * 111.0 * math.cos(math.radians(lat)) * 1000)
    dzdy = (synthetic_elevation_m(lat + h, lon) - synthetic_elevation_m(lat - h, lon)) / (2 * h * 111.0 * 1000)
    return round(math.degrees(math.atan(math.hypot(dzdx, dzdy))), 2)


def land_use_of(lat: float, lon: float, elevation: float, dist_coast: float) -> str:
    for d in DISTRICTS:
        c = d["center"]
        if abs(lat - c[0]) < 0.06 and abs(lon - c[1]) < 0.06:
            return "urban"
    if dist_coast < 3 and elevation < 4:
        return "coastal_wetland"
    if elevation > 80:
        return "forest"
    return "agricultural"


def nearest_district(lat: float, lon: float) -> str:
    return min(DISTRICTS, key=lambda d: (d["center"][0] - lat) ** 2 + ((d["center"][1] - lon) * math.cos(math.radians(lat))) ** 2)["name"]


@lru_cache
def district_polygons() -> dict[str, list[tuple[float, float]]]:
    """Schematic district zones: land polygon clipped by Voronoi half-planes."""
    out: dict[str, list[tuple[float, float]]] = {}
    lat_min, lat_max, lon_min, lon_max = REGION_BBOX
    box = [(lat_min, lon_min), (lat_min, lon_max), (lat_max, lon_max), (lat_max, lon_min)]
    land = list(LAND_RING)
    # clip the land ring to the region box (box is convex -> 4 half-plane clips)
    for (a, b) in zip(box, box[1:] + box[:1]):
        land = _clip_by_edge(land, a, b)
    for d in DISTRICTS:
        poly = list(land)
        for o in DISTRICTS:
            if o is not d and poly:
                poly = clip_polygon_halfplane(poly, d["center"], o["center"])
        out[d["name"]] = [(round(p[0], 4), round(p[1], 4)) for p in poly]
    return out


def _clip_by_edge(poly, a, b):
    """Keep the part of poly to the LEFT of directed edge a->b (box is CCW in lon/lat)."""
    def inside(p):
        return (b[1] - a[1]) * (p[0] - a[0]) - (b[0] - a[0]) * (p[1] - a[1]) >= 0
    out = []
    n = len(poly)
    for i in range(n):
        cur, nxt = poly[i], poly[(i + 1) % n]
        ic, inn = inside(cur), inside(nxt)
        if ic:
            out.append(cur)
        if ic != inn:
            # intersection of segment cur-nxt with line a-b
            x1, y1, x2, y2 = cur[1], cur[0], nxt[1], nxt[0]
            x3, y3, x4, y4 = a[1], a[0], b[1], b[0]
            den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if den != 0:
                t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
                out.append((y1 + t * (y2 - y1), x1 + t * (x2 - x1)))
    return out


def polygon_geojson(ring: list[tuple[float, float]]) -> dict:
    coords = [[lon, lat] for lat, lon in ring]
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    return {"type": "Polygon", "coordinates": [coords]}


def line_geojson(line: list[tuple[float, float]]) -> dict:
    return {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in line]}


def site_context(lat: float, lon: float, elevation_m: float | None = None) -> dict:
    """Derive geographic features for any point in the study region."""
    dc = dist_coast_km(lat, lon)
    dr, river = dist_river_km(lat, lon)
    elev = elevation_m if elevation_m is not None else synthetic_elevation_m(lat, lon)
    fz = flood_zone_of(lat, lon)
    return {
        "elevation_m": float(elev),
        "elevation_source": "provided" if elevation_m is not None else "synthetic-dem",
        "slope_deg": synthetic_slope_deg(lat, lon),
        "dist_coast_km": round(dc, 2),
        "dist_river_km": round(dr, 2),
        "nearest_river": river,
        "in_flood_zone": fz is not None,
        "flood_zone": fz,
        "land_use": land_use_of(lat, lon, elev, dc),
        "district": nearest_district(lat, lon),
    }


def in_region(lat: float, lon: float) -> bool:
    lat_min, lat_max, lon_min, lon_max = REGION_BBOX
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max
