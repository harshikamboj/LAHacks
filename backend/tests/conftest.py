"""Keep offline test settings independent of the developer's exported credentials."""

import os

import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def isolate_offline_settings_environment(request, monkeypatch):
    # Live Atlas tests intentionally use the real environment and repository .env.
    if request.node.get_closest_marker("atlas"):
        return

    # _env_file=None disables dotenv loading, but BaseSettings still reads os.environ.
    # Cover upper/lowercase names because Settings is case-insensitive by default.
    settings_names = {name.casefold() for name in Settings.model_fields}
    for name in tuple(os.environ):
        if name.casefold() in settings_names:
            monkeypatch.delenv(name)


# ---------- simulator fixtures (app lane) ----------
# Simulators run in-process with a fresh SQLite file per test; no MongoDB needed.
# The autouse fixture above clears SIM_ADMIN_TOKEN, so each fixture sets its own test token.

SIM_ADMIN = "test-admin-token"


@pytest.fixture
def admin_headers() -> dict:
    return {"X-Sim-Admin": SIM_ADMIN}


@pytest.fixture
def custodian(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from simulators.custodian import create_app

    monkeypatch.setenv("SIM_ADMIN_TOKEN", SIM_ADMIN)
    monkeypatch.setenv("LOST_RESPONSE_DELAY_SECONDS", "0")  # commit still precedes the drop
    with TestClient(create_app(tmp_path / "custodian.db")) as client:
        yield client


@pytest.fixture
def directory(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from simulators.directory import create_app

    monkeypatch.setenv("SIM_ADMIN_TOKEN", SIM_ADMIN)
    with TestClient(create_app(tmp_path / "directory.db")) as client:
        yield client


@pytest.fixture
def broker(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from simulators.broker import create_app

    monkeypatch.setenv("SIM_ADMIN_TOKEN", SIM_ADMIN)
    with TestClient(create_app(tmp_path / "broker.db")) as client:
        yield client
