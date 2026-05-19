"""
Passwordless authentication primitives for onboarding
"""

import hashlib
import secrets
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import psycopg

from core.db import get_database_url

MAGIC_LINK_TTL_MINUTES = 30
SESSION_TTL_DAYS = 30

DELETE_EXPIRED_TOKENS_SQL = """
DELETE FROM magic_link_tokens
WHERE expires_at < NOW()
   OR consumed_at IS NOT NULL;
"""

INSERT_MAGIC_TOKEN_SQL = """
INSERT INTO magic_link_tokens (
    token_hash,
    user_id,
    email,
    expires_at
)
VALUES (%s, %s, %s, %s);
"""

CONSUME_MAGIC_TOKEN_SQL = """
UPDATE magic_link_tokens
SET consumed_at = NOW()
WHERE token_hash = %s
  AND consumed_at IS NULL
  AND expires_at > NOW()
RETURNING user_id, email;
"""

DELETE_EXPIRED_SESSIONS_SQL = """
DELETE FROM auth_sessions
WHERE expires_at < NOW();
"""

DELETE_USER_SESSIONS_SQL = """
DELETE FROM auth_sessions
WHERE user_id = %s;
"""

INSERT_SESSION_SQL = """
INSERT INTO auth_sessions (
    session_id,
    user_id,
    email,
    expires_at
)
VALUES (%s, %s, %s, %s);
"""

GET_SESSION_SQL = """
SELECT user_id, email
FROM auth_sessions
WHERE session_id = %s
  AND expires_at > NOW();
"""


@contextmanager
def _connection_scope(conn=None):
    if conn is not None:
        yield conn
        return

    with psycopg.connect(get_database_url()) as owned_conn:
        yield owned_conn


def _normalize_email(email: str) -> str:
    value = email.strip().lower()
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        raise ValueError("email must be valid")
    return value


def _user_id_from_email(email: str) -> str:
    return _normalize_email(email)


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_magic_link(email: str, conn=None) -> tuple[str, str]:
    normalized_email = _normalize_email(email)
    user_id = _user_id_from_email(normalized_email)
    raw_token = secrets.token_urlsafe(32)
    token_hash = _token_hash(raw_token)
    expires_at = datetime.now(UTC) + timedelta(minutes=MAGIC_LINK_TTL_MINUTES)

    with _connection_scope(conn) as active_conn:
        with active_conn.cursor() as cur:
            cur.execute(DELETE_EXPIRED_TOKENS_SQL)
            cur.execute(
                INSERT_MAGIC_TOKEN_SQL,
                (token_hash, user_id, normalized_email, expires_at),
            )

    return raw_token, user_id


def verify_magic_link(token: str, conn=None) -> tuple[str, str, str]:
    token_hash = _token_hash(token)
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=SESSION_TTL_DAYS)

    with _connection_scope(conn) as active_conn:
        with active_conn.cursor() as cur:
            cur.execute(CONSUME_MAGIC_TOKEN_SQL, (token_hash,))
            row = cur.fetchone()
            if row is None:
                raise ValueError("magic link is invalid or expired")
            user_id = row[0]
            email = row[1]
            cur.execute(DELETE_EXPIRED_SESSIONS_SQL)
            cur.execute(DELETE_USER_SESSIONS_SQL, (user_id,))
            cur.execute(INSERT_SESSION_SQL, (session_id, user_id, email, expires_at))

    return session_id, user_id, email


def get_session_user(session_id: str, conn=None) -> tuple[str, str] | None:
    if not session_id:
        return None

    with _connection_scope(conn) as active_conn:
        with active_conn.cursor() as cur:
            cur.execute(GET_SESSION_SQL, (session_id,))
            row = cur.fetchone()

    if row is None:
        return None
    return row[0], row[1]
