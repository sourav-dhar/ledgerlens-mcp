"""A real PostgreSQL + pgvector, migrated to head, shared by the integration suite.

The image is read from ``compose.yaml`` so the tests always run the exact digest the local
stack runs, and a Dependabot bump of one is a bump of both.
"""

import re
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

from core_api.migrations import upgrade

_COMPOSE = Path(__file__).parents[4] / "compose.yaml"
_IMAGE = re.compile(r"^\s+image:\s+(pgvector/pgvector:\S+)\s*$", re.MULTILINE)


def _pgvector_image() -> str:
    match = _IMAGE.search(_COMPOSE.read_text(encoding="utf-8"))
    assert match, f"no pgvector image in {_COMPOSE}"
    return match.group(1)


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    container = PostgresContainer(
        _pgvector_image(),
        username="kosha",
        password="kosha-test",  # noqa: S106 — throwaway container bound to loopback
        dbname="kosha",
        driver=None,
    )
    with container:
        yield container


@pytest.fixture(scope="session")
def database_url(postgres: PostgresContainer) -> str:
    """Connection URL of the session database, migrated to head."""
    url = postgres.get_connection_url()
    upgrade(url)
    return url


@pytest.fixture
def db(database_url: str) -> Iterator[psycopg.Connection]:
    """A connection inside a transaction that is rolled back, so tests never see each other."""
    with psycopg.connect(database_url) as conn:
        try:
            yield conn
        finally:
            conn.rollback()
