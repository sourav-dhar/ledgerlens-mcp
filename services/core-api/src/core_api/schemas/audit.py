"""Audit records: one per gateway tool call."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from kosha_domain.vocabulary import AuditOutcome


class AuditRecord(BaseModel):
    """What the gateway reports about one tool call.

    The actor is not a field: it is the signed ``X-Kosha-Actor``, so a record can never be
    written in someone else's name.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: str = Field(min_length=1, max_length=128)
    roles: list[str] = Field(min_length=1)
    tool_name: str = Field(min_length=1, max_length=64)
    args_hash: str = Field(pattern=r"^[0-9a-f]{64}$", description="SHA-256 of the arguments.")
    resource_ids: list[str] = []
    pii_unmasked: bool = False
    outcome: AuditOutcome
    error_code: str | None = Field(default=None, max_length=64)
    latency_ms: int = Field(ge=0)
    trace_id: str | None = Field(default=None, max_length=128)


class AuditReceipt(BaseModel):
    audit_id: str
    occurred_at: datetime
