"""Minimal valid rows for integration tests; each helper returns the new row's key.

Keyword overrides replace column values, so a test states only what it is about.
"""

from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg import sql

from kosha_domain.ids import IdPrefix, new_id

NOW = datetime.now(UTC)


def insert(db: psycopg.Connection, table: str, values: dict[str, Any]) -> None:
    schema, name = table.split(".")
    statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(schema, name),
        sql.SQL(", ").join(map(sql.Identifier, values)),
        sql.SQL(", ").join(sql.Placeholder() * len(values)),
    )
    db.execute(statement, list(values.values()))


def customer(db: psycopg.Connection, **overrides: Any) -> str:
    customer_id = overrides.get("customer_id", new_id(IdPrefix.CUSTOMER))
    values: dict[str, Any] = {
        "customer_id": customer_id,
        "cif_number": customer_id[-10:].translate(_DIGITS),
        "first_name": "Ravi",
        "last_name": "Kumar",
        "date_of_birth": "1990-04-12",
        "gender": "male",
        "mobile": "9876543210",
        "persona": "salaried",
        "segment": "mass",
        "residential_status": "resident",
        "onboarding_channel": "app",
        "relationship_start_date": "2024-01-15",
        "status": "active",
        "risk_category": "low",
    } | overrides
    insert(db, "core.customers", values)
    return values["customer_id"]


def account(db: psycopg.Connection, customer_id: str, **overrides: Any) -> str:
    account_id = overrides.get("account_id", new_id(IdPrefix.ACCOUNT))
    values: dict[str, Any] = {
        "account_id": account_id,
        "customer_id": customer_id,
        "account_number": account_id[-14:].translate(_DIGITS),
        "ifsc": "KOSH0000001",
        "product_code": "savings_regular",
        "status": "active",
        "mode_of_operation": "single",
        "opened_at": NOW,
    } | overrides
    insert(db, "core.accounts", values)
    return values["account_id"]


def transaction(
    db: psycopg.Connection, account_id: str, customer_id: str, **overrides: Any
) -> tuple[str, datetime]:
    values: dict[str, Any] = {
        "txn_id": new_id(IdPrefix.TRANSACTION),
        "account_id": account_id,
        "customer_id": customer_id,
        "direction": "debit",
        "amount_paise": 25_000,
        "rail": "upi",
        "txn_type": "p2m",
        "status": "success",
        "channel": "mobile_app",
        "narration": "UPI/DR/412345678901/QUICKBASKET/qb@axis/Payment",
        "initiated_at": NOW,
    } | overrides
    insert(db, "core.transactions", values)
    return values["txn_id"], values["initiated_at"]


def status_change(db: psycopg.Connection, txn: tuple[str, datetime], **overrides: Any) -> str:
    values: dict[str, Any] = {
        "history_id": new_id(IdPrefix.TRANSACTION_STATUS_CHANGE),
        "txn_id": txn[0],
        "txn_initiated_at": txn[1],
        "to_status": "success",
        "actor": "npci",
        "occurred_at": txn[1],
    } | overrides
    insert(db, "core.transaction_status_history", values)
    return values["history_id"]


def journal_entry(
    db: psycopg.Connection, txn: tuple[str, datetime] | None = None, **overrides: Any
) -> str:
    values: dict[str, Any] = {
        "entry_id": new_id(IdPrefix.JOURNAL_ENTRY),
        "txn_id": txn[0] if txn else None,
        "txn_initiated_at": txn[1] if txn else None,
        "posted_at": NOW,
        "description": "UPI payment",
    } | overrides
    insert(db, "ledger.journal_entries", values)
    return values["entry_id"]


def posting(
    db: psycopg.Connection, entry_id: str, gl_account: str, amount_paise: int, **overrides: Any
) -> str:
    values: dict[str, Any] = {
        "posting_id": new_id(IdPrefix.POSTING),
        "entry_id": entry_id,
        "gl_account": gl_account,
        "amount_paise": amount_paise,
    } | overrides
    insert(db, "ledger.postings", values)
    return values["posting_id"]


def kyc_profile(db: psycopg.Connection, customer_id: str, **overrides: Any) -> str:
    values: dict[str, Any] = {
        "kyc_id": new_id(IdPrefix.KYC_PROFILE),
        "customer_id": customer_id,
        "kyc_type": "full_kyc",
        "kyc_status": "verified",
        "pan_token": "kms:v1:AQICAHh0c2VjcmV0LWNpcGhlcnRleHQ",
        "pan_last4": "234C",
        "aadhaar_ref_token": "vault:aadhaar:7f3c9e2a",
        "aadhaar_last4": "4821",
        "risk_category": "low",
    } | overrides
    insert(db, "kyc.kyc_profiles", values)
    return values["kyc_id"]


def aml_rule(db: psycopg.Connection, **overrides: Any) -> str:
    values: dict[str, Any] = {
        "rule_id": new_id(IdPrefix.AML_RULE),
        "name": f"Structuring {new_id(IdPrefix.AML_RULE)[-6:]}",
        "typology": "structuring",
        "params": '{"threshold_paise": 1000000000, "window_days": 7}',
        "severity": "high",
    } | overrides
    insert(db, "risk.aml_rules", values)
    return values["rule_id"]


def aml_alert(db: psycopg.Connection, customer_id: str, rule_id: str, **overrides: Any) -> str:
    values: dict[str, Any] = {
        "alert_id": new_id(IdPrefix.AML_ALERT),
        "customer_id": customer_id,
        "rule_id": rule_id,
        "typology": "structuring",
        "score": 82.5,
        "status": "open",
        "sla_due_at": NOW,
    } | overrides
    insert(db, "risk.aml_alerts", values)
    return values["alert_id"]


def audit_record(db: psycopg.Connection, **overrides: Any) -> str:
    values: dict[str, Any] = {
        "audit_id": new_id(IdPrefix.AUDIT_RECORD),
        "actor_sub": "staff-0042",
        "client_id": "claude-desktop",
        "roles": ["support_agent"],
        "tool_name": "get_customer_profile",
        "args_hash": "0" * 64,
        "outcome": "success",
        "latency_ms": 42,
    } | overrides
    insert(db, "ops.audit_log", values)
    return values["audit_id"]


def card(db: psycopg.Connection, account_id: str, **overrides: Any) -> str:
    values: dict[str, Any] = {
        "card_id": new_id(IdPrefix.CARD),
        "account_id": account_id,
        "network": "rupay",
        "card_type": "debit",
        "pan_last4": "4417",
        "token_ref": "card-token-for-tests",
        "status": "inactive",
        "expiry_month": 9,
        "expiry_year": 2030,
        "atm_limit_paise": 5_000_000,
        "pos_limit_paise": 20_000_000,
        "ecom_limit_paise": 10_000_000,
        "issued_at": NOW,
    } | overrides
    insert(db, "core.cards", values)
    return values["card_id"]


def beneficiary(db: psycopg.Connection, customer_id: str, **overrides: Any) -> str:
    values: dict[str, Any] = {
        "beneficiary_id": new_id(IdPrefix.BENEFICIARY),
        "customer_id": customer_id,
        "nickname": "Amma",
        "account_number_masked": "XXXXXX4521",
        "ifsc": "SBIN0001234",
        "bank_name": "State Bank of India",
        "added_at": NOW,
        "cooling_period_ends_at": NOW,
        "status": "pending_cooling",
    } | overrides
    insert(db, "core.beneficiaries", values)
    return values["beneficiary_id"]


def dispute(
    db: psycopg.Connection, txn: tuple[str, datetime], customer_id: str, **overrides: Any
) -> str:
    values: dict[str, Any] = {
        "dispute_id": new_id(IdPrefix.DISPUTE),
        "txn_id": txn[0],
        "txn_initiated_at": txn[1],
        "customer_id": customer_id,
        "reason_code": "failed_but_debited",
        "amount_paise": 25_000,
        "status": "raised",
        "tat_due_at": NOW,
        "created_by": "staff-0042",
    } | overrides
    insert(db, "ops.disputes", values)
    return values["dispute_id"]


def review(db: psycopg.Connection, txn: tuple[str, datetime], **overrides: Any) -> str:
    values: dict[str, Any] = {
        "review_id": new_id(IdPrefix.TRANSACTION_REVIEW),
        "txn_id": txn[0],
        "txn_initiated_at": txn[1],
        "reason": "Velocity spike on a new device",
        "priority": "high",
        "status": "queued",
        "created_by": "staff-0042",
    } | overrides
    insert(db, "ops.transaction_reviews", values)
    return values["review_id"]


def document(db: psycopg.Connection, **overrides: Any) -> str:
    doc_id = overrides.get("doc_id", new_id(IdPrefix.DOCUMENT))
    values: dict[str, Any] = {
        "doc_id": doc_id,
        "doc_code": f"CMP-SOP-{doc_id[-3:].translate(_DIGITS)}",
        "department": "compliance",
        "title": "Transaction Monitoring & Alert Handling SOP",
        "doc_type": "sop",
        "version": "1.0",
        "status": "effective",
        "effective_date": "2026-04-01",
        "classification": "internal",
        "source_format": "md",
        "sha256": "c" * 64,
    } | overrides
    insert(db, "kb.documents", values)
    return values["doc_id"]


def chunk(db: psycopg.Connection, doc_id: str, classification: str, **overrides: Any) -> str:
    values: dict[str, Any] = {
        "chunk_id": new_id(IdPrefix.CHUNK),
        "doc_id": doc_id,
        "classification": classification,
        "chunk_index": int(new_id(IdPrefix.CHUNK)[-4:].translate(_DIGITS)),
        "section_path": "4 › 4.2 Enhanced Due Diligence",  # noqa: RUF001 — plan v0.2's separator
        "content": "Escalate structuring alerts to the MLRO within one business day.",
        "token_count": 12,
    } | overrides
    insert(db, "kb.chunks", values)
    return values["chunk_id"]


# Crockford base32 → digits, to derive unique numeric identifiers from fresh ULIDs.
_DIGITS = str.maketrans("ABCDEFGHJKMNPQRSTVWXYZ", "0123456789012345678901")
