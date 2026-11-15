"""`/v1/accounts/{account_id}/insights`: where an Account's money went, month by month."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query

from core_api.deps import CallerDep, DatabaseDep, checked_id, require
from core_api.errors import NotFoundError
from core_api.repositories.accounts import AccountRepository
from core_api.repositories.insights import InsightsRepository, month_starts
from core_api.schemas.insights import SpendingInsights
from kosha_domain.ids import IdPrefix

router = APIRouter(prefix="/v1/accounts", tags=["insights"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"description": "Invalid argument"},
    404: {"description": "No such Account"},
    503: {"description": "Database unavailable; retry shortly"},
    504: {"description": "Deadline exceeded"},
}


@router.get("/{account_id}/insights", summary="Get spending insights", responses=_ERRORS)
async def get_spending_insights(
    account_id: str,
    caller: CallerDep,
    database: DatabaseDep,
    months: Annotated[int, Query(ge=1, le=12, description="Kolkata months, ending now.")] = 6,
) -> SpendingInsights:
    """Credits, debits and debits by category for each month; posted Transactions only."""
    checked_id(account_id, IdPrefix.ACCOUNT, name="account_id")
    starts = month_starts(datetime.now(UTC), months)
    async with require(database).unit_of_work(caller, read_only=True) as conn:
        if not await AccountRepository(conn).exists(account_id):
            msg = f"account {account_id} not found"
            raise NotFoundError(msg)
        monthly = await InsightsRepository(conn).monthly(account_id, starts)
    return SpendingInsights(account_id=account_id, months=monthly)
