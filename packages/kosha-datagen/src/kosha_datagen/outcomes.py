"""How a Transaction ends: the outcome scenarios and their weights.

Each scenario is an explicit status path rather than a sampled walk, so its economics are
stated next to it: whether money left the Account, whether it is held, and whether any of
it comes back as a separate reversal or refund. The test suite checks every path against
the Transaction lifecycle.
"""

from dataclasses import dataclass
from enum import StrEnum

from kosha_domain.lifecycles import TransactionStatus
from kosha_domain.vocabulary import Rail

T = TransactionStatus
_SUBMIT = (T.INITIATED, T.AUTHORISED, T.PROCESSING)


class Comeback(StrEnum):
    """What returns to the Account after the original Transaction posted."""

    NONE = "none"
    REVERSAL = "reversal"
    PARTIAL_REVERSAL = "partial_reversal"
    REFUND = "refund"


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    path: tuple[TransactionStatus, ...]
    posts: bool
    """Whether the original Transaction moves money (has a journal entry)."""
    holds: bool = False
    """Whether its amount sits in the Account's hold while the case is open."""
    comeback: Comeback = Comeback.NONE
    in_flight_days: int | None = None
    """Only Transactions initiated this many days before the as-of date end this way."""
    failure_code: str | None = None

    @property
    def status(self) -> TransactionStatus:
        return self.path[-1]


SUCCESS = Scenario("success", (*_SUBMIT, T.SUCCESS), posts=True)
SETTLED = Scenario("settled", (*_SUBMIT, T.SUCCESS, T.PENDING_SETTLEMENT, T.SETTLED), posts=True)
AWAITING_SETTLEMENT = Scenario(
    "awaiting_settlement",
    (*_SUBMIT, T.SUCCESS, T.PENDING_SETTLEMENT),
    posts=True,
    in_flight_days=2,
)
BATCHED = Scenario("batched", (*_SUBMIT, T.PENDING, T.SUCCESS), posts=True)
IN_NEXT_BATCH = Scenario("in_next_batch", (*_SUBMIT, T.PENDING), posts=True, in_flight_days=1)
INSUFFICIENT_FUNDS = Scenario("insufficient_funds", (T.INITIATED, T.DECLINED), posts=False)

_CORE: dict[Scenario, int] = {
    SUCCESS: 9_560,
    Scenario("failed", (*_SUBMIT, T.FAILED), posts=False, failure_code="U30"): 60,
    Scenario("bank_down", (*_SUBMIT, T.FAILED), posts=False, failure_code="U68"): 20,
    Scenario("wrong_pin", (T.INITIATED, T.DECLINED), posts=False, failure_code="ZM"): 30,
    Scenario("limit_exceeded", (T.INITIATED, T.DECLINED), posts=False, failure_code="Z8"): 15,
    Scenario("cancelled", (T.INITIATED, T.CANCELLED), posts=False): 10,
}
TIMED_OUT_REVERSED = Scenario(
    "timed_out_reversed",
    (*_SUBMIT, T.TIMED_OUT, T.REVERSAL_INITIATED, T.REVERSED),
    posts=True,
    comeback=Comeback.REVERSAL,
    failure_code="U90",
)
_INSTANT: dict[Scenario, int] = {
    TIMED_OUT_REVERSED: 15,
    Scenario(
        "credit_delayed_then_credited",
        (*_SUBMIT, T.PENDING, T.CREDIT_DELAYED, T.SUCCESS),
        posts=True,
    ): 10,
    Scenario(
        "credit_delayed_reversed",
        (*_SUBMIT, T.PENDING, T.CREDIT_DELAYED, T.REVERSAL_INITIATED, T.REVERSED),
        posts=True,
        comeback=Comeback.REVERSAL,
        failure_code="BT",
    ): 8,
    Scenario(
        "held_then_cleared",
        (*_SUBMIT, T.ON_HOLD, T.UNDER_REVIEW, T.PROCESSING, T.SUCCESS),
        posts=True,
    ): 6,
    Scenario(
        "held_then_declined",
        (*_SUBMIT, T.ON_HOLD, T.UNDER_REVIEW, T.DECLINED),
        posts=False,
        failure_code="U16",
    ): 2,
    Scenario(
        "partially_reversed",
        (*_SUBMIT, T.SUCCESS, T.REVERSAL_INITIATED, T.PARTIALLY_REVERSED),
        posts=True,
        comeback=Comeback.PARTIAL_REVERSAL,
    ): 2,
    # Open cases: only on recent Transactions, which is where operations queues find them.
    Scenario(
        "credit_delayed",
        (*_SUBMIT, T.PENDING, T.CREDIT_DELAYED),
        posts=True,
        in_flight_days=3,
    ): 6,
    Scenario(
        "on_hold",
        (*_SUBMIT, T.ON_HOLD),
        posts=False,
        holds=True,
        in_flight_days=4,
    ): 3,
    Scenario(
        "under_review",
        (*_SUBMIT, T.ON_HOLD, T.UNDER_REVIEW),
        posts=False,
        holds=True,
        in_flight_days=5,
    ): 3,
    Scenario(
        "reversal_pending",
        (*_SUBMIT, T.TIMED_OUT, T.REVERSAL_INITIATED),
        posts=True,
        in_flight_days=1,
        failure_code="U90",
    ): 2,
}
# Deemed success is UPI's: NPCI approves when the beneficiary bank times out.
_UPI_ONLY: dict[Scenario, int] = {
    Scenario(
        "deemed_then_confirmed",
        (*_SUBMIT, T.PENDING, T.DEEMED_SUCCESS, T.SUCCESS),
        posts=True,
    ): 8,
    Scenario(
        "deemed_then_reversed",
        (*_SUBMIT, T.PENDING, T.DEEMED_SUCCESS, T.REVERSAL_INITIATED, T.REVERSED),
        posts=True,
        comeback=Comeback.REVERSAL,
        failure_code="RB",
    ): 3,
    Scenario(
        "deemed_success",
        (*_SUBMIT, T.PENDING, T.DEEMED_SUCCESS),
        posts=True,
        in_flight_days=2,
    ): 4,
}
_COLLECT = {
    Scenario("collect_expired", (T.INITIATED, T.EXPIRED), posts=False, failure_code="U69"): 12,
}
_BANK_TRANSFER = {
    Scenario(
        "returned_reversed",
        (*_SUBMIT, T.PENDING, T.RETURNED, T.REVERSED),
        posts=True,
        comeback=Comeback.REVERSAL,
        failure_code="R03",
    ): 8,
    Scenario(
        "returned",
        (*_SUBMIT, T.PENDING, T.RETURNED),
        posts=True,
        in_flight_days=2,
        failure_code="R03",
    ): 3,
}
_CARD = {
    SETTLED: 9_560,
    AWAITING_SETTLEMENT: 300,
    Scenario(
        "refunded",
        (*_SUBMIT, T.SUCCESS, T.PENDING_SETTLEMENT, T.SETTLED, T.REFUNDED),
        posts=True,
        comeback=Comeback.REFUND,
    ): 60,
    Scenario(
        "chargeback",
        (*_SUBMIT, T.SUCCESS, T.PENDING_SETTLEMENT, T.SETTLED, T.CHARGEBACK_INITIATED),
        posts=True,
    ): 4,
    Scenario("card_declined", (T.INITIATED, T.DECLINED), posts=False, failure_code="55"): 40,
    Scenario("card_failed", (*_SUBMIT, T.FAILED), posts=False, failure_code="91"): 25,
}

FAILURE_REASONS = {
    "U30": "Debit has failed",
    "U68": "Remitter bank not available",
    "ZM": "Invalid UPI PIN",
    "Z8": "Per-transaction limit exceeded",
    "Z9": "Insufficient funds in remitter account",
    "U90": "Deemed high response time from beneficiary bank",
    "BT": "Beneficiary bank timed out after debit",
    "RB": "Deemed transaction reversed by beneficiary bank",
    "U16": "Risk threshold exceeded",
    "U69": "Collect request expired",
    "R03": "Beneficiary account closed or does not exist",
    "55": "Incorrect PIN",
    "51": "Insufficient funds",
    "91": "Issuer or switch inoperative",
}


def debit_scenarios(rail: Rail) -> dict[Scenario, int]:
    """Outcome weights for money leaving an Account on ``rail``."""
    match rail:
        case Rail.CARD_POS | Rail.CARD_ECOM:
            return _CARD
        case Rail.UPI:
            return _CORE | _INSTANT | _UPI_ONLY | _COLLECT
        case Rail.IMPS:
            return _CORE | _INSTANT | _BANK_TRANSFER
        case Rail.NEFT | Rail.RTGS:
            # Batch-settled rails pass through `pending` on the way to success.
            weights = _CORE | _BANK_TRANSFER | {IN_NEXT_BATCH: 150}
            weights[BATCHED] = weights.pop(SUCCESS)
            return weights
        case Rail.ATM:
            # Cash not dispensed but the Account debited: a timeout, reversed T+5.
            return _CORE | {TIMED_OUT_REVERSED: 20}
        case Rail.NACH | Rail.INTERNAL:
            return {SUCCESS: 1}


def credit_scenario(rail: Rail) -> Scenario:
    """Money arriving: a Customer's statement shows only credits that land."""
    return BATCHED if rail in (Rail.NEFT, Rail.RTGS) else SUCCESS


def insufficient_funds_code(rail: Rail) -> str:
    return "51" if rail in (Rail.CARD_POS, Rail.CARD_ECOM, Rail.ATM) else "Z9"


ALL_SCENARIOS: frozenset[Scenario] = frozenset(
    {*_CORE, *_INSTANT, *_UPI_ONLY, *_COLLECT, *_BANK_TRANSFER, *_CARD}
    | {BATCHED, IN_NEXT_BATCH, INSUFFICIENT_FUNDS}
)
