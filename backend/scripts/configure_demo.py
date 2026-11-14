"""Generate local demo tokens only when still blank/placeholders. Never print them."""

import argparse
import secrets
from pathlib import Path

from dotenv import dotenv_values, set_key

from app.config import REPO_ROOT

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--market-file", type=Path)
args = parser.parse_args()
path = REPO_ROOT / ".env"
if not path.exists():
    path.write_text((REPO_ROOT / ".env.example").read_text())
values = dotenv_values(path)
for name in ("SIM_ADMIN_TOKEN", "DEMO_REVIEWER_TOKEN"):
    if not values.get(name) or values[name].startswith("change-me"):
        set_key(path, name, secrets.token_urlsafe(32))
if args.market_file:
    set_key(path, "MARKET_DATA_FILE", str(args.market_file.resolve()))
path.chmod(0o600)
print("Local demo credentials configured in gitignored .env; secrets not printed.")
