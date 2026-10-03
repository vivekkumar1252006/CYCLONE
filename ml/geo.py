"""Lightweight geodesic helpers (no GDAL / shapely dependency).

All distances are in kilometres. Coordinates are (lat, lon) in decimal degrees.
Accuracy is more than sufficient for regional (< 1000 km) risk screening.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

EARTH_RADIUS_KM = 6371.0088

LatLon = tuple[float, float]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def _to_local_xy(lat: float, lon: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    """Equirectangular projection around a reference point (km)."""
    x = math.radians(lon - ref_lon) * EARTH_RADIUS_KM * math.cos(math.radians(ref_lat))
    y = math.radians(lat - ref_lat) * EARTH_RADIUS_KM
    return x, y


def point_segment_distance_km(p: LatLon, a: LatLon, b: LatLon) -> tuple[float, float, float]:
    """Distance from point p to segment a-b.

    Returns (distance_km, t, cross) where t in [0,1] is the projection parameter
    along the segment and ``cross`` is the signed z of (b-a) x (p-a): positive
    when p lies to the LEFT of the direction of travel a->b.
    """
    ax, ay = _to_local_xy(a[0], a[1], p[0], p[1])
    bx, by = _to_local_xy(b[0], b[1], p[0], p[1])
    dx, dy = bx - ax, by - ay
    seg_len2 = dx * dx + dy * dy
    if seg_len2 == 0:
        return math.hypot(ax, ay), 0.0, 0.0
    t = max(0.0, min(1.0, (-ax * dx - ay * dy) / seg_len2))
    cx, cy = ax + t * dx, ay + t * dy
    cross = dx * (-ay) - dy * (-ax)
    return math.hypot(cx, cy), t, cross


def point_polyline_distance_km(p: LatLon, line: Sequence[LatLon]) -> tuple[float, int, float, float]:
    """Minimum distance from p to a polyline.

    Returns (distance_km, segment_index, t, cross) for the closest segment.
    """
    if len(line) == 1:
        return haversine_km(p[0], p[1], line[0][0], line[0][1]), 0, 0.0, 0.0
    best = (float("inf"), 0, 0.0, 0.0)
    for i in range(len(line) - 1):
        d, t, cross = point_segment_distance_km(p, line[i], line[i + 1])
        if d < best[0]:
            best = (d, i, t, cross)
    return best


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def destination(lat: float, lon: float, bearing: float, dist_km: float) -> LatLon:
    br = math.radians(bearing)
    p1 = math.radians(lat)
    l1 = math.radians(lon)
    dr = dist_km / EARTH_RADIUS_KM
    p2 = math.asin(math.sin(p1) * math.cos(dr) + math.cos(p1) * math.sin(dr) * math.cos(br))
    l2 = l1 + math.atan2(math.sin(br) * math.sin(dr) * math.cos(p1), math.cos(dr) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540) % 360 - 180


def point_in_polygon(lat: float, lon: float, ring: Sequence[LatLon]) -> bool:
    """Ray-casting point-in-polygon test. ``ring`` is a list of (lat, lon)."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        yi, xi = ring[i]
        yj, xj = ring[j]
        if (yi > lat) != (yj > lat):
            x_int = (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
            if lon < x_int:
                inside = not inside
        j = i
    return inside


def clip_polygon_halfplane(poly: list[LatLon], a: LatLon, b: LatLon) -> list[LatLon]:
    """Keep the part of a convex polygon closer to ``a`` than to ``b``.

    Works in degree space (adequate for schematic zone boundaries).
    """
    mx, my = (a[1] + b[1]) / 2, (a[0] + b[0]) / 2
    nx, ny = b[1] - a[1], b[0] - a[0]

    def side(pt: LatLon) -> float:
        return (pt[1] - mx) * nx + (pt[0] - my) * ny  # <= 0 means closer to a

    out: list[LatLon] = []
    n = len(poly)
    for i in range(n):
        cur, nxt = poly[i], poly[(i + 1) % n]
        sc, sn = side(cur), side(nxt)
        if sc <= 0:
            out.append(cur)
        if (sc <= 0) != (sn <= 0):
            t = sc / (sc - sn)
            out.append((cur[0] + t * (nxt[0] - cur[0]), cur[1] + t * (nxt[1] - cur[1])))
    return out


def voronoi_cells(centers: Sequence[LatLon], bbox: tuple[float, float, float, float]) -> list[list[LatLon]]:
    """Voronoi cells for ``centers`` clipped to bbox (lat_min, lat_max, lon_min, lon_max)."""
    lat_min, lat_max, lon_min, lon_max = bbox
    base = [(lat_min, lon_min), (lat_min, lon_max), (lat_max, lon_max), (lat_max, lon_min)]
    cells = []
    for i, c in enumerate(centers):
        poly = list(base)
        for j, o in enumerate(centers):
            if i != j and poly:
                poly = clip_polygon_halfplane(poly, c, o)
        cells.append(poly)
    return cells


def densify_track(points: Sequence[dict], step_hours: float = 1.0) -> list[dict]:
    """Linearly interpolate a track (dicts with lat, lon, t_hours and numeric fields)."""
    if len(points) < 2:
        return [dict(p) for p in points]
    out: list[dict] = []
    numeric = [k for k, v in points[0].items() if isinstance(v, (int, float)) and k not in ("lat", "lon", "t_hours")]
    for a, b in zip(points[:-1], points[1:]):
        span = b["t_hours"] - a["t_hours"]
        steps = max(1, int(round(span / step_hours)))
        for s in range(steps):
            f = s / steps
            p = {"lat": a["lat"] + f * (b["lat"] - a["lat"]),
                 "lon": a["lon"] + f * (b["lon"] - a["lon"]),
                 "t_hours": a["t_hours"] + f * span}
            for k in numeric:
                if isinstance(b.get(k), (int, float)):
                    p[k] = a[k] + f * (b[k] - a[k])
            p["is_forecast"] = b.get("is_forecast", False) if f > 0 else a.get("is_forecast", False)
            out.append(p)
    last = dict(points[-1])
    out.append(last)
    return out


def bbox_of(points: Iterable[LatLon], pad: float = 0.0) -> tuple[float, float, float, float]:
    pts = list(points)
    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]
    return min(lats) - pad, max(lats) + pad, min(lons) - pad, max(lons) + pad
