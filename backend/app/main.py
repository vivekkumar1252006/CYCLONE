"""CycloneGuard AI - FastAPI application entry point.

Run from the repository root:
    uvicorn backend.app.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from .api import admin, alerts, cyclone, infrastructure, risk, statistics
from .config import get_settings
from .database import SessionLocal, init_db
from .models import Cyclone
from .services import demo_generator, pipeline, settings_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cycloneguard")


def seed_if_empty() -> None:
    with SessionLocal() as db:
        demo_generator.ensure_districts(db)
        db.commit()
        if db.scalar(select(Cyclone.id).limit(1)) is None and get_settings().auto_seed_demo:
            log.info("Seeding default DEMO scenario (simulated data)")
            cy = demo_generator.generate_demo(db, "alpha")
            settings_store.set_active_cyclone_id(db, cy.id)
            db.commit()
            pipeline.run_prediction(db, cy.id)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    pipeline.get_vulnerability_model()  # load or train once at startup
    seed_if_empty()
    yield


settings = get_settings()
app = FastAPI(
    title="CycloneGuard AI API",
    version="0.1.0",
    description=("Track-based cyclone impact & infrastructure vulnerability forecast. "
                 "All outputs are model estimates with stated confidence; demo data is simulated."),
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False,
                   allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type", "X-API-Key"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    errors = [{"loc": [str(x) for x in e.get("loc", [])], "msg": e.get("msg")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "invalid request", "errors": errors})


@app.exception_handler(Exception)
async def unhandled_handler(_: Request, exc: Exception):
    log.exception("unhandled error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment,
            "auth_enabled": bool(settings.admin_api_key)}


for r in (cyclone.router, infrastructure.router, risk.router, alerts.router, statistics.router, admin.router):
    app.include_router(r)
