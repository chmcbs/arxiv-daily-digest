"""
Scheduled digest generation for all subscribed users
"""

from contextlib import contextmanager

import psycopg

from core.db import get_database_url
from core.logging import configure_logging, get_logger
from core.pipeline import run_pipeline
from core.profiles import list_digest_selected_profile_ids

logger = get_logger(__name__)

LIST_DIGEST_USER_IDS_SQL = """
SELECT DISTINCT user_id
FROM user_profiles
WHERE digest_enabled = TRUE
ORDER BY user_id ASC;
"""


@contextmanager
def _connection_scope(conn=None):
    if conn is not None:
        yield conn
        return

    with psycopg.connect(get_database_url()) as owned_conn:
        yield owned_conn


def list_users_with_digest_selection(conn=None) -> list[str]:
    with _connection_scope(conn) as active_conn:
        with active_conn.cursor() as cur:
            cur.execute(LIST_DIGEST_USER_IDS_SQL)
            rows = cur.fetchall()
    return [row[0] for row in rows]


def run_daily_digest_for_all_users(
    *,
    max_results: int = 150,
    embedding_limit: int = 600,
    conn=None,
) -> dict:
    configure_logging()
    user_ids = list_users_with_digest_selection(conn=conn)
    results: list[dict] = []
    succeeded = 0
    failed = 0
    skipped = 0

    logger.info(
        "Daily digest cron started",
        extra={
            "event": "cron.daily_digest.started",
            "user_count": len(user_ids),
        },
    )

    for user_id in user_ids:
        profile_ids = list_digest_selected_profile_ids(user_id=user_id, conn=conn)
        if not profile_ids:
            skipped += 1
            results.append(
                {
                    "user_id": user_id,
                    "status": "skipped",
                    "profile_ids": [],
                    "error_message": "no digest-selected profiles",
                }
            )
            continue

        try:
            summary = run_pipeline(
                user_id=user_id,
                profile_ids=profile_ids,
                max_results=max_results,
                embedding_limit=embedding_limit,
            )
            succeeded += 1
            results.append(
                {
                    "user_id": user_id,
                    "status": "succeeded",
                    "profile_ids": profile_ids,
                    "run_ids": summary.get("run_ids", []),
                    "error_message": None,
                }
            )
        except Exception as error:
            failed += 1
            message = str(error).strip() or error.__class__.__name__
            logger.exception(
                "Daily digest cron failed for user",
                extra={
                    "event": "cron.daily_digest.user_failed",
                    "user_id": user_id,
                    "profile_ids": profile_ids,
                },
            )
            results.append(
                {
                    "user_id": user_id,
                    "status": "failed",
                    "profile_ids": profile_ids,
                    "error_message": message,
                }
            )

    payload = {
        "users_seen": len(user_ids),
        "users_succeeded": succeeded,
        "users_failed": failed,
        "users_skipped": skipped,
        "results": results,
    }
    logger.info(
        "Daily digest cron finished",
        extra={
            "event": "cron.daily_digest.completed",
            **{key: payload[key] for key in payload if key != "results"},
        },
    )
    return payload


def main() -> None:
    result = run_daily_digest_for_all_users()
    print(result)


if __name__ == "__main__":
    main()
