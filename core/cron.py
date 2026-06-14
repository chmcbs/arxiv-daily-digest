"""
Scheduled digest generation for all subscribed users
"""

import json
import os
import time
import uuid
from email.message import EmailMessage
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.db import connection_scope
from core.logging import configure_logging, get_logger
from core.config import (
    get_debug_admin_emails,
    get_embedding_limit,
    get_email_from,
    get_ingestion_max_results,
    get_llm_failure_alert_threshold,
    get_monitor_alert_cooldown_s,
    get_monitor_cron_runtime_warning_s,
    get_monitor_state_path,
    get_monitor_zero_output_streak_threshold,
    get_product_name,
    is_email_delivery_configured,
    is_monitor_daily_summary_enabled,
)
from core.pipeline import run_recommendations_for_profiles, run_shared_pipeline_steps
from core.descriptions import run_description_batch_for_recommendations
from core.digest_email import deliver_digest_email_for_user
from core.email import deliver_email_message
from core.profiles import list_digest_categories, list_digest_selected_profile_ids

logger = get_logger(__name__)

########################################
################ SQL ###################
########################################

LIST_DIGEST_USER_IDS_SQL = """
SELECT DISTINCT up.user_id
FROM user_profiles up
LEFT JOIN user_email_settings ues ON ues.user_id = up.user_id
WHERE up.digest_enabled = TRUE
  AND COALESCE(ues.digest_subscribed, TRUE) = TRUE
ORDER BY up.user_id ASC;
"""


########################################
######### MONITORING STATE #############
########################################

def _monitor_log_path_label() -> str:
    return os.getenv("LOG_PATH", "stdout")


def _load_monitor_state() -> dict[str, Any]:
    path = Path(get_monitor_state_path())
    if not path.is_file():
        return {
            "alert_last_sent_at": {},
            "zero_output_streak": 0,
            "last_daily_summary_date": "",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "alert_last_sent_at": {},
            "zero_output_streak": 0,
            "last_daily_summary_date": "",
        }
    alert_map = payload.get("alert_last_sent_at")
    if not isinstance(alert_map, dict):
        alert_map = {}
    return {
        "alert_last_sent_at": {
            str(key): float(value)
            for key, value in alert_map.items()
            if isinstance(key, str)
            and isinstance(value, (int, float))
            and float(value) > 0
        },
        "zero_output_streak": int(payload.get("zero_output_streak") or 0),
        "last_daily_summary_date": str(payload.get("last_daily_summary_date") or ""),
    }


def _save_monitor_state(state: dict[str, Any]) -> None:
    path = Path(get_monitor_state_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")


def _is_alert_on_cooldown(
    *,
    state: dict[str, Any],
    alert_key: str,
    now_ts: float,
) -> bool:
    alert_last_sent_at = state.setdefault("alert_last_sent_at", {})
    if not isinstance(alert_last_sent_at, dict):
        alert_last_sent_at = {}
        state["alert_last_sent_at"] = alert_last_sent_at
    cooldown_s = get_monitor_alert_cooldown_s()
    last_sent_at = float(alert_last_sent_at.get(alert_key) or 0.0)
    return (now_ts - last_sent_at) < cooldown_s


def _mark_alert_sent(
    *,
    state: dict[str, Any],
    alert_key: str,
    now_ts: float,
) -> None:
    alert_last_sent_at = state.setdefault("alert_last_sent_at", {})
    if not isinstance(alert_last_sent_at, dict):
        alert_last_sent_at = {}
        state["alert_last_sent_at"] = alert_last_sent_at
    alert_last_sent_at[alert_key] = now_ts


def _save_monitor_state_safely(state: dict[str, Any]) -> None:
    try:
        _save_monitor_state(state)
    except Exception:
        logger.exception(
            "Failed to persist monitor state",
            extra={"event": "cron.monitor_state.save_failed"},
        )


########################################
######### ORCHESTRATION ################
########################################

def list_users_with_digest_selection(conn=None) -> list[str]:
    with connection_scope(conn) as active_conn:
        with active_conn.cursor() as cur:
            cur.execute(LIST_DIGEST_USER_IDS_SQL)
            rows = cur.fetchall()
    return [row[0] for row in rows]


def run_daily_digest_for_all_users(
    *,
    max_results: int | None = None,
    embedding_limit: int | None = None,
    conn=None,
) -> dict:
    configure_logging()
    cron_run_id = str(uuid.uuid4())
    started_at = datetime.now(UTC)
    started_monotonic = time.monotonic()
    monitor_state = _load_monitor_state()
    resolved_max_results = (
        get_ingestion_max_results() if max_results is None else max_results
    )
    resolved_embedding_limit = (
        get_embedding_limit() if embedding_limit is None else embedding_limit
    )
    user_ids = list_users_with_digest_selection(conn=conn)
    results: list[dict] = []
    succeeded = 0
    failed = 0
    skipped = 0
    users_to_process: list[tuple[str, list[str]]] = []

    logger.info(
        "Daily digest cron started",
        extra={
            "event": "cron.daily_digest.started",
            "cron_run_id": cron_run_id,
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
        users_to_process.append((user_id, profile_ids))

    shared_run_ids: list[str] = []
    if users_to_process:
        try:
            ingest_categories = list_digest_categories(conn=conn)
            shared = run_shared_pipeline_steps(
                categories=ingest_categories,
                max_results=resolved_max_results,
                embedding_limit=resolved_embedding_limit,
            )
            shared_run_ids = shared["run_ids"]
        except Exception as error:
            message = str(error).strip() or error.__class__.__name__
            logger.exception(
                "Daily digest cron failed during shared pipeline steps",
                extra={
                    "event": "cron.daily_digest.shared_failed",
                    "cron_run_id": cron_run_id,
                },
            )
            _notify_admins_of_step_failure(
                monitor_state=monitor_state,
                alert_key="failure:shared_pipeline",
                cron_run_id=cron_run_id,
                step_name="shared_pipeline",
                message=message,
                run_ids=[],
            )
            for user_id, profile_ids in users_to_process:
                failed += 1
                results.append(
                    {
                        "user_id": user_id,
                        "status": "failed",
                        "profile_ids": profile_ids,
                        "run_ids": [],
                        "error_message": message,
                    }
                )
            payload = {
                "cron_run_id": cron_run_id,
                "started_at": started_at.isoformat(),
                "duration_s": int(time.monotonic() - started_monotonic),
                "users_seen": len(user_ids),
                "users_succeeded": succeeded,
                "users_failed": failed,
                "users_skipped": skipped,
                "description_batch": {},
                "results": results,
            }
            logger.info(
                "Daily digest cron finished",
                extra={
                    "event": "cron.daily_digest.completed",
                    "cron_run_id": cron_run_id,
                    **{key: payload[key] for key in payload if key != "results"},
                },
            )
            _save_monitor_state_safely(monitor_state)
            return payload

    for user_id, profile_ids in users_to_process:
        try:
            run_recommendations_for_profiles(
                user_id=user_id,
                profile_ids=profile_ids,
                run_ids=shared_run_ids,
            )
            succeeded += 1
            results.append(
                {
                    "user_id": user_id,
                    "status": "succeeded",
                    "profile_ids": profile_ids,
                    "run_ids": shared_run_ids,
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
                    "cron_run_id": cron_run_id,
                    "user_id": user_id,
                    "profile_ids": profile_ids,
                },
            )
            _notify_admins_of_step_failure(
                monitor_state=monitor_state,
                alert_key="failure:recommendations",
                cron_run_id=cron_run_id,
                step_name="recommendations",
                message=f"user={user_id} error={message}",
                run_ids=shared_run_ids,
            )
            results.append(
                {
                    "user_id": user_id,
                    "status": "failed",
                    "profile_ids": profile_ids,
                    "run_ids": shared_run_ids,
                    "error_message": message,
                }
            )

    description_batch = {}
    if shared_run_ids and users_to_process:
        # Continue digest delivery even when blurb generation degrades so core service remains available
        llm_error: Exception | None = None
        for attempt in range(3):
            try:
                description_batch = run_description_batch_for_recommendations(
                    run_ids=shared_run_ids,
                    conn=conn,
                )
                llm_error = None
                break
            except Exception as error:
                llm_error = error
                logger.warning(
                    "LLM blurb batch attempt failed",
                    extra={
                        "event": "llm.batch.retry",
                        "cron_run_id": cron_run_id,
                        "run_ids": shared_run_ids,
                        "attempt": attempt + 1,
                        "max_attempts": 3,
                        "error_type": error.__class__.__name__,
                    },
                )
        if llm_error is not None:
            logger.error(
                "Daily digest blurb batch failed",
                extra={
                    "event": "llm.batch.failed",
                    "cron_run_id": cron_run_id,
                    "run_ids": shared_run_ids,
                    "error_type": llm_error.__class__.__name__,
                },
            )
            _notify_admins_of_blurb_failure(
                monitor_state=monitor_state,
                run_ids=shared_run_ids,
                error=llm_error,
                cron_run_id=cron_run_id,
            )
        else:
            attempted = int(description_batch.get("attempted") or 0)
            non_success_count = (
                int(description_batch.get("failed") or 0)
                + int(description_batch.get("skipped_timeout") or 0)
                + int(description_batch.get("skipped_validation") or 0)
            )
            threshold = get_llm_failure_alert_threshold()
            # Alert only when non-success rate crosses threshold to avoid noise from isolated failures
            if attempted > 0 and (non_success_count / attempted) > threshold:
                logger.warning(
                    "LLM blurb batch exceeded failure threshold",
                    extra={
                        "event": "llm.batch.threshold_exceeded",
                        "cron_run_id": cron_run_id,
                        "run_ids": shared_run_ids,
                        "attempted": attempted,
                        "non_success_count": non_success_count,
                        "threshold": threshold,
                    },
                )
                _notify_admins_of_blurb_degradation(
                    monitor_state=monitor_state,
                    run_ids=shared_run_ids,
                    attempted=attempted,
                    non_success_count=non_success_count,
                    threshold=threshold,
                    cron_run_id=cron_run_id,
                )

    if shared_run_ids:
        for entry in results:
            if entry.get("status") != "succeeded":
                continue
            email_result = _deliver_digest_email_with_retries(
                monitor_state=monitor_state,
                cron_run_id=cron_run_id,
                user_id=entry["user_id"],
                profile_ids=entry["profile_ids"],
                run_ids=shared_run_ids,
                conn=conn,
            )
            entry["email_status"] = email_result["status"]
            entry["email_error"] = email_result["error_message"]

    duration_s = int(time.monotonic() - started_monotonic)
    runtime_warning_threshold_s = get_monitor_cron_runtime_warning_s()
    if duration_s > runtime_warning_threshold_s:
        _notify_admins_of_runtime_warning(
            monitor_state=monitor_state,
            cron_run_id=cron_run_id,
            duration_s=duration_s,
            threshold_s=runtime_warning_threshold_s,
            run_ids=shared_run_ids,
        )

    sent_count = sum(1 for row in results if row.get("email_status") == "sent")
    processed_count = len(users_to_process)
    had_zero_output = processed_count > 0 and sent_count == 0
    if had_zero_output:
        monitor_state["zero_output_streak"] = int(
            monitor_state.get("zero_output_streak") or 0
        ) + 1
    else:
        monitor_state["zero_output_streak"] = 0

    streak = int(monitor_state.get("zero_output_streak") or 0)
    zero_streak_threshold = get_monitor_zero_output_streak_threshold()
    if streak >= zero_streak_threshold:
        _notify_admins_of_zero_output_streak(
            monitor_state=monitor_state,
            cron_run_id=cron_run_id,
            streak=streak,
            threshold=zero_streak_threshold,
            run_ids=shared_run_ids,
        )

    payload = {
        "cron_run_id": cron_run_id,
        "started_at": started_at.isoformat(),
        "duration_s": duration_s,
        "users_seen": len(user_ids),
        "users_succeeded": succeeded,
        "users_failed": failed,
        "users_skipped": skipped,
        "description_batch": description_batch,
        "results": results,
    }
    logger.info(
        "Daily digest cron finished",
        extra={
            "event": "cron.daily_digest.completed",
            "cron_run_id": cron_run_id,
            **{key: payload[key] for key in payload if key != "results"},
        },
    )
    _maybe_send_daily_summary(
        monitor_state=monitor_state,
        payload=payload,
        run_ids=shared_run_ids,
    )
    _save_monitor_state_safely(monitor_state)
    return payload


########################################
############ ADMIN ALERTS ##############
########################################

def _send_admin_alert_email(
    *,
    subject: str,
    body: str,
    event: str,
    run_ids: list[str],
    cron_run_id: str,
) -> bool:
    admin_emails = sorted(get_debug_admin_emails())
    if not admin_emails:
        logger.warning(
            "Admin alert skipped because no recipients are configured",
            extra={
                "event": f"{event}.skipped_no_recipients",
                "cron_run_id": cron_run_id,
                "run_ids": run_ids,
            },
        )
        return False
    if not is_email_delivery_configured():
        logger.warning(
            "Admin alert skipped because SMTP is not configured",
            extra={
                "event": f"{event}.skipped_unconfigured",
                "cron_run_id": cron_run_id,
                "run_ids": run_ids,
            },
        )
        return False

    sent_count = 0
    for admin_email in admin_emails:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = get_email_from()
        message["To"] = admin_email
        message.set_content(body)
        try:
            deliver_email_message(message)
            sent_count += 1
        except Exception:
            logger.exception(
                "Failed to send admin alert",
                extra={
                    "event": f"{event}.failed",
                    "cron_run_id": cron_run_id,
                    "to_email": admin_email,
                    "run_ids": run_ids,
                },
            )
    return sent_count > 0


def _send_throttled_alert(
    *,
    monitor_state: dict[str, Any],
    alert_key: str,
    subject: str,
    body: str,
    event: str,
    run_ids: list[str],
    cron_run_id: str,
) -> None:
    now_ts = time.time()
    if _is_alert_on_cooldown(
        state=monitor_state,
        alert_key=alert_key,
        now_ts=now_ts,
    ):
        logger.info(
            "Admin alert suppressed by cooldown",
            extra={
                "event": f"{event}.suppressed",
                "cron_run_id": cron_run_id,
                "alert_key": alert_key,
                "run_ids": run_ids,
            },
        )
        return
    sent = _send_admin_alert_email(
        subject=subject,
        body=body,
        event=event,
        run_ids=run_ids,
        cron_run_id=cron_run_id,
    )
    if sent:
        _mark_alert_sent(
            state=monitor_state,
            alert_key=alert_key,
            now_ts=now_ts,
        )


def _notify_admins_of_step_failure(
    *,
    monitor_state: dict[str, Any],
    alert_key: str,
    cron_run_id: str,
    step_name: str,
    message: str,
    run_ids: list[str],
) -> None:
    subject = f"[{get_product_name()}] Cron step failed: {step_name}"
    body = (
        "A cron step failed after retries.\n\n"
        f"Cron run ID: {cron_run_id}\n"
        f"Step: {step_name}\n"
        f"Run IDs: {', '.join(run_ids) if run_ids else 'none'}\n"
        f"Error: {message}\n"
        f"Log path: {_monitor_log_path_label()}\n"
    )
    _send_throttled_alert(
        monitor_state=monitor_state,
        alert_key=alert_key,
        subject=subject,
        body=body,
        event="cron.admin_alert.step_failure",
        run_ids=run_ids,
        cron_run_id=cron_run_id,
    )


def _notify_admins_of_blurb_failure(
    *,
    monitor_state: dict[str, Any],
    run_ids: list[str],
    error: Exception,
    cron_run_id: str,
) -> None:
    subject = f"[{get_product_name()}] LLM blurb batch failed"
    body = (
        "The digest pipeline failed to generate LLM descriptions.\n\n"
        f"Cron run ID: {cron_run_id}\n"
        f"Run IDs: {', '.join(run_ids) if run_ids else 'none'}\n"
        f"Error: {error.__class__.__name__}: {str(error).strip() or 'unknown'}\n"
        f"Log path: {_monitor_log_path_label()}\n\n"
        "User digests continued to send without descriptions."
    )
    _send_throttled_alert(
        monitor_state=monitor_state,
        alert_key="failure:llm_batch",
        subject=subject,
        body=body,
        event="llm.batch.admin_alert",
        run_ids=run_ids,
        cron_run_id=cron_run_id,
    )


def _notify_admins_of_blurb_degradation(
    *,
    monitor_state: dict[str, Any],
    run_ids: list[str],
    attempted: int,
    non_success_count: int,
    threshold: float,
    cron_run_id: str,
) -> None:
    failure_rate = (non_success_count / attempted) if attempted else 0.0
    subject = f"[{get_product_name()}] LLM blurb quality degraded"
    body = (
        "The digest pipeline generated LLM descriptions, but failure rate exceeded "
        "the configured threshold.\n\n"
        f"Cron run ID: {cron_run_id}\n"
        f"Run IDs: {', '.join(run_ids) if run_ids else 'none'}\n"
        f"Attempted: {attempted}\n"
        f"Non-success count: {non_success_count}\n"
        f"Failure rate: {failure_rate:.1%}\n"
        f"Threshold: {threshold:.1%}\n\n"
        "User digests continued to send."
    )
    _send_throttled_alert(
        monitor_state=monitor_state,
        alert_key="warning:llm_degraded",
        subject=subject,
        body=body,
        event="llm.batch.admin_alert",
        run_ids=run_ids,
        cron_run_id=cron_run_id,
    )

def _notify_admins_of_runtime_warning(
    *,
    monitor_state: dict[str, Any],
    cron_run_id: str,
    duration_s: int,
    threshold_s: int,
    run_ids: list[str],
) -> None:
    subject = f"[{get_product_name()}] Cron runtime warning"
    body = (
        "The cron run exceeded the runtime warning threshold.\n\n"
        f"Cron run ID: {cron_run_id}\n"
        f"Run IDs: {', '.join(run_ids) if run_ids else 'none'}\n"
        f"Duration: {duration_s}s\n"
        f"Threshold: {threshold_s}s\n"
        f"Log path: {_monitor_log_path_label()}\n"
    )
    _send_throttled_alert(
        monitor_state=monitor_state,
        alert_key="warning:runtime",
        subject=subject,
        body=body,
        event="cron.admin_alert.runtime",
        run_ids=run_ids,
        cron_run_id=cron_run_id,
    )


def _notify_admins_of_zero_output_streak(
    *,
    monitor_state: dict[str, Any],
    cron_run_id: str,
    streak: int,
    threshold: int,
    run_ids: list[str],
) -> None:
    subject = f"[{get_product_name()}] Zero output warning"
    body = (
        "Digest generation produced zero delivered digests across consecutive runs.\n\n"
        f"Cron run ID: {cron_run_id}\n"
        f"Run IDs: {', '.join(run_ids) if run_ids else 'none'}\n"
        f"Current streak: {streak}\n"
        f"Alert threshold: {threshold}\n"
        f"Log path: {_monitor_log_path_label()}\n"
    )
    _send_throttled_alert(
        monitor_state=monitor_state,
        alert_key="warning:zero_output_streak",
        subject=subject,
        body=body,
        event="cron.admin_alert.zero_output",
        run_ids=run_ids,
        cron_run_id=cron_run_id,
    )


def _deliver_digest_email_with_retries(
    *,
    monitor_state: dict[str, Any],
    cron_run_id: str,
    user_id: str,
    profile_ids: list[str],
    run_ids: list[str],
    conn=None,
) -> dict[str, Any]:
    last_result: dict[str, Any] = {"status": "failed", "error_message": "unknown"}
    for attempt in range(3):
        try:
            last_result = deliver_digest_email_for_user(
                user_id=user_id,
                profile_ids=profile_ids,
                run_ids=run_ids,
                conn=conn,
            )
        except Exception as error:
            last_result = {
                "status": "failed",
                "error_message": str(error).strip() or error.__class__.__name__,
            }
        if last_result.get("status") != "failed":
            break
        logger.warning(
            "Digest email attempt failed",
            extra={
                "event": "digest.email.retry",
                "cron_run_id": cron_run_id,
                "user_id": user_id,
                "attempt": attempt + 1,
                "max_attempts": 3,
            },
        )
    if last_result.get("status") == "failed":
        _notify_admins_of_step_failure(
            monitor_state=monitor_state,
            alert_key="failure:email_delivery",
            cron_run_id=cron_run_id,
            step_name="email_delivery",
            message=f"user={user_id} error={last_result.get('error_message')}",
            run_ids=run_ids,
        )
    return last_result


def _maybe_send_daily_summary(
    *,
    monitor_state: dict[str, Any],
    payload: dict[str, Any],
    run_ids: list[str],
) -> None:
    if not is_monitor_daily_summary_enabled():
        return
    today_key = datetime.now(UTC).date().isoformat()
    if str(monitor_state.get("last_daily_summary_date") or "") == today_key:
        return
    subject = f"[{get_product_name()}] Daily cron health summary ({today_key})"
    body = (
        "Daily cron status summary.\n\n"
        f"Cron run ID: {payload.get('cron_run_id')}\n"
        f"Run IDs: {', '.join(run_ids) if run_ids else 'none'}\n"
        f"Users seen: {payload.get('users_seen')}\n"
        f"Users succeeded: {payload.get('users_succeeded')}\n"
        f"Users failed: {payload.get('users_failed')}\n"
        f"Users skipped: {payload.get('users_skipped')}\n"
        f"Duration: {payload.get('duration_s')}s\n"
        f"Zero-output streak: {monitor_state.get('zero_output_streak')}\n"
        f"Log path: {_monitor_log_path_label()}\n"
    )
    admin_emails = sorted(get_debug_admin_emails())
    if not admin_emails or not is_email_delivery_configured():
        return
    for admin_email in admin_emails:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = get_email_from()
        message["To"] = admin_email
        message.set_content(body)
        try:
            deliver_email_message(message)
        except Exception:
            logger.exception(
                "Failed to send daily cron summary",
                extra={
                    "event": "cron.daily_summary.failed",
                    "cron_run_id": str(payload.get("cron_run_id") or ""),
                    "to_email": admin_email,
                },
            )
            return
    monitor_state["last_daily_summary_date"] = today_key


def main() -> None:
    result = run_daily_digest_for_all_users()
    print(result)


if __name__ == "__main__":
    main()
