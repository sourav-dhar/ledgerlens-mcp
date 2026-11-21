"""Pipeline stage 4: who is calling, and may they call this tool (LLD §2, ADR 0016).

The principal is resolved once per call from the verified access token and kept in the
call's state for the tool. The scope comes from one table, `TOOL_SCOPES`, and a tool that
is missing from it is refused: forgetting to declare a scope fails closed.
"""

from collections.abc import Callable, Mapping
from typing import override

from fastmcp.server.auth import AccessToken
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult
from mcp import types as mt

from mcp_gateway.auth.principal import principal_from
from mcp_gateway.auth.scopes import TOOL_SCOPES, Role
from mcp_gateway.errors import ForbiddenError, InternalError, UnauthenticatedError
from mcp_gateway.runtime import PRINCIPAL

type TokenSource = Callable[[], AccessToken | None]


class Authorize(Middleware):
    def __init__(self, *, machine_roles: Mapping[str, Role], token_source: TokenSource) -> None:
        self._machine_roles = machine_roles
        self._token_source = token_source

    @override
    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        token = self._token_source()
        if token is None:
            msg = "the call carries no verified identity"
            raise UnauthenticatedError(msg)
        principal = principal_from(token, machine_roles=self._machine_roles)
        scope = TOOL_SCOPES.get(context.message.name)
        if scope is None:
            msg = f"the tool {context.message.name!r} is not available"
            raise ForbiddenError(msg)
        principal.require(scope)
        if context.fastmcp_context is None:  # pragma: no cover — FastMCP always sets it
            msg = "a tool call arrived without a request context"
            raise InternalError(msg)
        await context.fastmcp_context.set_state(PRINCIPAL, principal, serializable=False)
        return await call_next(context)
