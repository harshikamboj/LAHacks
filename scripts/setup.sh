#!/usr/bin/env bash
set -euo pipefail
MARKET_FILE="${1:-}"
if [[ -n "$MARKET_FILE" ]]; then
  MARKET_FILE="$(python3 -c 'import sys; from pathlib import Path; print(Path(sys.argv[1]).expanduser().resolve())' "$MARKET_FILE")"
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -d backend/.venv ]]; then python3 -m venv backend/.venv; fi
backend/.venv/bin/python -m pip install -e 'backend[dev]'
cd backend
if [[ -n "$MARKET_FILE" ]]; then
  .venv/bin/python scripts/configure_demo.py --market-file "$MARKET_FILE"
else
  .venv/bin/python scripts/configure_demo.py
fi
.venv/bin/python scripts/setup_atlas.py
.venv/bin/python - <<'PY'
from pathlib import Path
from app.config import Settings
from app.db import create_client,get_database
from app.market import import_market
import json
s=Settings()
if not s.market_data_file:
    raise SystemExit('Pass the supplied market_fail_observations.json path to scripts/setup.sh')
with create_client(s) as c:
    result=import_market(get_database(c,s),Path(s.market_data_file))
print(json.dumps(result,indent=2))
if result['rejected'] or not result['anchorVerified']:raise SystemExit(1)
PY
cd "$ROOT/frontend"
npm ci --no-audit --no-fund
echo "Setup complete. Run ./scripts/dev.sh, ./scripts/reset.sh, then ./scripts/worker.sh separately."
