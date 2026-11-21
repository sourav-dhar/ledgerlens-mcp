"""Guards that hold for every tool, including ones added later.

The scope table is the LLD's (§6), every registered tool appears in it, and a tool missing
from it cannot be called: forgetting to declare a scope fails closed.
"""

import re
from pathlib import Path

import pytest
from fastmcp import Client
from gateway_harness import FakeCoreApi, access_token, gateway

from mcp_gateway.auth.scopes import TOOL_SCOPES, Role, Scope

pytestmark = pytest.mark.anyio

LLD = Path(__file__).parents[3] / "docs" / "architecture" / "lld" / "mcp-gateway.md"


def _lld_tool_scopes() -> dict[str, Scope]:
    section = LLD.read_text(encoding="utf-8").split("## 6. Tool scopes", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\| `(\w+)` \| `([a-z:]+)` \|", section, flags=re.MULTILINE)
    return {tool: Scope(scope) for tool, scope in rows}


def test_tool_scopes_are_the_llds() -> None:
    assert dict(TOOL_SCOPES) == _lld_tool_scopes()


async def test_every_registered_tool_declares_a_scope() -> None:
    async with Client(gateway(FakeCoreApi(), access_token())) as client:
        names = {tool.name for tool in await client.list_tools()}

    assert names <= set(TOOL_SCOPES), names - set(TOOL_SCOPES)


async def test_a_tool_without_a_declared_scope_cannot_be_called() -> None:
    server = gateway(FakeCoreApi(), access_token(Role.COMPLIANCE_OFFICER))

    @server.tool
    async def undeclared() -> str:  # pyright: ignore[reportUnusedFunction]
        return "should never run"

    async with Client(server) as client:
        result = await client.call_tool("undeclared", {}, raise_on_error=False)

    assert result.is_error
    assert result.structured_content is not None
    assert result.structured_content["error"]["code"] == "forbidden"
