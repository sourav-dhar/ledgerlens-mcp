"""Status columns obey the kosha-domain lifecycles inside the database.

Legal and illegal moves are derived from the domain lifecycle under test, so these tests
exercise every entity without restating its rules.
"""

from collections.abc import Callable
from dataclasses import dataclass

import db_rows as rows
import psycopg
import pytest
from psycopg import errors, sql

from kosha_domain.lifecycles import LIFECYCLES, AnyLifecycle

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class StatusColumn:
    table: str
    key: str
    column: str
    make: Callable[[psycopg.Connection, str], str]  # (db, initial status) -> key


def _with_account(db: psycopg.Connection) -> tuple[str, str]:
    customer_id = rows.customer(db)
    return customer_id, rows.account(db, customer_id)


def _transaction(db: psycopg.Connection, status: str) -> str:
    customer_id, account_id = _with_account(db)
    return rows.transaction(db, account_id, customer_id, status=status)[0]


def _account(db: psycopg.Connection, status: str) -> str:
    return rows.account(db, rows.customer(db), status=status)


def _kyc_profile(db: psycopg.Connection, status: str) -> str:
    return rows.kyc_profile(db, rows.customer(db), kyc_status=status)


def _card(db: psycopg.Connection, status: str) -> str:
    return rows.card(db, _with_account(db)[1], status=status)


def _dispute(db: psycopg.Connection, status: str) -> str:
    customer_id, account_id = _with_account(db)
    txn = rows.transaction(db, account_id, customer_id)
    return rows.dispute(db, txn, customer_id, status=status)


def _aml_alert(db: psycopg.Connection, status: str) -> str:
    return rows.aml_alert(db, rows.customer(db), rows.aml_rule(db), status=status)


def _review(db: psycopg.Connection, status: str) -> str:
    customer_id, account_id = _with_account(db)
    return rows.review(db, rows.transaction(db, account_id, customer_id), status=status)


def _beneficiary(db: psycopg.Connection, status: str) -> str:
    return rows.beneficiary(db, rows.customer(db), status=status)


COLUMNS: dict[str, StatusColumn] = {
    "Transaction": StatusColumn("core.transactions", "txn_id", "status", _transaction),
    "Account": StatusColumn("core.accounts", "account_id", "status", _account),
    "KYC profile": StatusColumn("kyc.kyc_profiles", "kyc_id", "kyc_status", _kyc_profile),
    "Card": StatusColumn("core.cards", "card_id", "status", _card),
    "Dispute": StatusColumn("ops.disputes", "dispute_id", "status", _dispute),
    "AML alert": StatusColumn("risk.aml_alerts", "alert_id", "status", _aml_alert),
    "Transaction review": StatusColumn("ops.transaction_reviews", "review_id", "status", _review),
    "Beneficiary": StatusColumn("core.beneficiaries", "beneficiary_id", "status", _beneficiary),
}
BY_NAME = {lifecycle.name: lifecycle for lifecycle in LIFECYCLES}


def _set_status(db: psycopg.Connection, target: StatusColumn, key: str, status: str) -> None:
    schema, table = target.table.split(".")
    db.execute(
        sql.SQL("UPDATE {} SET {} = %s WHERE {} = %s").format(
            sql.Identifier(schema, table), sql.Identifier(target.column), sql.Identifier(target.key)
        ),
        [status, key],
    )


def _illegal_from(lifecycle: AnyLifecycle, status: str) -> str:
    allowed = {dst.value for dst in lifecycle.next_statuses(lifecycle.status_type(status))}
    return next(s.value for s in lifecycle.statuses if s.value not in allowed | {status})


def test_the_database_holds_exactly_the_domain_transitions(db: psycopg.Connection) -> None:
    stored = set(
        db.execute("SELECT lifecycle, from_status, to_status FROM kosha.allowed_transitions")
    )
    domain = {
        (lifecycle.name, src.value, dst.value)
        for lifecycle in LIFECYCLES
        for src, dst in lifecycle.transitions
    }

    assert stored == domain


def test_every_lifecycle_guards_a_status_column() -> None:
    assert set(COLUMNS) == set(BY_NAME)


@pytest.mark.parametrize("name", sorted(COLUMNS))
def test_a_legal_transition_is_accepted(db: psycopg.Connection, name: str) -> None:
    lifecycle, target = BY_NAME[name], COLUMNS[name]
    key = target.make(db, lifecycle.initial.value)
    legal = min(dst.value for dst in lifecycle.next_statuses(lifecycle.initial))

    _set_status(db, target, key, legal)


@pytest.mark.parametrize("name", sorted(COLUMNS))
def test_an_illegal_transition_is_rejected_as_the_domain_words_it(
    db: psycopg.Connection, name: str
) -> None:
    lifecycle, target = BY_NAME[name], COLUMNS[name]
    initial = lifecycle.initial.value
    illegal = _illegal_from(lifecycle, initial)
    key = target.make(db, initial)

    with pytest.raises(errors.CheckViolation) as raised, db.transaction():
        _set_status(db, target, key, illegal)

    assert raised.value.diag.message_primary == (
        f"{name} cannot move from {initial!r} to {illegal!r}"
    )
    assert (raised.value.diag.constraint_name or "").endswith("_lifecycle")


def test_rows_may_be_inserted_in_any_status(db: psycopg.Connection) -> None:
    lifecycle = BY_NAME["Transaction"]

    for status in lifecycle.statuses:
        _transaction(db, status.value)


def test_updates_that_keep_the_status_are_unaffected(db: psycopg.Connection) -> None:
    key = _account(db, "closed")

    db.execute(
        "UPDATE core.accounts SET status = 'closed', status_reason = 'customer request'"
        " WHERE account_id = %s",
        [key],
    )


def test_the_application_role_is_held_to_the_lifecycle(db: psycopg.Connection) -> None:
    key = _account(db, "closed")
    db.execute("SET LOCAL ROLE kosha_app")

    with pytest.raises(errors.CheckViolation), db.transaction():
        db.execute("UPDATE core.accounts SET status = 'active' WHERE account_id = %s", [key])
