"""`get_kyc_status` and `list_kyc_documents`, with their failure matrix (plan §8).

PAN and Aadhaar leave the gateway masked. The full PAN comes only from core-api's
`/kyc/pan`, which audits each unmasking, and only when a caller holding `kyc:pii` asks for
it with `reveal_pan`, so every unmasking is deliberate.
"""

from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
from fastmcp import Client
from fastmcp.server.auth import AccessToken
from gateway_harness import FakeCoreApi, access_token, core_api_error, gateway

from core_api.schemas.kyc import KycDocument, KycDocumentList, KycEvent, KycProfile, UnmaskedPan
from kosha_domain.ids import IdPrefix, new_id
from kosha_domain.lifecycles import KycStatus
from kosha_domain.vocabulary import (
    Actor,
    KycDocumentStatus,
    KycDocumentType,
    KycType,
    OvdType,
    PanStatus,
    RiskCategory,
)
from mcp_gateway.auth.scopes import ROLE_SCOPES, Role, Scope

pytestmark = pytest.mark.anyio

CUSTOMER_ID = new_id(IdPrefix.CUSTOMER)
KYC_ID = new_id(IdPrefix.KYC_PROFILE)
NOW = datetime(2026, 11, 20, 9, 30, tzinfo=UTC)
KYC = f"/v1/customers/{CUSTOMER_ID}/kyc"

PROFILE = KycProfile(
    kyc_id=KYC_ID,
    customer_id=CUSTOMER_ID,
    kyc_type=KycType.FULL_KYC,
    kyc_status=KycStatus.IN_REVIEW,
    ckyc_number=None,
    pan_last4="234X",
    pan_status=PanStatus.VALID,
    pan_name_match_score=0.97,
    aadhaar_last4="1234",
    ovd_type=OvdType.AADHAAR,
    vcip_session_id=None,
    vcip_agent_id=None,
    liveness_score=None,
    face_match_score=None,
    pep_flag=False,
    sanctions_flag=False,
    fatca_crs_declared=True,
    risk_category=RiskCategory.LOW,
    risk_rationale=None,
    verified_at=None,
    verified_by=None,
    next_review_due=date(2028, 11, 20),
    created_at=NOW,
    events=[
        KycEvent(
            from_status=None,
            to_status=KycStatus.IN_REVIEW,
            actor=Actor.SYSTEM,
            reason=None,
            occurred_at=NOW,
        )
    ],
)
DOCUMENTS = KycDocumentList(
    documents=[
        KycDocument(
            document_id=new_id(IdPrefix.KYC_DOCUMENT),
            kyc_id=KYC_ID,
            doc_type=KycDocumentType.PAN_CARD,
            status=KycDocumentStatus.ACCEPTED,
            rejection_reason=None,
            sha256="a" * 64,
            uploaded_at=NOW,
            expires_on=None,
        )
    ]
)
UNMASKED = UnmaskedPan(customer_id=CUSTOMER_ID, kyc_id=KYC_ID, pan="ABCPE1234X", pan_last4="234X")


@pytest.fixture
def core() -> FakeCoreApi:
    return FakeCoreApi(
        {f"GET {KYC}": PROFILE, f"GET {KYC}/documents": DOCUMENTS, f"GET {KYC}/pan": UNMASKED}
    )


async def _call(
    core: httpx.AsyncBaseTransport, token: AccessToken | None, tool: str, args: dict[str, Any]
) -> Any:
    async with Client(gateway(core, token)) as client:
        return await client.call_tool(tool, args, raise_on_error=False)


async def _ok(core: FakeCoreApi, role: Role, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    result = await _call(core, access_token(role), tool, args)
    assert not result.is_error, result.content
    content: dict[str, Any] = result.structured_content
    return content


async def _error(
    core: FakeCoreApi, token: AccessToken | None, tool: str, args: dict[str, Any]
) -> dict[str, Any]:
    result = await _call(core, token, tool, args)
    assert result.is_error
    body: dict[str, Any] = result.structured_content["error"]
    return body


def _paths(core: FakeCoreApi) -> list[str]:
    return [request.url.path for request in core.requests]


# --------------------------------------------------------------- get_kyc_status


@pytest.mark.parametrize("role", list(Role))
async def test_every_role_sees_pan_and_aadhaar_masked_by_default(
    core: FakeCoreApi, role: Role
) -> None:
    status = await _ok(core, role, "get_kyc_status", {"customer_id": CUSTOMER_ID})

    assert (status["pan"], status["aadhaar"]) == ("******234X", "XXXX XXXX 1234")
    assert status["kyc_status"] == "in_review"
    assert status["events"][0]["to_status"] == "in_review"
    assert _paths(core) == [KYC], "no unmasking unless asked for"


async def test_a_compliance_officer_can_ask_for_the_full_pan(core: FakeCoreApi) -> None:
    status = await _ok(
        core,
        Role.COMPLIANCE_OFFICER,
        "get_kyc_status",
        {"customer_id": CUSTOMER_ID, "reveal_pan": True},
    )

    assert status["pan"] == "ABCPE1234X"
    assert status["aadhaar"] == "XXXX XXXX 1234", "only the last four are stored"
    assert _paths(core) == [KYC, f"{KYC}/pan"]


@pytest.mark.parametrize("role", [Role.SUPPORT_AGENT, Role.ANALYST, Role.DEMO_READONLY])
async def test_revealing_the_pan_needs_kyc_pii(core: FakeCoreApi, role: Role) -> None:
    body = await _error(
        core, access_token(role), "get_kyc_status", {"customer_id": CUSTOMER_ID, "reveal_pan": True}
    )

    assert (body["code"], body["message"]) == ("forbidden", "the kyc:pii scope is required")
    assert core.requests == []


async def test_without_a_pan_on_file_nothing_is_unmasked(core: FakeCoreApi) -> None:
    core.route(f"GET {KYC}", PROFILE.model_copy(update={"pan_last4": None, "pan_status": None}))

    status = await _ok(
        core,
        Role.COMPLIANCE_OFFICER,
        "get_kyc_status",
        {"customer_id": CUSTOMER_ID, "reveal_pan": True},
    )

    assert status["pan"] is None
    assert _paths(core) == [KYC]


async def test_a_customer_without_a_kyc_profile_is_not_found(core: FakeCoreApi) -> None:
    core.route(f"GET {KYC}", core_api_error(404, "not_found", "no KYC profile"))

    body = await _error(core, access_token(), "get_kyc_status", {"customer_id": CUSTOMER_ID})

    assert (body["code"], body["message"]) == ("not_found", "no KYC profile")


# --------------------------------------------------------------- list_kyc_documents


async def test_documents_are_listed_as_metadata(core: FakeCoreApi) -> None:
    listed = await _ok(core, Role.SUPPORT_AGENT, "list_kyc_documents", {"customer_id": CUSTOMER_ID})

    [document] = listed["documents"]
    assert (document["doc_type"], document["status"]) == ("pan_card", "accepted")


async def test_a_customer_without_documents_has_an_empty_list(core: FakeCoreApi) -> None:
    core.route(f"GET {KYC}/documents", KycDocumentList(documents=[]))

    listed = await _ok(core, Role.ANALYST, "list_kyc_documents", {"customer_id": CUSTOMER_ID})

    assert listed == {"documents": []}


# --------------------------------------------------------------- failure matrix, both tools

TOOLS = [
    ("get_kyc_status", {"customer_id": CUSTOMER_ID}),
    ("list_kyc_documents", {"customer_id": CUSTOMER_ID}),
]


@pytest.mark.parametrize(("tool", "args"), TOOLS)
async def test_kyc_read_is_required(core: FakeCoreApi, tool: str, args: dict[str, Any]) -> None:
    scopes = ROLE_SCOPES[Role.COMPLIANCE_OFFICER] - {Scope.KYC_READ}

    body = await _error(core, access_token(Role.COMPLIANCE_OFFICER, scopes=scopes), tool, args)

    assert (body["code"], body["message"]) == ("forbidden", "the kyc:read scope is required")
    assert core.requests == []


@pytest.mark.parametrize(("tool", "args"), TOOLS)
async def test_a_malformed_customer_id_never_reaches_core_api(
    core: FakeCoreApi, tool: str, args: dict[str, Any]
) -> None:
    body = await _error(core, access_token(), tool, {**args, "customer_id": "cus_123"})

    assert body["code"] == "invalid_argument"
    assert core.requests == []


@pytest.mark.parametrize(("tool", "args"), TOOLS)
async def test_core_api_being_unavailable_is_a_dependency_failure(
    core: FakeCoreApi, tool: str, args: dict[str, Any]
) -> None:
    for route in list(core.routes):
        core.route(route, core_api_error(503, "unavailable"))

    body = await _error(core, access_token(), tool, args)

    assert (body["code"], body["retry_after_s"]) == ("dependency_unavailable", 1.0)
