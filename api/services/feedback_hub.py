"""
Service functions for the feedback hub endpoint
"""

from typing import Callable

from api.queries.feedback_hub import UserPaperHistoryRow
from core.arxiv_text import format_arxiv_display_text


def _to_paper_payload(row: UserPaperHistoryRow) -> dict:
    return {
        "arxiv_id": row.arxiv_id,
        "title": format_arxiv_display_text(row.title),
        "pdf_url": row.pdf_url,
        "profile_id": row.profile_id,
        "profile_name": row.profile_name,
        "category": row.category,
        "generated_at": row.generated_at,
        "final_score": row.final_score,
        "rank": row.rank,
        "published_at": row.published_at,
        "authors": list(row.authors or []),
    }


def get_feedback_hub_payload(
    user_id: str,
    fetch_user_paper_history: Callable[..., list[UserPaperHistoryRow]],
    profile_id: str | None = None,
) -> dict:
    rows = fetch_user_paper_history(user_id, profile_id=profile_id)

    seen: list[dict] = []
    liked: list[dict] = []
    disliked: list[dict] = []

    for row in rows:
        paper = _to_paper_payload(row)
        if row.feedback_label == "like":
            liked.append(paper)
        elif row.feedback_label == "dislike":
            disliked.append(paper)
        else:
            seen.append(paper)

    return {
        "user_id": user_id,
        "seen": seen,
        "liked": liked,
        "disliked": disliked,
    }
