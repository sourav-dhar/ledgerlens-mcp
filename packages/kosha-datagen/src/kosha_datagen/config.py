"""What to generate: the seed, the as-of date the data ends on, and how much of it."""

import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time

CUSTOMERS_AT_FULL_SCALE = 5_000
MERCHANTS_AT_FULL_SCALE = 1_200
MIN_MERCHANTS = 40
WINDOW_MONTHS = 18
"""Months of Transactions, counting the as-of month (plan v0.2 §2)."""

LEDGER_HISTORY_YEARS = 4
"""How far before the window the oldest relationships began."""


@dataclass(frozen=True, slots=True)
class GenerationConfig:
    """A dataset is fully determined by these values.

    Attributes:
        as_of: the last day of the dataset. Nothing happens after midday UTC on it; in-flight
            states (credit delayed, holds, open alerts) cluster in the days before it.
        seed: reproduces every value, identifiers included.
        scale: fraction of the planned volume. Customers are generated in a fixed order from
            per-Customer random streams, so a smaller scale is a prefix of a larger one.
    """

    as_of: date
    seed: int = 1729
    scale: float = 1.0

    def __post_init__(self) -> None:
        if not 0 < self.scale <= 1:
            msg = f"scale must be in (0, 1], got {self.scale}"
            raise ValueError(msg)

    @property
    def customers(self) -> int:
        return max(1, round(CUSTOMERS_AT_FULL_SCALE * self.scale))

    @property
    def merchants(self) -> int:
        return max(MIN_MERCHANTS, round(MERCHANTS_AT_FULL_SCALE * self.scale))

    @property
    def now(self) -> datetime:
        """The dataset's present: midday UTC on the as-of date."""
        return datetime.combine(self.as_of, time(12, 0), UTC)

    @property
    def window_start(self) -> datetime:
        """First instant of the Transaction window, which is also when the ledger went live."""
        months = self.as_of.year * 12 + self.as_of.month - 1 - (WINDOW_MONTHS - 1)
        return datetime(months // 12, months % 12 + 1, 1, tzinfo=UTC)

    @property
    def history_start(self) -> datetime:
        start = self.window_start
        return start.replace(year=start.year - LEDGER_HISTORY_YEARS)

    def rng(self, *stream: object) -> random.Random:
        """An independent random stream, e.g. ``rng("customer", 42)``.

        String seeds are hashed with SHA-512, so streams are stable across Python runs and
        independent of one another.
        """
        return random.Random(":".join(map(str, ("kosha", self.seed, *stream))))
