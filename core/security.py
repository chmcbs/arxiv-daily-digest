"""
Shared security helpers for redirects, CSRF, and internal service authentication
"""

import secrets

from core.config import is_debug_features_enabled, is_app_https

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"

PUBLIC_MAGIC_LINK_REDIRECTS = frozenset(
    {
        "/",
        "/preferences",
        "/digest",
        "/feedback",
    }
)

DEBUG_MAGIC_LINK_REDIRECTS = frozenset({"/validate"})


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def resolve_safe_redirect_path(next_path: str) -> str:
    normalized = (next_path or "/preferences").strip()
    if not normalized.startswith("/") or normalized.startswith("//"):
        return "/preferences"

    path_only = normalized.split("?", 1)[0].split("#", 1)[0]
    if path_only in PUBLIC_MAGIC_LINK_REDIRECTS:
        return path_only
    if path_only in DEBUG_MAGIC_LINK_REDIRECTS and is_debug_features_enabled():
        return path_only
    return "/preferences"


def is_csrf_enforcement_enabled() -> bool:
    import os

    return os.getenv("DISABLE_CSRF", "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    )


def validate_csrf_token(cookie_token: str | None, header_token: str | None) -> bool:
    if not is_csrf_enforcement_enabled():
        return True
    if not cookie_token or not header_token:
        return False
    return secrets.compare_digest(cookie_token, header_token)


def csrf_cookie_settings() -> dict:
    return {
        "key": CSRF_COOKIE_NAME,
        "httponly": False,
        "samesite": "lax",
        "secure": is_app_https(),
        "max_age": 60 * 60 * 24 * 30,
    }


def get_internal_cron_token() -> str | None:
    import os

    token = os.getenv("INTERNAL_CRON_TOKEN", "").strip()
    return token or None


def verify_internal_cron_token(provided_token: str | None) -> bool:
    expected = get_internal_cron_token()
    if expected is None:
        return False
    if not provided_token:
        return False
    return secrets.compare_digest(provided_token, expected)
