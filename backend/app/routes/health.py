"""GET /api/health — truthful status of every dependency. Nothing here is hardcoded to 'ok'."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import APIRouter
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.config import get_settings
from app.db import create_client, get_database
from app.services import simulator_clients as sims
from app.services.memory import IncidentMemory

router = APIRouter()

WORKER_ONLINE_SECONDS = 5.0
MEMORY_STATUS_TTL_SECONDS = 30.0  # listing search indexes is too heavy for a 1 s poll
_memory_cache: dict = {"at": 0.0, "value": None}


@lru_cache
def _client() -> MongoClient:
    # One pooled client per API process, using the runtime (readWrite-only) credentials.
    return create_client(get_settings())


def atlas_status() -> tuple[dict, object | None]:
    settings = get_settings()
    try:
        settings.connection_uri()
    except ValueError as exc:
        return {
            "ok": False,
            "status": "NOT_CONFIGURED",
            "db": settings.mongodb_db,
            "error": str(exc),
        }, None
    try:
        client = _client()
        client.admin.command("ping")
        return {
            "ok": True,
            "status": "CONNECTED",
            "db": settings.mongodb_db,
            "error": None,
        }, get_database(client, settings)
    except PyMongoError as exc:
        return {
            "ok": False,
            "status": "ERROR",
            "db": settings.mongodb_db,
            "error": type(exc).__name__,
        }, None  # never echo driver text: it can contain hosts


def worker_status(db) -> dict:
    if db is None:
        return {"online": False, "status": "UNKNOWN", "reason": "Atlas not connected"}
    try:
        doc = db.workers.find_one({"_id": get_settings().worker_record_id}, {"_id": 0})
    except PyMongoError:
        return {"online": False, "status": "UNKNOWN", "reason": "Heartbeat unreadable"}
    if not doc or not doc.get("heartbeatAt"):
        return {"online": False, "status": "NEVER_STARTED"}
    beat = doc["heartbeatAt"]
    if beat.tzinfo is None:
        beat = beat.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - beat).total_seconds()
    online = age <= WORKER_ONLINE_SECONDS and not doc.get("stoppedAt")
    return {
        "online": bool(online),
        "status": "ONLINE" if online else "OFFLINE",
        "workerId": doc.get("workerId"),
        "pid": doc.get("pid"),
        "heartbeatAt": beat.isoformat(),
        "ageSeconds": round(age, 1),
    }


def memory_status(db) -> dict:
    if db is None:
        return {"vectorSearch": "PENDING", "reason": "ATLAS_NOT_CONNECTED"}
    now = time.monotonic()
    if _memory_cache["value"] is None or now - _memory_cache["at"] > MEMORY_STATUS_TTL_SECONDS:
        _memory_cache["value"] = IncidentMemory(db, get_settings()).status()
        _memory_cache["at"] = now
    return _memory_cache["value"]


def simulator_status() -> dict:
    out = {}
    for name, client in (
        ("broker", sims.broker()),
        ("directory", sims.directory()),
        ("custodian", sims.custodian()),
    ):
        try:
            client.health()
            out[name] = {"ok": True, "url": client.base_url}
        except sims.SimulatorError as exc:
            out[name] = {"ok": False, "url": client.base_url, "error": exc.message}
    return out


@router.get("/health")
def health():
    atlas, db = atlas_status()
    return {
        "api": "ok",
        "atlas": atlas,
        "simulators": simulator_status(),
        "worker": worker_status(db),
        "memory": memory_status(db),
        "demoMode": get_settings().demo_mode,
    }
