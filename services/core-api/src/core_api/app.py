"""Application factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core_api import __version__
from core_api.db import Database
from core_api.errors import install_error_handlers
from core_api.health import router as health_router
from core_api.routers.customers import router as customers_router
from core_api.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI app. Tests pass explicit settings; production reads the environment."""
    settings = settings or Settings()
    database = None if settings.database_url is None else Database.from_settings(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        app.state.database = database
        if database is None:
            yield
            return
        await database.open()
        try:
            yield
        finally:
            await database.close()

    app = FastAPI(title="Kosha Core Banking API", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.database = None  # until the lifespan has opened the pool
    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(customers_router)
    return app
