"""`/v1/accounts`: an Account's summary, and a search over its Transactions."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from core_api.deps import CallerDep, DatabaseDep, checked_id, require
from core_api.errors import InvalidArgumentError, NotFoundError
from core_api.repositories.accounts import AccountRepository, TransactionSearch
from core_api.schemas.accounts import AccountSummary, KeysetPosition, TransactionPage
from kosha_domain.ids import IdPrefix
from kosha_domain.lifecycles import TransactionStatus
from kosha_domain.vocabulary import Direction, Rail

router = APIRouter(prefix="/v1/accounts", tags=["accounts"])

DEFAULT_WINDOW = timedelta(days=90)
MAX_WINDOW = timedelta(days=366)

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"description": "Invalid argument"},
    404: {"description": "No such Account"},
    503: {"description": "Database unavailable; retry shortly"},
    504: {"description": "Deadline exceeded"},
}


@router.get("/{account_id}", summary="Get an Account's summary", responses=_ERRORS)
async def get_account(account_id: str, caller: CallerDep, database: DatabaseDep) -> AccountSummary:
    """Balances, cards (newest first) and VPAs (primary first)."""
    checked_id(account_id, IdPrefix.ACCOUNT, name="account_id")
    async with require(database).unit_of_work(caller, read_only=True) as conn:
        summary = await AccountRepository(conn).summary(account_id)
    if summary is None:
        msg = f"account {account_id} not found"
        raise NotFoundError(msg)
    return summary


def _search(
    account_id: str,
    *,
    now: datetime,
    initiated_from: datetime | None,
    initiated_before: datetime | None,
    min_amount_paise: int | None,
    max_amount_paise: int | None,
    after_initiated_at: datetime | None,
    after_txn_id: str | None,
) -> tuple[datetime, KeysetPosition | None]:
    """Checks the criteria that relate to each other; returns the window start and position."""
    start = initiated_from or now - DEFAULT_WINDOW
    end = initiated_before or now
    if end <= start:
        msg = "initiated_before must be later than initiated_from"
        raise InvalidArgumentError(msg)
    if end - start > MAX_WINDOW:
        msg = f"the window may span at most {MAX_WINDOW.days} days"
        raise InvalidArgumentError(msg)
    if (
        min_amount_paise is not None
        and max_amount_paise is not None
        and min_amount_paise > max_amount_paise
    ):
        msg = "min_amount_paise must not exceed max_amount_paise"
        raise InvalidArgumentError(msg)
    if (after_initiated_at is None) != (after_txn_id is None):
        msg = "after_initiated_at and after_txn_id go together"
        raise InvalidArgumentError(msg)
    checked_id(account_id, IdPrefix.ACCOUNT, name="account_id")
    if after_initiated_at is None or after_txn_id is None:
        return start, None
    checked_id(after_txn_id, IdPrefix.TRANSACTION, name="after_txn_id")
    return start, KeysetPosition(initiated_at=after_initiated_at, txn_id=after_txn_id)


@router.get(
    "/{account_id}/transactions", summary="Search an Account's Transactions", responses=_ERRORS
)
async def search_transactions(
    account_id: str,
    *,
    caller: CallerDep,
    database: DatabaseDep,
    initiated_from: Annotated[
        AwareDatetime | None,
        Query(description="Inclusive start; defaults to 90 days ago. Windows span ≤ 366 days."),
    ] = None,
    initiated_before: Annotated[
        AwareDatetime | None, Query(description="Exclusive end; defaults to now.")
    ] = None,
    direction: Direction | None = None,
    status: Annotated[list[TransactionStatus] | None, Query()] = None,
    rail: Annotated[list[Rail] | None, Query()] = None,
    min_amount_paise: Annotated[int | None, Query(gt=0)] = None,
    max_amount_paise: Annotated[int | None, Query(gt=0)] = None,
    text: Annotated[
        str | None, Query(min_length=3, max_length=100, description="Part of the narration.")
    ] = None,
    after_initiated_at: Annotated[
        AwareDatetime | None, Query(description="From the previous page's `next`.")
    ] = None,
    after_txn_id: Annotated[
        str | None, Query(description="From the previous page's `next`.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> TransactionPage:
    """Transactions newest first, a page at a time (keyset on `initiated_at`, `txn_id`)."""
    start, after = _search(
        account_id,
        now=datetime.now(UTC),
        initiated_from=initiated_from,
        initiated_before=initiated_before,
        min_amount_paise=min_amount_paise,
        max_amount_paise=max_amount_paise,
        after_initiated_at=after_initiated_at,
        after_txn_id=after_txn_id,
    )
    search = TransactionSearch(
        account_id=account_id,
        initiated_from=start,
        initiated_before=initiated_before,
        direction=direction,
        statuses=status or (),
        rails=rail or (),
        min_amount_paise=min_amount_paise,
        max_amount_paise=max_amount_paise,
        text=text,
        after=after,
    )
    async with require(database).unit_of_work(caller, read_only=True) as conn:
        accounts = AccountRepository(conn)
        if not await accounts.exists(account_id):
            msg = f"account {account_id} not found"
            raise NotFoundError(msg)
        return await accounts.search(search, limit=limit)
