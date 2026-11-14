#!/usr/bin/env bash
# Start the three simulators (8101/8102/8103) and the API (8000). Ctrl+C stops all of them.
# The worker is started separately with scripts/worker.sh so it can be killed/restarted on its own.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"

pids=()
cleanup() { echo; echo "Stopping..."; kill "${pids[@]}" 2>/dev/null || true; wait 2>/dev/null || true; }
trap cleanup EXIT INT TERM

start() { # name port target
  echo "Starting $1 on :$2"
  .venv/bin/python -m uvicorn "$3" --host 127.0.0.1 --port "$2" --log-level warning "${@:4}" &
  pids+=($!)
}

start broker    8101 simulators.broker:create_app --factory
start directory 8102 simulators.directory:create_app --factory
start custodian 8103 simulators.custodian:create_app --factory
start api       8000 app.main:app

(cd "$ROOT/frontend" && npm run dev -- --host 127.0.0.1 --strictPort) &
pids+=($!)

echo "API: http://127.0.0.1:8000/docs   Health: http://127.0.0.1:8000/api/health"
echo "ProofStep Operations Console: http://localhost:3000"
wait
