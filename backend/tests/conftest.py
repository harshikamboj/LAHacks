"""Shared fixtures. Simulator tests run in-process with a fresh SQLite file per test (no MongoDB needed)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SIM_ADMIN_TOKEN", "test-admin-token")
ADMIN = {"X-Sim-Admin": os.environ["SIM_ADMIN_TOKEN"]}


@pytest.fixture
def admin_headers() -> dict:
    return dict(ADMIN)


@pytest.fixture
def custodian(tmp_path, monkeypatch):
    monkeypatch.setenv("LOST_RESPONSE_DELAY_SECONDS", "0")  # keep tests fast; commit still precedes the drop
    from simulators.custodian import create_app

    with TestClient(create_app(tmp_path / "custodian.db")) as client:
        yield client


@pytest.fixture
def directory(tmp_path):
    from simulators.directory import create_app

    with TestClient(create_app(tmp_path / "directory.db")) as client:
        yield client


@pytest.fixture
def broker(tmp_path):
    from simulators.broker import create_app

    with TestClient(create_app(tmp_path / "broker.db")) as client:
        yield client
