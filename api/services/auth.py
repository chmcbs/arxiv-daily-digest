"""
Service functions for magic-link authentication routes
"""

from typing import Callable


def request_magic_link_payload(
    request,
    create_magic_link: Callable[[str], tuple[str, str]],
    app_base_url: str,
) -> dict:
    token, _ = create_magic_link(request.email)
    return {
        "sent": True,
        "magic_link": f"{app_base_url}/auth/magic-link/verify?token={token}",
    }


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
