"""
Route-level tests for FastAPI HTTP contracts
"""

from unittest.mock import Mock

from starlette.testclient import TestClient

import api.routes as routes


def test_daily_picks_generate_route_returns_200_with_generation_status(monkeypatch):
    monkeypatch.setattr(
        routes,
        "generate_daily_picks_payload",
        Mock(
            return_value={
                "user_id": "default",
                "primary_profile_id": "profile-1",
                "requested_profile_ids": ["profile-1"],
                "run_ids": ["run-123"],
                "embedded_count": 5,
                "generation_runs": [
                    {
                        "run_id": "run-123",
                        "profile_statuses": [
                            {
                                "profile_id": "profile-1",
                                "status": "succeeded",
                                "recommendation_count": 1,
                                "error_message": None,
                            }
                        ],
                    }
                ],
                "has_failures": False,
                "needs_generation": False,
                "picks": [
                    {
                        "rank": 1,
                        "arxiv_id": "2601.00001",
                        "title": "Paper 1",
                        "abstract": "Abstract 1",
                        "pdf_url": "https://arxiv.org/pdf/2601.00001",
                        "final_score": 0.9,
                    }
                ],
                "sections": [
                    {
                        "profile_id": "profile-1",
                        "profile_slot": 1,
                        "category": "cs.AI",
                        "interest_sentence": "Efficient LLM systems",
                        "needs_generation": False,
                        "picks": [
                            {
                                "rank": 1,
                                "arxiv_id": "2601.00001",
                                "title": "Paper 1",
                                "abstract": "Abstract 1",
                                "pdf_url": "https://arxiv.org/pdf/2601.00001",
                                "final_score": 0.9,
                            }
                        ],
                    }
                ],
            }
        ),
    )

    client = TestClient(routes.app)
    response = client.post(
        "/daily-picks/generate",
        json={"user_id": "default", "max_results": 123, "embedding_limit": 456},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["primary_profile_id"] == "profile-1"
    assert payload["has_failures"] is False
    assert payload["generation_runs"][0]["profile_statuses"][0]["status"] == "succeeded"


def test_daily_picks_generate_route_returns_500_for_internal_failure(monkeypatch):
    monkeypatch.setattr(
        routes,
        "generate_daily_picks_payload",
        Mock(
            side_effect=routes.HTTPException(
                status_code=500,
                detail="NO_SUCCESSFUL_GENERATION: generation failed for all run/profile targets",
            )
        ),
    )

    client = TestClient(routes.app)
    response = client.post(
        "/daily-picks/generate",
        json={"user_id": "default", "max_results": 123, "embedding_limit": 456},
    )

    assert response.status_code == 500
    payload = response.json()
    assert "NO_SUCCESSFUL_GENERATION" in payload["detail"]


def test_validate_route_returns_internal_validation_ui():
    client = TestClient(routes.app)
    response = client.get("/validate")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Validation UI" in response.text
    assert "POST /daily-picks/generate" in response.text
    assert "Profile Keywords" in response.text


def test_landing_and_preferences_pages_are_served():
    client = TestClient(routes.app)

    landing = client.get("/")
    prefs = client.get("/preferences")

    assert landing.status_code == 200
    assert "<title>arXiv Assistant</title>" in landing.text
    assert prefs.status_code == 200
    assert "<title>Preferences - arXiv Assistant</title>" in prefs.text


def test_magic_link_request_route_returns_payload(monkeypatch):
    monkeypatch.setattr(
        routes,
        "request_magic_link_payload",
        Mock(
            return_value={
                "sent": True,
                "magic_link": "http://localhost:8000/auth/magic-link/verify?token=t",
            }
        ),
    )
    client = TestClient(routes.app)
    response = client.post("/auth/magic-link/request", json={"email": "x@example.com"})

    assert response.status_code == 200
    assert response.json()["sent"] is True


def test_magic_link_verify_sets_session_cookie_and_redirects(monkeypatch):
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
    response = client.get("/auth/magic-link/verify?token=abc", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/preferences"
    assert "session_id=session-123" in response.headers["set-cookie"]
