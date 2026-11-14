"""A scratch database the API tests commit to, and the app wired to it.

The API reads through its own pool, so it cannot see rows a rolled-back test transaction
wrote: these tests commit, which is why they get a database of their own.
"""

from collections.abc import AsyncIterator, Iterator

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from signed import TEST_KEY, SignedAs

from core_api.app import create_app
from core_api.db import Database
from core_api.migrations import upgrade
from core_api.settings import Settings

_SCRATCH = "kosha_api_test"


@pytest.fixture(scope="session")
def api_database_url(database_url: str) -> Iterator[str]:
    """A fresh database migrated to head, dropped at the end of the session."""
    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {_SCRATCH} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {_SCRATCH}")
        url = database_url.rsplit("/", 1)[0] + f"/{_SCRATCH}"
        try:
            upgrade(url)
            yield url
        finally:
            admin.execute(f"DROP DATABASE {_SCRATCH} WITH (FORCE)")


@pytest.fixture
def committed(api_database_url: str) -> Iterator[psycopg.Connection]:
    """An autocommit connection for arranging rows the API must be able to read."""
    with psycopg.connect(api_database_url, autocommit=True) as conn:
        yield conn


@pytest.fixture
def api_settings(api_database_url: str) -> Settings:
    return Settings(
        database_url=SecretStr(api_database_url),
        internal_signing_keys=SecretStr(TEST_KEY),
        db_pool_timeout_s=0.5,
    )


@pytest.fixture
async def database(api_settings: Settings) -> AsyncIterator[Database]:
    db = Database.from_settings(api_settings)
    await db.open()
    try:
        yield db
    finally:
        await db.close()


@pytest.fixture
async def api(api_settings: Settings) -> AsyncIterator[AsyncClient]:
    """The app with its lifespan running, so the pool is open as in production."""
    app = create_app(api_settings)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            auth=SignedAs("staff-0042"),
        ) as client,
    ):
        yield client
