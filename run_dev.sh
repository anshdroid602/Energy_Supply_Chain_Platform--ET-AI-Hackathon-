#!/usr/bin/env bash
# One command to run the whole demo locally: FastAPI + the Vite frontend.
#
# Matches the deployment decision in task.md — no Docker/NGINX for the
# hackathon, just uvicorn on the demo laptop + the frontend dev server (or
# `cd frontend && npm run build` + any static host for a public URL).
#
# Usage:
#   ./run_dev.sh
# Ctrl+C stops both.

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [ ! -f .env ]; then
  echo "! No .env found. /pipeline/run still works via 'Inject Signal' (no DB needed),"
  echo "  but every other endpoint needs DATABASE_URL. Copy .env.example to .env first."
fi

if [ ! -d .venv ]; then
  echo "! No .venv found. Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend dependencies (first run only)..."
  (cd frontend && npm install)
fi

source .venv/bin/activate

echo "Starting API on http://localhost:8000 (docs at /docs) ..."
uvicorn api.main:app --reload --port 8000 &
API_PID=$!

echo "Starting frontend on http://localhost:5173 ..."
(cd frontend && npm run dev) &
FRONTEND_PID=$!

trap 'echo; echo "Stopping..."; kill $API_PID $FRONTEND_PID 2>/dev/null' INT TERM
wait $API_PID $FRONTEND_PID
