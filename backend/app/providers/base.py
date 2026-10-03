"""Data-provider interfaces.

Each external data family has an interface so real sources can be plugged in
without changing the pipeline. Implementations must raise
``ProviderUnavailable`` on any failure; callers then fall back to demo data and
report the fallback to the user.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ProviderUnavailable(RuntimeError):
    pass


class CycloneForecastProvider(ABC):
    name = "abstract"

    @abstractmethod
    def fetch_tracks(self) -> list[dict]:
        """Return cyclones: [{name, points: [{time, lat, lon, wind_kmh, pressure_hpa, is_forecast, ...}]}]"""


class WeatherProvider(ABC):
    name = "abstract"

    @abstractmethod
    def fetch(self, points: list[dict]) -> list[dict]:
        """points: [{name, lat, lon}] -> observation/forecast dicts matching WeatherObservation fields."""


class GISProvider(ABC):
    name = "abstract"

    @abstractmethod
    def site_context(self, lat: float, lon: float, elevation_m: float | None = None) -> dict: ...


class InfrastructureProvider(ABC):
    name = "abstract"

    @abstractmethod
    def fetch_assets(self) -> list[dict]: ...


class SatelliteProvider(ABC):
    name = "abstract"

    @abstractmethod
    def scene_metadata(self, bbox: tuple[float, float, float, float]) -> dict: ...
