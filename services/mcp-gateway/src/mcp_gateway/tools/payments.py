"""Payments tools: `get_account_summary`, `search_transactions`, `get_transaction` and
`get_spending_insights` (LLD §6).

Money stays integer paise end to end; each amount has a ``*_display`` string beside it for
people. The account number is never revealed, a counterparty's VPA needs aml:read, the
Customer's own VPA kyc:pii (it is often their mobile number), and a Transaction's device
and location are withheld without aml:read.
"""

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.server.context import Context
from pydantic import AwareDatetime, Field, computed_field

from kosha_domain.lifecycles import AccountStatus, CardStatus, TransactionStatus
from kosha_domain.money import format_inr
from kosha_domain.vocabulary import (
    Actor,
    CardNetwork,
    CardType,
    Channel,
    Direction,
    ModeOfOperation,
    ProductCode,
    Rail,
    TransactionType,
    VpaStatus,
)
from mcp_gateway.errors import InvalidArgumentError
from mcp_gateway.masking import AML_ONLY, AccountNumber, CounterpartyVpa, OwnVpa, mask
from mcp_gateway.runtime import core_api, cursors, principal
from mcp_gateway.tools.common import READ_ONLY, AccountId, TransactionId, View

MAX_WINDOW = timedelta(days=366)


class Card(View):
    card_id: str
    network: CardNetwork
    card_type: CardType
    pan_last4: str
    status: CardStatus
    expiry_month: int
    expiry_year: int
    atm_limit_paise: int
    pos_limit_paise: int
    ecom_limit_paise: int
    contactless_enabled: bool
    international_enabled: bool
    issued_at: datetime


class Vpa(View):
    vpa_id: str
    vpa: OwnVpa
    is_primary: bool
    status: VpaStatus
    created_at: datetime


class AccountSummary(View):
    account_id: str
    customer_id: str
    account_number: AccountNumber
    ifsc: str
    product_code: ProductCode
    status: AccountStatus
    status_reason: str | None
    mode_of_operation: ModeOfOperation
    opened_at: datetime
    closed_at: datetime | None
    ledger_balance_paise: int
    hold_amount_paise: int
    available_balance_paise: int
    """Ledger balance less holds: what the Customer can spend now."""
    minimum_balance_paise: int
    interest_rate_bps: int
    overdraft_limit_paise: int
    nominee_registered: bool
    last_txn_at: datetime | None
    cards: list[Card]
    """Newest first."""
    vpas: list[Vpa]
    """Primary first."""

    @computed_field
    @property
    def ledger_balance_display(self) -> str:
        return format_inr(self.ledger_balance_paise)

    @computed_field
    @property
    def available_balance_display(self) -> str:
        return format_inr(self.available_balance_paise)


class Transaction(View):
    txn_id: str
    account_id: str
    customer_id: str
    direction: Direction
    amount_paise: int
    currency: str
    rail: Rail
    txn_type: TransactionType
    status: TransactionStatus
    status_reason_code: str | None
    failure_reason_code: str | None
    hold_reason: str | None
    expected_credit_by: datetime | None
    utr: str | None
    rrn: str | None
    npci_txn_id: str | None
    counterparty_name: str | None
    counterparty_vpa: CounterpartyVpa | None
    counterparty_account_masked: str | None
    counterparty_ifsc: str | None
    merchant_id: str | None
    mcc: int | None
    channel: Channel
    geo_city: str | None
    narration: str
    remarks: str | None
    initiated_at: datetime
    posted_at: datetime | None
    value_date: date | None
    balance_after_paise: int | None
    risk_score: int | None
    is_flagged: bool

    @computed_field
    @property
    def amount_display(self) -> str:
        return format_inr(self.amount_paise)


class StatusChange(View):
    from_status: TransactionStatus | None
    to_status: TransactionStatus
    reason_code: str | None
    actor: Actor
    occurred_at: datetime


class TransactionDetail(Transaction):
    device_id: Annotated[str | None, AML_ONLY]
    ip_address: Annotated[str | None, AML_ONLY]
    geo_lat: Annotated[float | None, AML_ONLY]
    geo_lng: Annotated[float | None, AML_ONLY]
    status_history: list[StatusChange]
    """Oldest first."""


class _Position(View):
    initiated_at: datetime
    txn_id: str


class _Page(View):
    items: list[Transaction]
    next: _Position | None


class TransactionSearch(View):
    items: list[Transaction]
    """Newest first."""
    next_cursor: str | None = Field(
        description="Pass back with the same filters for the next page; null on the last."
    )


class CategorySpend(View):
    category: str
    debits_paise: int
    transactions: int

    @computed_field
    @property
    def debits_display(self) -> str:
        return format_inr(self.debits_paise)


class MonthlySpend(View):
    month: str
    """A Kolkata calendar month, ``YYYY-MM``."""
    credits_paise: int
    debits_paise: int
    categories: list[CategorySpend]
    """Debits by category, largest first."""

    @computed_field
    @property
    def credits_display(self) -> str:
        return format_inr(self.credits_paise)

    @computed_field
    @property
    def debits_display(self) -> str:
        return format_inr(self.debits_paise)


class SpendingInsights(View):
    account_id: str
    months: list[MonthlySpend]
    """Oldest first, ending with the current month; quiet months are zeros."""


async def get_account_summary(ctx: Context, account_id: AccountId) -> AccountSummary:
    """An Account's balances, cards and VPAs. The account number is always masked."""
    caller = await principal(ctx)
    summary = await core_api(ctx).get(
        caller.signed_as(), f"/v1/accounts/{account_id}", AccountSummary
    )
    return mask(summary, caller.scopes)


def _check(
    initiated_from: datetime | None,
    initiated_before: datetime | None,
    min_amount_paise: int | None,
    max_amount_paise: int | None,
) -> None:
    """Rules across arguments, checked before anything is asked of core-api."""
    if initiated_from is not None and initiated_before is not None:
        if initiated_before <= initiated_from:
            msg = "initiated_before must be later than initiated_from"
            raise InvalidArgumentError(msg)
        if initiated_before - initiated_from > MAX_WINDOW:
            msg = f"the window may span at most {MAX_WINDOW.days} days"
            raise InvalidArgumentError(msg)
    if (
        min_amount_paise is not None
        and max_amount_paise is not None
        and min_amount_paise > max_amount_paise
    ):
        msg = "min_amount_paise must not exceed max_amount_paise"
        raise InvalidArgumentError(msg)


async def search_transactions(
    ctx: Context,
    account_id: AccountId,
    *,
    initiated_from: Annotated[
        AwareDatetime | None,
        Field(description="Inclusive start, ISO 8601 with an offset; defaults to 90 days ago."),
    ] = None,
    initiated_before: Annotated[
        AwareDatetime | None,
        Field(description="Exclusive end; defaults to now. A window spans at most 366 days."),
    ] = None,
    direction: Direction | None = None,
    statuses: list[TransactionStatus] | None = None,
    rails: list[Rail] | None = None,
    min_amount_paise: Annotated[int | None, Field(gt=0)] = None,
    max_amount_paise: Annotated[int | None, Field(gt=0)] = None,
    text: Annotated[
        str | None, Field(min_length=3, max_length=100, description="Part of the narration.")
    ] = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 25,
    cursor: Annotated[
        str | None,
        Field(max_length=2048, description="next_cursor from the previous page."),
    ] = None,
) -> TransactionSearch:
    """An Account's Transactions, newest first, a page at a time.

    Counterparty VPAs are masked unless you hold aml:read. To read the next page, call
    again with the same filters and the previous page's next_cursor.
    """
    _check(initiated_from, initiated_before, min_amount_paise, max_amount_paise)
    caller = await principal(ctx)
    pages = cursors(ctx)
    filters: Mapping[str, Any] = {
        "account_id": account_id,
        "initiated_from": None if initiated_from is None else initiated_from.isoformat(),
        "initiated_before": None if initiated_before is None else initiated_before.isoformat(),
        "direction": direction,
        "status": sorted(statuses or []),
        "rail": sorted(rails or []),
        "min_amount_paise": min_amount_paise,
        "max_amount_paise": max_amount_paise,
        "text": text,
    }
    after = {} if cursor is None else pages.open(cursor, query=filters, sub=caller.sub)
    page = await core_api(ctx).get(
        caller.signed_as(),
        f"/v1/accounts/{account_id}/transactions",
        _Page,
        params={
            **{name: value for name, value in filters.items() if name != "account_id"},
            "limit": limit,
            "after_initiated_at": after.get("initiated_at"),
            "after_txn_id": after.get("txn_id"),
        },
    )
    next_cursor = (
        None
        if page.next is None
        else pages.issue(
            {"initiated_at": page.next.initiated_at.isoformat(), "txn_id": page.next.txn_id},
            query=filters,
            sub=caller.sub,
        )
    )
    return mask(TransactionSearch(items=page.items, next_cursor=next_cursor), caller.scopes)


async def get_transaction(ctx: Context, txn_id: TransactionId) -> TransactionDetail:
    """One Transaction with every status it passed through.

    Device and location are withheld, and the counterparty VPA masked, unless you hold
    aml:read.
    """
    caller = await principal(ctx)
    detail = await core_api(ctx).get(
        caller.signed_as(), f"/v1/transactions/{txn_id}", TransactionDetail
    )
    return mask(detail, caller.scopes)


async def get_spending_insights(
    ctx: Context,
    account_id: AccountId,
    months: Annotated[int, Field(ge=1, le=12, description="Kolkata months, ending now.")] = 6,
) -> SpendingInsights:
    """Credits, debits and debits by category for each month; aggregates only."""
    caller = await principal(ctx)
    return await core_api(ctx).get(
        caller.signed_as(),
        f"/v1/accounts/{account_id}/insights",
        SpendingInsights,
        params={"months": months},
    )


def register(mcp: FastMCP) -> None:
    mcp.tool(get_account_summary, title="Account summary", annotations=READ_ONLY)
    mcp.tool(search_transactions, title="Search transactions", annotations=READ_ONLY)
    mcp.tool(get_transaction, title="Transaction detail", annotations=READ_ONLY)
    mcp.tool(get_spending_insights, title="Spending insights", annotations=READ_ONLY)
