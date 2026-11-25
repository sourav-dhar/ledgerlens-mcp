"""core-api wired to the shared scratch database (`tests/support/api_database.py`)."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from signed import SignedAs

from core_api.app import create_app
from core_api.db import Database
from core_api.settings import Settings


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
