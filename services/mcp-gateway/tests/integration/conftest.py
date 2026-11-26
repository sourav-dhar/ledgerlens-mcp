"""Real core-api on the shared scratch database (`tests/support/api_database.py`)."""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI

from core_api.app import create_app
from core_api.settings import Settings as CoreApiSettings


@pytest.fixture
async def core_api_app(api_settings: CoreApiSettings) -> AsyncIterator[FastAPI]:
    """core-api with its pool open on the scratch database, as in production.

    The gateway reaches it through `httpx.ASGITransport`, signing every request as it would
    over the network.
    """
    app = create_app(api_settings)
    async with app.router.lifespan_context(app):
        yield app
