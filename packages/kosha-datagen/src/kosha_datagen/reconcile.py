"""Prove the ledger and the data's integrity after a load.

The loader copies rows with triggers off (as ``pg_restore --disable-triggers`` does), so the
per-row foreign-key checks and the deferred balance triggers do not run. This module proves
the same guarantees in one set-based pass instead: every foreign key holds, every journal
entry balances across at least two Postings, every cached balance equals its Postings, and
the whole ledger sums to zero.
"""

from dataclasses import dataclass, field
from typing import LiteralString

import psycopg
from psycopg import sql

_MISMATCHES = """
    SELECT account_id, cached_balance_paise, posted_balance_paise, difference_paise
    FROM ledger.account_reconciliation
    WHERE difference_paise <> 0
    ORDER BY account_id
    LIMIT %s
"""
# Entries with fewer than two Postings or a non-zero sum, including Postings whose entry
# does not exist (the full join keeps them).
_UNBALANCED = """
    SELECT count(*)
    FROM ledger.journal_entries e
    FULL JOIN (
        SELECT entry_id, sum(amount_paise) AS total, count(*) AS legs
        FROM ledger.postings GROUP BY entry_id
    ) p USING (entry_id)
    WHERE coalesce(p.legs, 0) < 2 OR p.total <> 0
"""
# Every foreign key Kosha's schemas declare, with its columns in key order. Constraints
# cloned onto partitions (conparentid <> 0) are checked through their parent.
_FOREIGN_KEYS: LiteralString = """
    SELECT cn.nspname, cl.relname, pn.nspname, pl.relname,
           array(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(attnum, i)
                 JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
                 ORDER BY k.i),
           array(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(attnum, i)
                 JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.attnum
                 ORDER BY k.i)
    FROM pg_constraint c
    JOIN pg_class cl ON cl.oid = c.conrelid
    JOIN pg_namespace cn ON cn.oid = cl.relnamespace
    JOIN pg_class pl ON pl.oid = c.confrelid
    JOIN pg_namespace pn ON pn.oid = pl.relnamespace
    WHERE c.contype = 'f' AND c.conparentid = 0
      AND cn.nspname IN ('core', 'ledger', 'kyc', 'risk', 'ops', 'kb')
    ORDER BY cn.nspname, cl.relname, c.conname
"""


@dataclass(frozen=True, slots=True)
class Mismatch:
    account_id: str
    cached_balance_paise: int
    posted_balance_paise: int
    difference_paise: int


@dataclass(frozen=True, slots=True)
class Reconciliation:
    accounts: int
    mismatches: list[Mismatch]
    ledger_total_paise: int
    """The sum of every Posting in the ledger; double entry makes it zero."""
    unbalanced_entries: int = 0
    orphans: dict[str, int] = field(default_factory=dict[str, int])
    """Rows whose foreign key points nowhere, by ``child → parent``."""

    @property
    def ok(self) -> bool:
        return (
            not self.mismatches
            and self.ledger_total_paise == 0
            and self.unbalanced_entries == 0
            and not self.orphans
        )


def reconcile(conn: psycopg.Connection, *, limit: int = 20) -> Reconciliation:
    """Check balances against ``ledger.account_reconciliation``, entries and foreign keys."""
    accounts = conn.execute("SELECT count(*) FROM ledger.account_reconciliation").fetchone()
    total = conn.execute("SELECT coalesce(sum(amount_paise), 0) FROM ledger.postings").fetchone()
    unbalanced = conn.execute(_UNBALANCED).fetchone()
    rows = conn.execute(_MISMATCHES, [limit]).fetchall()
    return Reconciliation(
        accounts=accounts[0] if accounts else 0,
        mismatches=[Mismatch(*row) for row in rows],
        ledger_total_paise=int(total[0]) if total else 0,
        unbalanced_entries=unbalanced[0] if unbalanced else 0,
        orphans=_orphans(conn),
    )


def _orphans(conn: psycopg.Connection) -> dict[str, int]:
    found: dict[str, int] = {}
    for child_schema, child, parent_schema, parent, columns, keys in conn.execute(
        _FOREIGN_KEYS
    ).fetchall():
        # MATCH SIMPLE: a row with any key column null references nothing.
        query = sql.SQL(
            "SELECT count(*) FROM {child} c WHERE {present}"
            " AND NOT EXISTS (SELECT FROM {parent} p WHERE {joined})"
        ).format(
            child=sql.Identifier(child_schema, child),
            parent=sql.Identifier(parent_schema, parent),
            present=sql.SQL(" AND ").join(
                sql.SQL("c.{} IS NOT NULL").format(sql.Identifier(c)) for c in columns
            ),
            joined=sql.SQL(" AND ").join(
                sql.SQL("p.{} = c.{}").format(sql.Identifier(k), sql.Identifier(c))
                for c, k in zip(columns, keys, strict=True)
            ),
        )
        row = conn.execute(query).fetchone()
        if row and row[0]:
            label = f"{child_schema}.{child} → {parent_schema}.{parent}"
            found[label] = found.get(label, 0) + row[0]
    return found
