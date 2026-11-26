"""Payments tools end to end: real core-api on real rows, paged through real cursors.

Unit tests answer from core-api's response models; these prove the views parse real rows
(inet addresses, numeric coordinates, paise), that a search pages through signed cursors
to its last row, and that masking and withholding hold on that data.
"""

import secrets
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Ledger:
    account_id: str
    account_number: str
    mobile: str
    txn_ids: list[str]
    """Newest first."""


@pytest.fixture
def ledger(committed: psycopg.Connection) -> Ledger:
    """An Account with a mobile-number VPA and three posted UPI debits, a minute apart.

    VPAs are unique across the session's committed rows, so each test gets its own mobile.
    """
    mobile = "9" + "".join(secrets.choice("0123456789") for _ in range(9))
    customer_id = rows.customer(committed, mobile=mobile)
    account_id = rows.account(committed, customer_id)
    rows.vpa(committed, account_id, customer_id, vpa=f"{mobile}@kosha", is_primary=True)
    now = datetime.now(UTC)
    txn_ids: list[str] = []
    for minutes, amount_paise in ((1, 25_000), (2, 40_000), (3, 15_000)):
        at = now - timedelta(minutes=minutes)
        txn = rows.transaction(
            committed,
            account_id,
            customer_id,
            initiated_at=at,
            posted_at=at,
            amount_paise=amount_paise,
            counterparty_vpa="ravi.kumar@okaxis",
            device_id="device-7f3c",
            ip_address="203.0.113.7",
            geo_lat=12.97160,
            geo_lng=77.59460,
        )
        rows.status_change(committed, txn)
        txn_ids.append(txn[0])
    [(number,)] = committed.execute(
        "SELECT account_number FROM core.accounts WHERE account_id = %s", [account_id]
    ).fetchall()
    return Ledger(account_id=account_id, account_number=str(number), mobile=mobile, txn_ids=txn_ids)


async def _ok(app: FastAPI, role: Role, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    async with Client(gateway(httpx.ASGITransport(app=app), access_token(role))) as client:
        result = await client.call_tool(tool, args, raise_on_error=False)
    assert not result.is_error, result.content
    assert result.structured_content is not None
    return result.structured_content


async def test_a_summary_masks_the_account_number_and_the_mobile_vpa(
    core_api_app: FastAPI, ledger: Ledger
) -> None:
    summary = await _ok(
        core_api_app, Role.SUPPORT_AGENT, "get_account_summary", {"account_id": ledger.account_id}
    )

    assert summary["account_number"] == "XXXXXX" + ledger.account_number[-4:]
    assert [v["vpa"] for v in summary["vpas"]] == [f"{ledger.mobile[:2]}***@kosha"]
    assert summary["available_balance_display"].startswith("₹")


async def test_a_search_pages_through_signed_cursors_to_the_last_row(
    core_api_app: FastAPI, ledger: Ledger
) -> None:
    args = {"account_id": ledger.account_id, "limit": 2}

    first = await _ok(core_api_app, Role.SUPPORT_AGENT, "search_transactions", args)
    last = await _ok(
        core_api_app,
        Role.SUPPORT_AGENT,
        "search_transactions",
        {**args, "cursor": first["next_cursor"]},
    )

    seen = [item["txn_id"] for item in first["items"] + last["items"]]
    assert seen == ledger.txn_ids
    assert last["next_cursor"] is None
    assert {item["counterparty_vpa"] for item in first["items"]} == {"ra***@okaxis"}
    assert [item["amount_display"] for item in first["items"]] == ["₹250.00", "₹400.00"]


@pytest.mark.parametrize(
    ("role", "ip_address", "vpa"),
    [
        (Role.SUPPORT_AGENT, None, "ra***@okaxis"),
        (Role.ANALYST, "203.0.113.7", "ravi.kumar@okaxis"),
    ],
)
async def test_device_detail_is_withheld_without_aml_read(
    core_api_app: FastAPI, ledger: Ledger, role: Role, ip_address: str | None, vpa: str
) -> None:
    detail = await _ok(core_api_app, role, "get_transaction", {"txn_id": ledger.txn_ids[0]})

    assert (detail["ip_address"], detail["counterparty_vpa"]) == (ip_address, vpa)
    assert detail["status_history"][0]["to_status"] == "success"


async def test_insights_total_the_posted_debits(core_api_app: FastAPI, ledger: Ledger) -> None:
    insights = await _ok(
        core_api_app,
        Role.DEMO_READONLY,
        "get_spending_insights",
        {"account_id": ledger.account_id, "months": 2},
    )

    months = insights["months"]
    assert sum(month["debits_paise"] for month in months) == 80_000
    assert [m["month"] for m in months] == sorted(m["month"] for m in months), "oldest first"
