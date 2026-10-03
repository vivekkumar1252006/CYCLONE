"""Live-data adapters. All are optional and configured through environment variables."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..geodata import region
from .base import (CycloneForecastProvider, GISProvider, InfrastructureProvider, ProviderUnavailable,
                   SatelliteProvider, WeatherProvider)


class FeedCycloneProvider(CycloneForecastProvider):
    """Generic JSON track feed (e.g. an internal adapter over agency bulletins).

    Expected schema::

        {"cyclones": [{"name": "...", "points": [
            {"time": "2026-10-03T06:00:00Z", "lat": 17.9, "lon": 86.8, "wind_kmh": 165,
             "pressure_hpa": 962, "is_forecast": false,
             "rmw_km": 25, "roi_km": 280, "uncertainty_km": 0}  # last 3 optional
        ]}]}
    """
    name = "json-feed"

    def __init__(self, url: str, api_key: str | None, timeout: float):
        self.url, self.api_key, self.timeout = url, api_key, timeout

    def fetch_tracks(self) -> list[dict]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            r = httpx.get(self.url, headers=headers, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise ProviderUnavailable(f"cyclone feed unavailable: {e}") from e
        cyclones = data.get("cyclones") if isinstance(data, dict) else None
        if not isinstance(cyclones, list):
            raise ProviderUnavailable("cyclone feed returned an unexpected schema")
        return cyclones


class OpenMeteoWeatherProvider(WeatherProvider):
    """Open-Meteo forecast API (no key required). Returns 72-h precipitation totals + current conditions.

    Values are numerical-weather-prediction FORECASTS, labelled as such.
    """
    name = "open-meteo"

    def __init__(self, base_url: str, timeout: float):
        self.base_url, self.timeout = base_url, timeout

    def fetch(self, points: list[dict]) -> list[dict]:
        if not points:
            return []
        params = {
            "latitude": ",".join(f"{p['lat']:.3f}" for p in points),
            "longitude": ",".join(f"{p['lon']:.3f}" for p in points),
            "hourly": "precipitation,wind_speed_10m,wind_direction_10m,temperature_2m,relative_humidity_2m",
            "forecast_days": 3, "timezone": "UTC", "wind_speed_unit": "kmh",
        }
        try:
            r = httpx.get(self.base_url, params=params, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise ProviderUnavailable(f"Open-Meteo unavailable: {e}") from e
        items = data if isinstance(data, list) else [data]
        if len(items) != len(points):
            raise ProviderUnavailable("Open-Meteo returned an unexpected number of locations")
        now = datetime.now(timezone.utc)
        out = []
        for p, item in zip(points, items):
            h = item.get("hourly") or {}
            try:
                precip = [x or 0.0 for x in h["precipitation"]]
                out.append({
                    "station_name": f"{p['name']} (Open-Meteo 72h forecast)", "lat": p["lat"], "lon": p["lon"],
                    "observed_at": now, "rainfall_mm": round(sum(precip), 1),
                    "wind_speed_kmh": max(x or 0 for x in h["wind_speed_10m"]),
                    "wind_direction_deg": h["wind_direction_10m"][0],
                    "temperature_c": h["temperature_2m"][0], "humidity_pct": h["relative_humidity_2m"][0],
                    "surge_indicator_m": None, "source": "open-meteo", "is_demo": False,
                })
            except (KeyError, IndexError, TypeError) as e:
                raise ProviderUnavailable(f"Open-Meteo response missing fields: {e}") from e
        return out


class DemoGISProvider(GISProvider):
    name = "demo-region (simplified geometry + synthetic DEM)"

    def site_context(self, lat, lon, elevation_m=None):
        return region.site_context(lat, lon, elevation_m)


class DatabaseInfrastructureProvider(InfrastructureProvider):
    """Infrastructure comes from the database (demo inventory and/or user CSV/GeoJSON uploads)."""
    name = "database (demo + uploads)"

    def fetch_assets(self) -> list[dict]:  # pragma: no cover - the pipeline reads the DB directly
        return []


class ConfiguredSatelliteProvider(SatelliteProvider):
    name = "satellite (interface only)"

    def __init__(self, url: str | None, api_key: str | None):
        self.url, self.api_key = url, api_key

    def scene_metadata(self, bbox):
        if not self.url:
            raise ProviderUnavailable("no satellite provider configured (set SATELLITE_PROVIDER_URL)")
        # Interface placeholder: a real implementation would query a STAC / Sentinel Hub catalogue here.
        raise ProviderUnavailable("satellite scene search is not implemented in this prototype")
