"""Shared fixtures. Uses an isolated temporary SQLite database for every test session."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_tmp = tempfile.mkdtemp(prefix="cycloneguard-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp, 'test.db').as_posix()}"
os.environ["AUTO_SEED_DEMO"] = "false"
os.environ.pop("ADMIN_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from backend.app.main import app  # noqa: E402

SAMPLES = ROOT / "data" / "samples"


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        r = c.post("/api/demo/generate", json={"scenario": "alpha", "n_assets": 120, "seed": 1})
        assert r.status_code == 200, r.text
        yield c


@pytest.fixture
def sample_csv() -> bytes:
    return (SAMPLES / "sample_infrastructure.csv").read_bytes()


@pytest.fixture
def sample_geojson() -> bytes:
    return (SAMPLES / "sample_infrastructure.geojson").read_bytes()
