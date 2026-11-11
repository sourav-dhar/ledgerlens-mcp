"""Application factory."""

from fastapi import FastAPI

from core_api import __version__
from core_api.health import router as health_router
from core_api.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI app. Tests pass explicit settings; production reads the environment."""
    app = FastAPI(title="Kosha Core Banking API", version=__version__)
    app.state.settings = settings or Settings()
    app.include_router(health_router)
    return app
