"""Liveness and readiness probes."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from screening_sim import SERVICE_NAME, __version__

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    """Probe response; `status` is the only field orchestrators read."""

    status: Literal["ok"]
    service: str
    version: str


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> HealthStatus:
    """The process is up and serving requests."""
    return HealthStatus(status="ok", service=SERVICE_NAME, version=__version__)


@router.get("/readyz", summary="Readiness probe")
async def readyz() -> HealthStatus:
    """The service can do useful work. Dependency checks are added as dependencies arrive."""
    return HealthStatus(status="ok", service=SERVICE_NAME, version=__version__)
