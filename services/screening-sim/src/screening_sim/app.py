"""Application factory."""

from fastapi import FastAPI

from screening_sim import __version__
from screening_sim.health import router as health_router
from screening_sim.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI app. Tests pass explicit settings; production reads the environment."""
    app = FastAPI(title="Kosha Screening Vendor Simulator", version=__version__)
    app.state.settings = settings or Settings()
    app.include_router(health_router)
    return app
