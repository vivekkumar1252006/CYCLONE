#!/usr/bin/env bash
# Start backend (port 8000) and frontend (port 5173) for local development (Linux/macOS).
set -euo pipefail
cd "$(dirname "$0")/.."

[ -d .venv ] || { python3 -m venv .venv; .venv/bin/pip install -r backend/requirements.txt; }
[ -f models/vulnerability_model.joblib ] || .venv/bin/python -m ml.train
[ -d frontend/node_modules ] || (cd frontend && npm install)

.venv/bin/uvicorn backend.app.main:app --port 8000 --reload &
BACK=$!
trap 'kill $BACK' EXIT
cd frontend && npm run dev
