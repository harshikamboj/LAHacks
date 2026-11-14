"""GET /api/health — truthful status of every dependency. Nothing here is hardcoded to 'ok'."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.services import simulator_clients as sims

router = APIRouter()


def atlas_status() -> dict:
    settings = get_settings()
    if not settings.mongodb_uri:
        return {"ok": False, "status": "NOT_CONFIGURED", "db": settings.mongodb_db,
                "error": "MONGODB_URI is not set in .env"}
    try:
        from app import db  # owned by the DB lane; exposes ping()
    except ImportError:
        return {"ok": False, "status": "PENDING", "db": settings.mongodb_db,
                "error": "app/db.py is not implemented yet"}
    try:
        db.ping()
        return {"ok": True, "status": "CONNECTED", "db": settings.mongodb_db, "error": None}
    except Exception as exc:  # report any driver error rather than crash the health check
        return {"ok": False, "status": "ERROR", "db": settings.mongodb_db, "error": str(exc)}


def simulator_status() -> dict:
    out = {}
    for name, client in (("broker", sims.broker()), ("directory", sims.directory()),
                         ("custodian", sims.custodian())):
        try:
            client.health()
            out[name] = {"ok": True, "url": client.base_url}
        except sims.SimulatorError as exc:
            out[name] = {"ok": False, "url": client.base_url, "error": exc.message}
    return out


@router.get("/health")
def health():
    settings = get_settings()
    return {
        "api": "ok",
        "atlas": atlas_status(),
        "simulators": simulator_status(),
        # Worker heartbeat lives in Atlas (workers collection) once the worker is built.
        "worker": {"online": False, "status": "NOT_IMPLEMENTED"},
        "memory": {"vectorSearch": "PENDING",
                   "reason": None if settings.voyage_api_key else "VOYAGE_API_KEY is not set"},
        "demoMode": settings.demo_mode,
    }
