"""
Service functions for feedback mutation routes
"""

from typing import Callable


def save_feedback_payload(
    request,
    resolve_profile: Callable[[str, str | None], dict],
    save_feedback: Callable[..., str],
    update_preference_embedding: Callable[..., None],
) -> dict:
    profile = resolve_profile(user_id=request.user_id, profile_id=request.profile_id)
    resolved_profile_id = str(profile["profile_id"])
    feedback_id = save_feedback(
        arxiv_id=request.arxiv_id,
        label=request.label,
        user_id=request.user_id,
        profile_id=resolved_profile_id,
    )
    update_preference_embedding(
        user_id=request.user_id,
        profile_id=resolved_profile_id,
    )

    return {
        "feedback_id": feedback_id,
        "user_id": request.user_id,
        "profile_id": resolved_profile_id,
        "arxiv_id": request.arxiv_id,
        "label": request.label,
        "preference_updated": True,
    }


def remove_feedback_payload(
    request,
    resolve_profile: Callable[[str, str | None], dict],
    remove_feedback: Callable[..., bool],
    update_preference_embedding: Callable[..., None],
) -> dict:
    profile = resolve_profile(user_id=request.user_id, profile_id=request.profile_id)
    resolved_profile_id = str(profile["profile_id"])
    removed = remove_feedback(
        arxiv_id=request.arxiv_id,
        user_id=request.user_id,
        profile_id=resolved_profile_id,
    )
    if removed:
        update_preference_embedding(
            user_id=request.user_id,
            profile_id=resolved_profile_id,
        )

    return {
        "user_id": request.user_id,
        "profile_id": resolved_profile_id,
        "arxiv_id": request.arxiv_id,
        "removed": removed,
        "preference_updated": removed,
    }
