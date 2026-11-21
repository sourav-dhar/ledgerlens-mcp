"""The MCP contract is a reviewed snapshot: any change to a tool's schema shows up as a diff.

Agents are built against tool names, arguments, output schemas and annotations, so a change
to any of them is a contract change, reviewed like core-api's OpenAPI document.
"""

import pytest
from fastmcp import Client
from gateway_harness import FakeCoreApi, access_token, gateway
from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.json import JSONSnapshotExtension

pytestmark = pytest.mark.anyio


async def test_the_tool_contract_is_unchanged(snapshot: SnapshotAssertion) -> None:
    async with Client(gateway(FakeCoreApi(), access_token())) as client:
        tools = await client.list_tools()

    contract = {
        tool.name: tool.model_dump(mode="json", by_alias=True, exclude_none=True, exclude={"meta"})
        for tool in sorted(tools, key=lambda t: t.name)
    }

    assert contract == snapshot(extension_class=JSONSnapshotExtension)
