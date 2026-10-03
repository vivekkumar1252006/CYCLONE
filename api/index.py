"""Vercel serverless entry point. Only /tmp is writable, so the DB and model live there per instance."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/cycloneguard.db")
os.environ.setdefault("MODEL_PATH", "/tmp/vulnerability_model.joblib")

from backend.app.database import init_db  # noqa: E402
from backend.app.main import app, seed_if_empty  # noqa: E402
from backend.app.services import pipeline  # noqa: E402

init_db()
pipeline.get_vulnerability_model()
seed_if_empty()

__all__ = ["app"]
