"""Every revision applies and reverts cleanly on an empty database."""

from collections.abc import Iterator

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

from core_api.migrations import downgrade, upgrade

pytestmark = pytest.mark.integration

_SCRATCH = "kosha_roundtrip"
_OWN_SCHEMAS = "SELECT count(*) FROM pg_namespace WHERE nspname = ANY(%s)"
_SCHEMAS = ["kosha", "core", "ledger", "kyc", "risk", "ops", "kb"]


@pytest.fixture
def scratch_url(postgres: PostgresContainer, database_url: str) -> Iterator[str]:
    """A second, empty database in the same cluster (roles are shared, schemas are not)."""
    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {_SCRATCH}")
        try:
            yield database_url.rsplit("/", 1)[0] + f"/{_SCRATCH}"
        finally:
            admin.execute(f"DROP DATABASE {_SCRATCH} WITH (FORCE)")


def _schema_count(url: str) -> int:
    with psycopg.connect(url) as conn:
        row = conn.execute(_OWN_SCHEMAS, [_SCHEMAS]).fetchone()
    assert row is not None
    return row[0]


def test_upgrade_downgrade_upgrade_round_trip(scratch_url: str) -> None:
    upgrade(scratch_url)
    assert _schema_count(scratch_url) == len(_SCHEMAS)

    downgrade(scratch_url, "base")
    assert _schema_count(scratch_url) == 0

    upgrade(scratch_url)
    assert _schema_count(scratch_url) == len(_SCHEMAS)
