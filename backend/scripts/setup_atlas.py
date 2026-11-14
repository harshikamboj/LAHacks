"""Run: cd backend && .venv/bin/python scripts/setup_atlas.py (or uv run python ...)."""

import json
import sys

from pymongo.errors import PyMongoError

from app.config import Settings
from app.db import create_client, get_database
from app.schema import ensure_collections, ensure_vector_index
from app.seed import seed_database
from app.services.memory import IncidentMemory


def main() -> int:
    settings = Settings()
    try:
        with create_client(settings, setup=True) as client:
            db = get_database(client, settings)
            db.command("ping")
            ensure_collections(db)
            seeded = seed_database(db, settings)
            try:
                vector = ensure_vector_index(db, settings.mongodb_vector_index)
            except PyMongoError as exc:
                vector = {
                    "status": "PENDING",
                    "reason": "VECTOR_INDEX_SETUP_UNAVAILABLE",
                    "errorCode": exc.code if hasattr(exc, "code") else None,
                }
            report = {
                "database": settings.mongodb_db,
                "collections": db.list_collection_names(),
                "seed": seeded,
                "vectorIndex": vector,
                "memory": IncidentMemory(db, settings).status(),
                "organizerSandboxConfirmed": settings.atlas_sandbox_confirmed,
            }
            print(json.dumps(report, indent=2))
        return 0
    except (PyMongoError, ValueError) as exc:
        # Never print a connection URI, password, provider body, or raw traceback.
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "errorType": type(exc).__name__,
                    "errorCode": getattr(exc, "code", None),
                }
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
