"""One row type per table, its fields named and ordered as the table's columns.

These are the generator's output contract with the migrations: the loader copies each tuple
as-is, so a field here that the table lacks (or a misspelt name) fails the first load.
Generated columns (``available_balance_paise``) are left to the database.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, NamedTuple

from kosha_domain.lifecycles import (
    AccountStatus,
    AmlAlertStatus,
    BeneficiaryStatus,
    CardStatus,
    DisputeStatus,
    KycStatus,
    TransactionReviewStatus,
    TransactionStatus,
)
from kosha_domain.vocabulary import (
    Actor,
    AddressType,
    CardNetwork,
    CardType,
    Channel,
    CustomerStatus,
    Direction,
    DisputeReason,
    Gender,
    GlAccount,
    IncomeBand,
    KycDocumentStatus,
    KycDocumentType,
    KycType,
    ListSource,
    ModeOfOperation,
    OnboardingChannel,
    OvdType,
    PanStatus,
    Persona,
    ProductCode,
    Rail,
    ResidentialStatus,
    ReviewPriority,
    RiskCategory,
    ScreeningDecision,
    Segment,
    Severity,
    TransactionType,
    Typology,
    VpaStatus,
)

# --- core


class Customer(NamedTuple):
    customer_id: str
    cif_number: str
    first_name: str
    middle_name: str | None
    last_name: str
    date_of_birth: date
    gender: Gender
    email: str | None
    mobile: str
    mobile_verified: bool
    persona: Persona
    occupation: str | None
    employer_name: str | None
    annual_income_band: IncomeBand | None
    segment: Segment
    residential_status: ResidentialStatus
    preferred_language: str
    onboarding_channel: OnboardingChannel
    relationship_start_date: date
    status: CustomerStatus
    risk_category: RiskCategory
    created_at: datetime
    updated_at: datetime


class Address(NamedTuple):
    address_id: str
    customer_id: str
    address_type: AddressType
    line1: str
    line2: str | None
    city: str
    district: str | None
    state: str
    state_code: str
    pincode: str
    country: str
    is_verified: bool
    valid_from: date
    valid_to: date | None


class Account(NamedTuple):
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
    minimum_balance_paise: int
    interest_rate_bps: int
    overdraft_limit_paise: int
    nominee_registered: bool
    last_txn_at: datetime | None


class Card(NamedTuple):
    card_id: str
    account_id: str
    network: CardNetwork
    card_type: CardType
    pan_last4: str
    token_ref: str
    status: CardStatus
    expiry_month: int
    expiry_year: int
    atm_limit_paise: int
    pos_limit_paise: int
    ecom_limit_paise: int
    contactless_enabled: bool
    international_enabled: bool
    issued_at: datetime


class Vpa(NamedTuple):
    vpa_id: str
    customer_id: str
    account_id: str
    vpa: str
    is_primary: bool
    status: VpaStatus
    created_at: datetime


class Beneficiary(NamedTuple):
    beneficiary_id: str
    customer_id: str
    nickname: str
    account_number_masked: str
    ifsc: str
    bank_name: str
    added_at: datetime
    cooling_period_ends_at: datetime
    status: BeneficiaryStatus


class Merchant(NamedTuple):
    merchant_id: str
    display_name: str
    legal_name: str
    mcc: int
    category: str
    sub_category: str | None
    city: str
    state: str
    vpa: str | None
    gstin: str | None
    acquirer_bank: str
    risk_level: RiskCategory


class Transaction(NamedTuple):
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
    device_id: str | None
    ip_address: str | None
    geo_city: str | None
    geo_lat: Decimal | None
    geo_lng: Decimal | None
    narration: str
    remarks: str | None
    initiated_at: datetime
    posted_at: datetime | None
    value_date: date | None
    balance_after_paise: int | None
    risk_score: int | None
    is_flagged: bool


class TransactionStatusChange(NamedTuple):
    history_id: str
    txn_id: str
    txn_initiated_at: datetime
    from_status: TransactionStatus | None
    to_status: TransactionStatus
    reason_code: str | None
    actor: Actor
    occurred_at: datetime


# --- ledger


class JournalEntry(NamedTuple):
    entry_id: str
    txn_id: str | None
    txn_initiated_at: datetime | None
    posted_at: datetime
    description: str


class Posting(NamedTuple):
    posting_id: str
    entry_id: str
    gl_account: GlAccount
    account_id: str | None
    amount_paise: int


# --- kyc


class KycProfile(NamedTuple):
    kyc_id: str
    customer_id: str
    kyc_type: KycType
    kyc_status: KycStatus
    ckyc_number: str | None
    pan_token: str | None
    pan_last4: str | None
    pan_status: PanStatus | None
    pan_name_match_score: Decimal | None
    aadhaar_ref_token: str | None
    aadhaar_last4: str | None
    ovd_type: OvdType | None
    vcip_session_id: str | None
    vcip_agent_id: str | None
    liveness_score: Decimal | None
    face_match_score: Decimal | None
    vcip_geo_lat: Decimal | None
    vcip_geo_lng: Decimal | None
    pep_flag: bool
    sanctions_flag: bool
    fatca_crs_declared: bool
    risk_category: RiskCategory
    risk_rationale: str | None
    verified_at: datetime | None
    verified_by: str | None
    next_review_due: date | None
    created_at: datetime


class KycDocument(NamedTuple):
    document_id: str
    kyc_id: str
    customer_id: str
    doc_type: KycDocumentType
    s3_key: str
    sha256: str
    status: KycDocumentStatus
    rejection_reason: str | None
    uploaded_at: datetime
    expires_on: date | None


class KycEvent(NamedTuple):
    event_id: str
    kyc_id: str
    from_status: KycStatus | None
    to_status: KycStatus
    actor: Actor
    reason: str | None
    occurred_at: datetime


# --- risk


class AmlRule(NamedTuple):
    rule_id: str
    name: str
    typology: Typology
    params: dict[str, Any]
    severity: Severity
    enabled: bool


class AmlAlert(NamedTuple):
    alert_id: str
    customer_id: str
    rule_id: str
    typology: Typology
    score: Decimal
    status: AmlAlertStatus
    assigned_to: str | None
    sla_due_at: datetime
    triggering_txn_ids: list[str]
    narrative: str | None
    disposition: str | None
    str_reference: str | None
    created_at: datetime
    closed_at: datetime | None


class ScreeningResult(NamedTuple):
    screening_id: str
    customer_id: str
    screened_name: str
    list_source: ListSource
    match_score: Decimal
    decision: ScreeningDecision
    vendor_ref: str | None
    screened_at: datetime


# --- ops


class Dispute(NamedTuple):
    dispute_id: str
    txn_id: str
    txn_initiated_at: datetime
    customer_id: str
    reason_code: DisputeReason
    amount_paise: int
    status: DisputeStatus
    tat_due_at: datetime
    compensation_paise: int
    resolution: str | None
    chargeback_ref: str | None
    idempotency_key: str | None
    created_by: str
    created_at: datetime


class TransactionReview(NamedTuple):
    review_id: str
    txn_id: str
    txn_initiated_at: datetime
    reason: str
    priority: ReviewPriority
    status: TransactionReviewStatus
    idempotency_key: str | None
    created_by: str
    created_at: datetime
