"""
Service functions for magic-link authentication routes
"""

from typing import Callable


def request_magic_link_payload(
    request,
    create_magic_link: Callable[[str], tuple[str, str]],
    app_base_url: str,
    *,
    expose_magic_link: bool,
) -> dict:
    token, _ = create_magic_link(request.email)
    payload = {"sent": True, "magic_link": None}
    if expose_magic_link:
        payload["magic_link"] = (
            f"{app_base_url}/auth/magic-link/verify?token={token}"
        )
    return payload


def verify_magic_link_payload(
    token: str,
    verify_magic_link: Callable[[str], tuple[str, str, str]],
) -> dict:
    session_id, user_id, email = verify_magic_link(token)
    return {
        "verified": True,
        "session_id": session_id,
        "user_id": user_id,
        "email": email,
    }
