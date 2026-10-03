"""ORM models.

Geometries are stored as plain lat/lon columns + GeoJSON in JSON columns so the
same schema runs on SQLite (dev) and PostgreSQL. With PostGIS, see
``docker/postgres/init.sql`` which adds geometry columns + spatial indexes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; all stored values are UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


class Cyclone(Base):
    __tablename__ = "cyclones"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    basin: Mapped[str] = mapped_column(String(40), default="North Indian Ocean")
    scenario_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="demo")  # demo | live-feed | user
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    track: Mapped[list["CycloneTrackPoint"]] = relationship(back_populates="cyclone", cascade="all, delete-orphan",
                                                            order_by="CycloneTrackPoint.timestamp")


class CycloneTrackPoint(Base):
    __tablename__ = "cyclone_tracks"
    id: Mapped[int] = mapped_column(primary_key=True)
    cyclone_id: Mapped[int] = mapped_column(ForeignKey("cyclones.id", ondelete="CASCADE"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    wind_kmh: Mapped[float] = mapped_column(Float)
    pressure_hpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    category: Mapped[str] = mapped_column(String(10))
    rmw_km: Mapped[float] = mapped_column(Float, default=30.0)          # radius of maximum wind
    roi_km: Mapped[float] = mapped_column(Float, default=250.0)         # radius of influence (gale extent)
    is_forecast: Mapped[bool] = mapped_column(Boolean, default=False)
    uncertainty_km: Mapped[float] = mapped_column(Float, default=0.0)   # forecast cone radius
    cyclone: Mapped[Cyclone] = relationship(back_populates="track")


class WeatherObservation(Base):
    __tablename__ = "weather_observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    cyclone_id: Mapped[int | None] = mapped_column(ForeignKey("cyclones.id", ondelete="CASCADE"), nullable=True, index=True)
    station_name: Mapped[str] = mapped_column(String(120))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    rainfall_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_direction_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    surge_indicator_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="demo")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)


class District(Base):
    __tablename__ = "districts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    state: Mapped[str] = mapped_column(String(80))
    population: Mapped[int] = mapped_column(Integer)
    center_lat: Mapped[float] = mapped_column(Float)
    center_lon: Mapped[float] = mapped_column(Float)
    boundary: Mapped[dict] = mapped_column(JSON)  # GeoJSON Polygon geometry
    boundary_note: Mapped[str] = mapped_column(String(200), default="Schematic boundary (not official)")


class Infrastructure(Base):
    __tablename__ = "infrastructure"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    asset_type: Mapped[str] = mapped_column(String(40), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # original GeoJSON geometry if uploaded
    district: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    elevation_m: Mapped[float] = mapped_column(Float)
    elevation_source: Mapped[str] = mapped_column(String(40), default="provided")
    slope_deg: Mapped[float] = mapped_column(Float, default=1.0)
    dist_coast_km: Mapped[float] = mapped_column(Float)
    dist_river_km: Mapped[float] = mapped_column(Float)
    in_flood_zone: Mapped[bool] = mapped_column(Boolean, default=False)
    land_use: Mapped[str | None] = mapped_column(String(40), nullable=True)
    age_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    historical_damage_count: Mapped[float | None] = mapped_column(Float, nullable=True)
    criticality: Mapped[float | None] = mapped_column(Float, nullable=True)  # optional override 0-1
    capacity: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="demo")  # demo | upload
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelRun(Base):
    __tablename__ = "model_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    cyclone_id: Mapped[int] = mapped_column(ForeignKey("cyclones.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    impact_model: Mapped[str] = mapped_column(String(80))
    vulnerability_model: Mapped[str] = mapped_column(String(80))
    config: Mapped[dict] = mapped_column(JSON)
    n_assets: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # landfall, district stats, population exposure
    grids: Mapped[dict | None] = mapped_column(JSON, nullable=True)     # hazard grids for map layers
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class RiskPrediction(Base):
    __tablename__ = "risk_predictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("infrastructure.id", ondelete="CASCADE"), index=True)
    risk_score: Mapped[float] = mapped_column(Float)
    risk_category: Mapped[str] = mapped_column(String(20), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    confidence_label: Mapped[str] = mapped_column(String(10))
    vulnerability: Mapped[float] = mapped_column(Float)
    main_hazard: Mapped[str] = mapped_column(String(30))
    impact: Mapped[dict] = mapped_column(JSON)
    components: Mapped[dict] = mapped_column(JSON)
    contributions: Mapped[dict] = mapped_column(JSON)
    confidence_detail: Mapped[dict] = mapped_column(JSON)
    factors: Mapped[list] = mapped_column(JSON)
    ml_attributions: Mapped[list] = mapped_column(JSON)
    recommendations: Mapped[list] = mapped_column(JSON)
    asset: Mapped[Infrastructure] = relationship()


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("infrastructure.id", ondelete="CASCADE"), index=True)
    rule: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(20), index=True)  # critical | warning | advisory
    title: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(200))
    main_hazard: Mapped[str] = mapped_column(String(30))
    risk_score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    recommended_action: Mapped[str] = mapped_column(Text)
    triggered_rules: Mapped[list] = mapped_column(JSON, default=list)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    asset: Mapped[Infrastructure] = relationship()


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
