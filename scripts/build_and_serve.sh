#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Activate venv if not already
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  source .venv/bin/activate
fi

# Build frontend
echo ">>> Building frontend..."
cd frontend
npm install --no-audit --no-fund
npm run build
cd "$ROOT"

# Start FastAPI
echo ">>> Starting FastAPI at http://127.0.0.1:8000"
exec uvicorn tutor.web.api:create_app --factory --host 127.0.0.1 --port 8000
