"""
Keyword search helpers
"""

SEARCH_DICTIONARY = "simple"
MAX_KEYWORDS_PER_PROFILE = 20
MAX_KEYWORD_LENGTH = 24


def paper_search_vector_sql(alias: str | None = None) -> str:
    prefix = f"{alias}." if alias else ""
    return (
        f"setweight(to_tsvector('{SEARCH_DICTIONARY}', coalesce({prefix}title, '')), 'A') || "
        f"setweight(to_tsvector('{SEARCH_DICTIONARY}', coalesce({prefix}abstract, '')), 'B')"
    )


PAPER_SEARCH_VECTOR_SQL = paper_search_vector_sql()


def normalize_keyword(value: str) -> str:
    keyword = value.strip().lower()
    if not keyword:
        raise ValueError("keyword must not be empty")
    if len(keyword) > MAX_KEYWORD_LENGTH:
        raise ValueError(f"keyword must be <= {MAX_KEYWORD_LENGTH} characters")
    return keyword
