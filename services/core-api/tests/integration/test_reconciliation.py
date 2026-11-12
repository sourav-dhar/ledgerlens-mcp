"""Cached Account balances reconcile against the ledger, and balances can be brought forward."""

import db_rows as rows
import psycopg
import pytest

pytestmark = pytest.mark.integration

_RECONCILE = """
    SELECT cached_balance_paise, posted_balance_paise, difference_paise
    FROM ledger.account_reconciliation WHERE account_id = %s
"""


def _reconciliation(db: psycopg.Connection, account_id: str) -> tuple[int, int, int]:
    row = db.execute(_RECONCILE, [account_id]).fetchone()
    assert row is not None
    return row


def _post(db: psycopg.Connection, account_id: str, amount_paise: int) -> None:
    entry_id = rows.journal_entry(db)
    rows.posting(db, entry_id, "customer_deposits", amount_paise, account_id=account_id)
    rows.posting(db, entry_id, "upi_settlement", -amount_paise)


def test_an_account_whose_cache_matches_its_postings_reconciles(db: psycopg.Connection) -> None:
    account_id = rows.account(db, rows.customer(db), ledger_balance_paise=75_000)
    _post(db, account_id, 100_000)
    _post(db, account_id, -25_000)

    assert _reconciliation(db, account_id) == (75_000, 75_000, 0)


def test_a_drifted_cache_shows_the_difference(db: psycopg.Connection) -> None:
    account_id = rows.account(db, rows.customer(db), ledger_balance_paise=80_000)
    _post(db, account_id, 75_000)

    assert _reconciliation(db, account_id) == (80_000, 75_000, 5_000)


def test_an_account_without_postings_has_posted_nothing(db: psycopg.Connection) -> None:
    account_id = rows.account(db, rows.customer(db))

    assert _reconciliation(db, account_id) == (0, 0, 0)


def test_a_balance_brought_forward_balances_against_opening_balances(
    db: psycopg.Connection,
) -> None:
    account_id = rows.account(db, rows.customer(db), ledger_balance_paise=4_250_000)
    entry_id = rows.journal_entry(db, description="Balance brought forward")
    rows.posting(db, entry_id, "customer_deposits", 4_250_000, account_id=account_id)
    rows.posting(db, entry_id, "opening_balances", -4_250_000)

    db.execute("SET CONSTRAINTS ALL IMMEDIATE")
    assert _reconciliation(db, account_id) == (4_250_000, 4_250_000, 0)


def test_the_application_role_may_read_the_reconciliation(db: psycopg.Connection) -> None:
    row = db.execute(
        "SELECT has_table_privilege('kosha_app', 'ledger.account_reconciliation', 'SELECT')"
    ).fetchone()

    assert row == (True,)
