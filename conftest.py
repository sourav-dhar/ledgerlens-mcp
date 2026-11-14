"""Repo-wide pytest configuration.

Async tests use AnyIO's pytest plugin (`pytestmark = pytest.mark.anyio` per module) rather
than pytest-asyncio: AnyIO keeps an async fixture's setup and teardown in the same task,
which task-group based lifespans (FastMCP, Starlette) require.
"""

import asyncio
import sys
from typing import Any

import pytest

# Shared fixtures (tests/support is on pytest's pythonpath): one Postgres container per session.
pytest_plugins = ["pg_container"]


@pytest.fixture(scope="session")
def anyio_backend() -> tuple[str, dict[str, Any]]:
    # psycopg's async connections cannot run on Windows' default Proactor loop.
    if sys.platform == "win32":
        return "asyncio", {"loop_factory": asyncio.SelectorEventLoop}
    return "asyncio", {}
