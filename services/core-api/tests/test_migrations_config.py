"""Migration wiring that needs no database: revision graph and the command-line entry point."""

import runpy

import pytest
from alembic.script import ScriptDirectory

from core_api import migrations
from core_api.migrations import alembic_config


def test_revisions_form_a_single_line() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql://unused/kosha"))

    assert len(script.get_heads()) == 1
    assert len(script.get_bases()) == 1


def test_libpq_urls_use_the_psycopg_3_driver() -> None:
    config = alembic_config("postgresql://kosha:p%40ss@db:5432/kosha")

    assert config.attributes["database_url"] == "postgresql+psycopg://kosha:p%40ss@db:5432/kosha"


@pytest.fixture
def upgrades(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Record upgrade calls instead of connecting to a database."""
    calls: list[tuple[str, str]] = []

    def record(database_url: str, revision: str = "head") -> None:
        calls.append((database_url, revision))

    monkeypatch.setattr(migrations, "upgrade", record)
    monkeypatch.setenv("DATABASE_URL", "postgresql://kosha@db/kosha")
    return calls


def test_main_upgrades_the_database_named_in_the_environment(
    upgrades: list[tuple[str, str]],
) -> None:
    migrations.main([])

    assert upgrades == [("postgresql://kosha@db/kosha", "head")]


def test_main_accepts_a_target_revision(upgrades: list[tuple[str, str]]) -> None:
    migrations.main(["0001"])

    assert upgrades == [("postgresql://kosha@db/kosha", "0001")]


def test_main_refuses_to_run_without_a_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(SystemExit, match="DATABASE_URL"):
        migrations.main([])


def test_package_runs_as_a_module(
    upgrades: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["python -m core_api.migrations"])

    runpy.run_module("core_api.migrations", run_name="__main__")

    assert upgrades == [("postgresql://kosha@db/kosha", "head")]
