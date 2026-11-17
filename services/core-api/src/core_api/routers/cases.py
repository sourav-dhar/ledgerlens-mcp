"""`/v1/disputes` and `/v1/reviews`: the two idempotent writes (ADR 0007)."""

from typing import Annotated, Any

from fastapi import APIRouter, Header, Response

from core_api.deps import CallerDep, DatabaseDep, checked_id, require
from core_api.schemas.cases import Dispute, FlagTransaction, RaiseDispute, TransactionReview
from core_api.services.cases import CaseService
from kosha_domain.ids import IdPrefix

router = APIRouter(tags=["cases"])

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        pattern=r"^[\x21-\x7e]{1,255}$",
        description="Client-chosen, unique per intended write; a retry reuses it. Kept 24 h.",
    ),
]

_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Replay: the stored response to an earlier request with this key,"
        " marked `Idempotent-Replayed: true`"
    },
    400: {"description": "Invalid argument"},
    404: {"description": "No such Transaction"},
    409: {
        "description": "Key reused for a different request, or the Transaction's state forbids it"
    },
    503: {"description": "Database unavailable; retry shortly with the same key"},
    504: {"description": "Deadline exceeded; retry with the same key"},
}


@router.post("/v1/disputes", status_code=201, summary="Raise a dispute", responses=_RESPONSES)
async def raise_dispute(
    body: RaiseDispute,
    response: Response,
    idempotency_key: IdempotencyKey,
    caller: CallerDep,
    database: DatabaseDep,
) -> Dispute:
    """Open a dispute on a debit, due back by the rail's RBI turnaround time."""
    checked_id(body.txn_id, IdPrefix.TRANSACTION, name="txn_id")
    async with require(database).unit_of_work(caller) as conn:
        written = await CaseService(conn, caller).raise_dispute(idempotency_key, body)
    if written.replayed:
        response.status_code = 200
        response.headers["Idempotent-Replayed"] = "true"
    return written.value


@router.post(
    "/v1/reviews",
    status_code=201,
    summary="Flag a Transaction for review",
    responses=_RESPONSES,
)
async def flag_transaction(
    body: FlagTransaction,
    response: Response,
    idempotency_key: IdempotencyKey,
    caller: CallerDep,
    database: DatabaseDep,
) -> TransactionReview:
    """Queue a review, mark the Transaction flagged, and tell the review queue."""
    checked_id(body.txn_id, IdPrefix.TRANSACTION, name="txn_id")
    async with require(database).unit_of_work(caller) as conn:
        written = await CaseService(conn, caller).flag_transaction(idempotency_key, body)
    if written.replayed:
        response.status_code = 200
        response.headers["Idempotent-Replayed"] = "true"
    return written.value
