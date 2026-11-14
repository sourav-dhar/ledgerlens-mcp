"""The connection pool and the unit of work: the only place a transaction is opened."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Self

import psycopg
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from core_api.db.rls import CONTEXT_SQL, Caller, context_params
from core_api.settings import Settings

type Connection = AsyncConnection[DictRow]


async def _configure(conn: Connection) -> None:
    # Autocommit: transactions are opened explicitly by ``unit_of_work``, so a connection
    # never sits idle in a transaction between requests.
    await conn.set_autocommit(True)


async def _check(conn: Connection) -> None:
    # A Lambda instance can sleep for minutes between requests; a pooled connection is
    # probed before it is handed out, and a dead one is replaced rather than failing.
    await conn.execute("SELECT 1")


class Database:
    """A small pool (Lambda serves one request per instance) and its units of work."""

    def __init__(
        self,
        pool: AsyncConnectionPool[Connection],
        *,
        role: str,
        statement_timeout_ms: int,
    ) -> None:
        self._pool = pool
        self._role = role
        self._statement_timeout_ms = statement_timeout_ms

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        if settings.database_url is None:
            msg = "DATABASE_URL is not set"
            raise ValueError(msg)
        pool = AsyncConnectionPool(
            settings.database_url.get_secret_value(),
            connection_class=AsyncConnection[DictRow],
            kwargs={"row_factory": dict_row, "connect_timeout": 5},
            configure=_configure,
            check=_check,
            min_size=0,
            max_size=settings.db_pool_max_size,
            timeout=settings.db_pool_timeout_s,
            open=False,
            name="core-api",
        )
        return cls(
            pool,
            role=settings.db_role,
            statement_timeout_ms=settings.db_statement_timeout_ms,
        )

    async def open(self) -> None:
        """Start the pool without connecting: the first request connects (``min_size=0``)."""
        await self._pool.open(wait=False)

    async def close(self) -> None:
        await self._pool.close()

    @asynccontextmanager
    async def unit_of_work(
        self, caller: Caller, *, read_only: bool = False
    ) -> AsyncGenerator[Connection]:
        """One transaction as the application role, carrying the caller's context.

        Commits when the block exits normally and rolls back when it raises. Read-only
        work runs in a ``READ ONLY`` transaction, so a read route cannot write by mistake.
        """
        async with self._pool.connection() as conn, conn.transaction():
            await conn.execute(
                CONTEXT_SQL,
                context_params(
                    caller,
                    role=self._role,
                    read_only=read_only,
                    statement_timeout_ms=self._statement_timeout_ms,
                ),
            )
            yield conn

    async def schema_revision(self) -> str | None:
        """The applied Alembic revision, or ``None`` when the database cannot be reached."""
        try:
            async with self._pool.connection() as conn:
                cursor = await conn.execute("SELECT version_num FROM public.alembic_version")
                row = await cursor.fetchone()
        except psycopg.Error:
            return None
        return None if row is None else str(row["version_num"])
