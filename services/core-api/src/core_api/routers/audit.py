"""`/v1/audit`: append a tool call to the audit log, in a transaction of its own."""

from typing import Any

from fastapi import APIRouter, Response

from core_api.deps import CallerDep, DatabaseDep, require
from core_api.errors import ConflictError
from core_api.schemas.audit import AuditReceipt, AuditRecord

router = APIRouter(prefix="/v1/audit", tags=["audit"])

# ops.audit_log is append-only: kosha_app may only insert, and kosha.forbid_change()
# rejects UPDATE, DELETE and TRUNCATE from anyone. ON CONFLICT DO NOTHING writes nothing,
# so a retried record neither duplicates nor changes the first.
_APPEND = """
    INSERT INTO ops.audit_log (
        audit_id, actor_sub, client_id, roles, tool_name, args_hash, resource_ids,
        pii_unmasked, outcome, error_code, latency_ms, trace_id
    ) VALUES (
        %(audit_id)s, %(actor_sub)s, %(client_id)s, %(roles)s, %(tool_name)s, %(args_hash)s,
        %(resource_ids)s, %(pii_unmasked)s, %(outcome)s, %(error_code)s, %(latency_ms)s,
        %(trace_id)s
    )
    ON CONFLICT (audit_id) DO NOTHING
    RETURNING audit_id, occurred_at
"""

_EXISTING = """
    SELECT audit_id, occurred_at, actor_sub FROM ops.audit_log WHERE audit_id = %s
"""

_ERRORS: dict[int | str, dict[str, Any]] = {
    200: {"description": "Replay: this audit_id was already recorded"},
    409: {"description": "This audit_id was recorded for another caller"},
    503: {"description": "Database unavailable; the gateway logs and meters the miss"},
    504: {"description": "Deadline exceeded"},
}


@router.post("", status_code=201, summary="Record a tool call", responses=_ERRORS)
async def record_tool_call(
    body: AuditRecord, response: Response, caller: CallerDep, database: DatabaseDep
) -> AuditReceipt:
    """Append one record under the signed caller's name, once per ``audit_id``.

    Never joined with a business write (LLD core-api §3), so an audit failure cannot roll
    back the call it describes, and the gateway treats a failure here as non-fatal. The
    gateway mints ``audit_id`` per tool call and may retry; a retry answers ``200`` with
    ``Idempotent-Replayed: true`` and the original receipt.
    """
    params = body.model_dump(mode="json") | {"actor_sub": caller.actor}
    async with require(database).unit_of_work(caller) as conn:
        row = await (await conn.execute(_APPEND, params)).fetchone()
        if row is None:
            row = await (await conn.execute(_EXISTING, [body.audit_id])).fetchone()
            if row is None or row["actor_sub"] != caller.actor:
                msg = f"audit_id {body.audit_id} was recorded for another caller"
                raise ConflictError(msg)
            response.status_code = 200
            response.headers["Idempotent-Replayed"] = "true"
    return AuditReceipt.model_validate(row)
