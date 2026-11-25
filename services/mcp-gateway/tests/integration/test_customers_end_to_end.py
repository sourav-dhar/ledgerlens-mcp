"""Customer tools end to end: gateway -> signed HTTP -> real core-api -> PostgreSQL.

The unit tests answer from core-api's response models; these prove the gateway's views
parse what core-api actually returns from real rows, and that masking holds on them.
"""

import secrets
from collections.abc import AsyncIterator
from typing import Any

import db_rows as rows
import httpx
import psycopg
import pytest
from fastapi import FastAPI
from fastmcp import Client
from gateway_harness import access_token, gateway

from core_api.app import create_app
from core_api.settings import Settings as CoreApiSettings
from kosha_domain.ids import IdPrefix, new_id
from mcp_gateway.auth.scopes import Role

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
async def core_api_app(api_settings: CoreApiSettings) -> AsyncIterator[FastAPI]:
    """core-api with its pool open on the scratch database, as in production."""
    app = create_app(api_settings)
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
def surname() -> str:
    """A surname no other test uses: committed rows are shared by the whole session."""
    return "Zed" + "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(8))


async def _call(app: FastAPI, role: Role, tool: str, args: dict[str, Any]) -> Any:
    transport = httpx.ASGITransport(app=app)
    async with Client(gateway(transport, access_token(role))) as client:
        return await client.call_tool(tool, args, raise_on_error=False)


async def _ok(app: FastAPI, role: Role, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    result = await _call(app, role, tool, args)
    assert not result.is_error, result.content
    content: dict[str, Any] = result.structured_content
    return content


def _ananya(committed: psycopg.Connection, surname: str) -> str:
    customer_id = rows.customer(
        committed,
        first_name="Ananya",
        last_name=surname,
        mobile="9123456789",
        email="ananya.iyer@example.com",
        date_of_birth="1992-08-30",
    )
    rows.address(committed, customer_id, city="Chennai", state="Tamil Nadu", state_code="33")
    return customer_id


@pytest.mark.parametrize(
    ("role", "mobile"),
    [(Role.SUPPORT_AGENT, "******6789"), (Role.COMPLIANCE_OFFICER, "9123456789")],
)
async def test_a_search_by_name_finds_the_customer_with_the_mobile_masked_per_role(
    core_api_app: FastAPI, committed: psycopg.Connection, surname: str, role: Role, mobile: str
) -> None:
    customer_id = _ananya(committed, surname)

    found = await _ok(core_api_app, role, "search_customers", {"name": surname})

    [hit] = found["customers"]
    assert (hit["customer_id"], hit["full_name"], hit["mobile"]) == (
        customer_id,
        f"Ananya {surname}",
        mobile,
    )


async def test_an_analyst_reads_the_profile_with_contact_details_masked(
    core_api_app: FastAPI, committed: psycopg.Connection, surname: str
) -> None:
    customer_id = _ananya(committed, surname)

    profile = await _ok(
        core_api_app, Role.ANALYST, "get_customer_profile", {"customer_id": customer_id}
    )

    assert (profile["last_name"], profile["status"]) == (surname, "active")
    assert (profile["mobile"], profile["email"], profile["date_of_birth"]) == (
        "******6789",
        "a****@example.com",
        "1992",
    )
    [address] = profile["addresses"]
    assert (address["city"], address["state_code"]) == ("Chennai", "33")


async def test_a_compliance_officer_reads_the_profile_unmasked(
    core_api_app: FastAPI, committed: psycopg.Connection, surname: str
) -> None:
    customer_id = _ananya(committed, surname)

    profile = await _ok(
        core_api_app, Role.COMPLIANCE_OFFICER, "get_customer_profile", {"customer_id": customer_id}
    )

    assert (profile["mobile"], profile["email"], profile["date_of_birth"]) == (
        "9123456789",
        "ananya.iyer@example.com",
        "1992-08-30",
    )


async def test_an_unknown_customer_is_not_found(core_api_app: FastAPI) -> None:
    missing = new_id(IdPrefix.CUSTOMER)

    result = await _call(
        core_api_app, Role.SUPPORT_AGENT, "get_customer_profile", {"customer_id": missing}
    )

    assert result.is_error
    error = result.structured_content["error"]
    assert (error["code"], error["message"]) == ("not_found", f"customer {missing} not found")
