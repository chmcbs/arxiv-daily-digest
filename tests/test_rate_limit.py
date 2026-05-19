"""
Tests in-memory rate limiting helpers
"""

import pytest

from core.rate_limit import RateLimitExceeded, check_rate_limit, reset_rate_limits


@pytest.fixture(autouse=True)
def _clear_limits(monkeypatch):
    monkeypatch.delenv("DISABLE_RATE_LIMIT", raising=False)
    reset_rate_limits()


def test_check_rate_limit_allows_up_to_max_attempts():
    for _ in range(3):
        check_rate_limit("key", max_attempts=3, window_seconds=60)


def test_check_rate_limit_blocks_additional_attempts():
    for _ in range(2):
        check_rate_limit("key", max_attempts=2, window_seconds=60)

    with pytest.raises(RateLimitExceeded, match="rate limit exceeded"):
        check_rate_limit("key", max_attempts=2, window_seconds=60)
