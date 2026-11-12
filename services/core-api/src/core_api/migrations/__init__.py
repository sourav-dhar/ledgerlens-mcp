"""Alembic migrations for every schema core-api owns.

Revisions are raw SQL (``op.execute``) with enum labels frozen as literals, so a revision
means the same thing forever; parity with ``kosha-domain`` is enforced by the test suite.
They are forward-only in production; downgrades exist for local development and tests.

``python -m core_api.migrations [revision]`` upgrades ``$DATABASE_URL`` (default: head).
"""

import os
import sys
from collections.abc import Sequence
from pathlib import Path

from alembic import command
from alembic.config import Config

_SCRIPT_LOCATION = Path(__file__).parent


def alembic_config(database_url: str) -> Config:
    """An Alembic config for ``database_url``, a libpq-style ``postgresql://`` URL.

    The URL travels in ``attributes`` rather than ``sqlalchemy.url`` because Alembic's ini
    interpolation would mangle a ``%``-encoded password.
    """
    config = Config()
    config.set_main_option("script_location", str(_SCRIPT_LOCATION))
    config.attributes["database_url"] = database_url.replace(
        "postgresql://", "postgresql+psycopg://", 1
    )
    return config


def upgrade(database_url: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(database_url), revision)


def downgrade(database_url: str, revision: str) -> None:
    command.downgrade(alembic_config(database_url), revision)


def main(argv: Sequence[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        sys.exit("DATABASE_URL is not set")
    upgrade(database_url, args[0] if args else "head")
