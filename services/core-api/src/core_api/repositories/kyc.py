"""KYC profiles, their events and document metadata."""

from core_api.db import Connection
from core_api.schemas.kyc import KycDocument, KycEvent, KycProfile

# The newest profile is the one in force: Re-KYC opens a new profile rather than editing
# the old one. Tokens are deliberately not selected.
_CURRENT_PROFILE = """
    SELECT kyc_id, customer_id, kyc_type, kyc_status, ckyc_number, pan_last4, pan_status,
           pan_name_match_score::float8 AS pan_name_match_score, aadhaar_last4, ovd_type,
           vcip_session_id, vcip_agent_id, liveness_score::float8 AS liveness_score,
           face_match_score::float8 AS face_match_score, pep_flag, sanctions_flag,
           fatca_crs_declared, risk_category, risk_rationale, verified_at, verified_by,
           next_review_due, created_at
    FROM kyc.kyc_profiles
    WHERE customer_id = %s
    ORDER BY created_at DESC, kyc_id DESC
    LIMIT 1
"""

_EVENTS = """
    SELECT from_status, to_status, actor, reason, occurred_at
    FROM kyc.kyc_events
    WHERE kyc_id = %s
    ORDER BY occurred_at, event_id
"""

_DOCUMENTS = """
    SELECT document_id, kyc_id, doc_type, status, rejection_reason, sha256, uploaded_at,
           expires_on
    FROM kyc.kyc_documents
    WHERE customer_id = %s
    ORDER BY uploaded_at DESC, document_id DESC
"""


class KycRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    async def customer_exists(self, customer_id: str) -> bool:
        cursor = await self._conn.execute(
            "SELECT 1 AS found FROM core.customers WHERE customer_id = %s", [customer_id]
        )
        return await cursor.fetchone() is not None

    async def current_profile(self, customer_id: str) -> KycProfile | None:
        row = await (await self._conn.execute(_CURRENT_PROFILE, [customer_id])).fetchone()
        if row is None:
            return None
        events = await (await self._conn.execute(_EVENTS, [row["kyc_id"]])).fetchall()
        return KycProfile.model_validate(
            row | {"events": [KycEvent.model_validate(e) for e in events]}
        )

    async def documents(self, customer_id: str) -> list[KycDocument]:
        found = await (await self._conn.execute(_DOCUMENTS, [customer_id])).fetchall()
        return [KycDocument.model_validate(d) for d in found]
