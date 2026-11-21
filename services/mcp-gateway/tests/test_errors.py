"""A failed tool call reaches the client as an `isError` result with a structured body.

The body is what an agent reasons about (LLD §4): a stable `code`, a safe `message`, a
`trace_id` to quote, and `retry_after_s` or `dependency` when they apply. It never carries
stack traces, SQL or upstream payloads.
"""

import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Annotated, Any

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.transports import FastMCPTransport
from pydantic import BaseModel, Field

from mcp_gateway.errors import (
    ConflictError,
    DeadlineExceededError,
    DependencyUnavailableError,
    ErrorResults,
    ForbiddenError,
    GatewayError,
    InvalidArgumentError,
    NotFoundError,
)

pytestmark = pytest.mark.anyio

type McpClient = Client[FastMCPTransport]

TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
INTERNALS = "SELECT pan_token FROM kyc.profiles"

RAISED: dict[str, GatewayError] = {
    "forbidden": ForbiddenError("the kyc:pii scope is required"),
    "invalid_argument": InvalidArgumentError("the cursor does not belong to this query"),
    "not_found": NotFoundError("customer cus_01 not found"),
    "conflict": ConflictError("the idempotency key was used for a different request"),
    "deadline_exceeded": DeadlineExceededError("core-api did not answer in time"),
    "dependency_unavailable": DependencyUnavailableError(
        "core-api is unavailable", dependency="core-api", retry_after_s=1.0
    ),
}


class Echo(BaseModel):
    value: int


async def fail(kind: str) -> Echo:
    """Raise the gateway error named ``kind``, or crash when it names none."""
    if kind in RAISED:
        raise RAISED[kind]
    raise RuntimeError(INTERNALS)


async def echo(value: Annotated[int, Field(ge=0)]) -> Echo:
    return Echo(value=value)


@pytest.fixture
async def client() -> AsyncIterator[McpClient]:
    mcp = FastMCP("errors-under-test", mask_error_details=True, strict_input_validation=True)
    mcp.add_middleware(ErrorResults())
    mcp.tool(fail)
    mcp.tool(echo)
    async with Client(mcp) as c:
        yield c


async def _error(client: McpClient, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await client.call_tool(tool, arguments, raise_on_error=False)
    assert result.is_error
    assert result.structured_content is not None
    [text] = result.content
    assert json.loads(getattr(text, "text", "")) == result.structured_content
    body: dict[str, Any] = result.structured_content["error"]
    return body


@pytest.mark.parametrize("kind", list(RAISED))
async def test_a_gateway_error_keeps_its_code_and_message(client: McpClient, kind: str) -> None:
    body = await _error(client, "fail", {"kind": kind})

    assert body["code"] == kind
    assert body["message"] == RAISED[kind].message
    assert TRACE_ID.match(body["trace_id"])


async def test_a_dependency_failure_says_which_dependency_and_when_to_retry(
    client: McpClient,
) -> None:
    body = await _error(client, "fail", {"kind": "dependency_unavailable"})

    assert (body["dependency"], body["retry_after_s"]) == ("core-api", 1.0)


async def test_optional_fields_are_absent_when_they_do_not_apply(client: McpClient) -> None:
    body = await _error(client, "fail", {"kind": "not_found"})

    assert set(body) == {"code", "message", "trace_id"}


async def test_each_call_gets_its_own_trace_id(client: McpClient) -> None:
    first = await _error(client, "fail", {"kind": "not_found"})
    second = await _error(client, "fail", {"kind": "not_found"})

    assert first["trace_id"] != second["trace_id"]


@pytest.mark.parametrize("arguments", [{"value": -1}, {"value": "many"}, {"value": 1, "x": 2}, {}])
async def test_invalid_arguments_are_an_invalid_argument(
    client: McpClient, arguments: dict[str, Any]
) -> None:
    body = await _error(client, "echo", arguments)

    assert body["code"] == "invalid_argument"


async def test_an_invalid_argument_names_the_field_but_does_not_echo_the_value(
    client: McpClient,
) -> None:
    body = await _error(client, "echo", {"value": "4111111111111111"})

    assert "value" in body["message"]
    assert "4111111111111111" not in body["message"]


async def test_an_unexpected_failure_is_internal_and_reveals_nothing(
    client: McpClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="mcp_gateway.errors"):
        body = await _error(client, "fail", {"kind": "crash"})

    assert body["code"] == "internal"
    assert INTERNALS not in json.dumps(body)
    assert body["trace_id"] in caplog.text, "operators find the failure by its trace_id"


async def test_a_successful_call_is_untouched(client: McpClient) -> None:
    result = await client.call_tool("echo", {"value": 7})

    assert not result.is_error
    assert result.structured_content == {"value": 7}
