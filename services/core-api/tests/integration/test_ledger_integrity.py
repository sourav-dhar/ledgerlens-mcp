"""The ledger balances at commit and, like the history tables, is never rewritten."""

from typing import LiteralString

import db_rows as rows
import psycopg
import pytest
from psycopg import errors, sql

from kosha_domain.ids import IdPrefix, new_id

pytestmark = pytest.mark.integration


def _check_deferred(db: psycopg.Connection) -> None:
    """Run the deferred balance checks now instead of at commit."""
    db.execute("SET CONSTRAINTS ALL IMMEDIATE")


@pytest.fixture
def account_id(db: psycopg.Connection) -> str:
    return rows.account(db, rows.customer(db))


def test_a_balanced_entry_may_be_written_header_first(
    db: psycopg.Connection, account_id: str
) -> None:
    entry_id = rows.journal_entry(db)
    rows.posting(db, entry_id, "customer_deposits", -25_000, account_id=account_id)
    rows.posting(db, entry_id, "upi_settlement", 25_000)

    _check_deferred(db)


def test_a_charge_with_gst_balances_across_three_postings(
    db: psycopg.Connection, account_id: str
) -> None:
    entry_id = rows.journal_entry(db, description="SMS charges with 18% GST")
    rows.posting(db, entry_id, "customer_deposits", -1_180, account_id=account_id)
    rows.posting(db, entry_id, "fee_income", 1_000)
    rows.posting(db, entry_id, "gst_payable", 180)

    _check_deferred(db)


def test_an_unbalanced_entry_is_rejected(db: psycopg.Connection, account_id: str) -> None:
    entry_id = rows.journal_entry(db)
    rows.posting(db, entry_id, "customer_deposits", -25_000, account_id=account_id)
    rows.posting(db, entry_id, "upi_settlement", 24_999)

    with pytest.raises(errors.CheckViolation, match="unbalanced"), db.transaction():
        _check_deferred(db)


def test_an_entry_without_postings_is_rejected(db: psycopg.Connection) -> None:
    rows.journal_entry(db)

    with pytest.raises(errors.CheckViolation, match="unbalanced"), db.transaction():
        _check_deferred(db)


def test_the_check_runs_at_commit(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        entry_id = rows.journal_entry(conn)
        rows.posting(conn, entry_id, "suspense", 100)

        with pytest.raises(errors.CheckViolation, match="unbalanced"):
            conn.commit()


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE ledger.postings SET amount_paise = amount_paise * 2",
        "DELETE FROM ledger.postings",
        "UPDATE ledger.journal_entries SET description = 'edited'",
        "DELETE FROM ledger.journal_entries",
        "UPDATE core.transaction_status_history SET reason_code = 'edited'",
        "DELETE FROM core.transaction_status_history",
        "UPDATE kyc.kyc_events SET reason = 'edited'",
        "DELETE FROM kyc.kyc_events",
    ],
)
def test_not_even_the_owner_can_rewrite_the_ledger_or_history(
    db: psycopg.Connection, account_id: str, statement: LiteralString
) -> None:
    customer_id = rows.customer(db)
    txn = rows.transaction(db, rows.account(db, customer_id), customer_id)
    rows.status_change(db, txn)
    entry_id = rows.journal_entry(db, txn)
    rows.posting(db, entry_id, "customer_deposits", -25_000, account_id=account_id)
    rows.posting(db, entry_id, "upi_settlement", 25_000)
    rows.insert(
        db,
        "kyc.kyc_events",
        {
            "event_id": new_id(IdPrefix.KYC_EVENT),
            "kyc_id": rows.kyc_profile(db, customer_id),
            "to_status": "verified",
            "actor": "staff",
            "occurred_at": rows.NOW,
        },
    )

    with pytest.raises(errors.RestrictViolation, match="append-only"), db.transaction():
        db.execute(statement)


@pytest.mark.parametrize(
    "table",
    ["ledger.postings", "core.transaction_status_history", "kyc.kyc_events"],
)
def test_not_even_the_owner_can_truncate_the_ledger_or_history(
    db: psycopg.Connection, table: str
) -> None:
    # Runs before any insert: a table with pending deferred checks cannot be truncated at all.
    schema, name = table.split(".")
    statement = sql.SQL("TRUNCATE {}").format(sql.Identifier(schema, name))

    with pytest.raises(errors.RestrictViolation, match="append-only"), db.transaction():
        db.execute(statement)
