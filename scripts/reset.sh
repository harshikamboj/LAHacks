#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
"$ROOT/scripts/stop-worker.sh"
cd "$ROOT/backend"
.venv/bin/python - <<'PY'
import json,httpx
from app.config import Settings
s=Settings()
r=httpx.post('http://127.0.0.1:8000/api/demo/reset',json={'confirm':'RESET'},
    headers={'X-Reviewer-Token':s.demo_reviewer_token.get_secret_value()},timeout=30)
r.raise_for_status()
print(json.dumps(r.json(),indent=2))
PY
