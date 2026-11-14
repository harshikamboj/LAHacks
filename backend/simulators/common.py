"""Shared helpers for the three simulated external systems.

Each simulator is its own FastAPI process with its own SQLite file, so it stays an
independent authority and keeps its records when the workflow worker restarts.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Header, HTTPException
from fastapi.responses import JSONResponse

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
FIXTURES_DIR = BACKEND_DIR / "fixtures"

load_dotenv(REPO_DIR / ".env")


def data_dir() -> Path:
    """Directory holding the simulators' SQLite files (gitignored)."""
    raw = os.getenv("SIM_DATA_DIR", "backend/simulators/data")
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_DIR / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def utc_now() -> str:
    """ISO-8601 UTC timestamp with milliseconds, e.g. 2026-11-14T15:04:05.123Z."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def load_fixture(name: str) -> Any:
    with open(FIXTURES_DIR / name, encoding="utf-8") as fh:
        value = json.load(fh)
    # Integration tests use unique synthetic IDs and their own simulator databases.
    if name in {"trades.json", "instructions.json"}:
        for row in value:
            row["tradeId"] = os.getenv("DEMO_TRADE_ID", row["tradeId"])
            if "instructionId" in row:
                row["instructionId"] = os.getenv("DEMO_CASE_ID", row["instructionId"])
    return value


def ensure_columns(store, table: str, columns: tuple[str, ...]) -> None:
    present = {r["name"] for r in store.query_all(f"PRAGMA table_info({table})")}
    for name in columns:
        if name not in present:
            store.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")


def canonical_hash(payload: dict) -> str:
    """sha256 of canonical JSON (sorted keys, no whitespace)."""
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


class Store:
    """One SQLite connection per simulator, serialised with a lock.

    `isolation_level=None` puts sqlite3 in autocommit mode so we can issue explicit
    `BEGIN IMMEDIATE` transactions where atomicity matters (custodian PATCH).
    """

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self.lock:
            return self.conn.execute(sql, params).fetchone()

    def query_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, params).fetchall()

    def script(self, sql: str) -> None:
        with self.lock:
            self.conn.executescript(sql)


def error(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    """Uniform error body: {"error": {"code", "message", "details"}}."""
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def require_admin(x_sim_admin: str | None = Header(default=None)) -> None:
    """FastAPI dependency guarding /admin/* mutation routes with SIM_ADMIN_TOKEN."""
    expected = os.getenv("SIM_ADMIN_TOKEN", "")
    if not expected or not x_sim_admin or not hmac.compare_digest(x_sim_admin, expected):
        raise HTTPException(status_code=401, detail="Missing or invalid X-Sim-Admin token")
