"""The generated rows load into a migrated database, and the ledger reconciles afterwards."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

import psycopg
import pytest
from psycopg import sql

from core_api.migrations import upgrade
from kosha_datagen import Batch, GenerationConfig, generate
from kosha_datagen.__main__ import main
from kosha_datagen.loader import AlreadySeededError, LoadReport, load
from kosha_datagen.reconcile import reconcile

pytestmark = pytest.mark.integration

# Earlier than the migration's own partition window, so the loader must create months.
CONFIG = GenerationConfig(as_of=date(2025, 8, 15), seed=3, scale=0.01)
_SCRATCH = "kosha_seed_test"


@dataclass(frozen=True)
class Seeded:
    url: str
    report: LoadReport
    expected: Batch


@pytest.fixture(scope="module")
def seeded(database_url: str) -> Iterator[Seeded]:
    """A fresh database, migrated and seeded; dropped afterwards."""
    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {_SCRATCH} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {_SCRATCH}")
        url = database_url.rsplit("/", 1)[0] + f"/{_SCRATCH}"
        try:
            upgrade(url)
            with psycopg.connect(url, autocommit=True) as conn:
                report = load(conn, CONFIG, generate(CONFIG))
            yield Seeded(url, report, Batch.merge(generate(CONFIG)))
        finally:
            admin.execute(f"DROP DATABASE {_SCRATCH} WITH (FORCE)")


def _count(conn: psycopg.Connection, table: str) -> int:
    schema, name = table.split(".")
    row = conn.execute(
        sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(schema, name))
    ).fetchone()
    assert row is not None
    return row[0]


def test_every_generated_row_lands(seeded: Seeded) -> None:
    with psycopg.connect(seeded.url) as conn:
        for table in seeded.expected.tables():
            assert _count(conn, table.table) == len(table.rows), table.table
    assert seeded.report.rows == {t.table: len(t.rows) for t in seeded.expected.tables()}


def test_the_ledger_reconciles(seeded: Seeded) -> None:
    with psycopg.connect(seeded.url) as conn:
        result = reconcile(conn)

    assert result.ok
    assert result.accounts == len(seeded.expected.accounts)
    assert result.ledger_total_paise == 0
    assert result.unbalanced_entries == 0
    assert result.orphans == {}


def test_every_transaction_lands_in_its_monthly_partition(seeded: Seeded) -> None:
    with psycopg.connect(seeded.url) as conn:
        assert _count(conn, "core.transactions_default") == 0
        months = conn.execute(
            "SELECT count(DISTINCT date_trunc('month', initiated_at)) FROM core.transactions"
        ).fetchone()
    assert months == (18,)


def test_a_seeded_database_is_not_seeded_twice(seeded: Seeded) -> None:
    with psycopg.connect(seeded.url, autocommit=True) as conn:
        with pytest.raises(AlreadySeededError):
            load(conn, CONFIG, generate(CONFIG))
        assert _count(conn, "core.customers") == len(seeded.expected.customers)


def test_reconciliation_names_an_account_whose_cache_drifted(seeded: Seeded) -> None:
    account = seeded.expected.accounts[0]
    with psycopg.connect(seeded.url) as conn:
        conn.execute(
            "UPDATE core.accounts SET ledger_balance_paise = ledger_balance_paise + 100"
            " WHERE account_id = %s",
            [account.account_id],
        )
        result = reconcile(conn)
        conn.rollback()

    assert not result.ok
    assert [m.account_id for m in result.mismatches] == [account.account_id]
    assert result.mismatches[0].difference_paise == 100


def test_the_command_line_seeds_and_proves_the_ledger(
    database_url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    name = "kosha_seed_cli_test"
    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {name}")
        url = database_url.rsplit("/", 1)[0] + f"/{name}"
        try:
            upgrade(url)
            monkeypatch.setenv("DATABASE_URL", url)
            main(["--scale", "0.002", "--seed", "9", "--as-of", "2026-11-12"])
            with pytest.raises(SystemExit, match="already holds 10 customers"):
                main(["--scale", "0.002"])
        finally:
            admin.execute(f"DROP DATABASE {name} WITH (FORCE)")

    out = capsys.readouterr().out
    assert "Seeding 10 customers, seed 9, Jun 2025 to 12 Nov 2026" in out
    assert "Ledger reconciles" in out


def test_reconciliation_finds_rows_that_bypassed_their_constraints(seeded: Seeded) -> None:
    entry = seeded.expected.journal_entries[0].entry_id
    with psycopg.connect(seeded.url) as conn:
        # What the loader's trigger-free COPY could let through, were the generator wrong.
        conn.execute("SET LOCAL session_replication_role = replica")
        conn.execute(
            "INSERT INTO ledger.postings (posting_id, entry_id, gl_account, amount_paise)"
            " VALUES ('pst_01JC3W4Q8Z9X7V5T3R1N0M2K4P', %s, 'suspense', 100),"
            " ('pst_01JC3W4Q8Z9X7V5T3R1N0M2K4Q', 'jrn_01JC3W4Q8Z9X7V5T3R1N0M2K4P', 'suspense', 5)",
            [entry],
        )
        result = reconcile(conn)
        conn.rollback()

    assert not result.ok
    assert result.unbalanced_entries == 2
    assert result.orphans == {"ledger.postings → ledger.journal_entries": 1}
