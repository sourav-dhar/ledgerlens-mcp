"""When a Transaction may be disputed, and how fast it must be put right.

Turnaround times and compensation follow RBI's TAT harmonisation circular: a failed
UPI, IMPS or NEFT debit must be reversed by T+1, an ATM or card one by T+5, and every
day past that owes the Customer ₹100.
"""

from datetime import timedelta

from kosha_domain.lifecycles import DisputeStatus, TransactionStatus
from kosha_domain.vocabulary import Direction, Rail

COMPENSATION_PER_DAY_PAISE = 10_000
"""₹100 for each day a reversal runs past its turnaround time."""

_DAY = timedelta(days=1)
_SLOW_RAILS = {Rail.ATM: 5 * _DAY, Rail.CARD_POS: 5 * _DAY, Rail.CARD_ECOM: 5 * _DAY}

_T = TransactionStatus
_NOT_DISPUTABLE = frozenset(
    {
        # Still in flight: the outcome is not known yet, so there is nothing to dispute.
        _T.INITIATED,
        _T.AUTHORISED,
        _T.PROCESSING,
        _T.PENDING,
        # Ended without moving money.
        _T.DECLINED,
        _T.CANCELLED,
        _T.EXPIRED,
    }
)


_D = DisputeStatus
OPEN_DISPUTE_STATUSES = frozenset(
    {
        _D.RAISED,
        _D.ACKNOWLEDGED,
        _D.AWAITING_CUSTOMER_INFO,
        _D.UNDER_INVESTIGATION,
        _D.ON_HOLD,
        _D.CHARGEBACK_RAISED,
        _D.PRE_ARBITRATION,
        _D.ARBITRATION,
    }
)
"""Not yet decided: while one of these stands, the Transaction cannot be disputed again."""


def turnaround(rail: Rail) -> timedelta:
    """How long after initiation a failed debit on ``rail`` must be reversed."""
    return _SLOW_RAILS.get(rail, _DAY)


def is_disputable(direction: Direction, status: TransactionStatus) -> bool:
    """Whether a Customer may dispute a Transaction in this state.

    Only debits: a missing credit is disputed through the debit that should have
    caused it. A failed or timed-out debit stays disputable, because "failed but
    debited" is the commonest complaint there is.
    """
    return direction is Direction.DEBIT and status not in _NOT_DISPUTABLE
