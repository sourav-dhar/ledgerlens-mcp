"""Risk tools end to end: the alert queue paged through real cursors, and real evidence.

Unit tests answer from core-api's response models; these prove the views parse real rows
(a rule's JSON thresholds, numeric scores, the triggering Transactions an alert cites) and
that a queue pages through signed cursors to its last alert.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import db_rows as rows
import httpx
import psycopg
import pytest
from fastapi import FastAPI
from fastmcp import Client
from gateway_harness import access_token, gateway

from mcp_gateway.auth.scopes import Role

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

NOW = datetime.now(UTC)


async def _ok(app: FastAPI, role: Role, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    async with Client(gateway(httpx.ASGITransport(app=app), access_token(role))) as client:
        result = await client.call_tool(tool, args, raise_on_error=False)
    assert not result.is_error, result.content
    assert result.structured_content is not None
    return result.structured_content


async def test_the_queue_pages_through_signed_cursors_soonest_sla_first(
    core_api_app: FastAPI, committed: psycopg.Connection
) -> None:
    customer_id = rows.customer(committed)
    rule_id = rows.aml_rule(committed, name="Cash just below ₹10 lakh", severity="critical")
    later, soonest, middle = (
        rows.aml_alert(committed, customer_id, rule_id, sla_due_at=NOW + timedelta(hours=h))
        for h in (3, 1, 2)
    )
    rows.aml_alert(
        committed,
        customer_id,
        rule_id,
        status="closed_false_positive",
        closed_at=NOW,
        sla_due_at=NOW,
    )
    args = {"customer_id": customer_id, "statuses": ["open"], "limit": 2}

    first = await _ok(core_api_app, Role.ANALYST, "list_aml_alerts", args)
    last = await _ok(
        core_api_app,
        Role.ANALYST,
        "list_aml_alerts",
        {**args, "cursor": first["next_cursor"]},
    )

    seen = [item["alert_id"] for item in first["items"] + last["items"]]
    assert seen == [soonest, middle, later]
    assert last["next_cursor"] is None
    assert {(i["rule_name"], i["severity"]) for i in first["items"]} == {
        ("Cash just below ₹10 lakh", "critical")
    }


async def test_an_alert_shows_its_thresholds_and_real_evidence(
    core_api_app: FastAPI, committed: psycopg.Connection
) -> None:
    customer_id = rows.customer(committed)
    account_id = rows.account(committed, customer_id)
    triggers = [
        rows.transaction(
            committed,
            account_id,
            customer_id,
            amount_paise=95_000_000,
            counterparty_vpa="ravi.kumar@okaxis",
            initiated_at=NOW - timedelta(days=days),
        )[0]
        for days in (3, 1)
    ]
    alert_id = rows.aml_alert(
        committed,
        customer_id,
        rows.aml_rule(committed),
        triggering_txn_ids=triggers,
        narrative="Two credits just under the reporting threshold within a week",
    )

    alert = await _ok(
        core_api_app, Role.COMPLIANCE_OFFICER, "get_aml_alert", {"alert_id": alert_id}
    )

    assert alert["rule"]["params"] == {"threshold_paise": 1_000_000_000, "window_days": 7}
    evidence = alert["triggering_transactions"]
    assert [t["txn_id"] for t in evidence] == triggers, "oldest first"
    assert {(t["amount_display"], t["counterparty_vpa"]) for t in evidence} == {
        ("₹9,50,000.00", "ravi.kumar@okaxis")
    }
