"""Accounts are read with their balances, cards and VPAs; their Transactions page newest first."""

from datetime import UTC, datetime, timedelta
from typing import Any

import db_rows as rows
import psycopg
import pytest
from httpx import AsyncClient

from kosha_domain.ids import IdPrefix, new_id

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

NOW = datetime.now(UTC).replace(microsecond=0)


def _owned_account(db: psycopg.Connection, **overrides: Any) -> tuple[str, str]:
    customer_id = rows.customer(db)
    return customer_id, rows.account(db, customer_id, **overrides)


def _txn(db: psycopg.Connection, owner: tuple[str, str], ago: timedelta, **overrides: Any) -> str:
    customer_id, account_id = owner
    return rows.transaction(db, account_id, customer_id, initiated_at=NOW - ago, **overrides)[0]


async def _ids(api: AsyncClient, account_id: str, **params: Any) -> list[str]:
    response = await api.get(f"/v1/accounts/{account_id}/transactions", params=params)
    assert response.status_code == 200, response.text
    return [t["txn_id"] for t in response.json()["items"]]


# --- Account summary


async def test_an_account_summary_carries_balances_cards_and_vpas(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    customer_id, account_id = _owned_account(
        committed, ledger_balance_paise=1_250_000, hold_amount_paise=50_000
    )
    rows.card(committed, account_id, pan_last4="4417", status="active")
    rows.vpa(committed, account_id, customer_id, vpa="ananya.iyer@kosha", is_primary=True)

    response = await api.get(f"/v1/accounts/{account_id}")

    assert response.status_code == 200
    body = response.json()
    assert (body["account_id"], body["customer_id"]) == (account_id, customer_id)
    assert (body["product_code"], body["status"], body["ifsc"]) == (
        "savings_regular",
        "active",
        "KOSH0000001",
    )
    assert (
        body["ledger_balance_paise"],
        body["hold_amount_paise"],
        body["available_balance_paise"],
    ) == (1_250_000, 50_000, 1_200_000)
    assert [(c["pan_last4"], c["network"], c["status"]) for c in body["cards"]] == [
        ("4417", "rupay", "active")
    ]
    assert [(v["vpa"], v["is_primary"]) for v in body["vpas"]] == [("ananya.iyer@kosha", True)]


async def test_an_unknown_account_is_not_found(api: AsyncClient) -> None:
    unknown = new_id(IdPrefix.ACCOUNT)

    for path in (f"/v1/accounts/{unknown}", f"/v1/accounts/{unknown}/transactions"):
        response = await api.get(path)
        assert response.status_code == 404, path
        assert response.json()["error"]["code"] == "not_found"


# --- Transaction search


async def test_transactions_come_newest_first_and_only_from_the_account(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    owner, stranger = _owned_account(committed), _owned_account(committed)
    old = _txn(committed, owner, timedelta(days=3))
    new = _txn(committed, owner, timedelta(hours=2))
    _txn(committed, stranger, timedelta(hours=1))

    assert await _ids(api, owner[1]) == [new, old]


async def test_pages_walk_every_transaction_exactly_once(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    owner = _owned_account(committed)
    # Two share an instant, so the txn_id tiebreak decides their order.
    expected = [_txn(committed, owner, timedelta(hours=h)) for h in (1, 2, 2, 3, 4)]
    tied = sorted(expected[1:3], reverse=True)
    expected[1:3] = tied

    seen: list[str] = []
    params: dict[str, Any] = {"limit": 2}
    while True:
        page = (await api.get(f"/v1/accounts/{owner[1]}/transactions", params=params)).json()
        seen += [t["txn_id"] for t in page["items"]]
        if page["next"] is None:
            break
        params |= {
            "after_initiated_at": page["next"]["initiated_at"],
            "after_txn_id": page["next"]["txn_id"],
        }

    assert seen == expected


async def test_the_default_window_is_the_last_ninety_days(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    owner = _owned_account(committed)
    recent = _txn(committed, owner, timedelta(days=89))
    older = _txn(committed, owner, timedelta(days=91))

    assert await _ids(api, owner[1]) == [recent]
    window = {"initiated_from": (NOW - timedelta(days=120)).isoformat()}
    assert await _ids(api, owner[1], **window) == [recent, older]


async def test_the_window_is_half_open(api: AsyncClient, committed: psycopg.Connection) -> None:
    owner = _owned_account(committed)
    at_start = _txn(committed, owner, timedelta(days=2))
    _txn(committed, owner, timedelta(days=1))

    found = await _ids(
        api,
        owner[1],
        initiated_from=(NOW - timedelta(days=2)).isoformat(),
        initiated_before=(NOW - timedelta(days=1)).isoformat(),
    )

    assert found == [at_start]


@pytest.mark.parametrize(
    ("params", "wanted"),
    [
        ({"direction": "credit"}, "salary"),
        ({"status": ["failed", "reversed"]}, "failed"),
        ({"rail": ["neft"]}, "salary"),
        ({"min_amount_paise": 1_000_000}, "salary"),
        ({"max_amount_paise": 9_999, "min_amount_paise": 100}, "chai"),
        ({"text": "zomato"}, "food"),
    ],
)
async def test_filters_narrow_the_search(
    api: AsyncClient, committed: psycopg.Connection, params: dict[str, Any], wanted: str
) -> None:
    owner = _owned_account(committed)
    made = {
        "salary": _txn(
            committed,
            owner,
            timedelta(days=1),
            direction="credit",
            rail="neft",
            txn_type="salary",
            amount_paise=8_500_000,
            narration="NEFT/CR/SALARY/NOVALOOM TECH",
        ),
        "failed": _txn(committed, owner, timedelta(days=2), status="failed"),
        "chai": _txn(committed, owner, timedelta(days=3), amount_paise=2_000),
        "food": _txn(
            committed, owner, timedelta(days=4), narration="UPI/DR/ZOMATO ORDER/zomato@hdfc"
        ),
    }

    assert await _ids(api, owner[1], **params) == [made[wanted]]


# --- One transaction


async def test_a_transaction_carries_its_status_history_in_order(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    customer_id, account_id = _owned_account(committed)
    txn = rows.transaction(
        committed,
        account_id,
        customer_id,
        status="success",
        initiated_at=NOW - timedelta(minutes=5),
        ip_address="203.0.113.7",
        geo_lat=12.97160,
        geo_lng=77.59460,
    )
    for minutes, (src, dst) in enumerate([(None, "initiated"), ("initiated", "success")]):
        rows.status_change(
            committed,
            txn,
            from_status=src,
            to_status=dst,
            occurred_at=txn[1] + timedelta(minutes=minutes),
        )

    response = await api.get(f"/v1/transactions/{txn[0]}")

    assert response.status_code == 200
    body = response.json()
    assert (body["txn_id"], body["account_id"], body["status"]) == (txn[0], account_id, "success")
    assert (body["ip_address"], body["geo_lat"], body["geo_lng"]) == (
        "203.0.113.7",
        12.9716,
        77.5946,
    )
    assert [(h["from_status"], h["to_status"]) for h in body["status_history"]] == [
        (None, "initiated"),
        ("initiated", "success"),
    ]


async def test_an_unknown_transaction_is_not_found(api: AsyncClient) -> None:
    response = await api.get(f"/v1/transactions/{new_id(IdPrefix.TRANSACTION)}")

    assert response.status_code == 404
