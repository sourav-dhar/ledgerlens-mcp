"""Liveness and readiness probes."""

from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel

from core_api import SERVICE_NAME, __version__
from core_api.deps import DatabaseDep
from core_api.migrations import head

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    """Probe response; `status` is the only field orchestrators read."""

    status: Literal["ok"]
    service: str
    version: str


class Readiness(BaseModel):
    status: Literal["ok", "unavailable"]
    service: str
    version: str
    schema_revision: str | None
    """The migration the database is at; ready only when it is the one this build ships."""


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> HealthStatus:
    """The process is up and serving requests. It never touches the database."""
    return HealthStatus(status="ok", service=SERVICE_NAME, version=__version__)


@router.get(
    "/readyz",
    summary="Readiness probe",
    responses={503: {"model": Readiness, "description": "Not ready; retry shortly"}},
)
async def readyz(response: Response, database: DatabaseDep) -> Readiness:
    """The database answers and is migrated to exactly the revision this build expects."""
    revision = None if database is None else await database.schema_revision()
    ready = revision is not None and revision == head()
    if not ready:
        response.status_code = 503
        response.headers["Retry-After"] = "1"
    return Readiness(
        status="ok" if ready else "unavailable",
        service=SERVICE_NAME,
        version=__version__,
        schema_revision=revision,
    )
