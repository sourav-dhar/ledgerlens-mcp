"""Raising a dispute is idempotent: the key, the dispute and its event commit together."""

from datetime import UTC, datetime, timedelta
from typing import Any, LiteralString

import anyio
import db_rows as rows
import psycopg
import pytest
from httpx import AsyncClient, Response
from signed import SignedAs

from kosha_domain.ids import IdPrefix, new_id

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

NOW = datetime.now(UTC).replace(microsecond=0)


def _debit(db: psycopg.Connection, **overrides: Any) -> str:
    customer_id = rows.customer(db)
    account_id = rows.account(db, customer_id)
    values = {"initiated_at": NOW - timedelta(hours=3), "amount_paise": 250_000} | overrides
    return rows.transaction(db, account_id, customer_id, **values)[0]


async def _raise(api: AsyncClient, key: str, body: dict[str, Any], **kwargs: Any) -> Response:
    return await api.post("/v1/disputes", json=body, headers={"Idempotency-Key": key}, **kwargs)


def _count(db: psycopg.Connection, query: LiteralString, value: str) -> int:
    row = db.execute(query, [value]).fetchone()
    assert row is not None
    return row[0]


def _disputes(db: psycopg.Connection, txn_id: str) -> int:
    return _count(db, "SELECT count(*) FROM ops.disputes WHERE txn_id = %s", txn_id)


def _events(db: psycopg.Connection, txn_id: str) -> int:
    return _count(
        db,
        "SELECT count(*) FROM ops.outbox WHERE event_type = 'DisputeRaised'"
        " AND payload ->> 'txn_id' = %s",
        txn_id,
    )


async def test_a_dispute_is_raised_with_its_event_and_idempotency_record(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    txn_id = _debit(committed)
    key = f"dsp-{txn_id}"

    response = await _raise(api, key, {"txn_id": txn_id, "reason_code": "failed_but_debited"})

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["status"], body["amount_paise"], body["created_by"]) == (
        "raised",
        250_000,
        "staff-0042",
    )
    assert datetime.fromisoformat(body["tat_due_at"]) == NOW - timedelta(hours=3) + timedelta(
        days=1
    )
    event = committed.execute(
        "SELECT aggregate_type, aggregate_id, payload FROM ops.outbox"
        " WHERE event_type = 'DisputeRaised' AND aggregate_id = %s",
        [body["dispute_id"]],
    ).fetchone()
    assert event is not None
    assert event[0] == "dispute"
    assert (event[2]["txn_id"], event[2]["reason_code"]) == (txn_id, "failed_but_debited")
    stored = committed.execute(
        "SELECT status, response ->> 'dispute_id' FROM ops.idempotency_keys"
        " WHERE scope = 'raise_dispute' AND key = %s",
        [key],
    ).fetchone()
    assert stored == ("completed", body["dispute_id"])


async def test_a_card_dispute_turns_around_in_five_days_and_may_be_partial(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    txn_id = _debit(committed, rail="card_ecom", txn_type="p2m", channel="web")

    response = await _raise(
        api,
        f"dsp-{txn_id}",
        {"txn_id": txn_id, "reason_code": "amount_mismatch", "amount_paise": 40_000},
    )

    body = response.json()
    assert body["amount_paise"] == 40_000
    assert datetime.fromisoformat(body["tat_due_at"]) == NOW - timedelta(hours=3) + timedelta(
        days=5
    )


async def test_a_retry_replays_the_first_response(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    txn_id = _debit(committed)
    request = {"txn_id": txn_id, "reason_code": "duplicate"}

    first = await _raise(api, f"dsp-{txn_id}", request)
    again = await _raise(api, f"dsp-{txn_id}", request)

    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json() == first.json()
    assert (_disputes(committed, txn_id), _events(committed, txn_id)) == (1, 1)


@pytest.mark.parametrize(
    ("change", "auth"),
    [
        ({"reason_code": "unauthorised"}, None),
        ({}, SignedAs("support-7")),
    ],
    ids=["different request", "different caller"],
)
async def test_a_reused_key_for_another_request_is_a_conflict(
    api: AsyncClient,
    committed: psycopg.Connection,
    change: dict[str, Any],
    auth: SignedAs | None,
) -> None:
    txn_id = _debit(committed)
    request = {"txn_id": txn_id, "reason_code": "duplicate"}
    await _raise(api, f"dsp-{txn_id}", request)

    extra = {} if auth is None else {"auth": auth}
    response = await _raise(api, f"dsp-{txn_id}", request | change, **extra)

    assert response.status_code == 409
    assert "Idempotency-Key" in response.json()["error"]["message"]
    assert _disputes(committed, txn_id) == 1


async def test_concurrent_duplicates_raise_one_dispute(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    txn_id = _debit(committed)
    request = {"txn_id": txn_id, "reason_code": "duplicate"}
    statuses: list[int] = []

    async def send() -> None:
        statuses.append((await _raise(api, f"dsp-{txn_id}", request)).status_code)

    async with anyio.create_task_group() as tg:
        tg.start_soon(send)
        tg.start_soon(send)

    assert sorted(statuses) == [200, 201]
    assert (_disputes(committed, txn_id), _events(committed, txn_id)) == (1, 1)


async def test_concurrent_disputes_of_one_transaction_raise_one(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    txn_id = _debit(committed)
    statuses: list[int] = []

    async def send(key: str) -> None:
        response = await _raise(api, key, {"txn_id": txn_id, "reason_code": "duplicate"})
        statuses.append(response.status_code)

    async with anyio.create_task_group() as tg:
        tg.start_soon(send, f"a-{txn_id}")
        tg.start_soon(send, f"b-{txn_id}")

    assert sorted(statuses) == [201, 409]
    assert _disputes(committed, txn_id) == 1


async def test_an_open_dispute_blocks_another_but_a_withdrawn_one_does_not(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    open_txn, withdrawn_txn = _debit(committed), _debit(committed)
    for txn_id, status in ((open_txn, "under_investigation"), (withdrawn_txn, "withdrawn")):
        found = committed.execute(
            "SELECT initiated_at, customer_id FROM core.transactions WHERE txn_id = %s", [txn_id]
        ).fetchone()
        assert found is not None
        rows.dispute(committed, (txn_id, found[0]), found[1], status=status)

    blocked = await _raise(api, f"x-{open_txn}", {"txn_id": open_txn, "reason_code": "duplicate"})
    allowed = await _raise(
        api, f"x-{withdrawn_txn}", {"txn_id": withdrawn_txn, "reason_code": "duplicate"}
    )

    assert blocked.status_code == 409
    assert "already has an open dispute" in blocked.json()["error"]["message"]
    assert allowed.status_code == 201


@pytest.mark.parametrize(
    "overrides",
    [{"direction": "credit"}, {"status": "declined"}, {"status": "processing"}],
    ids=["credit", "declined", "in flight"],
)
async def test_a_transaction_that_cannot_be_disputed_is_a_conflict(
    api: AsyncClient, committed: psycopg.Connection, overrides: dict[str, Any]
) -> None:
    txn_id = _debit(committed, **overrides)

    response = await _raise(api, f"dsp-{txn_id}", {"txn_id": txn_id, "reason_code": "duplicate"})

    assert response.status_code == 409
    assert "cannot be disputed" in response.json()["error"]["message"]


async def test_disputing_more_than_the_transaction_is_an_invalid_argument(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    txn_id = _debit(committed)

    response = await _raise(
        api,
        f"dsp-{txn_id}",
        {"txn_id": txn_id, "reason_code": "amount_mismatch", "amount_paise": 250_001},
    )

    assert response.status_code == 400


async def test_a_refused_request_leaves_its_key_unused(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    txn_id = _debit(committed)
    key = f"dsp-{txn_id}"

    missing = await _raise(
        api, key, {"txn_id": new_id(IdPrefix.TRANSACTION), "reason_code": "duplicate"}
    )
    retried = await _raise(api, key, {"txn_id": txn_id, "reason_code": "duplicate"})

    assert (missing.status_code, retried.status_code) == (404, 201)
