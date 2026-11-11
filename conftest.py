"""Repo-wide pytest configuration.

Async tests use AnyIO's pytest plugin (`pytestmark = pytest.mark.anyio` per module) rather
than pytest-asyncio: AnyIO keeps an async fixture's setup and teardown in the same task,
which task-group based lifespans (FastMCP, Starlette) require.
"""

import pytest


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"
