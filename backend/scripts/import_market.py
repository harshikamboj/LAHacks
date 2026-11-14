"""Stream the supplied Extended JSON dataset into Atlas. Never embed it as incident memory."""

import argparse
import json
from pathlib import Path

from app.config import Settings
from app.db import create_client, get_database
from app.market import import_market


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    settings = Settings()
    with create_client(settings) as client:
        report = import_market(get_database(client, settings), args.path)
    print(json.dumps(report, indent=2))
    return 0 if not report["rejected"] and report["anchorVerified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
