"""KYC as the API returns it.

PAN and Aadhaar appear only as their last four characters. The tokens never leave the
database through this API: unmasking a PAN (the `kyc:pii` scope) needs a KMS decrypt that
belongs to its own route.
"""

from datetime import date, datetime

from pydantic import BaseModel

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


class KycEvent(BaseModel):
    from_status: KycStatus | None
    to_status: KycStatus
    actor: Actor
    reason: str | None
    occurred_at: datetime


class KycProfile(BaseModel):
    kyc_id: str
    customer_id: str
    kyc_type: KycType
    kyc_status: KycStatus
    ckyc_number: str | None
    pan_last4: str | None
    pan_status: PanStatus | None
    pan_name_match_score: float | None
    aadhaar_last4: str | None
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


class KycDocument(BaseModel):
    """Metadata only: the document itself is never returned."""

    document_id: str
    kyc_id: str
    doc_type: KycDocumentType
    status: KycDocumentStatus
    rejection_reason: str | None
    sha256: str
    uploaded_at: datetime
    expires_on: date | None


class UnmaskedPan(BaseModel):
    """The full PAN, for callers the gateway granted ``kyc:pii``; every read is audited."""

    customer_id: str
    kyc_id: str
    pan: str
    pan_last4: str


class KycDocumentList(BaseModel):
    documents: list[KycDocument]
    """Newest first, across every profile the Customer has had."""
