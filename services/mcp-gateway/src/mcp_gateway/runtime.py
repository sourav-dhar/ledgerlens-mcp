"""What tools share within one gateway instance, and how a tool reaches it.

The server's lifespan opens one HTTP client per instance and builds the `Runtime` around it;
the `Authorize` middleware resolves the principal once per call. Tools read both through
the typed accessors here, so a missing piece is a clear error rather than a `KeyError`.
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.server.context import Context

from mcp_gateway.auth.principal import Principal
from mcp_gateway.clients.core_api import CORE_API, CoreApi
from mcp_gateway.errors import DependencyUnavailableError, InternalError
from mcp_gateway.settings import Settings

RUNTIME = "runtime"
PRINCIPAL = "principal"


@dataclass(frozen=True, slots=True)
class Runtime:
    core_api: CoreApi | None
    """``None`` until an internal signing key is configured."""


def _runtime(settings: Settings, http: httpx.AsyncClient) -> Runtime:
    key = settings.internal_signing_key
    if key is None:
        return Runtime(core_api=None)
    return Runtime(
        core_api=CoreApi(
            http,
            signing_key=key.get_secret_value().encode(),
            attempts=settings.core_api_attempts,
            backoff_s=settings.core_api_backoff_s,
        )
    )


def lifespan(
    settings: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> Callable[[FastMCP[Any]], AbstractAsyncContextManager[dict[str, Any]]]:
    """Open the instance's client to core-api for as long as the server runs."""

    @asynccontextmanager
    async def run(_: FastMCP[Any]) -> AsyncGenerator[dict[str, Any]]:
        timeout = httpx.Timeout(
            settings.core_api_timeout_s, connect=settings.core_api_connect_timeout_s
        )
        async with httpx.AsyncClient(
            base_url=settings.core_api_url, transport=transport, timeout=timeout
        ) as http:
            yield {RUNTIME: _runtime(settings, http)}

    return run


def _the_runtime(ctx: Context) -> Runtime:
    runtime = ctx.lifespan_context.get(RUNTIME)
    if not isinstance(runtime, Runtime):
        msg = "the gateway's runtime was not started"
        raise InternalError(msg)
    return runtime


def core_api(ctx: Context) -> CoreApi:
    client = _the_runtime(ctx).core_api
    if client is None:
        msg = "core-api is not configured on this gateway"
        raise DependencyUnavailableError(msg, dependency=CORE_API)
    return client


async def principal(ctx: Context) -> Principal:
    """The principal `Authorize` resolved for this call."""
    found = await ctx.get_state(PRINCIPAL)
    if not isinstance(found, Principal):
        msg = "no principal was resolved for this call"
        raise InternalError(msg)
    return found
