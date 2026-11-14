"""Runtime configuration, read once from environment variables (and the repo-root .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

REPO_DIR = Path(__file__).resolve().parents[2]
load_dotenv(REPO_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # MongoDB Atlas (runtime access via PyMongo; see app/db.py — owned by the DB lane)
    mongodb_uri: str
    mongodb_db: str
    # Voyage AI embeddings for Atlas Vector Search
    voyage_api_key: str
    voyage_model: str
    memory_enabled: bool
    # Simulated external systems
    broker_url: str
    directory_url: str
    custodian_url: str
    sim_admin_token: str
    # Worker
    custodian_timeout_seconds: float
    worker_poll_seconds: float
    # Demo mode
    demo_mode: bool
    demo_reviewer_id: str
    demo_reviewer_token: str
    demo_case_id: str = "SI-2041"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        mongodb_uri=os.getenv("MONGODB_URI", ""),
        mongodb_db=os.getenv("MONGODB_DB", "tradeops"),
        voyage_api_key=os.getenv("VOYAGE_API_KEY", ""),
        voyage_model=os.getenv("VOYAGE_MODEL", "voyage-3.5-lite"),
        memory_enabled=_bool("MEMORY_ENABLED", True),
        broker_url=os.getenv("BROKER_URL", "http://127.0.0.1:8101"),
        directory_url=os.getenv("DIRECTORY_URL", "http://127.0.0.1:8102"),
        custodian_url=os.getenv("CUSTODIAN_URL", "http://127.0.0.1:8103"),
        sim_admin_token=os.getenv("SIM_ADMIN_TOKEN", ""),
        custodian_timeout_seconds=float(os.getenv("CUSTODIAN_TIMEOUT_SECONDS", "3")),
        worker_poll_seconds=float(os.getenv("WORKER_POLL_SECONDS", "1")),
        demo_mode=_bool("DEMO_MODE", False),
        demo_reviewer_id=os.getenv("DEMO_REVIEWER_ID", "demo-reviewer"),
        demo_reviewer_token=os.getenv("DEMO_REVIEWER_TOKEN", ""),
    )
