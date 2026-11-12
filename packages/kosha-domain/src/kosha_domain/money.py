"""Money as integer paise.

Every amount in Kosha is an `int` count of paise (1 rupee = 100 paise) from the database to
the wire. Rupees appear only at the edges: parsed from text on the way in, rendered with
Indian digit grouping (lakh, crore) on the way out. Floats are refused outright.
"""

from decimal import Decimal, InvalidOperation
from typing import NewType

Paise = NewType("Paise", int)
"""An amount of Indian rupees in paise. Zero-cost at runtime: it is an `int`."""

_PAISE_PER_RUPEE = 100


def paise_from_rupees(rupees: str | Decimal) -> Paise:
    """Convert a rupee amount such as ``"1234.50"`` to paise, exactly.

    Raises:
        TypeError: for floats, which cannot represent most paise amounts exactly.
        ValueError: for non-numeric text or amounts finer than one paisa.
    """
    if isinstance(rupees, float):
        msg = "float rupee amounts are refused; pass a str or Decimal"
        raise TypeError(msg)
    try:
        amount = Decimal(rupees)
    except InvalidOperation:
        msg = f"not a rupee amount: {rupees!r}"
        raise ValueError(msg) from None
    if not amount.is_finite():
        msg = f"not a rupee amount: {rupees!r}"
        raise ValueError(msg)
    paise = amount * _PAISE_PER_RUPEE
    if paise != paise.to_integral_value():
        msg = f"{rupees!r} is not a whole number of paisa"
        raise ValueError(msg)
    return Paise(int(paise))


def format_inr(paise: int) -> str:
    """Render paise as rupees with Indian digit grouping: ``12345678`` → ``₹1,23,456.78``."""
    sign = "-" if paise < 0 else ""
    rupees, fraction = divmod(abs(paise), _PAISE_PER_RUPEE)
    return f"{sign}₹{_group_indian(rupees)}.{fraction:02d}"


def _group_indian(rupees: int) -> str:
    """Group the last three digits, then every two: 12345678 → 1,23,45,678."""
    digits = str(rupees)
    if len(digits) <= 3:  # noqa: PLR2004 — the thousands group is three digits wide
        return digits
    head, tail = digits[:-3], digits[-3:]
    pairs = [head[max(i - 2, 0) : i] for i in range(len(head), 0, -2)]
    return ",".join(reversed(pairs)) + "," + tail
