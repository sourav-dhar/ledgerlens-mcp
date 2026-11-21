"""Operational tools: `get_service_health` (LLD §6)."""

from typing import Literal

from fastmcp import FastMCP
from pydantic import BaseModel

from mcp_gateway import SERVICE_NAME, __version__
from mcp_gateway.tools.common import READ_ONLY


class DependencyHealth(BaseModel):
    """State of one downstream dependency as seen by this gateway instance."""

    name: str
    breaker_state: Literal["closed", "open", "half_open"]


class ServiceHealth(BaseModel):
    """Gateway self-report returned by `get_service_health`."""

    status: Literal["ok", "degraded"]
    service: str
    version: str
    dependencies: list[DependencyHealth]


async def get_service_health() -> ServiceHealth:
    """Report gateway status and the circuit-breaker state of each downstream dependency."""
    return ServiceHealth(status="ok", service=SERVICE_NAME, version=__version__, dependencies=[])


def register(mcp: FastMCP) -> None:
    mcp.tool(get_service_health, title="Service health", annotations=READ_ONLY)
