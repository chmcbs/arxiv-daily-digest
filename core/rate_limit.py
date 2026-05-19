"""
Rate limiting for sensitive authentication endpoints
"""

import threading
import time
from collections import defaultdict


class RateLimitExceeded(ValueError):
    """Raised when a caller exceeds a configured rate limit."""


_lock = threading.Lock()
_attempts: dict[str, list[float]] = defaultdict(list)


def _is_disabled() -> bool:
    import os

    return os.getenv("DISABLE_RATE_LIMIT", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def check_rate_limit(key: str, *, max_attempts: int, window_seconds: int) -> None:
    if _is_disabled():
        return
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if window_seconds < 1:
        raise ValueError("window_seconds must be >= 1")

    now = time.monotonic()
    cutoff = now - window_seconds

    with _lock:
        bucket = [timestamp for timestamp in _attempts[key] if timestamp >= cutoff]
        if len(bucket) >= max_attempts:
            raise RateLimitExceeded("rate limit exceeded")
        bucket.append(now)
        _attempts[key] = bucket


def reset_rate_limits() -> None:
    with _lock:
        _attempts.clear()
