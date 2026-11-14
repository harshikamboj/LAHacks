#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT/backend/.runtime/worker.pid"
if [[ ! -f "$PID_FILE" ]]; then echo "No local worker PID recorded"; exit 0; fi
WORKER_PID="$(cat "$PID_FILE")"
if ! [[ "$WORKER_PID" =~ ^[0-9]+$ ]]; then echo "Invalid PID file"; exit 1; fi
if ps -p "$WORKER_PID" -o args= | grep -q 'app.worker'; then
  kill -TERM "$WORKER_PID"
  for _ in {1..30}; do
    if ! kill -0 "$WORKER_PID" 2>/dev/null; then break; fi
    sleep 0.2
  done
  echo "Local workflow worker stopped"
else
  echo "Recorded worker is already stopped"
fi
