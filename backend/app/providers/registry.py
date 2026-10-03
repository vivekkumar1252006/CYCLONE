"""Provider selection + status reporting (live when configured, demo fallback otherwise)."""
from __future__ import annotations

from ..config import get_settings
from .live import (ConfiguredSatelliteProvider, DatabaseInfrastructureProvider, DemoGISProvider,
                   FeedCycloneProvider, OpenMeteoWeatherProvider)


def cyclone_provider() -> FeedCycloneProvider | None:
    s = get_settings()
    return FeedCycloneProvider(s.cyclone_feed_url, s.cyclone_feed_api_key, s.provider_timeout_s) if s.cyclone_feed_url else None


def weather_provider() -> OpenMeteoWeatherProvider | None:
    s = get_settings()
    return OpenMeteoWeatherProvider(s.openmeteo_base_url, s.provider_timeout_s) if s.weather_provider == "openmeteo" else None


def gis_provider() -> DemoGISProvider:
    return DemoGISProvider()


def satellite_provider() -> ConfiguredSatelliteProvider:
    s = get_settings()
    return ConfiguredSatelliteProvider(s.satellite_provider_url, s.satellite_api_key)


def status() -> list[dict]:
    s = get_settings()
    return [
        {"family": "cyclone_forecast", "provider": "json-feed" if s.cyclone_feed_url else "demo-scenarios",
         "mode": "live" if s.cyclone_feed_url else "demo",
         "note": "Set CYCLONE_FEED_URL to import live tracks" if not s.cyclone_feed_url else "Use POST /api/cyclone/import-live"},
        {"family": "weather", "provider": "open-meteo" if s.weather_provider == "openmeteo" else "demo-simulated-stations",
         "mode": "live" if s.weather_provider == "openmeteo" else "demo",
         "note": "Set WEATHER_PROVIDER=openmeteo for NWP forecast rainfall" if s.weather_provider != "openmeteo"
         else "Use POST /api/weather/refresh"},
        {"family": "gis", "provider": DemoGISProvider.name, "mode": "demo",
         "note": "Replace with SRTM/Copernicus DEM, OSM / Bhuvan layers and official boundaries"},
        {"family": "infrastructure", "provider": DatabaseInfrastructureProvider.name, "mode": "mixed",
         "note": "Upload CSV/GeoJSON via POST /api/infrastructure/upload"},
        {"family": "satellite", "provider": "not configured" if not s.satellite_provider_url else "configured (interface only)",
         "mode": "unavailable",
         "note": "Satellite basemap is shown in the UI; scene analytics are a documented future extension"},
    ]
