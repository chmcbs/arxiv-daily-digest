"""
Service functions for admin-only test digest generation and preview
"""

from typing import Callable

from api.mappers import to_debug_pick, to_public_pick
from api.services.errors import BadRequestError, InternalServerError
from core.digest_email import deliver_digest_email_for_user
from core.security import is_debug_admin_email


def get_test_generation_payload(
    user_id: str,
    profile_id: str | None,
    resolve_profile: Callable[[str, str | None], dict],
    list_digest_selected_profile_ids: Callable[[str], list[str]],
    fetch_latest_picks: Callable[[str], list],
    anchored_run_ids: list[str] | None = None,
) -> dict:
    if profile_id is not None:
        target_profile_ids = [profile_id]
    else:
        target_profile_ids = list_digest_selected_profile_ids(user_id=user_id)
        if not target_profile_ids:
            raise BadRequestError(
                "at least one profile must be selected for digest generation"
            )

    sections = []
    has_anchor_runs = bool(anchored_run_ids)
    generated_at = None
    for target_profile_id in target_profile_ids:
        profile = resolve_profile(user_id=user_id, profile_id=target_profile_id)
        resolved_profile_id = str(profile["profile_id"])
        rows = fetch_latest_picks(resolved_profile_id)
        if rows:
            section_generated_at = rows[0].generated_at
            if generated_at is None or section_generated_at > generated_at:
                generated_at = section_generated_at
        section_needs_generation = not rows and not has_anchor_runs
        section_payload = {
            "profile_id": resolved_profile_id,
            "profile_slot": profile["profile_slot"],
            "category": profile["category"],
            "interest_sentence": profile["interest_sentence"],
            "needs_generation": section_needs_generation,
            "picks": [to_public_pick(row) for row in rows],
        }
        if "profile_name" in profile:
            section_payload["profile_name"] = profile["profile_name"]
        sections.append(section_payload)

    primary_section = sections[0]

    return {
        "user_id": user_id,
        "profile_id": primary_section["profile_id"],
        "needs_generation": any(section["needs_generation"] for section in sections),
        "generated_at": generated_at,
        "picks": primary_section["picks"],
        "sections": sections,
    }


def get_test_generation_debug_payload(
    user_id: str,
    profile_id: str | None,
    resolve_profile: Callable[[str, str | None], dict],
    fetch_latest_picks: Callable[[str], list],
) -> dict:
    profile = resolve_profile(user_id=user_id, profile_id=profile_id)
    resolved_profile_id = str(profile["profile_id"])
    rows = fetch_latest_picks(resolved_profile_id)

    payload = {
        "user_id": user_id,
        "profile_id": resolved_profile_id,
        "needs_generation": not rows,
        "run_id": None,
        "category": None,
        "generated_at": None,
        "picks": [to_debug_pick(row) for row in rows],
    }

    if rows:
        payload["run_id"] = rows[0].run_id
        payload["category"] = rows[0].category
        payload["generated_at"] = rows[0].generated_at

    return payload


def run_test_generation_payload(
    request,
    user_id: str,
    admin_email: str,
    resolve_profile: Callable[[str, str | None], dict],
    run_pipeline: Callable[..., dict],
    get_test_generation_payload: Callable[[str, str | None], dict],
) -> dict:
    if not is_debug_admin_email(admin_email):
        raise InternalServerError("test generation email is restricted to admin emails")

    target_profile_ids = list(dict.fromkeys(request.profile_ids))
    for target_profile_id in target_profile_ids:
        resolve_profile(user_id=user_id, profile_id=target_profile_id)

    summary = run_pipeline(
        user_id=user_id,
        profile_ids=target_profile_ids,
        max_results=request.max_results,
        embedding_limit=request.embedding_limit,
    )
    picks_payload = get_test_generation_payload(
        user_id=user_id,
        profile_id=None,
        run_ids=summary["run_ids"],
    )

    recommendations_by_run_profile = summary.get("recommendations_by_run_profile", {})
    recommendation_status_by_run_profile = summary.get(
        "recommendation_status_by_run_profile", {}
    )
    generation_runs = []
    has_failures = False
    has_successes = False
    for run_id in summary["run_ids"]:
        profile_statuses = []
        status_map = recommendation_status_by_run_profile.get(run_id, {})
        recommendation_map = recommendations_by_run_profile.get(run_id, {})
        for target_profile_id in target_profile_ids:
            status_entry = status_map.get(target_profile_id)
            if status_entry is None:
                recommendation_count = len(
                    recommendation_map.get(target_profile_id, [])
                )
                status_entry = {
                    "status": "succeeded",
                    "recommendation_count": recommendation_count,
                    "error_message": None,
                }

            status = status_entry["status"]
            if status == "failed":
                has_failures = True
            if status == "succeeded":
                has_successes = True

            profile_statuses.append(
                {
                    "profile_id": target_profile_id,
                    "status": status,
                    "recommendation_count": status_entry.get("recommendation_count", 0),
                    "error_message": status_entry.get("error_message"),
                }
            )

        generation_runs.append(
            {
                "run_id": run_id,
                "profile_statuses": profile_statuses,
            }
        )

    if has_failures and not has_successes:
        raise InternalServerError(
            "NO_SUCCESSFUL_GENERATION: generation failed for all run/profile targets"
        )

    email_result = None
    if summary["run_ids"] and not picks_payload["needs_generation"]:
        email_result = deliver_digest_email_for_user(
            user_id=user_id,
            profile_ids=target_profile_ids,
            run_ids=summary["run_ids"],
            to_email=admin_email,
        )

    return {
        "user_id": user_id,
        "primary_profile_id": picks_payload["profile_id"],
        "requested_profile_ids": target_profile_ids,
        "run_ids": summary["run_ids"],
        "embedded_count": summary["embedded_count"],
        "generation_runs": generation_runs,
        "has_failures": has_failures,
        "needs_generation": picks_payload["needs_generation"],
        "picks": picks_payload["picks"],
        "sections": picks_payload["sections"],
        "email_status": email_result["status"] if email_result else None,
        "email_error": email_result["error_message"] if email_result else None,
    }
