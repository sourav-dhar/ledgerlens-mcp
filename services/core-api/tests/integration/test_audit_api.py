"""Tool calls are recorded in the append-only audit log under the signed caller's name."""

from typing import Any

import psycopg
import pytest
from httpx import AsyncClient
from signed import SignedAs

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

RECORD: dict[str, Any] = {
    "client_id": "claude-desktop",
    "roles": ["support_agent"],
    "tool_name": "get_customer_profile",
    "args_hash": "b" * 64,
    "resource_ids": ["cus_01JZ8Q4V9X2M3N4P5Q6R7S8T9V"],
    "pii_unmasked": False,
    "outcome": "success",
    "latency_ms": 87,
    "trace_id": "1-6735a1b2-0123456789abcdef01234567",
}


async def test_a_record_is_appended_under_the_signed_caller(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    response = await api.post("/v1/audit", json=RECORD, auth=SignedAs("support-7"))

    assert response.status_code == 201, response.text
    audit_id = response.json()["audit_id"]
    stored = committed.execute(
        "SELECT actor_sub, tool_name, roles, outcome::text, latency_ms FROM ops.audit_log"
        " WHERE audit_id = %s",
        [audit_id],
    ).fetchone()
    assert stored == ("support-7", "get_customer_profile", ["support_agent"], "success", 87)


async def test_a_denied_call_is_recorded_with_its_error_code(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    record = RECORD | {"outcome": "denied", "error_code": "permission_denied"}

    response = await api.post("/v1/audit", json=record)

    stored = committed.execute(
        "SELECT outcome::text, error_code FROM ops.audit_log WHERE audit_id = %s",
        [response.json()["audit_id"]],
    ).fetchone()
    assert stored == ("denied", "permission_denied")
