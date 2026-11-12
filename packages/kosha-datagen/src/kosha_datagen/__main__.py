"""``python -m kosha_datagen``: generate, load and reconcile into ``$DATABASE_URL``.

The database must already be migrated (``uv run poe seed`` migrates first) and empty.
Exits non-zero if the ledger does not reconcile.
"""

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime

import psycopg

from kosha_datagen.config import GenerationConfig
from kosha_datagen.dataset import generate
from kosha_datagen.loader import AlreadySeededError, LoadReport, load
from kosha_datagen.reconcile import reconcile


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="kosha-seed", description=__doc__)
    parser.add_argument("--seed", type=int, default=1729, help="reproduces every value")
    parser.add_argument(
        "--scale", type=float, default=1.0, help="fraction of the planned volume, in (0, 1]"
    )
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=datetime.now(UTC).date(),
        help="last day of the dataset (default: today, UTC)",
    )
    return parser.parse_args(argv)


def _say(message: str) -> None:
    sys.stdout.write(message + "\n")
    sys.stdout.flush()


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse(argv)
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        sys.exit("DATABASE_URL is not set")
    config = GenerationConfig(as_of=args.as_of, seed=args.seed, scale=args.scale)
    _say(
        f"Seeding {config.customers:,} customers, seed {config.seed}, "
        f"{config.window_start:%b %Y} to {config.as_of:%d %b %Y}"
    )

    def progress(report: LoadReport) -> None:
        customers = report.rows.get("core.customers", 0)
        if report.batches % 5 == 0 or customers == config.customers:
            rate = report.total_rows / max(report.seconds, 0.001)
            _say(f"  {customers:>6,} customers, {report.total_rows:>11,} rows ({rate:,.0f}/s)")

    with psycopg.connect(database_url, autocommit=True) as conn:
        try:
            report = load(conn, config, generate(config), progress=progress)
        except AlreadySeededError as exc:
            sys.exit(str(exc))
        for table, count in report.rows.items():
            _say(f"  {table:<36}{count:>11,}")
        result = reconcile(conn)
    checks = "set-based after the load" if report.triggers_off else "per row"
    _say(f"Loaded {report.total_rows:,} rows in {report.seconds:.0f}s (integrity checked {checks})")
    if not result.ok:
        for m in result.mismatches:
            _say(f"  {m.account_id}: cached balance off by {m.difference_paise} paise")
        for label, count in result.orphans.items():
            _say(f"  {count:,} orphaned rows in {label}")
        sys.exit(
            f"Ledger does not reconcile: {result.unbalanced_entries} unbalanced entries, "
            f"postings total {result.ledger_total_paise} paise"
        )
    _say(
        f"Ledger reconciles: {result.accounts:,} accounts, every entry balanced, "
        "every foreign key holds, postings sum to zero"
    )


if __name__ == "__main__":
    main()
