"""`/v1/transactions`: one Transaction with its status history."""

from typing import Any

from fastapi import APIRouter

from core_api.deps import CallerDep, DatabaseDep, checked_id, require
from core_api.errors import NotFoundError
from core_api.repositories.accounts import AccountRepository
from core_api.schemas.accounts import TransactionDetail
from kosha_domain.ids import IdPrefix

router = APIRouter(prefix="/v1/transactions", tags=["transactions"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"description": "Invalid argument"},
    404: {"description": "No such Transaction"},
    503: {"description": "Database unavailable; retry shortly"},
    504: {"description": "Deadline exceeded"},
}


@router.get("/{txn_id}", summary="Get a Transaction", responses=_ERRORS)
async def get_transaction(
    txn_id: str, caller: CallerDep, database: DatabaseDep
) -> TransactionDetail:
    """The Transaction, its device and location, and every status it passed through."""
    checked_id(txn_id, IdPrefix.TRANSACTION, name="txn_id")
    async with require(database).unit_of_work(caller, read_only=True) as conn:
        detail = await AccountRepository(conn).transaction(txn_id)
    if detail is None:
        msg = f"transaction {txn_id} not found"
        raise NotFoundError(msg)
    return detail
