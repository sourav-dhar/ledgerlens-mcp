"""MCP server definition: the pipeline, and every tool, resource and prompt."""

import httpx
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_gateway import SERVICE_NAME, __version__
from mcp_gateway.errors import ErrorResults
from mcp_gateway.middleware.authorize import Authorize, TokenSource
from mcp_gateway.runtime import lifespan
from mcp_gateway.settings import Settings
from mcp_gateway.tools import customers, knowledge, kyc, ops, payments, risk

INSTRUCTIONS = """\
LedgerLens gives Kosha Financial staff read access to customers, accounts,
transactions, KYC and AML data, controlled write actions for disputes and
transaction reviews, and search over internal policies and SOPs.
All data is synthetic. Personal data is masked unless the caller holds kyc:pii.
"""


def _probe_body() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": __version__}


async def _healthz(_: Request) -> JSONResponse:
    """Liveness: the process is up and serving requests."""
    return JSONResponse(_probe_body())


async def _readyz(_: Request) -> JSONResponse:
    """Readiness: dependency checks are added as dependencies arrive."""
    return JSONResponse(_probe_body())


def create_server(
    settings: Settings | None = None,
    *,
    core_api_transport: httpx.AsyncBaseTransport | None = None,
    token_source: TokenSource = get_access_token,
) -> FastMCP:
    """Build the MCP server with every tool registered.

    ``core_api_transport`` and ``token_source`` exist for tests: the first routes calls to
    an in-process core-api, the second supplies the identity JWT verification would.
    """
    settings = settings or Settings()
    mcp = FastMCP(
        name="LedgerLens",
        instructions=INSTRUCTIONS,
        version=__version__,
        lifespan=lifespan(settings, core_api_transport),
        mask_error_details=True,
        strict_input_validation=True,
    )
    # Outermost first: every failure below, authorization included, becomes a result.
    mcp.add_middleware(ErrorResults())
    mcp.add_middleware(
        Authorize(machine_roles=settings.machine_client_roles, token_source=token_source)
    )
    ops.register(mcp)
    customers.register(mcp)
    kyc.register(mcp)
    payments.register(mcp)
    risk.register(mcp)
    knowledge.register(mcp)
    mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)(_healthz)
    mcp.custom_route("/readyz", methods=["GET"], include_in_schema=False)(_readyz)
    return mcp
