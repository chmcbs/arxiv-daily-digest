"""
Fetches papers from arXiv and stores them idempotently
"""

import re
import uuid

import arxiv
import psycopg

from core.config import get_arxiv_categories
from core.db import get_database_url
from core.logging import get_logger

logger = get_logger(__name__)

UPSERT_PAPER_SQL = """
INSERT INTO papers (
    arxiv_id,
    title,
    abstract,
    authors,
    published_at,
    updated_at,
    pdf_url,
    entry_url,
    categories
)
VALUES (
    %(arxiv_id)s,
    %(title)s,
    %(abstract)s,
    %(authors)s,
    %(published_at)s,
    %(updated_at)s,
    %(pdf_url)s,
    %(entry_url)s,
    %(categories)s
)
ON CONFLICT (arxiv_id)
DO UPDATE SET
    title = EXCLUDED.title,
    abstract = EXCLUDED.abstract,
    authors = EXCLUDED.authors,
    published_at = EXCLUDED.published_at,
    updated_at = EXCLUDED.updated_at,
    pdf_url = EXCLUDED.pdf_url,
    entry_url = EXCLUDED.entry_url,
    categories = EXCLUDED.categories;
"""

INSERT_RUN_SQL = """
INSERT INTO runs (run_id, status, category, max_results)
VALUES (%s, 'running', %s, %s);
"""

COMPLETE_RUN_SQL = """
UPDATE runs
SET status = 'completed',
    fetched_count = %s,
    saved_count = %s,
    finished_at = NOW()
WHERE run_id = %s;
"""

FAIL_RUN_SQL = """
UPDATE runs
SET status = 'failed',
    finished_at = NOW(),
    error_message = %s
WHERE run_id = %s;
"""


def fetch_papers(
    category: str = "cs.AI",
    max_results: int = 150,
    sort_by: arxiv.SortCriterion = arxiv.SortCriterion.SubmittedDate,
    sort_order: arxiv.SortOrder = arxiv.SortOrder.Descending,
):
    client = arxiv.Client()
    search = arxiv.Search(
        query=f"cat:{category}",
        max_results=max_results,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return list(client.results(search))


def clean_id(arxiv_id: str) -> str:
    """
    Convert IDs so different versions update to the same paper row
    """
    return re.sub(r"v\d+$", "", arxiv_id)


def save_papers(papers: list[arxiv.Result]) -> int:
    """
    Insert or update papers by canonical arXiv ID
    """
    rows = [
        {
            "arxiv_id": clean_id(paper.get_short_id()),
            "title": paper.title,
            "abstract": paper.summary,
            "authors": [str(author) for author in paper.authors],
            "published_at": paper.published,
            "updated_at": paper.updated,
            "pdf_url": paper.pdf_url,
            "entry_url": paper.entry_id,
            "categories": paper.categories,
        }
        for paper in papers
    ]
    with psycopg.connect(get_database_url()) as conn:
        with conn.cursor() as cur:
            cur.executemany(UPSERT_PAPER_SQL, rows)
    return len(rows)


def start_run(category: str, max_results: int) -> str:
    run_id = str(uuid.uuid4())

    with psycopg.connect(get_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(INSERT_RUN_SQL, (run_id, category, max_results))

    return run_id


def complete_run(run_id: str, fetched_count: int, saved_count: int) -> None:
    with psycopg.connect(get_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(COMPLETE_RUN_SQL, (fetched_count, saved_count, run_id))


def fail_run(run_id: str, error_message: str) -> None:
    with psycopg.connect(get_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(FAIL_RUN_SQL, (error_message, run_id))


def run_ingestion(
    categories: list[str] | None = None, max_results: int = 150
) -> list[str]:
    if categories is None:
        categories = get_arxiv_categories()

    run_ids = []

    for category in categories:
        run_id = start_run(category, max_results)

        try:
            papers = fetch_papers(category=category, max_results=max_results)
            saved_count = save_papers(papers)
            complete_run(run_id, len(papers), saved_count)
            logger.info(
                "Category ingestion completed",
                extra={
                    "event": "pipeline.step.completed",
                    "step": "ingestion",
                    "run_id": run_id,
                    "category": category,
                    "fetched_count": len(papers),
                    "saved_count": saved_count,
                },
            )
        except Exception as error:
            fail_run(run_id, str(error))
            logger.exception(
                "Category ingestion failed",
                extra={
                    "event": "pipeline.step.failed",
                    "step": "ingestion",
                    "run_id": run_id,
                    "category": category,
                    "error_type": error.__class__.__name__,
                },
            )

        run_ids.append(run_id)

    return run_ids


if __name__ == "__main__":
    run_ingestion()
