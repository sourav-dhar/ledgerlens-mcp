"""Tool calls are recorded once in the append-only audit log, under the signed caller's name."""

from typing import Any

import psycopg
import pytest
from httpx import AsyncClient
from signed import SignedAs

from kosha_domain.ids import IdPrefix, new_id

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

SUPPORT = SignedAs("support-7")


def _record(**overrides: Any) -> dict[str, Any]:
    """A tool call as the gateway reports it, with the audit ID it minted for the call."""
    return {
        "audit_id": new_id(IdPrefix.AUDIT_RECORD),
        "client_id": "claude-desktop",
        "roles": ["support_agent"],
        "tool_name": "get_customer_profile",
        "args_hash": "b" * 64,
        "resource_ids": ["cus_01JZ8Q4V9X2M3N4P5Q6R7S8T9V"],
        "pii_unmasked": False,
        "outcome": "success",
        "latency_ms": 87,
        "trace_id": "1-6735a1b2-0123456789abcdef01234567",
    } | overrides


def _stored(db: psycopg.Connection, audit_id: str) -> list[tuple[Any, ...]]:
    return db.execute(
        "SELECT actor_sub, tool_name, roles, outcome::text, error_code, latency_ms"
        " FROM ops.audit_log WHERE audit_id = %s",
        [audit_id],
    ).fetchall()


async def test_a_record_is_appended_under_the_signed_caller(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    record = _record()

    response = await api.post("/v1/audit", json=record, auth=SUPPORT)

    assert response.status_code == 201, response.text
    assert response.json()["audit_id"] == record["audit_id"]
    assert _stored(committed, record["audit_id"]) == [
        ("support-7", "get_customer_profile", ["support_agent"], "success", None, 87)
    ]


async def test_a_denied_call_is_recorded_with_its_error_code(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    record = _record(outcome="denied", error_code="permission_denied")

    await api.post("/v1/audit", json=record, auth=SUPPORT)

    [(_, _, _, outcome, error_code, _)] = _stored(committed, record["audit_id"])
    assert (outcome, error_code) == ("denied", "permission_denied")


async def test_a_retried_record_is_stored_once_and_replayed(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    record = _record()

    first = await api.post("/v1/audit", json=record, auth=SUPPORT)
    again = await api.post("/v1/audit", json=record, auth=SUPPORT)

    assert (first.status_code, again.status_code) == (201, 200)
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json() == first.json()
    assert len(_stored(committed, record["audit_id"])) == 1


async def test_an_audit_id_reused_by_another_caller_is_a_conflict(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    record = _record()
    await api.post("/v1/audit", json=record, auth=SUPPORT)

    response = await api.post("/v1/audit", json=record, auth=SignedAs("analyst-9"))

    assert response.status_code == 409
    assert _stored(committed, record["audit_id"])[0][0] == "support-7"
