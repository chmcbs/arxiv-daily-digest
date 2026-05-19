"""
Tests passwordless authentication helpers
"""

from unittest.mock import MagicMock

import pytest

from core import auth


def _mock_connection_with_cursor(cursor):
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    connect = MagicMock()
    connect.return_value.__enter__.return_value = connection
    return connect


def test_create_magic_link_inserts_normalized_email(monkeypatch):
    monkeypatch.setattr(auth.secrets, "token_urlsafe", lambda _: "token-value")
    cursor = MagicMock()
    monkeypatch.setattr(auth.psycopg, "connect", _mock_connection_with_cursor(cursor))

    token, user_id = auth.create_magic_link("  User@Example.com ")

    assert token == "token-value"
    assert user_id == "user@example.com"
    insert_params = cursor.execute.call_args_list[1].args[1]
    assert insert_params[1] == "user@example.com"
    assert insert_params[2] == "user@example.com"


def test_verify_magic_link_rejects_missing_token(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    monkeypatch.setattr(auth.psycopg, "connect", _mock_connection_with_cursor(cursor))

    with pytest.raises(ValueError, match="invalid or expired"):
        auth.verify_magic_link("bad-token")


def test_verify_magic_link_rotates_user_sessions(monkeypatch):
    monkeypatch.setattr(auth.secrets, "token_urlsafe", lambda _: "session-123")
    cursor = MagicMock()
    cursor.fetchone.return_value = ("user@example.com", "user@example.com")
    monkeypatch.setattr(auth.psycopg, "connect", _mock_connection_with_cursor(cursor))

    session_id, user_id, email = auth.verify_magic_link("good-token")

    assert session_id == "session-123"
    assert user_id == "user@example.com"
    delete_user_sessions_sql = cursor.execute.call_args_list[2].args[0]
    delete_user_sessions_params = cursor.execute.call_args_list[2].args[1]
    assert "DELETE FROM auth_sessions" in delete_user_sessions_sql
    assert "user_id" in delete_user_sessions_sql
    assert delete_user_sessions_params == ("user@example.com",)
    insert_params = cursor.execute.call_args_list[3].args[1]
    assert insert_params[0] == "session-123"
    assert email == "user@example.com"


def test_get_session_user_returns_tuple(monkeypatch):
    cursor = MagicMock()
    cursor.fetchone.return_value = ("u@example.com", "u@example.com")
    monkeypatch.setattr(auth.psycopg, "connect", _mock_connection_with_cursor(cursor))

    assert auth.get_session_user("session") == ("u@example.com", "u@example.com")
