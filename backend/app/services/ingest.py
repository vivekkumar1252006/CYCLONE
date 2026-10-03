"""Validated ingestion of infrastructure inventories (CSV / GeoJSON).

Required fields: name, asset_type, lat, lon (CSV) or Point/LineString/Polygon
geometry (GeoJSON). Optional: district, elevation_m, age_years,
historical_damage_count, criticality (0-1), capacity.

Invalid rows are rejected individually with a reason; valid rows are accepted.
Missing geographic attributes are derived from the GIS provider and flagged.
"""
from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass, field

from ml.features import ASSET_TYPE_KEYS, normalize_asset_type

from ..geodata import region

MAX_ROWS = 5000
COAST_TOLERANCE_KM = 2.0
ALLOWED_EXTENSIONS = {".csv", ".geojson", ".json"}


class IngestError(ValueError):
    pass


@dataclass
class IngestResult:
    accepted: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _num(v, name: str, lo: float | None = None, hi: float | None = None, required: bool = False) -> float | None:
    if v is None or (isinstance(v, str) and v.strip() == ""):
        if required:
            raise IngestError(f"missing {name}")
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise IngestError(f"{name} is not a number: {v!r}")
    if math.isnan(x) or math.isinf(x):
        raise IngestError(f"{name} is not finite")
    if (lo is not None and x < lo) or (hi is not None and x > hi):
        raise IngestError(f"{name}={x} outside [{lo}, {hi}]")
    return x


def _clean_text(v, max_len: int) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    # strip control characters; keep it a plain label
    s = "".join(ch for ch in s if ch.isprintable())
    return s[:max_len] or None


def validate_record(props: dict, lat, lon, geometry: dict | None = None) -> dict:
    name = _clean_text(props.get("name"), 200)
    if not name:
        raise IngestError("missing name")
    raw_type = props.get("asset_type") or props.get("type") or ""
    atype = normalize_asset_type(str(raw_type))
    if atype is None:
        raise IngestError(f"unknown asset_type {raw_type!r}; expected one of {', '.join(ASSET_TYPE_KEYS)}")
    lat_f = _num(lat, "lat", -90, 90, required=True)
    lon_f = _num(lon, "lon", -180, 180, required=True)
    if not region.in_region(lat_f, lon_f):
        raise IngestError(f"location ({lat_f:.4f}, {lon_f:.4f}) is outside the configured study region {region.REGION_BBOX}")
    if not region.is_land(lat_f, lon_f) and region.dist_coast_km(lat_f, lon_f) > COAST_TOLERANCE_KM:
        # the reference coastline is simplified, so points just seaward of it are accepted
        raise IngestError("location falls in the sea according to the study-region coastline")
    elev = _num(props.get("elevation_m"), "elevation_m", -50, 9000)
    ctx = region.site_context(lat_f, lon_f, elev)
    district = _clean_text(props.get("district"), 80) or ctx["district"]
    return {
        "name": name, "asset_type": atype, "lat": round(lat_f, 6), "lon": round(lon_f, 6), "geometry": geometry,
        "district": district, "elevation_m": ctx["elevation_m"], "elevation_source": ctx["elevation_source"],
        "slope_deg": ctx["slope_deg"], "dist_coast_km": ctx["dist_coast_km"], "dist_river_km": ctx["dist_river_km"],
        "in_flood_zone": ctx["in_flood_zone"], "land_use": ctx["land_use"],
        "age_years": _num(props.get("age_years"), "age_years", 0, 300),
        "historical_damage_count": _num(props.get("historical_damage_count"), "historical_damage_count", 0, 1000),
        "criticality": _num(props.get("criticality"), "criticality", 0, 1),
        "capacity": _clean_text(props.get("capacity"), 80),
    }


def parse_csv(content: bytes) -> IngestResult:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise IngestError("CSV must be UTF-8 encoded")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise IngestError("CSV has no header row")
    headers = {h.strip().lower() for h in reader.fieldnames if h}
    lat_key = next((k for k in ("lat", "latitude") if k in headers), None)
    lon_key = next((k for k in ("lon", "lng", "longitude") if k in headers), None)
    missing = [k for k, ok in (("name", "name" in headers), ("asset_type", "asset_type" in headers or "type" in headers),
                               ("lat", lat_key), ("lon", lon_key)) if not ok]
    if missing:
        raise IngestError(f"CSV missing required columns: {', '.join(missing)}")
    res = IngestResult()
    for i, raw in enumerate(reader, start=2):  # row 1 = header
        if i - 1 > MAX_ROWS:
            res.warnings.append(f"only the first {MAX_ROWS} rows were processed")
            break
        row = {(k or "").strip().lower(): v for k, v in raw.items()}
        try:
            res.accepted.append(validate_record(row, row.get(lat_key), row.get(lon_key)))
        except IngestError as e:
            res.rejected.append({"row": i, "name": row.get("name"), "error": str(e)})
    return res


def _representative_point(geom: dict) -> tuple[float, float]:
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    try:
        if gtype == "Point":
            return float(coords[1]), float(coords[0])
        if gtype == "LineString":
            mid = coords[len(coords) // 2]
            return float(mid[1]), float(mid[0])
        if gtype == "MultiLineString":
            line = coords[0]
            mid = line[len(line) // 2]
            return float(mid[1]), float(mid[0])
        if gtype == "Polygon":
            ring = coords[0]
            return sum(float(p[1]) for p in ring) / len(ring), sum(float(p[0]) for p in ring) / len(ring)
    except (TypeError, IndexError, ValueError, ZeroDivisionError):
        raise IngestError("malformed geometry coordinates")
    raise IngestError(f"unsupported geometry type {gtype!r}")


def parse_geojson(content: bytes) -> IngestResult:
    try:
        data = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise IngestError(f"invalid GeoJSON: {e}")
    if not isinstance(data, dict):
        raise IngestError("GeoJSON root must be an object")
    if data.get("type") == "Feature":
        features = [data]
    elif data.get("type") == "FeatureCollection" and isinstance(data.get("features"), list):
        features = data["features"]
    else:
        raise IngestError("GeoJSON must be a Feature or FeatureCollection")
    res = IngestResult()
    for i, f in enumerate(features[:MAX_ROWS]):
        props = (f or {}).get("properties") or {}
        try:
            geom = (f or {}).get("geometry")
            if not isinstance(geom, dict):
                raise IngestError("feature has no geometry")
            lat, lon = _representative_point(geom)
            res.accepted.append(validate_record({k.lower(): v for k, v in props.items()}, lat, lon, geometry=geom))
        except IngestError as e:
            res.rejected.append({"feature": i, "name": props.get("name"), "error": str(e)})
    if len(features) > MAX_ROWS:
        res.warnings.append(f"only the first {MAX_ROWS} features were processed")
    return res


def parse_upload(filename: str, content: bytes, max_bytes: int) -> IngestResult:
    if not filename:
        raise IngestError("missing filename")
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise IngestError(f"unsupported file type {ext or '(none)'}; allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    if len(content) == 0:
        raise IngestError("file is empty")
    if len(content) > max_bytes:
        raise IngestError(f"file exceeds the {max_bytes // (1024 * 1024)} MB limit")
    if b"\x00" in content[:4096]:
        raise IngestError("file appears to be binary, not text")
    return parse_csv(content) if ext == ".csv" else parse_geojson(content)
