"""Request schemas (strict validation of all client input)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TrackPointIn(_Strict):
    time: datetime
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    wind_kmh: float = Field(ge=0, le=400)
    pressure_hpa: float | None = Field(default=None, ge=850, le=1060)
    is_forecast: bool = False
    rmw_km: float | None = Field(default=None, ge=5, le=200)
    roi_km: float | None = Field(default=None, ge=20, le=1500)
    uncertainty_km: float | None = Field(default=None, ge=0, le=1000)

    @field_validator("time")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        # naive timestamps are interpreted as UTC
        return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)


class CycloneIn(_Strict):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    points: list[TrackPointIn] = Field(min_length=2, max_length=500)

    @model_validator(mode="after")
    def _check_track(self):
        times = [p.time for p in self.points]
        if any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError("track point times must be strictly increasing")
        if all(p.is_forecast for p in self.points):
            raise ValueError("track must contain at least one observed (is_forecast=false) point")
        seen_forecast = False
        for p in self.points:
            if p.is_forecast:
                seen_forecast = True
            elif seen_forecast:
                raise ValueError("observed points must precede forecast points")
        return self


class DemoGenerateIn(_Strict):
    scenario: Literal["alpha", "bravo", "charlie"] = "alpha"
    n_assets: int = Field(default=320, ge=20, le=2000)
    seed: int = Field(default=42, ge=0, le=10_000_000)
    regenerate_assets: bool = True


class PredictAssetIn(_Strict):
    name: str = Field(default="Ad-hoc asset", max_length=200)
    asset_type: str = Field(min_length=1, max_length=60)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    elevation_m: float | None = Field(default=None, ge=-50, le=9000)
    age_years: float | None = Field(default=None, ge=0, le=300)
    historical_damage_count: float | None = Field(default=None, ge=0, le=1000)
    criticality: float | None = Field(default=None, ge=0, le=1)


class PredictIn(_Strict):
    cyclone_id: int | None = None
    assets: list[PredictAssetIn] | None = Field(default=None, max_length=500)


class HazardSubweights(_Strict):
    wind: float = Field(ge=0, le=1)
    rain: float = Field(ge=0, le=1)
    flood: float = Field(ge=0, le=1)
    surge: float = Field(ge=0, le=1)


class RiskConfigIn(_Strict):
    w_hazard: float = Field(ge=0, le=1)
    w_vulnerability: float = Field(ge=0, le=1)
    w_environment: float = Field(ge=0, le=1)
    w_criticality: float = Field(ge=0, le=1)
    hazard_gate: float = Field(default=0.25, ge=0, le=1)
    threshold_low: float = Field(ge=0, le=100)
    threshold_moderate: float = Field(ge=0, le=100)
    threshold_high: float = Field(ge=0, le=100)
    alert_min_confidence: float = Field(ge=0, le=1)
    hazard_subweights: HazardSubweights | None = None

    @field_validator("threshold_high")
    @classmethod
    def _order(cls, v, info):
        lo, mo = info.data.get("threshold_low"), info.data.get("threshold_moderate")
        if lo is not None and mo is not None and not (lo < mo < v):
            raise ValueError("thresholds must satisfy low < moderate < high")
        return v

    @model_validator(mode="after")
    def _weights(self):
        if self.w_hazard + self.w_vulnerability + self.w_environment + self.w_criticality <= 0:
            raise ValueError("at least one weight must be > 0")
        return self
