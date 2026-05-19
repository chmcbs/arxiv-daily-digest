"""
Tests scheduled digest cron helpers
"""

from unittest.mock import MagicMock, Mock

from core import cron


def test_list_users_with_digest_selection_returns_distinct_user_ids(monkeypatch):
    cursor = MagicMock()
    cursor.fetchall.return_value = [("user-a",), ("user-b",)]
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    connect = MagicMock()
    connect.return_value.__enter__.return_value = connection
    monkeypatch.setattr(cron.psycopg, "connect", connect)

    assert cron.list_users_with_digest_selection() == ["user-a", "user-b"]


def test_run_daily_digest_for_all_users_skips_users_without_profiles(monkeypatch):
    monkeypatch.setattr(cron, "list_users_with_digest_selection", Mock(return_value=["user-1"]))
    monkeypatch.setattr(cron, "list_digest_selected_profile_ids", Mock(return_value=[]))
    run_pipeline = Mock()
    monkeypatch.setattr(cron, "run_pipeline", run_pipeline)

    payload = cron.run_daily_digest_for_all_users()

    assert payload["users_seen"] == 1
    assert payload["users_skipped"] == 1
    assert payload["users_succeeded"] == 0
    run_pipeline.assert_not_called()


def test_run_daily_digest_for_all_users_runs_pipeline_per_user(monkeypatch):
    monkeypatch.setattr(
        cron,
        "list_users_with_digest_selection",
        Mock(return_value=["user-1", "user-2"]),
    )
    monkeypatch.setattr(
        cron,
        "list_digest_selected_profile_ids",
        Mock(side_effect=[["profile-1"], ["profile-2"]]),
    )
    monkeypatch.setattr(
        cron,
        "run_pipeline",
        Mock(side_effect=[{"run_ids": ["run-1"]}, {"run_ids": ["run-2"]}]),
    )

    payload = cron.run_daily_digest_for_all_users()

    assert payload["users_succeeded"] == 2
    assert payload["results"][0]["run_ids"] == ["run-1"]
    assert payload["results"][1]["run_ids"] == ["run-2"]
