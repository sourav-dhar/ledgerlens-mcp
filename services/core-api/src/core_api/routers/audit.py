"""`/v1/audit`: append a tool call to the audit log, in a transaction of its own."""

from typing import Any

from fastapi import APIRouter

from core_api.deps import CallerDep, DatabaseDep, require
from core_api.schemas.audit import AuditReceipt, AuditRecord
from kosha_domain.ids import IdPrefix, new_id

router = APIRouter(prefix="/v1/audit", tags=["audit"])

# ops.audit_log is append-only: kosha_app may only insert, and kosha.forbid_change()
# rejects UPDATE, DELETE and TRUNCATE from anyone.
_APPEND = """
    INSERT INTO ops.audit_log (
        audit_id, actor_sub, client_id, roles, tool_name, args_hash, resource_ids,
        pii_unmasked, outcome, error_code, latency_ms, trace_id
    ) VALUES (
        %(audit_id)s, %(actor_sub)s, %(client_id)s, %(roles)s, %(tool_name)s, %(args_hash)s,
        %(resource_ids)s, %(pii_unmasked)s, %(outcome)s, %(error_code)s, %(latency_ms)s,
        %(trace_id)s
    )
    RETURNING audit_id, occurred_at
"""

_ERRORS: dict[int | str, dict[str, Any]] = {
    503: {"description": "Database unavailable; the gateway logs and meters the miss"},
    504: {"description": "Deadline exceeded"},
}


@router.post("", status_code=201, summary="Record a tool call", responses=_ERRORS)
async def record_tool_call(
    body: AuditRecord, caller: CallerDep, database: DatabaseDep
) -> AuditReceipt:
    """Append one record under the signed caller's name.

    Never joined with a business write (LLD core-api §3), so an audit failure cannot roll
    back the call it describes, and the gateway treats a failure here as non-fatal.
    """
    params = body.model_dump(mode="json") | {
        "audit_id": new_id(IdPrefix.AUDIT_RECORD),
        "actor_sub": caller.actor,
    }
    async with require(database).unit_of_work(caller) as conn:
        row = await (await conn.execute(_APPEND, params)).fetchone()
    return AuditReceipt.model_validate(row)
