"""
Rate limiting for sensitive authentication endpoints
"""

import threading
import time

from core.config import is_rate_limit_disabled


class RateLimitExceeded(ValueError):
    """Raised when a caller exceeds a configured rate limit."""


_lock = threading.Lock()
_attempts: dict[str, list[float]] = {}


def check_rate_limit(key: str, *, max_attempts: int, window_seconds: int) -> None:
    if is_rate_limit_disabled():
        return
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if window_seconds < 1:
        raise ValueError("window_seconds must be >= 1")

    now = time.monotonic()
    cutoff = now - window_seconds

    with _lock:
        bucket = [timestamp for timestamp in _attempts.get(key, []) if timestamp >= cutoff]
        if len(bucket) >= max_attempts:
            raise RateLimitExceeded("rate limit exceeded")
        bucket.append(now)
        _attempts[key] = bucket


def reset_rate_limits() -> None:
    with _lock:
        _attempts.clear()
