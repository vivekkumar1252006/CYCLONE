# Start backend (port 8000) and frontend (port 5173) for local development on Windows.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\run_dev.ps1
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv")) {
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
}
if (-not (Test-Path "models\vulnerability_model.joblib")) { .\.venv\Scripts\python.exe -m ml.train }
if (-not (Test-Path "frontend\node_modules")) { Push-Location frontend; npm install; Pop-Location }

Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-m uvicorn backend.app.main:app --port 8000 --reload" -WorkingDirectory $root
Push-Location frontend
npm run dev
Pop-Location
