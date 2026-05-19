"""
Shared pytest fixtures for the test suite
"""

import os

import pytest


if os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("PYTEST_SETUP_DB") != "1":
    os.environ.pop("DATABASE_URL", None)


@pytest.fixture(scope="session", autouse=True)
def database_schema() -> None:
    if os.environ.get("PYTEST_SETUP_DB") != "1":
        return

    if not os.environ.get("DATABASE_URL"):
        return

    from core.schema import main as setup_database

    setup_database()
