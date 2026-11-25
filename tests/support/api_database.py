"""A scratch database that API tests commit to, and core-api settings wired to it.

core-api reads through its own pool, so it cannot see rows a rolled-back test transaction
wrote: tests that call it commit, which is why they get a database of their own. Registered
as a plugin from the root ``conftest.py``, so core-api's and the gateway's integration
suites share one scratch database per session.
"""

from collections.abc import Iterator

import psycopg
import pytest
from pydantic import SecretStr
from signed import TEST_KEY

from core_api.migrations import upgrade
from core_api.settings import Settings
from kosha_domain.vault import LOCAL_PASSPHRASE

_SCRATCH = "kosha_api_test"


@pytest.fixture(scope="session")
def api_database_url(database_url: str) -> Iterator[str]:
    """A fresh database migrated to head, dropped at the end of the session."""
    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {_SCRATCH} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {_SCRATCH}")
        url = database_url.rsplit("/", 1)[0] + f"/{_SCRATCH}"
        try:
            upgrade(url)
            yield url
        finally:
            admin.execute(f"DROP DATABASE {_SCRATCH} WITH (FORCE)")


@pytest.fixture
def committed(api_database_url: str) -> Iterator[psycopg.Connection]:
    """An autocommit connection for arranging rows the API must be able to read."""
    with psycopg.connect(api_database_url, autocommit=True) as conn:
        yield conn


@pytest.fixture
def api_settings(api_database_url: str) -> Settings:
    """core-api on the scratch database, trusting the test signing key."""
    return Settings(
        database_url=SecretStr(api_database_url),
        internal_signing_keys=SecretStr(TEST_KEY),
        pan_keyring_passphrase=SecretStr(LOCAL_PASSPHRASE),
        db_pool_timeout_s=0.5,
    )
