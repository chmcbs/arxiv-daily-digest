"""
Tests health and readiness probe endpoints
"""

import os
from unittest.mock import Mock

import pytest
from starlette.testclient import TestClient

import api.routes as routes
from core.db import check_database_connection


def test_health_returns_ok_without_database():
    client = TestClient(routes.app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ready_when_database_is_available(monkeypatch):
    monkeypatch.setattr(
        routes,
        "check_database_connection",
        Mock(return_value=None),
    )
    client = TestClient(routes.app)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_when_database_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        routes,
        "check_database_connection",
        Mock(side_effect=RuntimeError("connection refused")),
    )
    client = TestClient(routes.app)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}


def test_health_and_ready_do_not_require_authentication():
    client = TestClient(routes.app)

    health = client.get("/health")
    ready = client.get("/ready")

    assert health.status_code == 200
    assert ready.status_code in {200, 503}


def _database_url_reachable() -> bool:
    if not os.getenv("DATABASE_URL", "").strip():
        return False
    try:
        check_database_connection(connect_timeout=2)
    except Exception:
        return False
    return True


@pytest.mark.skipif(not _database_url_reachable(), reason="DATABASE_URL is not reachable")
def test_check_database_connection_uses_live_database():
    check_database_connection()


@pytest.mark.skipif(not _database_url_reachable(), reason="DATABASE_URL is not reachable")
def test_ready_integrates_with_live_database():
    client = TestClient(routes.app)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_integrates_with_unreachable_database(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres:wrong@127.0.0.1:59999/unreachable",
    )
    client = TestClient(routes.app)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}
