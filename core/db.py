"""
Database connection utilities
"""

import os

import psycopg
from dotenv import load_dotenv

load_dotenv()


def get_database_url() -> str:
    return os.environ["DATABASE_URL"]


def check_database_connection(*, connect_timeout: int = 5) -> None:
    with psycopg.connect(
        get_database_url(),
        connect_timeout=connect_timeout,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            if cur.fetchone() is None:
                raise RuntimeError("database health check returned no rows")
