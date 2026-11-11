"""MCP server definition: tools, resources and prompts are registered here."""

from typing import Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_gateway import SERVICE_NAME, __version__

INSTRUCTIONS = """\
LedgerLens gives Kosha Financial staff read access to customers, accounts,
transactions, KYC and AML data, controlled write actions for disputes and
transaction reviews, and search over internal policies and SOPs.
All data is synthetic. Personal data is masked unless the caller holds kyc:pii.
"""

READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)


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


def _probe_body() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": __version__}


async def _healthz(_: Request) -> JSONResponse:
    """Liveness: the process is up and serving requests."""
    return JSONResponse(_probe_body())


async def _readyz(_: Request) -> JSONResponse:
    """Readiness: dependency checks are added as dependencies arrive."""
    return JSONResponse(_probe_body())


async def get_service_health() -> ServiceHealth:
    """Report gateway status and the circuit-breaker state of each downstream dependency."""
    return ServiceHealth(status="ok", service=SERVICE_NAME, version=__version__, dependencies=[])


def create_server() -> FastMCP:
    """Build the MCP server with every tool registered."""
    mcp = FastMCP(
        name="LedgerLens",
        instructions=INSTRUCTIONS,
        version=__version__,
        mask_error_details=True,
        strict_input_validation=True,
    )
    mcp.tool(get_service_health, title="Service health", annotations=READ_ONLY)
    mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)(_healthz)
    mcp.custom_route("/readyz", methods=["GET"], include_in_schema=False)(_readyz)
    return mcp
