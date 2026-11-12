"""Small helpers for drawing from seeded random streams."""

import random
from collections.abc import Mapping
from datetime import datetime, timedelta


def pick[T](rng: random.Random, weights: Mapping[T, float]) -> T:
    """One key of ``weights``, drawn with probability proportional to its value."""
    return rng.choices(list(weights), list(weights.values()))[0]


def between(rng: random.Random, start: datetime, end: datetime) -> datetime:
    """A whole second in ``[start, end]``; ``start`` when the range is empty."""
    seconds = max(0, int((end - start).total_seconds()))
    return start + timedelta(seconds=rng.randint(0, seconds))
