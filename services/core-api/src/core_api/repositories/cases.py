"""Disputes, Transaction reviews, the Transactions they concern, and the outbox."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, LiteralString

from psycopg.types.json import Jsonb
from pydantic import BaseModel

from core_api.db import Connection
from core_api.schemas.cases import Dispute, TransactionReview
from kosha_domain.disputes import OPEN_DISPUTE_STATUSES
from kosha_domain.ids import IdPrefix, new_id
from kosha_domain.lifecycles import TRANSACTION_REVIEW, TransactionStatus
from kosha_domain.vocabulary import Direction, Rail

# Not yet decided: a review in one of these states blocks another on the same Transaction.
_OPEN_REVIEWS = [
    s.value for s in TRANSACTION_REVIEW.statuses if TRANSACTION_REVIEW.next_statuses(s)
]
_OPEN_DISPUTES = sorted(s.value for s in OPEN_DISPUTE_STATUSES)

# Locks the row, so two writes about one Transaction run one after the other and the
# second sees what the first decided.
_LOCK = """
    SELECT txn_id, initiated_at, customer_id, direction, status, rail, amount_paise
    FROM core.transactions
    WHERE txn_id = %s
    FOR UPDATE
"""

_INSERT_DISPUTE = """
    INSERT INTO ops.disputes (
        dispute_id, txn_id, txn_initiated_at, customer_id, reason_code, amount_paise,
        status, tat_due_at, idempotency_key, created_by
    ) VALUES (
        %(dispute_id)s, %(txn_id)s, %(txn_initiated_at)s, %(customer_id)s, %(reason_code)s,
        %(amount_paise)s, 'raised', %(tat_due_at)s, %(idempotency_key)s, %(created_by)s
    )
    RETURNING dispute_id, txn_id, txn_initiated_at, customer_id, reason_code, amount_paise,
              status, tat_due_at, compensation_paise, created_by, created_at
"""

_INSERT_REVIEW = """
    INSERT INTO ops.transaction_reviews (
        review_id, txn_id, txn_initiated_at, reason, priority, status, idempotency_key,
        created_by
    ) VALUES (
        %(review_id)s, %(txn_id)s, %(txn_initiated_at)s, %(reason)s, %(priority)s, 'queued',
        %(idempotency_key)s, %(created_by)s
    )
    RETURNING review_id, txn_id, txn_initiated_at, reason, priority, status, created_by,
              created_at
"""

_INSERT_EVENT = """
    INSERT INTO ops.outbox (event_id, aggregate_type, aggregate_id, event_type, payload)
    VALUES (%(event_id)s, %(aggregate_type)s, %(aggregate_id)s, %(event_type)s, %(payload)s)
"""


@dataclass(frozen=True, slots=True)
class LockedTransaction:
    """A Transaction held ``FOR UPDATE`` until the unit of work ends."""

    txn_id: str
    initiated_at: datetime
    customer_id: str
    direction: Direction
    status: TransactionStatus
    rail: Rail
    amount_paise: int


class CaseRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    async def lock_transaction(self, txn_id: str) -> LockedTransaction | None:
        row = await (await self._conn.execute(_LOCK, [txn_id])).fetchone()
        if row is None:
            return None
        return LockedTransaction(
            txn_id=row["txn_id"],
            initiated_at=row["initiated_at"],
            customer_id=row["customer_id"],
            direction=Direction(row["direction"]),
            status=TransactionStatus(row["status"]),
            rail=Rail(row["rail"]),
            amount_paise=row["amount_paise"],
        )

    async def _any(self, query: LiteralString, txn: LockedTransaction, statuses: list[str]) -> bool:
        cursor = await self._conn.execute(query, [txn.txn_id, txn.initiated_at, statuses])
        return await cursor.fetchone() is not None

    async def has_open_dispute(self, txn: LockedTransaction) -> bool:
        return await self._any(
            "SELECT 1 AS found FROM ops.disputes WHERE txn_id = %s"
            " AND txn_initiated_at = %s AND status::text = ANY(%s)",
            txn,
            _OPEN_DISPUTES,
        )

    async def has_open_review(self, txn: LockedTransaction) -> bool:
        return await self._any(
            "SELECT 1 AS found FROM ops.transaction_reviews WHERE txn_id = %s"
            " AND txn_initiated_at = %s AND status::text = ANY(%s)",
            txn,
            _OPEN_REVIEWS,
        )

    async def insert_dispute(self, values: dict[str, Any]) -> Dispute:
        params = values | {"dispute_id": new_id(IdPrefix.DISPUTE)}
        row = await (await self._conn.execute(_INSERT_DISPUTE, params)).fetchone()
        return Dispute.model_validate(row)

    async def insert_review(self, values: dict[str, Any]) -> TransactionReview:
        params = values | {"review_id": new_id(IdPrefix.TRANSACTION_REVIEW)}
        row = await (await self._conn.execute(_INSERT_REVIEW, params)).fetchone()
        return TransactionReview.model_validate(row)

    async def mark_flagged(self, txn: LockedTransaction) -> None:
        await self._conn.execute(
            "UPDATE core.transactions SET is_flagged = true"
            " WHERE txn_id = %s AND initiated_at = %s",
            [txn.txn_id, txn.initiated_at],
        )

    async def emit(
        self, *, aggregate_type: str, aggregate_id: str, event_type: str, payload: BaseModel
    ) -> None:
        """Append a domain event to the outbox; the relay publishes it after commit (ADR 0008)."""
        await self._conn.execute(
            _INSERT_EVENT,
            {
                "event_id": new_id(IdPrefix.OUTBOX_EVENT),
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "event_type": event_type,
                "payload": Jsonb(payload.model_dump(mode="json")),
            },
        )
