"""Flagging a Transaction queues a review, marks the Transaction and emits an event, once."""

from datetime import UTC, datetime, timedelta
from typing import Any

import db_rows as rows
import psycopg
import pytest
from httpx import AsyncClient, Response

from kosha_domain.ids import IdPrefix, new_id

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

NOW = datetime.now(UTC).replace(microsecond=0)
REASON = "Five UPI debits to new payees within ten minutes"


def _txn(db: psycopg.Connection) -> tuple[str, datetime]:
    customer_id = rows.customer(db)
    account_id = rows.account(db, customer_id)
    return rows.transaction(db, account_id, customer_id, initiated_at=NOW - timedelta(hours=1))


async def _flag(api: AsyncClient, key: str, body: dict[str, Any]) -> Response:
    return await api.post("/v1/reviews", json=body, headers={"Idempotency-Key": key})


async def test_flagging_queues_a_review_marks_the_transaction_and_emits_an_event(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    txn_id, _ = _txn(committed)

    response = await _flag(
        api, f"rev-{txn_id}", {"txn_id": txn_id, "reason": REASON, "priority": "urgent"}
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["status"], body["priority"], body["reason"], body["created_by"]) == (
        "queued",
        "urgent",
        REASON,
        "staff-0042",
    )
    flagged = committed.execute(
        "SELECT is_flagged FROM core.transactions WHERE txn_id = %s", [txn_id]
    ).fetchone()
    assert flagged == (True,)
    event = committed.execute(
        "SELECT aggregate_type, payload ->> 'txn_id' FROM ops.outbox"
        " WHERE event_type = 'TransactionFlagged' AND aggregate_id = %s",
        [body["review_id"]],
    ).fetchone()
    assert event == ("transaction_review", txn_id)


async def test_the_priority_defaults_to_normal(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    txn_id, _ = _txn(committed)

    response = await _flag(api, f"rev-{txn_id}", {"txn_id": txn_id, "reason": REASON})

    assert response.json()["priority"] == "normal"


async def test_a_retry_replays_the_first_response(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    txn_id, _ = _txn(committed)
    request = {"txn_id": txn_id, "reason": REASON}

    first = await _flag(api, f"rev-{txn_id}", request)
    again = await _flag(api, f"rev-{txn_id}", request)

    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json() == first.json()
    assert again.headers["Idempotent-Replayed"] == "true"
    assert "Idempotent-Replayed" not in first.headers
    reviews = committed.execute(
        "SELECT count(*) FROM ops.transaction_reviews WHERE txn_id = %s", [txn_id]
    ).fetchone()
    assert reviews == (1,)


async def test_an_open_review_blocks_another_but_a_cleared_one_does_not(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    open_txn, cleared_txn = _txn(committed), _txn(committed)
    rows.review(committed, open_txn, status="in_review")
    rows.review(committed, cleared_txn, status="cleared")

    blocked = await _flag(api, f"x-{open_txn[0]}", {"txn_id": open_txn[0], "reason": REASON})
    allowed = await _flag(api, f"x-{cleared_txn[0]}", {"txn_id": cleared_txn[0], "reason": REASON})

    assert blocked.status_code == 409
    assert "already queued for review" in blocked.json()["error"]["message"]
    assert allowed.status_code == 201


async def test_an_unknown_transaction_is_not_found(api: AsyncClient) -> None:
    txn_id = new_id(IdPrefix.TRANSACTION)

    response = await _flag(api, f"rev-{txn_id}", {"txn_id": txn_id, "reason": REASON})

    assert response.status_code == 404
