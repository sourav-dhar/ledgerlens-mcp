"""Disputes Customers raise and Transaction reviews the risk engine queues.

Disputes come from the Transactions people actually complain about: debits that came
back late (or have not yet), card payments that went to chargeback, refunds, and a few
claims of unauthorised or duplicate payments. Turnaround times and compensation follow
RBI's TAT harmonisation circular: T+1 for UPI, IMPS and NEFT, T+5 for ATM, and ₹100 for
every day a reversal runs past it. Every flagged Transaction is queued for review.
"""

import math
import random
from datetime import datetime, timedelta

from kosha_datagen import refs
from kosha_datagen.chance import pick
from kosha_datagen.config import GenerationConfig
from kosha_datagen.payments import Booked
from kosha_datagen.rows import Dispute, TransactionReview
from kosha_domain.ids import IdPrefix, new_id
from kosha_domain.lifecycles import DisputeStatus, TransactionReviewStatus, TransactionStatus
from kosha_domain.money import format_inr
from kosha_domain.vocabulary import DisputeReason, Rail, ReviewPriority

D = DisputeStatus
T = TransactionStatus
R = TransactionReviewStatus
DAY = timedelta(days=1)
HOUR = timedelta(hours=1)
COMPENSATION_PER_DAY_PAISE = 10_000
_TAT = {Rail.ATM: 5 * DAY, Rail.CARD_POS: 5 * DAY, Rail.CARD_ECOM: 5 * DAY}
_LATE_STATES = {T.CREDIT_DELAYED, T.DEEMED_SUCCESS, T.REVERSAL_INITIATED, T.RETURNED}
_CARD_CLAIMS = {
    DisputeReason.GOODS_NOT_RECEIVED: 5,
    DisputeReason.UNAUTHORISED: 3,
    DisputeReason.DUPLICATE: 1,
    DisputeReason.AMOUNT_MISMATCH: 1,
}


def tat(rail: Rail) -> timedelta:
    return _TAT.get(rail, DAY)


def dispute_rows(
    config: GenerationConfig, rng: random.Random, booked: list[Booked]
) -> list[Dispute]:
    disputes: list[Dispute] = []
    for b in booked:
        txn = b.txn
        if txn.posted_at is None or txn.direction != "debit":
            continue
        status = txn.status
        if status is T.CHARGEBACK_INITIATED:
            disputes.append(_chargeback(config, rng, b))
        elif status is T.REVERSED and rng.random() < 0.15:
            disputes.append(_reversed(config, rng, b))
        elif status in _LATE_STATES and rng.random() < 0.5:
            disputes.append(_still_open(config, rng, b))
        elif status is T.REFUNDED and rng.random() < 0.12:
            disputes.append(_refunded(config, rng, b))
        elif status in (T.SETTLED, T.SUCCESS) and txn.merchant_id and rng.random() < 0.0003:
            disputes.append(_claim(config, rng, b))
    return disputes


def _dispute(
    rng: random.Random,
    b: Booked,
    *,
    created: datetime,
    reason: DisputeReason,
    status: DisputeStatus,
    amount: int | None = None,
    compensation: int = 0,
    resolution: str | None = None,
    chargeback_ref: str | None = None,
) -> Dispute:
    txn = b.txn
    return Dispute(
        dispute_id=new_id(IdPrefix.DISPUTE, at=created, rng=rng),
        txn_id=txn.txn_id,
        txn_initiated_at=txn.initiated_at,
        customer_id=txn.customer_id,
        reason_code=reason,
        amount_paise=amount or txn.amount_paise,
        status=status,
        tat_due_at=txn.initiated_at + tat(txn.rail),
        compensation_paise=compensation,
        resolution=resolution,
        chargeback_ref=chargeback_ref,
        idempotency_key=None,
        created_by=f"staff-{rng.randint(100, 160):04d}",
        created_at=created,
    )


def _chargeback(config: GenerationConfig, rng: random.Random, b: Booked) -> Dispute:
    raised = b.reached(T.CHARGEBACK_INITIATED) or b.txn.initiated_at
    created = max(b.txn.initiated_at, raised - rng.randint(1, 3) * DAY)
    age = config.now - raised
    status = D.CHARGEBACK_RAISED
    if age > 45 * DAY:
        status = pick(rng, {D.PRE_ARBITRATION: 3, D.ARBITRATION: 1})
    elif age > 20 * DAY:
        status = pick(rng, {D.CHARGEBACK_RAISED: 2, D.PRE_ARBITRATION: 1})
    return _dispute(
        rng,
        b,
        created=created,
        reason=pick(rng, _CARD_CLAIMS),
        status=status,
        chargeback_ref=f"CB{b.txn.rrn or refs.digits(rng, 12)}",
    )


def _reversed(config: GenerationConfig, rng: random.Random, b: Booked) -> Dispute:
    txn = b.txn
    back = b.reached(T.REVERSED) or config.now
    created = txn.initiated_at + rng.randint(2, 20) * HOUR
    late_days = math.ceil((back - (txn.initiated_at + tat(txn.rail))) / DAY)
    compensation = max(0, late_days) * COMPENSATION_PER_DAY_PAISE
    if created >= back:
        created = back - HOUR
    status = D.CLOSED if config.now - back > 7 * DAY else D.AUTO_REVERSED
    reason = (
        DisputeReason.CREDIT_NOT_RECEIVED
        if T.CREDIT_DELAYED in dict(b.steps) or T.RETURNED in dict(b.steps)
        else DisputeReason.FAILED_BUT_DEBITED
    )
    resolution = f"Auto-reversed {back:%d %b %Y}"
    if compensation:
        resolution += f"; {format_inr(compensation)} compensation for {late_days} days past TAT"
    return _dispute(
        rng,
        b,
        created=max(created, txn.initiated_at),
        reason=reason,
        status=status,
        compensation=compensation,
        resolution=resolution,
    )


def _still_open(config: GenerationConfig, rng: random.Random, b: Booked) -> Dispute:
    txn = b.txn
    created = min(txn.initiated_at + rng.randint(1, 12) * HOUR, config.now)
    age = config.now - created
    status = D.RAISED if age < DAY else pick(rng, {D.ACKNOWLEDGED: 2, D.UNDER_INVESTIGATION: 3})
    return _dispute(
        rng, b, created=created, reason=DisputeReason.CREDIT_NOT_RECEIVED, status=status
    )


def _refunded(config: GenerationConfig, rng: random.Random, b: Booked) -> Dispute:
    refunded = b.reached(T.REFUNDED) or config.now
    created = max(b.txn.initiated_at, refunded - rng.randint(2, 6) * DAY)
    return _dispute(
        rng,
        b,
        created=created,
        reason=DisputeReason.GOODS_NOT_RECEIVED,
        status=D.CLOSED,
        resolution="Merchant refunded the customer",
    )


def _claim(config: GenerationConfig, rng: random.Random, b: Booked) -> Dispute:
    txn = b.txn
    created = min(txn.initiated_at + rng.randint(1, 20) * DAY, config.now)
    age = config.now - created
    reason = pick(rng, _CARD_CLAIMS)
    amount = None
    if reason is DisputeReason.AMOUNT_MISMATCH:
        amount = max(100, txn.amount_paise * rng.randint(10, 60) // 100)
    if age < 10 * DAY:
        status = pick(rng, {D.RAISED: 2, D.ACKNOWLEDGED: 2, D.UNDER_INVESTIGATION: 3})
        resolution = None
    elif age < 40 * DAY:
        status = pick(rng, {D.UNDER_INVESTIGATION: 3, D.AWAITING_CUSTOMER_INFO: 2, D.ON_HOLD: 1})
        resolution = None
    else:
        status = pick(
            rng, {D.CLOSED: 6, D.RESOLVED_MERCHANT_FAVOUR: 2, D.RESOLVED_CUSTOMER_FAVOUR: 1}
        )
        resolution = {
            D.CLOSED: "Withdrawn after the customer recognised the payment",
            D.RESOLVED_MERCHANT_FAVOUR: "Merchant evidence of delivery accepted",
            D.RESOLVED_CUSTOMER_FAVOUR: "Merchant did not respond within the window",
        }[status]
    return _dispute(
        rng, b, created=created, reason=reason, status=status, amount=amount, resolution=resolution
    )


def review_rows(
    config: GenerationConfig, rng: random.Random, booked: list[Booked], escalated: set[str]
) -> list[TransactionReview]:
    """One review per flagged Transaction, in the state its outcome implies."""
    reviews: list[TransactionReview] = []
    for b in booked:
        txn = b.txn
        if not txn.is_flagged:
            continue
        created = (b.reached(T.ON_HOLD) or txn.initiated_at) + rng.randint(1, 10) * timedelta(
            minutes=1
        )
        created = min(created, config.now)
        if txn.status is T.ON_HOLD:
            status = R.QUEUED
        elif txn.status is T.UNDER_REVIEW:
            status = pick(rng, {R.IN_REVIEW: 3, R.ON_HOLD: 1})
        elif txn.status is T.DECLINED:
            status = R.BLOCKED
        elif txn.txn_id in escalated:
            status = R.ESCALATED_TO_AML
        elif config.now - created < 2 * DAY:
            status = pick(rng, {R.QUEUED: 1, R.IN_REVIEW: 1})
        else:
            status = R.CLEARED
        risk = txn.risk_score or 0
        priority = (
            ReviewPriority.URGENT
            if risk >= 90
            else ReviewPriority.HIGH
            if risk >= 80
            else ReviewPriority.NORMAL
        )
        reviews.append(
            TransactionReview(
                review_id=new_id(IdPrefix.TRANSACTION_REVIEW, at=created, rng=rng),
                txn_id=txn.txn_id,
                txn_initiated_at=txn.initiated_at,
                reason=txn.hold_reason or f"Risk score {risk} above review threshold",
                priority=priority,
                status=status,
                idempotency_key=None,
                created_by="risk-engine",
                created_at=created,
            )
        )
    return reviews
