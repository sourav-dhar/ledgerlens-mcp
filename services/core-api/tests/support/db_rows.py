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


# Crockford base32 → digits, to derive unique numeric identifiers from fresh ULIDs.
_DIGITS = str.maketrans("ABCDEFGHJKMNPQRSTVWXYZ", "0123456789012345678901")
