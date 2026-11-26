"""Write tools end to end: what an agreed write leaves in Postgres, and what a refused one does not.

Unit tests prove the confirmation in both protocol eras; these prove the writes themselves on
real rows: a dispute and its outbox event are written once however often the call is retried
with its key, a declined write leaves nothing behind, and a flag marks the Transaction.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, LiteralString
from uuid import uuid4

import db_rows as rows
import httpx
import psycopg
import pytest
from fastapi import FastAPI
from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult
from gateway_harness import access_token, gateway

from mcp_gateway.auth.scopes import Role

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

NOW = datetime.now(UTC).replace(microsecond=0)


async def _yes(*_: Any) -> ElicitResult[dict[str, bool]]:
    return ElicitResult(action="accept", content={"value": True})


async def _no(*_: Any) -> ElicitResult[dict[str, bool]]:
    return ElicitResult(action="decline")


@pytest.fixture
def txn_id(committed: psycopg.Connection) -> str:
    """A debit of ₹2,500 three hours ago, on its own Customer's Account."""
    customer_id = rows.customer(committed)
    account_id = rows.account(committed, customer_id)
    return rows.transaction(
        committed,
        account_id,
        customer_id,
        initiated_at=NOW - timedelta(hours=3),
        amount_paise=250_000,
    )[0]


async def _call(app: FastAPI, role: Role, tool: str, args: dict[str, Any], user: Any = _yes) -> Any:
    transport = httpx.ASGITransport(app=app)
    async with Client(gateway(transport, access_token(role)), elicitation_handler=user) as client:
        return await client.call_tool(tool, args, raise_on_error=False)


def _count(db: psycopg.Connection, query: LiteralString, txn_id: str) -> int:
    row = db.execute(query, [txn_id]).fetchone()
    assert row is not None
    return row[0]


DISPUTES: LiteralString = "SELECT count(*) FROM ops.disputes WHERE txn_id = %s"
DISPUTE_EVENTS: LiteralString = (
    "SELECT count(*) FROM ops.outbox"
    " WHERE event_type = 'DisputeRaised' AND payload ->> 'txn_id' = %s"
)


async def test_a_retried_dispute_is_written_once_with_one_event(
    core_api_app: FastAPI, committed: psycopg.Connection, txn_id: str
) -> None:
    args = {"txn_id": txn_id, "reason_code": "failed_but_debited", "idempotency_key": str(uuid4())}

    first = await _call(core_api_app, Role.SUPPORT_AGENT, "raise_dispute", args)
    retry = await _call(core_api_app, Role.SUPPORT_AGENT, "raise_dispute", args)

    assert not first.is_error, first.content
    assert not retry.is_error, retry.content
    raised, replayed = first.structured_content, retry.structured_content
    assert (raised["status"], raised["amount_display"], raised["replayed"]) == (
        "raised",
        "₹2,500.00",
        False,
    )
    assert raised["created_by"] == "staff-0042", "core-api records who the gateway signed for"
    assert (replayed["dispute_id"], replayed["replayed"]) == (raised["dispute_id"], True)
    assert _count(committed, DISPUTES, txn_id) == 1
    assert _count(committed, DISPUTE_EVENTS, txn_id) == 1


async def test_a_declined_dispute_leaves_nothing_behind(
    core_api_app: FastAPI, committed: psycopg.Connection, txn_id: str
) -> None:
    args = {"txn_id": txn_id, "reason_code": "unauthorised", "idempotency_key": str(uuid4())}

    result = await _call(core_api_app, Role.SUPPORT_AGENT, "raise_dispute", args, user=_no)

    assert result.is_error
    assert result.structured_content["error"]["code"] == "declined"
    assert _count(committed, DISPUTES, txn_id) == 0
    assert _count(committed, DISPUTE_EVENTS, txn_id) == 0


async def test_a_flag_marks_the_transaction_and_tells_the_review_queue(
    core_api_app: FastAPI, committed: psycopg.Connection, txn_id: str
) -> None:
    args = {
        "txn_id": txn_id,
        "reason": "Five round-amount credits from new payees in an hour",
        "priority": "urgent",
        "idempotency_key": str(uuid4()),
    }

    result = await _call(core_api_app, Role.ANALYST, "flag_transaction_for_review", args)

    assert not result.is_error, result.content
    review = result.structured_content
    assert (review["status"], review["priority"]) == ("queued", "urgent")
    flagged = committed.execute(
        "SELECT is_flagged FROM core.transactions WHERE txn_id = %s", [txn_id]
    ).fetchone()
    assert flagged == (True,)
    event = committed.execute(
        "SELECT payload ->> 'txn_id' FROM ops.outbox"
        " WHERE event_type = 'TransactionFlagged' AND aggregate_id = %s",
        [review["review_id"]],
    ).fetchone()
    assert event == (txn_id,)
