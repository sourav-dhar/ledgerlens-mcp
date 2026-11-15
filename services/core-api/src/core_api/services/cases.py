"""Raising a dispute and flagging a Transaction for review: one transaction each.

Each runs inside ``idempotent``: the key is claimed first, then the Transaction is locked,
the rules are checked, the case row and its outbox event are written, and the response is
stored, all in the caller's unit of work (LLD core-api §3).
"""

from core_api.db import Caller, Connection
from core_api.errors import ConflictError, InvalidArgumentError, NotFoundError
from core_api.repositories.cases import CaseRepository, LockedTransaction
from core_api.schemas.cases import Dispute, FlagTransaction, RaiseDispute, TransactionReview
from core_api.services.idempotency import Written, idempotent
from kosha_domain.disputes import is_disputable, turnaround


class CaseService:
    def __init__(self, conn: Connection, caller: Caller) -> None:
        self._conn = conn
        self._caller = caller
        self._cases = CaseRepository(conn)

    async def _locked(self, txn_id: str) -> LockedTransaction:
        txn = await self._cases.lock_transaction(txn_id)
        if txn is None:
            msg = f"transaction {txn_id} not found"
            raise NotFoundError(msg)
        return txn

    async def raise_dispute(self, key: str, request: RaiseDispute) -> Written[Dispute]:
        async def perform() -> Dispute:
            txn = await self._locked(request.txn_id)
            if not is_disputable(txn.direction, txn.status):
                msg = (
                    f"a {txn.direction.value} transaction that is {txn.status.value}"
                    " cannot be disputed"
                )
                raise ConflictError(msg)
            amount_paise = request.amount_paise or txn.amount_paise
            if amount_paise > txn.amount_paise:
                msg = f"amount_paise exceeds the transaction's {txn.amount_paise} paise"
                raise InvalidArgumentError(msg)
            if await self._cases.has_open_dispute(txn):
                msg = f"transaction {txn.txn_id} already has an open dispute"
                raise ConflictError(msg)
            dispute = await self._cases.insert_dispute(
                {
                    "txn_id": txn.txn_id,
                    "txn_initiated_at": txn.initiated_at,
                    "customer_id": txn.customer_id,
                    "reason_code": request.reason_code.value,
                    "amount_paise": amount_paise,
                    "tat_due_at": txn.initiated_at + turnaround(txn.rail),
                    "idempotency_key": key,
                    "created_by": self._caller.actor,
                }
            )
            await self._cases.emit(
                aggregate_type="dispute",
                aggregate_id=dispute.dispute_id,
                event_type="DisputeRaised",
                payload=dispute,
            )
            return dispute

        return await idempotent(
            self._conn,
            scope="raise_dispute",
            key=key,
            actor=self._caller.actor,
            request=request,
            result=Dispute,
            perform=perform,
        )

    async def flag_transaction(
        self, key: str, request: FlagTransaction
    ) -> Written[TransactionReview]:
        async def perform() -> TransactionReview:
            txn = await self._locked(request.txn_id)
            if await self._cases.has_open_review(txn):
                msg = f"transaction {txn.txn_id} is already queued for review"
                raise ConflictError(msg)
            review = await self._cases.insert_review(
                {
                    "txn_id": txn.txn_id,
                    "txn_initiated_at": txn.initiated_at,
                    "reason": request.reason,
                    "priority": request.priority.value,
                    "idempotency_key": key,
                    "created_by": self._caller.actor,
                }
            )
            await self._cases.mark_flagged(txn)
            await self._cases.emit(
                aggregate_type="transaction_review",
                aggregate_id=review.review_id,
                event_type="TransactionFlagged",
                payload=review,
            )
            return review

        return await idempotent(
            self._conn,
            scope="flag_transaction",
            key=key,
            actor=self._caller.actor,
            request=request,
            result=TransactionReview,
            perform=perform,
        )
