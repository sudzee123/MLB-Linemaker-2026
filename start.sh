#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Backend ────────────────────────────────────────────────────────
echo "Starting backend on http://localhost:8000 ..."
cd "$ROOT"
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# ── Frontend ───────────────────────────────────────────────────────
cd "$ROOT/frontend"

if [ ! -d node_modules ]; then
  echo "Installing frontend dependencies (first run)..."
  npm install
fi

echo "Starting frontend on http://localhost:3000 ..."
npm run dev &
FRONTEND_PID=$!

echo ""
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo "  (Ctrl-C to stop both)"
echo ""

wait $BACKEND_PID $FRONTEND_PID
