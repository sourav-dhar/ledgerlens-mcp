"""Closed vocabularies of the banking domain that are not status lifecycles.

Each enum is stored as a Postgres ``ENUM`` of the same values (plan v0.2 §1). Values are
lower snake case, and a parity test against the migrated database fails if the two drift.
"""

from enum import StrEnum

# --- Parties


class Gender(StrEnum):
    """Gender as recorded on Indian KYC documents."""

    FEMALE = "female"
    MALE = "male"
    TRANSGENDER = "transgender"


class Persona(StrEnum):
    """The behavioural archetype a Customer belongs to (see GLOSSARY: Persona)."""

    SALARIED = "salaried"
    STUDENT = "student"
    GIG_WORKER = "gig_worker"
    SME_OWNER = "sme_owner"
    NRI = "nri"
    SENIOR_CITIZEN = "senior_citizen"


class Segment(StrEnum):
    """The commercial tier a Customer is served in (see GLOSSARY: Segment)."""

    MASS = "mass"
    AFFLUENT = "affluent"
    PREMIUM = "premium"


class IncomeBand(StrEnum):
    """Declared annual income, in the lakh bands Indian onboarding forms use."""

    UP_TO_3_LAKH = "up_to_3_lakh"
    FROM_3_TO_6_LAKH = "3_to_6_lakh"
    FROM_6_TO_12_LAKH = "6_to_12_lakh"
    FROM_12_TO_25_LAKH = "12_to_25_lakh"
    FROM_25_TO_50_LAKH = "25_to_50_lakh"
    ABOVE_50_LAKH = "above_50_lakh"


class ResidentialStatus(StrEnum):
    RESIDENT = "resident"
    NRI = "nri"


class OnboardingChannel(StrEnum):
    """Where a Customer's relationship began."""

    APP = "app"
    WEB = "web"
    ASSISTED = "assisted"
    PARTNER = "partner"


class CustomerStatus(StrEnum):
    """A Customer's standing with the bank; Account and KYC statuses are separate lifecycles."""

    PROSPECT = "prospect"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    DORMANT = "dormant"
    FROZEN = "frozen"
    UNDER_INVESTIGATION = "under_investigation"
    DECEASED_CLAIM_PENDING = "deceased_claim_pending"
    CLOSED = "closed"


class RiskCategory(StrEnum):
    """KYC risk category; it sets the Re-KYC interval (see GLOSSARY: Risk category)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AddressType(StrEnum):
    PERMANENT = "permanent"
    CORRESPONDENCE = "correspondence"


class Actor(StrEnum):
    """Who or what caused a status change recorded in history."""

    SYSTEM = "system"
    CUSTOMER = "customer"
    STAFF = "staff"
    NPCI = "npci"
    RISK_ENGINE = "risk_engine"


# --- Accounts and money


class ProductCode(StrEnum):
    """The deposit product an Account is opened under."""

    SAVINGS_REGULAR = "savings_regular"
    SAVINGS_SALARY = "savings_salary"
    CURRENT = "current"
    FIXED_DEPOSIT = "fixed_deposit"
    RECURRING_DEPOSIT = "recurring_deposit"


class ModeOfOperation(StrEnum):
    SINGLE = "single"
    JOINT = "joint"


class GlAccount(StrEnum):
    """The general-ledger account a Posting lands in (see GLOSSARY: GL account).

    Customer Accounts are sub-ledgers of ``customer_deposits``; every other GL account is
    internal to the bank.
    """

    CUSTOMER_DEPOSITS = "customer_deposits"
    UPI_SETTLEMENT = "upi_settlement"
    IMPS_SETTLEMENT = "imps_settlement"
    NEFT_SETTLEMENT = "neft_settlement"
    RTGS_SETTLEMENT = "rtgs_settlement"
    CARD_SETTLEMENT = "card_settlement"
    ATM_SETTLEMENT = "atm_settlement"
    NACH_SETTLEMENT = "nach_settlement"
    FEE_INCOME = "fee_income"
    GST_PAYABLE = "gst_payable"
    INTEREST_EXPENSE = "interest_expense"
    SUSPENSE = "suspense"
    OPENING_BALANCES = "opening_balances"
    """Contra for balances brought forward from before Kosha's ledger went live."""

    @property
    def holds_customer_accounts(self) -> bool:
        """Whether a Posting to this GL account must name the customer Account it moves."""
        return self is GlAccount.CUSTOMER_DEPOSITS


# --- Payments


class Rail(StrEnum):
    """The payment network a Transaction travels on (see GLOSSARY: Rail)."""

    UPI = "upi"
    IMPS = "imps"
    NEFT = "neft"
    RTGS = "rtgs"
    CARD_POS = "card_pos"
    CARD_ECOM = "card_ecom"
    ATM = "atm"
    NACH = "nach"
    INTERNAL = "internal"


class Channel(StrEnum):
    """The touchpoint where a Transaction was initiated (see GLOSSARY: Channel)."""

    MOBILE_APP = "mobile_app"
    WEB = "web"
    POS = "pos"
    ATM = "atm"
    API = "api"


class Direction(StrEnum):
    """Whether a Transaction takes money out of the Account or brings it in."""

    DEBIT = "debit"
    CREDIT = "credit"


class TransactionType(StrEnum):
    """The economic purpose of a Transaction, independent of its Rail."""

    P2P = "p2p"
    P2M = "p2m"
    SALARY = "salary"
    EMI = "emi"
    BILL_PAY = "bill_pay"
    REFUND = "refund"
    REVERSAL = "reversal"
    CASH_WITHDRAWAL = "cash_withdrawal"
    INTEREST_CREDIT = "interest_credit"
    CHARGES = "charges"
    FD_BOOKING = "fd_booking"


class CardNetwork(StrEnum):
    RUPAY = "rupay"
    VISA = "visa"
    MASTERCARD = "mastercard"


class CardType(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"
    PREPAID = "prepaid"


class VpaStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEREGISTERED = "deregistered"


# --- Know your customer


class KycType(StrEnum):
    """How a KYC profile was verified (see GLOSSARY: Min-KYC, Full KYC, V-CIP)."""

    MIN_KYC = "min_kyc"
    FULL_KYC = "full_kyc"
    V_CIP = "v_cip"
    CKYC_DOWNLOAD = "ckyc_download"


class PanStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    NOT_AADHAAR_LINKED = "not_aadhaar_linked"


class OvdType(StrEnum):
    """Officially Valid Documents accepted as proof of address (see GLOSSARY: OVD)."""

    PASSPORT = "passport"
    VOTER_ID = "voter_id"
    DRIVING_LICENCE = "driving_licence"
    AADHAAR = "aadhaar"


class KycDocumentType(StrEnum):
    PAN_CARD = "pan_card"
    AADHAAR_MASKED = "aadhaar_masked"
    PASSPORT = "passport"
    SELFIE = "selfie"
    ADDRESS_PROOF = "address_proof"
    SIGNATURE = "signature"


class KycDocumentStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


# --- Financial crime


class Typology(StrEnum):
    """A recognised money-laundering or fraud pattern (see GLOSSARY: Typology)."""

    STRUCTURING = "structuring"
    RAPID_MOVEMENT = "rapid_movement"
    MULE_ACCOUNT = "mule_account"
    ROUND_TRIPPING = "round_tripping"
    DORMANT_REACTIVATION = "dormant_reactivation"
    HIGH_RISK_GEO = "high_risk_geo"
    VELOCITY = "velocity"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ListSource(StrEnum):
    """The (synthetic) watch list a Screening matched against."""

    UN_SC = "un_sc"
    OFAC_SDN = "ofac_sdn"
    MHA_UAPA = "mha_uapa"
    INTERNAL_PEP = "internal_pep"


class ScreeningDecision(StrEnum):
    CLEAR = "clear"
    POTENTIAL_MATCH = "potential_match"
    TRUE_MATCH = "true_match"


class DisputeReason(StrEnum):
    UNAUTHORISED = "unauthorised"
    GOODS_NOT_RECEIVED = "goods_not_received"
    DUPLICATE = "duplicate"
    AMOUNT_MISMATCH = "amount_mismatch"
    FAILED_BUT_DEBITED = "failed_but_debited"
    CREDIT_NOT_RECEIVED = "credit_not_received"


class ReviewPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


# --- Operations


class IdempotencyStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    DENIED = "denied"
    ERROR = "error"


# --- Knowledge


class Department(StrEnum):
    """The Kosha department that owns a Document (see GLOSSARY: Department)."""

    COMPLIANCE = "compliance"
    ONBOARDING = "onboarding"
    LEGAL = "legal"
    RISK = "risk"
    CUSTOMER_SUPPORT = "customer_support"
    SALES = "sales"
    MARKETING = "marketing"
    ENGINEERING = "engineering"
    COMPANY = "company"


class DocumentType(StrEnum):
    POLICY = "policy"
    SOP = "sop"
    RUNBOOK = "runbook"
    PLAYBOOK = "playbook"
    API_REFERENCE = "api_reference"
    GUIDELINE = "guideline"
    FAQ = "faq"
    TEMPLATE = "template"


class DocumentStatus(StrEnum):
    DRAFT = "draft"
    EFFECTIVE = "effective"
    SUPERSEDED = "superseded"


class Classification(StrEnum):
    """How sensitive a Document is, from least to most (see GLOSSARY: Classification).

    Declaration order is significant: the database enum keeps it, and row-level security
    lets a caller read chunks at or below their ceiling.
    """

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class SourceFormat(StrEnum):
    MD = "md"
    PDF = "pdf"
    DOCX = "docx"
    HTML = "html"
    OPENAPI = "openapi"
