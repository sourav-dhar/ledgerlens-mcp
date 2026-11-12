"""Core banking and ledger tables: partitioning, money, integrity and privileges."""

from datetime import UTC, datetime, timedelta
from typing import LiteralString

import db_rows as rows
import psycopg
import pytest
from psycopg import errors

pytestmark = pytest.mark.integration


def _partition_names(first_offset: int, last_offset: int) -> set[str]:
    """Partition names for the months ``first_offset``..``last_offset`` from this month."""
    today = datetime.now(UTC).date()
    current = today.year * 12 + today.month - 1
    return {
        f"transactions_{month // 12:04d}_{month % 12 + 1:02d}"
        for month in range(current + first_offset, current + last_offset + 1)
    }


def _partitions(db: psycopg.Connection) -> set[str]:
    rows_ = db.execute("""
        SELECT c.relname FROM pg_inherits i
        JOIN pg_class c ON c.oid = i.inhrelid
        WHERE i.inhparent = 'core.transactions'::regclass
    """).fetchall()
    return {name for (name,) in rows_}


def _partition_of(db: psycopg.Connection, txn_id: str) -> str:
    row = db.execute(
        "SELECT tableoid::regclass::text FROM core.transactions WHERE txn_id = %s", [txn_id]
    ).fetchone()
    assert row is not None
    return row[0]


@pytest.fixture
def owner(db: psycopg.Connection) -> tuple[str, str]:
    customer_id = rows.customer(db)
    return customer_id, rows.account(db, customer_id)


# --- Partitioning


def test_monthly_partitions_cover_eighteen_months_back_and_three_ahead(
    db: psycopg.Connection,
) -> None:
    expected = _partition_names(-18, 3)

    assert len(expected) == 22
    assert expected | {"transactions_default"} <= _partitions(db)


def test_rows_land_in_their_month_or_the_default_partition(
    db: psycopg.Connection, owner: tuple[str, str]
) -> None:
    now = datetime.now(UTC)
    recent, _ = rows.transaction(db, owner[1], owner[0], initiated_at=now)
    ancient, _ = rows.transaction(db, owner[1], owner[0], initiated_at=now - timedelta(days=1500))

    assert _partition_of(db, recent) == f"core.transactions_{now:%Y_%m}"
    assert _partition_of(db, ancient) == "core.transactions_default"


def test_partition_helper_adds_missing_months_and_is_idempotent(db: psycopg.Connection) -> None:
    created = db.execute(
        "SELECT kosha.create_transaction_partitions('2031-01-01', '2031-02-01')"
    ).fetchone()
    again = db.execute(
        "SELECT kosha.create_transaction_partitions('2031-01-15', '2031-02-28')"
    ).fetchone()

    assert (created, again) == ((2,), (0,))
    assert {"transactions_2031_01", "transactions_2031_02"} <= _partitions(db)


# --- Money


def test_transaction_amount_must_be_positive(
    db: psycopg.Connection, owner: tuple[str, str]
) -> None:
    with pytest.raises(errors.CheckViolation), db.transaction():
        rows.transaction(db, owner[1], owner[0], amount_paise=0)


def test_available_balance_is_ledger_balance_minus_holds(db: psycopg.Connection) -> None:
    account_id = rows.account(
        db, rows.customer(db), ledger_balance_paise=1_000_000, hold_amount_paise=250_000
    )

    row = db.execute(
        "SELECT available_balance_paise FROM core.accounts WHERE account_id = %s", [account_id]
    ).fetchone()

    assert row == (750_000,)


def test_available_balance_cannot_be_written(db: psycopg.Connection) -> None:
    with pytest.raises(errors.GeneratedAlways), db.transaction():
        rows.account(db, rows.customer(db), available_balance_paise=1)


# --- Integrity


def test_transaction_customer_must_own_the_account(
    db: psycopg.Connection, owner: tuple[str, str]
) -> None:
    stranger = rows.customer(db)

    with pytest.raises(errors.ForeignKeyViolation), db.transaction():
        rows.transaction(db, owner[1], stranger)


def test_history_must_reference_the_transaction_and_its_initiation_time(
    db: psycopg.Connection, owner: tuple[str, str]
) -> None:
    txn_id, initiated_at = rows.transaction(db, owner[1], owner[0])
    rows.status_change(db, (txn_id, initiated_at))

    with pytest.raises(errors.ForeignKeyViolation), db.transaction():
        rows.status_change(db, (txn_id, initiated_at - timedelta(seconds=1)))


def test_customer_deposit_postings_name_an_account_and_internal_ones_do_not(
    db: psycopg.Connection, owner: tuple[str, str]
) -> None:
    entry_id = rows.journal_entry(db)
    rows.posting(db, entry_id, "customer_deposits", -25_000, account_id=owner[1])
    rows.posting(db, entry_id, "upi_settlement", 25_000)

    with pytest.raises(errors.CheckViolation), db.transaction():
        rows.posting(db, entry_id, "customer_deposits", -1)
    with pytest.raises(errors.CheckViolation), db.transaction():
        rows.posting(db, entry_id, "fee_income", 1, account_id=owner[1])


def test_a_transaction_has_at_most_one_journal_entry(
    db: psycopg.Connection, owner: tuple[str, str]
) -> None:
    txn = rows.transaction(db, owner[1], owner[0])
    rows.journal_entry(db, txn)

    with pytest.raises(errors.UniqueViolation), db.transaction():
        rows.journal_entry(db, txn)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("customer_id", "cus_not-a-ulid"),
        ("cif_number", "12345"),
        ("mobile", "5876543210"),
    ],
)
def test_customer_formats_are_checked(db: psycopg.Connection, column: str, value: str) -> None:
    with pytest.raises(errors.CheckViolation), db.transaction():
        rows.customer(db, **{column: value})


@pytest.mark.parametrize(("column", "value"), [("ifsc", "KOSH1000001"), ("account_id", "acc_x")])
def test_account_formats_are_checked(db: psycopg.Connection, column: str, value: str) -> None:
    with pytest.raises(errors.CheckViolation), db.transaction():
        rows.account(db, rows.customer(db), **{column: value})


# --- Privileges


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE ledger.postings SET amount_paise = 1",
        "DELETE FROM ledger.postings",
        "UPDATE ledger.journal_entries SET description = 'x'",
        "DELETE FROM ledger.journal_entries",
        "DELETE FROM core.transaction_status_history",
        "DELETE FROM core.customers",
        "DELETE FROM core.accounts",
        "DELETE FROM core.transactions",
    ],
)
def test_application_role_cannot_rewrite_history(
    db: psycopg.Connection, statement: LiteralString
) -> None:
    db.execute("SET LOCAL ROLE kosha_app")

    with pytest.raises(errors.InsufficientPrivilege), db.transaction():
        db.execute(statement)


def test_application_role_can_record_a_payment(
    db: psycopg.Connection, owner: tuple[str, str]
) -> None:
    with db.transaction():
        db.execute("SET LOCAL ROLE kosha_app")
        txn = rows.transaction(db, owner[1], owner[0])
        entry_id = rows.journal_entry(db, txn)
        rows.posting(db, entry_id, "customer_deposits", -25_000, account_id=owner[1])
        rows.posting(db, entry_id, "upi_settlement", 25_000)
        db.execute(
            "UPDATE core.accounts SET ledger_balance_paise = ledger_balance_paise - 25000"
            " WHERE account_id = %s",
            [owner[1]],
        )


def test_indexes_from_the_design_exist(db: psycopg.Connection) -> None:
    rows_ = db.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname IN ('core', 'ledger')"
        " AND tablename IN ('transactions', 'customers', 'postings')"
    ).fetchall()

    assert {
        "transactions_account_timeline_idx",
        "transactions_customer_timeline_idx",
        "transactions_merchant_idx",
        "transactions_utr_idx",
        "transactions_narration_trgm_idx",
        "transactions_ops_queue_idx",
        "customers_name_trgm_idx",
        "postings_account_idx",
    } <= {name for (name,) in rows_}
