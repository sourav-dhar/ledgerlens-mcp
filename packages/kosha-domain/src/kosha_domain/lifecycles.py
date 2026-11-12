"""Status lifecycles: every entity's statuses and the transitions allowed between them.

This module is the single definition of plan v0.2 §1a. The database mirrors it into
``kosha.allowed_transitions`` and enforces it with triggers; the LLD's state diagrams are
checked against it by the test suite, so code, schema and design cannot drift apart.
"""

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class IllegalTransitionError(ValueError):
    """A status change that the entity's lifecycle does not permit."""

    def __init__(self, lifecycle: str, src: StrEnum, dst: StrEnum) -> None:
        super().__init__(f"{lifecycle} cannot move from {src.value!r} to {dst.value!r}")
        self.lifecycle = lifecycle
        self.src = src
        self.dst = dst


@dataclass(frozen=True, slots=True)
class Lifecycle[S: StrEnum]:
    """A state machine over one entity's statuses."""

    name: str
    status_type: type[S]
    initial: S
    transitions: frozenset[tuple[S, S]]

    @property
    def statuses(self) -> tuple[S, ...]:
        """Every status, in declaration order."""
        return tuple(self.status_type)

    def can_transition(self, src: S, dst: S) -> bool:
        return (src, dst) in self.transitions

    def ensure_transition(self, src: S, dst: S) -> None:
        """Raise `IllegalTransitionError` unless ``src → dst`` is permitted."""
        if not self.can_transition(src, dst):
            raise IllegalTransitionError(self.name, src, dst)

    def next_statuses(self, src: S) -> frozenset[S]:
        return frozenset(dst for s, dst in self.transitions if s == src)

    def path_to(self, target: S) -> list[S]:
        """The shortest status history from the initial status to ``target``.

        Ties break by status declaration order, so the result is deterministic.
        """
        order = self.statuses
        previous: dict[S, S | None] = {self.initial: None}
        queue = deque([self.initial])
        while queue:
            status = queue.popleft()
            if status == target:
                path = [status]
                while (prior := previous[path[-1]]) is not None:
                    path.append(prior)
                return path[::-1]
            for nxt in sorted(self.next_statuses(status), key=order.index):
                if nxt not in previous:
                    previous[nxt] = status
                    queue.append(nxt)
        msg = f"{self.name} status {target.value!r} is unreachable"  # pragma: no cover
        raise ValueError(msg)  # pragma: no cover


type AnyLifecycle = Lifecycle[Any]


def _lifecycle[S: StrEnum](
    name: str, statuses: type[S], initial: S, moves: Mapping[S, tuple[S, ...]]
) -> Lifecycle[S]:
    edges = frozenset((src, dst) for src, dsts in moves.items() for dst in dsts)
    return Lifecycle(name, statuses, initial, edges)


# ------------------------------------------------------------------------------ transaction
class TransactionStatus(StrEnum):
    INITIATED = "initiated"
    AUTHORISED = "authorised"
    PROCESSING = "processing"
    PENDING = "pending"
    SUCCESS = "success"
    CREDIT_DELAYED = "credit_delayed"
    DEEMED_SUCCESS = "deemed_success"
    ON_HOLD = "on_hold"
    UNDER_REVIEW = "under_review"
    PENDING_SETTLEMENT = "pending_settlement"
    SETTLED = "settled"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    RETURNED = "returned"
    REVERSAL_INITIATED = "reversal_initiated"
    REVERSED = "reversed"
    PARTIALLY_REVERSED = "partially_reversed"
    REFUNDED = "refunded"
    CHARGEBACK_INITIATED = "chargeback_initiated"


_T = TransactionStatus
TRANSACTION = _lifecycle(
    "Transaction",
    _T,
    _T.INITIATED,
    {
        _T.INITIATED: (_T.AUTHORISED, _T.DECLINED, _T.CANCELLED, _T.EXPIRED),
        _T.AUTHORISED: (_T.PROCESSING,),
        _T.PROCESSING: (_T.PENDING, _T.SUCCESS, _T.FAILED, _T.TIMED_OUT, _T.ON_HOLD),
        _T.ON_HOLD: (_T.UNDER_REVIEW,),
        _T.UNDER_REVIEW: (_T.PROCESSING, _T.DECLINED),
        _T.PENDING: (_T.SUCCESS, _T.CREDIT_DELAYED, _T.DEEMED_SUCCESS, _T.FAILED, _T.RETURNED),
        _T.CREDIT_DELAYED: (_T.SUCCESS, _T.REVERSAL_INITIATED),
        _T.DEEMED_SUCCESS: (_T.SUCCESS, _T.REVERSAL_INITIATED),
        _T.TIMED_OUT: (_T.REVERSAL_INITIATED,),
        _T.SUCCESS: (_T.PENDING_SETTLEMENT, _T.REVERSAL_INITIATED),
        _T.PENDING_SETTLEMENT: (_T.SETTLED,),
        _T.SETTLED: (_T.REFUNDED, _T.CHARGEBACK_INITIATED),
        _T.REVERSAL_INITIATED: (_T.REVERSED, _T.PARTIALLY_REVERSED),
        _T.RETURNED: (_T.REVERSED,),
    },
)


# ------------------------------------------------------------------------------ account
class AccountStatus(StrEnum):
    PENDING_ACTIVATION = "pending_activation"
    ACTIVE = "active"
    KYC_PENDING = "kyc_pending"
    DORMANT = "dormant"
    INOPERATIVE = "inoperative"
    DEBIT_FREEZE = "debit_freeze"
    CREDIT_FREEZE = "credit_freeze"
    TOTAL_FREEZE = "total_freeze"
    LIEN_MARKED = "lien_marked"
    ON_HOLD = "on_hold"
    PENDING_CLOSURE = "pending_closure"
    CLOSED = "closed"


_A = AccountStatus
ACCOUNT = _lifecycle(
    "Account",
    _A,
    _A.PENDING_ACTIVATION,
    {
        _A.PENDING_ACTIVATION: (_A.KYC_PENDING, _A.ACTIVE),
        _A.KYC_PENDING: (_A.ACTIVE,),
        _A.ACTIVE: (
            _A.DORMANT,
            _A.DEBIT_FREEZE,
            _A.CREDIT_FREEZE,
            _A.TOTAL_FREEZE,
            _A.LIEN_MARKED,
            _A.ON_HOLD,
            _A.PENDING_CLOSURE,
        ),
        _A.DORMANT: (_A.INOPERATIVE, _A.ACTIVE),
        _A.INOPERATIVE: (_A.ACTIVE,),
        _A.DEBIT_FREEZE: (_A.ACTIVE,),
        _A.CREDIT_FREEZE: (_A.ACTIVE,),
        _A.TOTAL_FREEZE: (_A.ACTIVE,),
        _A.LIEN_MARKED: (_A.ACTIVE,),
        _A.ON_HOLD: (_A.ACTIVE,),
        _A.PENDING_CLOSURE: (_A.CLOSED,),
    },
)


# ------------------------------------------------------------------------------ KYC profile
class KycStatus(StrEnum):
    NOT_STARTED = "not_started"
    PENDING_DOCUMENTS = "pending_documents"
    PENDING_VCIP = "pending_vcip"
    IN_REVIEW = "in_review"
    ON_HOLD = "on_hold"
    ESCALATED = "escalated"
    VERIFIED = "verified"
    REJECTED = "rejected"
    RE_KYC_DUE = "re_kyc_due"
    RE_KYC_OVERDUE = "re_kyc_overdue"
    EXPIRED = "expired"


_K = KycStatus
KYC_PROFILE = _lifecycle(
    "KYC profile",
    _K,
    _K.NOT_STARTED,
    {
        _K.NOT_STARTED: (_K.PENDING_DOCUMENTS,),
        _K.PENDING_DOCUMENTS: (_K.PENDING_VCIP, _K.IN_REVIEW),
        _K.PENDING_VCIP: (_K.IN_REVIEW,),
        _K.IN_REVIEW: (_K.VERIFIED, _K.REJECTED, _K.ON_HOLD, _K.ESCALATED),
        _K.ON_HOLD: (_K.IN_REVIEW,),
        _K.ESCALATED: (_K.VERIFIED, _K.REJECTED),
        _K.VERIFIED: (_K.RE_KYC_DUE,),
        _K.RE_KYC_DUE: (_K.IN_REVIEW, _K.RE_KYC_OVERDUE),
        _K.RE_KYC_OVERDUE: (_K.IN_REVIEW, _K.EXPIRED),
    },
)


# ------------------------------------------------------------------------------ card
class CardStatus(StrEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    TEMP_BLOCKED = "temp_blocked"
    PIN_BLOCKED = "pin_blocked"
    BLOCKED = "blocked"
    HOTLISTED = "hotlisted"
    EXPIRED = "expired"
    REPLACED = "replaced"


_C = CardStatus
CARD = _lifecycle(
    "Card",
    _C,
    _C.INACTIVE,
    {
        _C.INACTIVE: (_C.ACTIVE, _C.EXPIRED),
        _C.ACTIVE: (_C.TEMP_BLOCKED, _C.PIN_BLOCKED, _C.BLOCKED, _C.HOTLISTED, _C.EXPIRED),
        _C.TEMP_BLOCKED: (_C.ACTIVE, _C.HOTLISTED),
        _C.PIN_BLOCKED: (_C.ACTIVE, _C.HOTLISTED),
        _C.BLOCKED: (_C.REPLACED,),
        _C.HOTLISTED: (_C.REPLACED,),
        _C.EXPIRED: (_C.REPLACED,),
    },
)


# ------------------------------------------------------------------------------ dispute
class DisputeStatus(StrEnum):
    RAISED = "raised"
    ACKNOWLEDGED = "acknowledged"
    AWAITING_CUSTOMER_INFO = "awaiting_customer_info"
    UNDER_INVESTIGATION = "under_investigation"
    ON_HOLD = "on_hold"
    CHARGEBACK_RAISED = "chargeback_raised"
    PRE_ARBITRATION = "pre_arbitration"
    ARBITRATION = "arbitration"
    RESOLVED_CUSTOMER_FAVOUR = "resolved_customer_favour"
    RESOLVED_MERCHANT_FAVOUR = "resolved_merchant_favour"
    AUTO_REVERSED = "auto_reversed"
    WITHDRAWN = "withdrawn"
    CLOSED = "closed"


_D = DisputeStatus
_RESOLVED = (_D.RESOLVED_CUSTOMER_FAVOUR, _D.RESOLVED_MERCHANT_FAVOUR)
DISPUTE = _lifecycle(
    "Dispute",
    _D,
    _D.RAISED,
    {
        _D.RAISED: (_D.ACKNOWLEDGED, _D.AUTO_REVERSED, _D.WITHDRAWN),
        _D.ACKNOWLEDGED: (_D.UNDER_INVESTIGATION, _D.WITHDRAWN),
        _D.UNDER_INVESTIGATION: (
            _D.AWAITING_CUSTOMER_INFO,
            _D.ON_HOLD,
            _D.CHARGEBACK_RAISED,
            *_RESOLVED,
        ),
        _D.AWAITING_CUSTOMER_INFO: (_D.UNDER_INVESTIGATION,),
        _D.ON_HOLD: (_D.UNDER_INVESTIGATION,),
        _D.CHARGEBACK_RAISED: (_D.PRE_ARBITRATION, *_RESOLVED),
        _D.PRE_ARBITRATION: (_D.ARBITRATION, *_RESOLVED),
        _D.ARBITRATION: _RESOLVED,
        _D.AUTO_REVERSED: (_D.CLOSED,),
        _D.RESOLVED_CUSTOMER_FAVOUR: (_D.CLOSED,),
        _D.RESOLVED_MERCHANT_FAVOUR: (_D.CLOSED,),
        _D.WITHDRAWN: (_D.CLOSED,),
    },
)


# ------------------------------------------------------------------------------ AML alert
class AmlAlertStatus(StrEnum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_REVIEW = "in_review"
    PENDING_INFO = "pending_info"
    ON_HOLD = "on_hold"
    ESCALATED = "escalated"
    CLOSED_FALSE_POSITIVE = "closed_false_positive"
    CLOSED_NO_ACTION = "closed_no_action"
    CLOSED_STR_FILED = "closed_str_filed"


_L = AmlAlertStatus
AML_ALERT = _lifecycle(
    "AML alert",
    _L,
    _L.OPEN,
    {
        _L.OPEN: (_L.ASSIGNED,),
        _L.ASSIGNED: (_L.IN_REVIEW,),
        _L.IN_REVIEW: (
            _L.PENDING_INFO,
            _L.ON_HOLD,
            _L.ESCALATED,
            _L.CLOSED_FALSE_POSITIVE,
            _L.CLOSED_NO_ACTION,
        ),
        _L.PENDING_INFO: (_L.IN_REVIEW,),
        _L.ON_HOLD: (_L.IN_REVIEW,),
        _L.ESCALATED: (_L.CLOSED_STR_FILED, _L.CLOSED_NO_ACTION),
    },
)


# ------------------------------------------------------------------------------ transaction review
class TransactionReviewStatus(StrEnum):
    QUEUED = "queued"
    IN_REVIEW = "in_review"
    ON_HOLD = "on_hold"
    CLEARED = "cleared"
    ESCALATED_TO_AML = "escalated_to_aml"
    BLOCKED = "blocked"


_R = TransactionReviewStatus
TRANSACTION_REVIEW = _lifecycle(
    "Transaction review",
    _R,
    _R.QUEUED,
    {
        _R.QUEUED: (_R.IN_REVIEW,),
        _R.IN_REVIEW: (_R.ON_HOLD, _R.CLEARED, _R.ESCALATED_TO_AML, _R.BLOCKED),
        _R.ON_HOLD: (_R.IN_REVIEW,),
    },
)


# ------------------------------------------------------------------------------ beneficiary
class BeneficiaryStatus(StrEnum):
    PENDING_COOLING = "pending_cooling"
    ACTIVE = "active"
    DISABLED = "disabled"
    DELETED = "deleted"


_B = BeneficiaryStatus
BENEFICIARY = _lifecycle(
    "Beneficiary",
    _B,
    _B.PENDING_COOLING,
    {
        _B.PENDING_COOLING: (_B.ACTIVE, _B.DELETED),
        _B.ACTIVE: (_B.DISABLED, _B.DELETED),
        _B.DISABLED: (_B.ACTIVE, _B.DELETED),
    },
)


LIFECYCLES: tuple[AnyLifecycle, ...] = (
    TRANSACTION,
    ACCOUNT,
    KYC_PROFILE,
    CARD,
    DISPUTE,
    AML_ALERT,
    TRANSACTION_REVIEW,
    BENEFICIARY,
)
"""Every lifecycle, in the order the schema creates them."""
