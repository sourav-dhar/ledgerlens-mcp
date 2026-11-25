"""KYC tools: `get_kyc_status` and `list_kyc_documents` (LLD §6).

PAN and Aadhaar leave the gateway masked. The full PAN comes only from core-api's
`/kyc/pan`, which records an audit entry for every unmasking, and only when a caller
holding `kyc:pii` asks for it, so each unmasking is a deliberate, recorded act.
"""

from datetime import date, datetime
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.server.context import Context
from pydantic import AliasChoices, Field

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
from mcp_gateway.auth.scopes import Scope
from mcp_gateway.masking import Aadhaar, Pan, mask
from mcp_gateway.runtime import core_api, principal
from mcp_gateway.tools.common import READ_ONLY, CustomerId, View


class KycEvent(View):
    from_status: KycStatus | None
    to_status: KycStatus
    actor: Actor
    reason: str | None
    occurred_at: datetime


class KycProfile(View):
    """The KYC profile in force, with its status history."""

    kyc_id: str
    customer_id: str
    kyc_type: KycType
    kyc_status: KycStatus
    ckyc_number: str | None
    pan: Pan | None = Field(
        default=None,
        validation_alias=AliasChoices("pan_last4", "pan"),
        description="Masked to its last four; in full only when revealed with kyc:pii.",
    )
    pan_status: PanStatus | None
    pan_name_match_score: float | None
    aadhaar: Aadhaar | None = Field(
        default=None,
        validation_alias=AliasChoices("aadhaar_last4", "aadhaar"),
        description="Always masked: only the last four digits are stored.",
    )
    ovd_type: OvdType | None
    vcip_session_id: str | None
    vcip_agent_id: str | None
    liveness_score: float | None
    face_match_score: float | None
    pep_flag: bool
    sanctions_flag: bool
    fatca_crs_declared: bool
    risk_category: RiskCategory
    risk_rationale: str | None
    verified_at: datetime | None
    verified_by: str | None
    next_review_due: date | None
    created_at: datetime
    events: list[KycEvent]
    """Oldest first."""


class _UnmaskedPan(View):
    pan: str


class KycDocument(View):
    """Metadata only: the document itself is never returned."""

    document_id: str
    kyc_id: str
    doc_type: KycDocumentType
    status: KycDocumentStatus
    rejection_reason: str | None
    sha256: str
    uploaded_at: datetime
    expires_on: date | None


class KycDocuments(View):
    documents: list[KycDocument]
    """Newest first, across every profile the Customer has had."""


async def get_kyc_status(
    ctx: Context,
    customer_id: CustomerId,
    reveal_pan: Annotated[
        bool,
        Field(description="Return the full PAN. Needs kyc:pii; every reveal is audited."),
    ] = False,
) -> KycProfile:
    """A Customer's KYC profile in force, with its status history.

    PAN and Aadhaar are masked to their last four. Holders of kyc:pii may pass
    reveal_pan to see the full PAN; each reveal is recorded in the audit log.
    """
    caller = await principal(ctx)
    if reveal_pan:
        caller.require(Scope.KYC_PII)
    api = core_api(ctx)
    path = f"/v1/customers/{customer_id}/kyc"
    profile = await api.get(caller.signed_as(), path, KycProfile)
    if reveal_pan and profile.pan is not None:
        unmasked = await api.get(caller.signed_as(), f"{path}/pan", _UnmaskedPan)
        return mask(profile.model_copy(update={"pan": unmasked.pan}), caller.scopes)
    # kyc:pii reveals only what was asked for: a status check keeps the PAN masked.
    return mask(profile, caller.scopes - {Scope.KYC_PII})


async def list_kyc_documents(ctx: Context, customer_id: CustomerId) -> KycDocuments:
    """Metadata of a Customer's KYC documents, newest first; never the documents."""
    caller = await principal(ctx)
    return await core_api(ctx).get(
        caller.signed_as(), f"/v1/customers/{customer_id}/kyc/documents", KycDocuments
    )


def register(mcp: FastMCP) -> None:
    mcp.tool(get_kyc_status, title="KYC status", annotations=READ_ONLY)
    mcp.tool(list_kyc_documents, title="KYC documents", annotations=READ_ONLY)
