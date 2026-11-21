"""How tools reach what the gateway instance shares, and what happens when it is missing."""

from typing import Any, cast

import pytest
from fastmcp import Client
from fastmcp.server.context import Context
from gateway_harness import FakeCoreApi, access_token, gateway
from pydantic import SecretStr, ValidationError

from kosha_domain.ids import IdPrefix, new_id
from mcp_gateway.errors import InternalError
from mcp_gateway.runtime import core_api, principal
from mcp_gateway.settings import Settings

pytestmark = pytest.mark.anyio


async def test_without_a_signing_key_core_api_tools_are_a_dependency_failure() -> None:
    core = FakeCoreApi()
    server = gateway(core, access_token(), settings=Settings())

    async with Client(server) as client:
        result = await client.call_tool(
            "get_customer_profile", {"customer_id": new_id(IdPrefix.CUSTOMER)}, raise_on_error=False
        )

    assert result.is_error
    assert result.structured_content is not None
    body = result.structured_content["error"]
    assert (body["code"], body["dependency"]) == ("dependency_unavailable", "core-api")
    assert core.requests == []


def test_a_short_signing_key_is_refused_at_startup() -> None:
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        Settings(internal_signing_key=SecretStr("too-short"))


class _OutsideThePipeline:
    """A context no lifespan started and no middleware authorized."""

    def __init__(self) -> None:
        self.lifespan_context: dict[str, Any] = {}

    async def get_state(self, _key: str) -> Any:
        return None


async def test_a_tool_run_outside_the_pipeline_is_a_defect_not_a_crash() -> None:
    ctx = cast("Context", _OutsideThePipeline())

    with pytest.raises(InternalError):
        core_api(ctx)
    with pytest.raises(InternalError):
        await principal(ctx)
