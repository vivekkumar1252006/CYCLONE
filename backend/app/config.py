"""Application settings, loaded from environment variables / .env (never hard-coded secrets)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore")

    app_name: str = "CycloneGuard AI"
    environment: str = "development"

    # sqlite fallback by default; e.g. postgresql+psycopg2://user:pass@db:5432/cycloneguard
    database_url: str = f"sqlite:///{(REPO_ROOT / 'data' / 'cycloneguard.db').as_posix()}"

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080"

    # If set, mutating endpoints require header `X-API-Key: <value>`.
    admin_api_key: str | None = None

    max_upload_mb: float = 5.0

    model_path: Path = REPO_ROOT / "models" / "vulnerability_model.joblib"
    vuln_model_backend: str = "random_forest"  # or "xgboost"

    # ---- live data providers (all optional; demo fallback when unset/unavailable) ----
    cyclone_feed_url: str | None = None        # JSON feed in the documented track schema
    cyclone_feed_api_key: str | None = None
    weather_provider: str = "demo"             # "demo" | "openmeteo"
    openmeteo_base_url: str = "https://api.open-meteo.com/v1/forecast"
    satellite_provider_url: str | None = None
    satellite_api_key: str | None = None
    provider_timeout_s: float = 6.0

    auto_seed_demo: bool = True  # create the default demo scenario on first start

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
