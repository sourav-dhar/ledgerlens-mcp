"""Protocol-level tests through the in-memory MCP client (no network)."""

from collections.abc import AsyncIterator

import pytest
from fastmcp import Client
from fastmcp.client.transports import FastMCPTransport

from mcp_gateway import __version__
from mcp_gateway.server import create_server

pytestmark = pytest.mark.anyio

type McpClient = Client[FastMCPTransport]


@pytest.fixture
async def client() -> AsyncIterator[McpClient]:
    async with Client(create_server()) as c:
        yield c


async def test_server_identifies_itself(client: McpClient) -> None:
    info = client.server_info

    assert info is not None
    assert (info.name, info.version) == ("LedgerLens", __version__)
    assert client.instructions is not None
    assert "synthetic" in client.instructions


async def test_service_health_tool_is_listed_as_read_only(client: McpClient) -> None:
    tools = {t.name: t for t in await client.list_tools()}

    tool = tools["get_service_health"]
    assert tool.annotations is not None
    assert tool.annotations.read_only_hint is True
    assert tool.annotations.destructive_hint is False
    assert tool.output_schema is not None


async def test_service_health_reports_ok(client: McpClient) -> None:
    result = await client.call_tool("get_service_health", {})

    assert result.structured_content == {
        "status": "ok",
        "service": "mcp-gateway",
        "version": __version__,
        "dependencies": [],
    }


async def test_unknown_tool_is_an_error(client: McpClient) -> None:
    result = await client.call_tool("no_such_tool", {}, raise_on_error=False)

    assert result.is_error


async def test_unexpected_arguments_are_rejected(client: McpClient) -> None:
    result = await client.call_tool("get_service_health", {"surprise": 1}, raise_on_error=False)

    assert result.is_error
