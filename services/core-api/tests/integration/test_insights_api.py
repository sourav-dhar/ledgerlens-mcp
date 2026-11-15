"""Spending insights total posted money by Kolkata calendar month and category."""

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import db_rows as rows
import psycopg
import pytest
from httpx import AsyncClient

from kosha_domain.ids import IdPrefix, new_id

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

IST = ZoneInfo("Asia/Kolkata")


def _month_start(at: datetime) -> datetime:
    local = at.astimezone(IST)
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


THIS_MONTH = _month_start(datetime.now(UTC))
LAST_MONTH = _month_start(THIS_MONTH - timedelta(days=1))


async def test_insights_total_posted_money_by_month_and_category(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    customer_id = rows.customer(committed)
    account_id = rows.account(committed, customer_id)
    grocer = rows.merchant(committed, category="groceries")
    cafe = rows.merchant(committed, category="dining", mcc=5812, display_name="Dosa Junction")

    def posted(at: datetime, amount_paise: int, **overrides: Any) -> None:
        rows.transaction(
            committed,
            account_id,
            customer_id,
            initiated_at=at,
            posted_at=at,
            amount_paise=amount_paise,
            **overrides,
        )

    # 00:30 IST on the 1st is still the previous day in UTC; it belongs to this month.
    first_minutes = THIS_MONTH + timedelta(minutes=30)
    posted(first_minutes, 60_000, merchant_id=grocer)
    posted(first_minutes + timedelta(hours=2), 40_000, merchant_id=grocer)
    posted(first_minutes + timedelta(hours=3), 90_000, merchant_id=cafe)
    posted(
        first_minutes + timedelta(hours=4),
        8_500_000,
        direction="credit",
        rail="neft",
        txn_type="salary",
    )
    rows.transaction(  # never posted: a failed payment moves no money
        committed, account_id, customer_id, initiated_at=first_minutes, status="failed"
    )
    posted(LAST_MONTH + timedelta(days=9), 30_000, merchant_id=cafe)
    posted(LAST_MONTH - timedelta(days=9), 99_000, merchant_id=cafe)  # outside the window

    response = await api.get(f"/v1/accounts/{account_id}/insights", params={"months": 2})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["account_id"] == account_id
    previous, current = body["months"]
    assert previous == {
        "month": LAST_MONTH.strftime("%Y-%m"),
        "credits_paise": 0,
        "debits_paise": 30_000,
        "categories": [{"category": "dining", "debits_paise": 30_000, "transactions": 1}],
    }
    assert current["month"] == THIS_MONTH.strftime("%Y-%m")
    assert (current["credits_paise"], current["debits_paise"]) == (8_500_000, 190_000)
    assert current["categories"] == [
        {"category": "groceries", "debits_paise": 100_000, "transactions": 2},
        {"category": "dining", "debits_paise": 90_000, "transactions": 1},
    ]


async def test_quiet_months_are_present_with_zeros(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    account_id = rows.account(committed, rows.customer(committed))

    response = await api.get(f"/v1/accounts/{account_id}/insights", params={"months": 3})

    months = response.json()["months"]
    assert len(months) == 3
    assert all(
        (m["credits_paise"], m["debits_paise"], m["categories"]) == (0, 0, []) for m in months
    )
    assert months[-1]["month"] == THIS_MONTH.strftime("%Y-%m")


async def test_debits_without_a_merchant_are_grouped_by_their_purpose(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    customer_id = rows.customer(committed)
    account_id = rows.account(committed, customer_id)
    at = THIS_MONTH + timedelta(hours=1)
    rows.transaction(
        committed,
        account_id,
        customer_id,
        initiated_at=at,
        posted_at=at,
        rail="nach",
        txn_type="emi",
        amount_paise=1_250_000,
    )

    current = (await api.get(f"/v1/accounts/{account_id}/insights", params={"months": 1})).json()[
        "months"
    ][-1]

    assert current["categories"] == [
        {"category": "emi", "debits_paise": 1_250_000, "transactions": 1}
    ]


async def test_an_unknown_account_has_no_insights(api: AsyncClient) -> None:
    response = await api.get(f"/v1/accounts/{new_id(IdPrefix.ACCOUNT)}/insights")

    assert response.status_code == 404
