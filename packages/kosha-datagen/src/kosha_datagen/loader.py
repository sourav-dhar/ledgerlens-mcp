"""Copy generated batches into a migrated database, one transaction per batch.

Rows go in with ``COPY`` as the table owner, with triggers off where the role may do that
(``session_replication_role = replica``, as ``pg_restore --disable-triggers`` does). Per-row
foreign-key checks into the partitioned Transactions table and the deferred balance
triggers otherwise cost about ten times the load itself; CHECK constraints and unique
indexes still apply, and `reconcile` proves foreign keys and balanced entries afterwards in
one set-based pass. A role that may not switch triggers off loads with them on: slower,
and just as correct.

Each batch commits on its own, so a load with triggers on never queues millions of deferred
events in one transaction.
"""

import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from kosha_datagen.batch import Batch, TableRows
from kosha_datagen.config import GenerationConfig


class AlreadySeededError(RuntimeError):
    """The target database already holds Customers; seeding is for empty databases only."""


@dataclass(slots=True)
class LoadReport:
    rows: dict[str, int] = field(default_factory=dict[str, int])
    batches: int = 0
    seconds: float = 0.0
    triggers_off: bool = False
    """Whether rows were copied without per-row triggers (verify with `reconcile`)."""

    @property
    def total_rows(self) -> int:
        return sum(self.rows.values())


def load(
    conn: psycopg.Connection,
    config: GenerationConfig,
    batches: Iterable[Batch],
    *,
    progress: Callable[[LoadReport], None] | None = None,
) -> LoadReport:
    """Load every batch, creating the Transaction partitions the dataset needs first.

    Raises:
        AlreadySeededError: if the database already holds Customers.
    """
    started = time.monotonic()
    row = conn.execute("SELECT count(*) FROM core.customers").fetchone()
    if row is not None and row[0]:
        msg = f"the database already holds {row[0]} customers; seed an empty database"
        raise AlreadySeededError(msg)
    with conn.transaction():
        # Rows must land in monthly partitions: a month whose rows sit in the default
        # partition can never be split out later without moving them.
        conn.execute(
            "SELECT kosha.create_transaction_partitions(%s, %s)",
            [config.window_start.date(), config.as_of],
        )
    counts = Counter[str]()
    report = LoadReport(triggers_off=_can_switch_triggers_off(conn))
    for batch in batches:
        with conn.transaction():
            if report.triggers_off:
                conn.execute("SET LOCAL session_replication_role = replica")
            for table in batch.tables():
                _copy(conn, table)
                counts[table.table] += len(table.rows)
        report.batches += 1
        report.rows = dict(counts)
        report.seconds = time.monotonic() - started
        if progress is not None:
            progress(report)
    conn.execute("ANALYZE")
    report.seconds = time.monotonic() - started
    return report


def _can_switch_triggers_off(conn: psycopg.Connection) -> bool:
    """Whether this role may set ``session_replication_role`` (superuser, or granted SET)."""
    row = conn.execute(
        "SELECT has_parameter_privilege(current_user, 'session_replication_role', 'SET')"
    ).fetchone()
    return bool(row and row[0])


def _copy(conn: psycopg.Connection, table: TableRows) -> None:
    schema, name = table.table.split(".")
    statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(schema, name), sql.SQL(", ").join(map(sql.Identifier, table.columns))
    )
    json_columns = [i for i, value in enumerate(table.rows[0]) if isinstance(value, dict)]
    with conn.cursor() as cursor, cursor.copy(statement) as copy:
        for row in table.rows:
            copy.write_row(_with_jsonb(row, json_columns) if json_columns else row)


def _with_jsonb(row: tuple[Any, ...], columns: list[int]) -> list[Any]:
    values = list(row)
    for i in columns:
        values[i] = Jsonb(values[i])
    return values
