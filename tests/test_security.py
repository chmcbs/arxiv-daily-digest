"""
Security-focused route tests for session auth and profile ownership
"""

from unittest.mock import Mock

import pytest
from starlette.testclient import TestClient

import api.routes as routes
from core.rate_limit import reset_rate_limits
from core.security import resolve_safe_redirect_path


@pytest.fixture
def unauthenticated_client(monkeypatch):
    monkeypatch.setattr(
        routes,
        "require_authenticated_user_id",
        Mock(
            side_effect=routes.HTTPException(
                status_code=401, detail="Sign in required"
            )
        ),
    )
    return TestClient(routes.app)


@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("GET", "/profiles", None),
        ("GET", "/daily-picks", None),
        ("GET", "/daily-picks/debug?profile_id=profile-1", None),
        ("GET", "/api/feedback/hub", None),
        ("GET", "/metrics", None),
        ("POST", "/profiles", {"category": "cs.AI", "interest_sentence": "test"}),
        (
            "POST",
            "/daily-picks/generate",
            {"profile_ids": ["profile-1"]},
        ),
        (
            "POST",
            "/api/feedback",
            {
                "profile_id": "profile-1",
                "arxiv_id": "2601.00001",
                "label": "like",
            },
        ),
    ],
)
def test_product_routes_require_authentication(
    unauthenticated_client, method, path, json_body
):
    response = unauthenticated_client.request(method, path, json=json_body)
    assert response.status_code == 401
    assert response.json()["detail"] == "Sign in required"


def test_profiles_list_ignores_spoofed_user_id_query_param(monkeypatch):
    list_mock = Mock(return_value={"user_id": "user@example.com", "profiles": []})
    monkeypatch.setattr(routes, "list_profiles_payload", list_mock)

    client = TestClient(routes.app)
    response = client.get("/profiles?user_id=attacker@example.com")

    assert response.status_code == 200
    list_mock.assert_called_once_with(user_id="default")


def test_magic_link_redirect_rejects_unlisted_paths(monkeypatch):
    monkeypatch.setattr(
        routes,
        "verify_magic_link_payload",
        Mock(
            return_value={
                "verified": True,
                "session_id": "session-123",
                "user_id": "x@example.com",
                "email": "x@example.com",
            }
        ),
    )
    client = TestClient(routes.app)
    response = client.get(
        "/auth/magic-link/verify?token=abc&next=https://evil.example",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/preferences"


def test_magic_link_redirect_allows_known_app_paths(monkeypatch):
    monkeypatch.setattr(
        routes,
        "verify_magic_link_payload",
        Mock(
            return_value={
                "verified": True,
                "session_id": "session-123",
                "user_id": "x@example.com",
                "email": "x@example.com",
            }
        ),
    )
    client = TestClient(routes.app)
    response = client.get(
        "/auth/magic-link/verify?token=abc&next=/digest",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/digest"
    assert "csrf_token=" in response.headers["set-cookie"]


def test_validate_route_hidden_when_debug_disabled(monkeypatch):
    monkeypatch.delenv("ALLOW_DEBUG_FEATURES", raising=False)
    monkeypatch.delenv("ALLOW_DEBUG_DIGEST_DATA_RESET", raising=False)
    client = TestClient(routes.app)

    response = client.get("/validate")

    assert response.status_code == 404


def test_mutating_route_requires_csrf_when_enabled(monkeypatch):
    monkeypatch.delenv("DISABLE_CSRF", raising=False)
    client = TestClient(routes.app)
    client.cookies.set("session_id", "session-123")

    response = client.post(
        "/profiles",
        json={"category": "cs.AI", "interest_sentence": "test"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF validation failed"


def test_mutating_route_accepts_matching_csrf_token(monkeypatch):
    monkeypatch.delenv("DISABLE_CSRF", raising=False)
    monkeypatch.setattr(
        routes,
        "create_profile_payload",
        Mock(
            return_value={
                "profile": {
                    "profile_id": "profile-1",
                    "user_id": "default",
                    "profile_slot": 1,
                    "profile_name": "Profile",
                    "category": "cs.AI",
                    "interest_sentence": "test",
                    "digest_enabled": False,
                    "keywords": [],
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "preference_updated_at": None,
                }
            }
        ),
    )
    client = TestClient(routes.app)
    client.cookies.set("session_id", "session-123")
    client.cookies.set("csrf_token", "csrf-abc")

    response = client.post(
        "/profiles",
        json={"category": "cs.AI", "interest_sentence": "test"},
        headers={"X-CSRF-Token": "csrf-abc"},
    )

    assert response.status_code == 200


def test_magic_link_request_is_rate_limited(monkeypatch):
    monkeypatch.delenv("DISABLE_RATE_LIMIT", raising=False)
    reset_rate_limits()
    monkeypatch.setenv("MAGIC_LINK_REQUEST_LIMIT_PER_EMAIL", "1")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "3600")
    monkeypatch.setattr(
        "api.dependencies.create_magic_link",
        lambda email, conn=None: ("token-value", email.strip().lower()),
    )
    client = TestClient(routes.app)

    first = client.post("/auth/magic-link/request", json={"email": "user@example.com"})
    second = client.post("/auth/magic-link/request", json={"email": "user@example.com"})

    assert first.status_code == 200
    assert second.status_code == 429


def test_internal_cron_requires_bearer_token(monkeypatch):
    monkeypatch.setattr(
        routes,
        "run_daily_digest_cron_payload",
        Mock(return_value={"users_seen": 0, "users_succeeded": 0, "users_failed": 0, "users_skipped": 0, "results": []}),
    )
    client = TestClient(routes.app)

    denied = client.post("/internal/cron/daily-digest")
    allowed = client.post(
        "/internal/cron/daily-digest",
        headers={"Authorization": "Bearer test-cron-token"},
    )

    assert denied.status_code == 401
    assert allowed.status_code == 200


def test_security_headers_are_present(monkeypatch):
    monkeypatch.setattr(
        routes,
        "list_profiles_payload",
        Mock(return_value={"user_id": "default", "profiles": []}),
    )
    client = TestClient(routes.app)
    response = client.get("/profiles")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


@pytest.mark.parametrize(
    "next_path,expected",
    [
        ("/digest", "/digest"),
        ("//evil.example", "/preferences"),
        ("/admin", "/preferences"),
        ("/validate", "/validate"),
    ],
)
def test_resolve_safe_redirect_path(next_path, expected, monkeypatch):
    monkeypatch.setenv("ALLOW_DEBUG_FEATURES", "1")
    assert resolve_safe_redirect_path(next_path) == expected
