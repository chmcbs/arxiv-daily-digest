"""
Default application settings
"""

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "default")
DEFAULT_DAILY_K = int(os.getenv("DAILY_PICKS_K", "3"))
DEFAULT_INTEREST_TEXT = os.getenv(
    "DEFAULT_INTEREST_TEXT",
    "I'm interested in learning about artificial intelligence research.",
)


# Ingestion
def get_arxiv_categories() -> list[str]:
    raw = os.getenv("ARXIV_CATEGORIES", "cs.AI")
    categories = [c.strip() for c in raw.split(",") if c.strip()]

    if not categories:
        raise ValueError("At least one arXiv category must be configured")

    return categories


# Recommendation
def get_daily_picks_k() -> int:
    if DEFAULT_DAILY_K < 1:
        raise ValueError("DAILY_PICKS_K must be >= 1")

    return DEFAULT_DAILY_K


# Ranking
def get_keyword_boost_cap() -> float:
    raw_value = float(os.getenv("KEYWORD_BOOST_CAP", "0.25"))
    if raw_value < 0:
        raise ValueError("KEYWORD_BOOST_CAP must be non-negative")
    return raw_value

def get_app_base_url() -> str:
    return os.getenv("APP_BASE_URL", "http://localhost:8000")
