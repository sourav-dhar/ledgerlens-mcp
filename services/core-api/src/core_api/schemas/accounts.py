"""Accounts and Transactions as the API returns them. Values are unmasked: the gateway masks."""

from datetime import date, datetime

from pydantic import BaseModel

from kosha_domain.lifecycles import AccountStatus, CardStatus, TransactionStatus
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


class Card(BaseModel):
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


class Vpa(BaseModel):
    vpa_id: str
    vpa: str
    is_primary: bool
    status: VpaStatus
    created_at: datetime


class AccountSummary(BaseModel):
    account_id: str
    customer_id: str
    account_number: str
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


class Transaction(BaseModel):
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
    counterparty_vpa: str | None
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


class StatusChange(BaseModel):
    from_status: TransactionStatus | None
    to_status: TransactionStatus
    reason_code: str | None
    actor: Actor
    occurred_at: datetime


class TransactionDetail(Transaction):
    device_id: str | None
    ip_address: str | None
    geo_lat: float | None
    geo_lng: float | None
    status_history: list[StatusChange]
    """Oldest first."""


class KeysetPosition(BaseModel):
    """The last row of a page; pass it back as ``after_*`` to read the next one."""

    initiated_at: datetime
    txn_id: str


class TransactionPage(BaseModel):
    items: list[Transaction]
    """Newest first: by ``initiated_at``, then ``txn_id``, both descending."""
    next: KeysetPosition | None
    """``None`` on the last page."""
