"""The foundation revision: schemas, extensions, the application role and shared checks."""

import psycopg
import pytest

from kosha_domain.ids import IdPrefix, new_id

pytestmark = pytest.mark.integration

SCHEMAS = {"kosha", "core", "ledger", "kyc", "risk", "ops", "kb"}


def test_every_domain_schema_exists(db: psycopg.Connection) -> None:
    rows = db.execute("SELECT nspname FROM pg_namespace").fetchall()

    assert {name for (name,) in rows} >= SCHEMAS


def test_vector_and_trigram_extensions_are_installed(db: psycopg.Connection) -> None:
    rows = db.execute("SELECT extname FROM pg_extension").fetchall()

    assert {"vector", "pg_trgm"} <= {name for (name,) in rows}


def test_application_role_cannot_log_in_and_can_use_every_schema(db: psycopg.Connection) -> None:
    (can_login,) = db.execute(
        "SELECT rolcanlogin FROM pg_roles WHERE rolname = 'kosha_app'"
    ).fetchone() or (None,)

    assert can_login is False
    for schema in SCHEMAS:
        row = db.execute("SELECT has_schema_privilege('kosha_app', %s, 'USAGE')", [schema])
        assert row.fetchone() == (True,), schema


@pytest.mark.parametrize("prefix", list(IdPrefix))
def test_is_id_accepts_identifiers_minted_by_the_domain(
    db: psycopg.Connection, prefix: IdPrefix
) -> None:
    row = db.execute("SELECT kosha.is_id(%s, %s)", [new_id(prefix), prefix.value])

    assert row.fetchone() == (True,)


@pytest.mark.parametrize(
    "value",
    [
        "cus_01JC3W4Q8Z9X7V5T3R1N0M2K4",  # one character short
        "cus_01jc3w4q8z9x7v5t3r1n0m2k4p",  # lower case
        "cus_01JC3W4Q8Z9X7V5T3R1N0M2K4U",  # U is not Crockford base32
        "cus_81JC3W4Q8Z9X7V5T3R1N0M2K4P",  # first character overflows 128 bits
        "acc_01JC3W4Q8Z9X7V5T3R1N0M2K4P",  # wrong entity
        "cus-01JC3W4Q8Z9X7V5T3R1N0M2K4P",  # wrong separator
    ],
)
def test_is_id_rejects_malformed_identifiers(db: psycopg.Connection, value: str) -> None:
    row = db.execute("SELECT kosha.is_id(%s, 'cus')", [value])

    assert row.fetchone() == (False,)
