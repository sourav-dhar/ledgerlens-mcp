"""`search_customers` and `get_customer_profile`, with their failure matrix (plan §8).

Each tool is called through the in-memory MCP client as a Staff member in a given Role.
Answers come from `FakeCoreApi`, built from core-api's own response models, or from the
real core-api app (without a database) where its own behaviour is the point.
"""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastmcp import Client
from fastmcp.server.auth import AccessToken
from gateway_harness import FakeCoreApi, access_token, core_api_error, gateway
from pydantic import SecretStr
from signed import TEST_KEY

from core_api.app import create_app
from core_api.schemas.customers import (
    Address,
    CustomerProfile,
    CustomerSearchResult,
    CustomerSummary,
)
from core_api.settings import Settings as CoreApiSettings
from kosha_domain.ids import IdPrefix, new_id
from kosha_domain.signing import ACTOR, KB_CEILING
from kosha_domain.vocabulary import (
    AddressType,
    CustomerStatus,
    Gender,
    OnboardingChannel,
    Persona,
    ResidentialStatus,
    RiskCategory,
    Segment,
)
from mcp_gateway.auth.scopes import ROLE_SCOPES, Role, Scope

pytestmark = pytest.mark.anyio

CUSTOMER_ID = new_id(IdPrefix.CUSTOMER)
NOW = datetime(2026, 11, 20, 9, 30, tzinfo=UTC)

SUMMARY = CustomerSummary(
    customer_id=CUSTOMER_ID,
    cif_number="4000012345",
    full_name="Ravi Kumar",
    mobile="9876547890",
    segment=Segment.MASS,
    status=CustomerStatus.ACTIVE,
)
PROFILE = CustomerProfile(
    customer_id=CUSTOMER_ID,
    cif_number="4000012345",
    first_name="Ravi",
    middle_name=None,
    last_name="Kumar",
    date_of_birth=date(1987, 4, 12),
    gender=Gender.MALE,
    email="ravi.kumar@example.com",
    mobile="9876547890",
    mobile_verified=True,
    persona=Persona.SALARIED,
    occupation="Engineer",
    employer_name="Acme Software",
    annual_income_band=None,
    segment=Segment.MASS,
    residential_status=ResidentialStatus.RESIDENT,
    preferred_language="en",
    onboarding_channel=OnboardingChannel.APP,
    relationship_start_date=date(2021, 6, 1),
    status=CustomerStatus.ACTIVE,
    risk_category=RiskCategory.LOW,
    created_at=NOW,
    updated_at=NOW,
    addresses=[
        Address(
            address_id=new_id(IdPrefix.ADDRESS),
            address_type=AddressType.PERMANENT,
            line1="12 MG Road",
            line2=None,
            city="Bengaluru",
            district="Bengaluru Urban",
            state="Karnataka",
            state_code="29",
            pincode="560001",
            country="IN",
            is_verified=True,
            valid_from=date(2021, 6, 1),
            valid_to=None,
        )
    ],
)


@pytest.fixture
def core() -> FakeCoreApi:
    return FakeCoreApi(
        {
            "GET /v1/customers": CustomerSearchResult(customers=[SUMMARY]),
            f"GET /v1/customers/{CUSTOMER_ID}": PROFILE,
        }
    )


async def _call(
    transport: httpx.AsyncBaseTransport, token: AccessToken | None, tool: str, args: dict[str, Any]
) -> Any:
    async with Client(gateway(transport, token)) as client:
        return await client.call_tool(tool, args, raise_on_error=False)


async def _ok(core: FakeCoreApi, role: Role, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    result = await _call(core, access_token(role), tool, args)
    assert not result.is_error, result.content
    content: dict[str, Any] = result.structured_content
    return content


async def _error(
    transport: httpx.AsyncBaseTransport, token: AccessToken | None, tool: str, args: dict[str, Any]
) -> dict[str, Any]:
    result = await _call(transport, token, tool, args)
    assert result.is_error
    body: dict[str, Any] = result.structured_content["error"]
    return body


# --------------------------------------------------------------- search_customers


async def test_search_finds_customers_by_name(core: FakeCoreApi) -> None:
    found = await _ok(core, Role.SUPPORT_AGENT, "search_customers", {"name": "Ravi"})

    assert [c["customer_id"] for c in found["customers"]] == [CUSTOMER_ID]
    assert core.last.url.params["name"] == "Ravi"


async def test_search_passes_every_criterion_given(core: FakeCoreApi) -> None:
    await _ok(
        core,
        Role.ANALYST,
        "search_customers",
        {"cif_number": "4000012345", "mobile_last4": "7890", "limit": 5},
    )

    assert dict(core.last.url.params) == {
        "cif_number": "4000012345",
        "mobile_last4": "7890",
        "limit": "5",
    }


@pytest.mark.parametrize(
    ("role", "mobile"),
    [
        (Role.SUPPORT_AGENT, "******7890"),
        (Role.ANALYST, "******7890"),
        (Role.DEMO_READONLY, "******7890"),
        (Role.COMPLIANCE_OFFICER, "9876547890"),
    ],
)
async def test_search_masks_the_mobile_unless_kyc_pii(
    core: FakeCoreApi, role: Role, mobile: str
) -> None:
    found = await _ok(core, role, "search_customers", {"name": "Ravi"})

    assert found["customers"][0]["mobile"] == mobile


async def test_an_empty_search_is_an_empty_list(core: FakeCoreApi) -> None:
    core.route("GET /v1/customers", CustomerSearchResult(customers=[]))

    found = await _ok(core, Role.ANALYST, "search_customers", {"name": "Nobody"})

    assert found == {"customers": []}


async def test_a_search_needs_a_criterion(core: FakeCoreApi) -> None:
    body = await _error(core, access_token(), "search_customers", {})

    assert body["code"] == "invalid_argument"
    assert core.requests == [], "nothing reaches core-api"


@pytest.mark.parametrize(
    "args",
    [
        {"name": "R"},
        {"cif_number": "12345"},
        {"mobile_last4": "78a0"},
        {"name": "Ravi", "limit": 0},
        {"name": "Ravi", "limit": 101},
        {"name": "Ravi", "surprise": True},
    ],
)
async def test_malformed_search_criteria_are_invalid_arguments(
    core: FakeCoreApi, args: dict[str, Any]
) -> None:
    body = await _error(core, access_token(), "search_customers", args)

    assert body["code"] == "invalid_argument"
    assert core.requests == []


# --------------------------------------------------------------- get_customer_profile


async def test_a_profile_is_read_for_the_caller(core: FakeCoreApi) -> None:
    profile = await _ok(
        core, Role.SUPPORT_AGENT, "get_customer_profile", {"customer_id": CUSTOMER_ID}
    )

    assert (profile["customer_id"], profile["first_name"]) == (CUSTOMER_ID, "Ravi")
    assert profile["addresses"][0]["city"] == "Bengaluru"
    assert (core.last.headers[ACTOR], core.last.headers[KB_CEILING]) == ("staff-0042", "internal")


@pytest.mark.parametrize("role", [Role.SUPPORT_AGENT, Role.ANALYST, Role.DEMO_READONLY])
async def test_a_profile_hides_contact_details_and_birth_date_without_kyc_pii(
    core: FakeCoreApi, role: Role
) -> None:
    profile = await _ok(core, role, "get_customer_profile", {"customer_id": CUSTOMER_ID})

    assert (profile["mobile"], profile["email"], profile["date_of_birth"]) == (
        "******7890",
        "r****@example.com",
        "1987",
    )


async def test_a_compliance_officer_sees_contact_details_and_birth_date(core: FakeCoreApi) -> None:
    profile = await _ok(
        core, Role.COMPLIANCE_OFFICER, "get_customer_profile", {"customer_id": CUSTOMER_ID}
    )

    assert (profile["mobile"], profile["email"], profile["date_of_birth"]) == (
        "9876547890",
        "ravi.kumar@example.com",
        "1987-04-12",
    )


@pytest.mark.parametrize("customer_id", ["cus_123", new_id(IdPrefix.ACCOUNT), "x" * 40])
async def test_a_malformed_customer_id_never_reaches_core_api(
    core: FakeCoreApi, customer_id: str
) -> None:
    body = await _error(core, access_token(), "get_customer_profile", {"customer_id": customer_id})

    assert body["code"] == "invalid_argument"
    assert core.requests == []


async def test_an_unknown_customer_is_not_found(core: FakeCoreApi) -> None:
    missing = new_id(IdPrefix.CUSTOMER)
    core.route(
        f"GET /v1/customers/{missing}",
        core_api_error(404, "not_found", f"customer {missing} not found"),
    )

    body = await _error(core, access_token(), "get_customer_profile", {"customer_id": missing})

    assert body == {
        "code": "not_found",
        "message": f"customer {missing} not found",
        "trace_id": body["trace_id"],
    }


# --------------------------------------------------------------- failure matrix, both tools

TOOLS = [
    ("search_customers", {"name": "Ravi"}),
    ("get_customer_profile", {"customer_id": CUSTOMER_ID}),
]


@pytest.mark.parametrize(("tool", "args"), TOOLS)
async def test_customers_read_is_required(
    core: FakeCoreApi, tool: str, args: dict[str, Any]
) -> None:
    token = access_token(Role.ANALYST, scopes=ROLE_SCOPES[Role.ANALYST] - {Scope.CUSTOMERS_READ})

    body = await _error(core, token, tool, args)

    assert (body["code"], body["message"]) == ("forbidden", "the customers:read scope is required")
    assert core.requests == []


@pytest.mark.parametrize(("tool", "args"), TOOLS)
async def test_a_call_without_a_verified_identity_is_unauthenticated(
    core: FakeCoreApi, tool: str, args: dict[str, Any]
) -> None:
    body = await _error(core, None, tool, args)

    assert body["code"] == "unauthenticated"
    assert core.requests == []


@pytest.mark.parametrize(("tool", "args"), TOOLS)
async def test_a_principal_without_a_role_is_forbidden(
    core: FakeCoreApi, tool: str, args: dict[str, Any]
) -> None:
    body = await _error(core, access_token(None), tool, args)

    assert body["code"] == "forbidden"
    assert core.requests == []


@pytest.fixture
async def core_without_database() -> AsyncIterator[FastAPI]:
    app = create_app(CoreApiSettings(internal_signing_keys=SecretStr(TEST_KEY)))
    async with app.router.lifespan_context(app):
        yield app


@pytest.mark.parametrize(("tool", "args"), TOOLS)
async def test_core_api_without_its_database_is_a_dependency_failure(
    core_without_database: FastAPI, tool: str, args: dict[str, Any]
) -> None:
    transport = httpx.ASGITransport(app=core_without_database)

    body = await _error(transport, access_token(), tool, args)

    assert (body["code"], body["dependency"], body["retry_after_s"]) == (
        "dependency_unavailable",
        "core-api",
        1.0,
    )


@pytest.mark.parametrize(("tool", "args"), TOOLS)
@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (core_api_error(504, "deadline_exceeded"), "deadline_exceeded"),
        (httpx.Response(500, text="boom"), "dependency_unavailable"),
    ],
)
async def test_core_api_failures_reach_the_caller_as_the_taxonomy(
    core: FakeCoreApi, tool: str, args: dict[str, Any], failure: httpx.Response, code: str
) -> None:
    for route in list(core.routes):
        core.route(route, failure)

    body = await _error(core, access_token(), tool, args)

    assert body["code"] == code
