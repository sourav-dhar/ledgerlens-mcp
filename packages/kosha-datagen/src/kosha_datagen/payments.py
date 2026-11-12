"""The Transaction timeline: intents in, Transactions, history and balanced ledger out.

Intents (pay this merchant, receive this salary) are executed in time order against the
Accounts' running balances. Each draws an outcome scenario; a debit the Account cannot
cover is declined for insufficient funds instead. A scenario whose later steps would fall
after the as-of date is cut short there, which is how open cases (credit delayed, on hold,
awaiting settlement) arise on recent Transactions. Money that comes back after a reversal
or refund arrives as its own credit Transaction, later on the timeline.
"""

import heapq
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from kosha_datagen import catalog, refs
from kosha_datagen.accounts import Holding
from kosha_datagen.chance import pick
from kosha_datagen.config import GenerationConfig
from kosha_datagen.ledger import Leg, legs_for, opening_legs
from kosha_datagen.outcomes import (
    INSUFFICIENT_FUNDS,
    SUCCESS,
    Comeback,
    Scenario,
    credit_scenario,
    debit_scenarios,
    insufficient_funds_code,
)
from kosha_datagen.rows import JournalEntry, Posting, Transaction, TransactionStatusChange
from kosha_domain.ids import IdPrefix, new_id
from kosha_domain.lifecycles import TransactionStatus
from kosha_domain.vocabulary import Actor, Channel, Direction, Rail, TransactionType, Typology

T = TransactionStatus
SECOND = timedelta(seconds=1)
MINUTE = timedelta(minutes=1)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
_POSTING_STATUSES = {T.PENDING, T.SUCCESS, T.TIMED_OUT}
_CITIES = {c.name: c for c in catalog.CITIES}
_ACTOR = {
    T.AUTHORISED: Actor.SYSTEM,
    T.PROCESSING: Actor.SYSTEM,
    T.ON_HOLD: Actor.RISK_ENGINE,
    T.UNDER_REVIEW: Actor.STAFF,
    T.CANCELLED: Actor.CUSTOMER,
    T.REVERSAL_INITIATED: Actor.SYSTEM,
    T.CHARGEBACK_INITIATED: Actor.STAFF,
    T.REFUNDED: Actor.SYSTEM,
}


@dataclass(frozen=True, slots=True)
class Counterparty:
    name: str
    vpa: str | None = None
    account_masked: str | None = None
    ifsc: str | None = None
    merchant_id: str | None = None
    mcc: int | None = None
    city: str | None = None
    """Where a card was used, for card-present and planted overseas Transactions."""
    geo: tuple[str, Decimal, Decimal] | None = None


@dataclass(slots=True)
class Intent:
    """Something that would move money, before its outcome is known."""

    at: datetime
    holding: Holding
    direction: Direction
    rail: Rail
    txn_type: TransactionType
    amount_paise: int
    counterparty: Counterparty
    remark: str
    channel: Channel = Channel.MOBILE_APP
    customer_initiated: bool = True
    counter_holding: Holding | None = None
    """The Customer's own other Account, for an internal transfer."""
    sweep: bool = False
    """Move what is available, up to the amount, rather than risk a decline."""
    budget_share: float | None = None
    """Move at most this share of the available balance, in ₹5,000 steps (deposit bookings)."""
    discretionary: bool = False
    """Skipped when it would leave less than half the available balance."""
    scenario: Scenario | None = None
    pattern: Typology | None = None
    reverses: "Booked | None" = None
    interest_bps: int | None = None
    """Interest at this annual rate on the balance when the intent executes (a quarter's)."""
    then: "Callable[[Booked | None], None] | None" = None


@dataclass(frozen=True, slots=True)
class Booked:
    """A generated Transaction with what the later stages need to know about it."""

    txn: Transaction
    scenario: Scenario
    customer_initiated: bool
    pattern: Typology | None
    steps: list[tuple[TransactionStatus, datetime]]
    """Every status the Transaction passed through, with when, in order."""

    def reached(self, status: TransactionStatus) -> datetime | None:
        return next((at for s, at in self.steps if s is status), None)


@dataclass(slots=True)
class Ledger:
    transactions: list[Transaction] = field(default_factory=list[Transaction])
    history: list[TransactionStatusChange] = field(default_factory=list[TransactionStatusChange])
    entries: list[JournalEntry] = field(default_factory=list[JournalEntry])
    postings: list[Posting] = field(default_factory=list[Posting])
    booked: list[Booked] = field(default_factory=list[Booked])


class Timeline:
    """Executes one Customer's intents in time order."""

    def __init__(
        self,
        config: GenerationConfig,
        rng: random.Random,
        device_id: str,
        home: catalog.City,
    ) -> None:
        self._config = config
        self._rng = rng
        self._device_id = device_id
        self._home = home
        self._queue: list[tuple[datetime, int, Intent]] = []
        self._seq = 0
        self.ledger = Ledger()

    def schedule(self, intent: Intent) -> None:
        if self._config.window_start <= intent.at <= self._config.now:
            heapq.heappush(self._queue, (intent.at, self._seq, intent))
            self._seq += 1

    def bring_forward(self, holding: Holding, amount_paise: int) -> None:
        """Post a balance brought forward at ledger go-live."""
        if amount_paise <= 0:
            return
        at = self._config.window_start
        self._entry(
            None,
            None,
            at,
            "Balance brought forward at ledger go-live",
            opening_legs(holding.account_id, amount_paise),
        )
        holding.balance_paise += amount_paise

    def run(self) -> Ledger:
        while self._queue:
            _, _, intent = heapq.heappop(self._queue)
            booked = self._execute(intent)
            if intent.then is not None:
                intent.then(booked)
        return self.ledger

    # --- execution

    def _execute(self, intent: Intent) -> Booked | None:
        admitted = self._admit(intent)
        if admitted is None:
            return None
        amount, scenario = admitted
        holding = intent.holding
        steps = self._steps(scenario, intent.at)
        final, final_at = steps[-1]
        posted_at = next((at for s, at in steps if s in _POSTING_STATUSES), None)
        posts = scenario.posts and posted_at is not None
        completed = len(steps) == len(scenario.path)
        txn = self._transaction(intent, amount, scenario, steps, posted_at if posts else None)
        self._history(txn, steps)
        if posted_at is not None and posts:
            counter = intent.counter_holding
            legs = legs_for(
                account_id=holding.account_id,
                direction=intent.direction,
                rail=intent.rail,
                txn_type=intent.txn_type,
                amount_paise=amount,
                counter_account_id=counter.account_id if counter else None,
            )
            self._entry(txn.txn_id, txn.initiated_at, posted_at, _describe(intent), legs)
            sign = 1 if intent.direction is Direction.CREDIT else -1
            holding.balance_paise += sign * amount
            if counter is not None:
                counter.balance_paise -= sign * amount
            txn = txn._replace(balance_after_paise=holding.balance_paise)
        elif final in (T.ON_HOLD, T.UNDER_REVIEW):
            holding.hold_paise += amount
        holding.last_txn_at = max(holding.last_txn_at or intent.at, intent.at)
        booked = Booked(txn, scenario, intent.customer_initiated, intent.pattern, steps)
        self.ledger.transactions.append(txn)
        self.ledger.booked.append(booked)
        if posts and completed and scenario.comeback is not Comeback.NONE:
            self._schedule_comeback(intent, booked, amount, final_at)
        return booked

    def _admit(self, intent: Intent) -> tuple[int, Scenario] | None:
        """The amount and outcome of an intent, or None if it never becomes a Transaction."""
        if not self._accounts_allow(intent):
            return None
        holding = intent.holding
        amount = intent.amount_paise
        if intent.interest_bps is not None:
            amount = holding.balance_paise * intent.interest_bps // 40_000
        if intent.direction is Direction.CREDIT:
            if amount < 100:
                return None
            return amount, intent.scenario or credit_scenario(intent.rail)
        resolved = self._debit_amount(intent, amount)
        if resolved is None:
            return None
        if resolved > holding.available_paise:
            return resolved, INSUFFICIENT_FUNDS
        return resolved, intent.scenario or self._debit_outcome(intent)

    def _debit_amount(self, intent: Intent, amount: int) -> int | None:
        """What the Customer actually tries to send, or None if they would not try."""
        available = intent.holding.available_paise
        if intent.sweep:
            amount = min(amount, available)
        if intent.budget_share is not None:
            amount = min(amount, int(available * intent.budget_share) // 500_000 * 500_000)
            if amount < 1_000_000:
                return None
        too_dear = intent.discretionary and amount > available // 2
        if amount < 100 or (too_dear and self._rng.random() < 0.95):
            return None
        # People rarely try a payment they know will bounce; mandates (NACH) do bounce.
        if amount > available and intent.rail is not Rail.NACH and self._rng.random() > 0.08:
            return None
        return amount

    def _accounts_allow(self, intent: Intent) -> bool:
        holding = intent.holding
        if intent.reverses is not None:
            # Money coming back from a reversal or refund was the Customer's: it lands even
            # on a frozen Account. Only closure ends an Account's timeline.
            return holding.closed_at is None or intent.at <= holding.closed_at
        counter = intent.counter_holding
        return holding.accepts(intent.direction, intent.at) and (
            counter is None or counter.accepts(Direction.CREDIT, intent.at)
        )

    def _debit_outcome(self, intent: Intent) -> Scenario:
        weights = debit_scenarios(intent.rail)
        while True:
            scenario = pick(self._rng, weights)
            days = scenario.in_flight_days
            if days is None or intent.at >= self._config.now - days * DAY:
                return scenario

    def _schedule_comeback(
        self, intent: Intent, original: Booked, amount: int, at: datetime
    ) -> None:
        if original.scenario.comeback is Comeback.PARTIAL_REVERSAL:
            amount = max(100, amount * self._rng.randint(20, 80) // 100)
        refund = original.scenario.comeback is Comeback.REFUND
        self.schedule(
            Intent(
                at=at,
                holding=intent.holding,
                direction=Direction.CREDIT,
                rail=intent.rail,
                txn_type=TransactionType.REFUND if refund else TransactionType.REVERSAL,
                amount_paise=amount,
                counterparty=intent.counterparty,
                remark="Refund" if refund else "Reversal",
                channel=Channel.API,
                customer_initiated=False,
                scenario=SUCCESS,
                reverses=original,
            )
        )

    # --- timing

    def _steps(
        self, scenario: Scenario, start: datetime
    ) -> list[tuple[TransactionStatus, datetime]]:
        """The path with when each status was reached, cut where it passes the as-of date."""
        steps = [(scenario.path[0], start)]
        at = start
        for status in scenario.path[1:]:
            at += self._delay(steps[-1][0], status)
            if at > self._config.now:
                break
            steps.append((status, at))
        return steps

    def _delay(  # noqa: PLR0911, PLR0912 — a lookup table: one delay per transition
        self, src: TransactionStatus, dst: TransactionStatus
    ) -> timedelta:
        r = self._rng
        match (src, dst):
            case (_, T.AUTHORISED | T.PROCESSING | T.PENDING_SETTLEMENT):
                return r.randint(1, 4) * SECOND
            case (T.PROCESSING, T.SUCCESS | T.FAILED | T.ON_HOLD | T.PENDING):
                return r.randint(1, 9) * SECOND
            case (T.PROCESSING, T.TIMED_OUT):
                return r.randint(30, 90) * SECOND
            case (T.PENDING, T.SUCCESS):
                return r.randint(20, 180) * MINUTE
            case (T.PENDING, T.CREDIT_DELAYED | T.DEEMED_SUCCESS):
                return r.randint(30, 120) * SECOND
            case (T.PENDING, T.RETURNED) | (T.RETURNED, T.REVERSED):
                return r.randint(2, 24) * HOUR
            case (T.CREDIT_DELAYED | T.DEEMED_SUCCESS, T.SUCCESS):
                return r.randint(2, 40) * HOUR
            case (_, T.REVERSAL_INITIATED):
                return r.randint(20, 30) * HOUR  # T+1 auto-reversal
            case (T.REVERSAL_INITIATED, _):
                # Usually inside the TAT; sometimes late, which is what compensation pays for.
                return r.choice((4, 8, 20, 30, 60, 100)) * HOUR
            case (T.ON_HOLD, T.UNDER_REVIEW):
                return r.randint(5, 120) * MINUTE
            case (T.UNDER_REVIEW, _):
                return r.randint(1, 30) * HOUR
            case (T.PENDING_SETTLEMENT, T.SETTLED):
                return r.randint(12, 36) * HOUR
            case (T.SETTLED, T.REFUNDED):
                return r.randint(3, 20) * DAY
            case (T.SETTLED, T.CHARGEBACK_INITIATED):
                return r.randint(5, 30) * DAY
            case (T.INITIATED, T.CANCELLED):
                return r.randint(10, 120) * SECOND
            case (T.INITIATED, T.EXPIRED):
                return r.randint(30, 24 * 60) * MINUTE
            case _:
                return r.randint(1, 3) * SECOND

    # --- rows

    def _transaction(
        self,
        intent: Intent,
        amount: int,
        scenario: Scenario,
        steps: list[tuple[TransactionStatus, datetime]],
        posted_at: datetime | None,
    ) -> Transaction:
        r = self._rng
        at = intent.at
        rail = intent.rail
        cp = intent.counterparty
        final = steps[-1][0]
        reached = dict(steps)
        rrn = refs.rrn(r, at) if rail not in (Rail.NEFT, Rail.RTGS, Rail.INTERNAL) else None
        match rail:
            case Rail.NEFT:
                utr = refs.neft_utr(r, "KOSH", at)
            case Rail.RTGS:
                utr = refs.rtgs_utr(r, "KOSH", at)
            case Rail.IMPS:
                utr = rrn
            case _:
                utr = None
        failure = scenario.failure_code
        if scenario is INSUFFICIENT_FUNDS:
            failure = insufficient_funds_code(rail)
        app = intent.channel in (Channel.MOBILE_APP, Channel.WEB)
        geo = cp.geo or self._geo(intent)
        risk = r.randint(62, 96) if intent.pattern else r.randint(1, 35)
        if final in (T.ON_HOLD, T.UNDER_REVIEW):
            risk = max(risk, r.randint(70, 92))
        reversed_ = intent.reverses
        return Transaction(
            txn_id=new_id(IdPrefix.TRANSACTION, at=at, rng=r),
            account_id=intent.holding.account_id,
            customer_id=intent.holding.customer_id,
            direction=intent.direction,
            amount_paise=amount,
            currency="INR",
            rail=rail,
            txn_type=intent.txn_type,
            status=final,
            status_reason_code=failure if final not in (T.SUCCESS, T.SETTLED) else None,
            failure_reason_code=failure if final in (T.FAILED, T.DECLINED, T.EXPIRED) else None,
            hold_reason=(
                "Unusual amount for this customer; risk review" if T.ON_HOLD in reached else None
            ),
            expected_credit_by=(
                reached[T.CREDIT_DELAYED] + DAY if final is T.CREDIT_DELAYED else None
            ),
            utr=utr,
            rrn=rrn,
            npci_txn_id=refs.npci_txn_id(r) if rail is Rail.UPI else None,
            counterparty_name=cp.name,
            counterparty_vpa=cp.vpa,
            counterparty_account_masked=cp.account_masked,
            counterparty_ifsc=cp.ifsc,
            merchant_id=cp.merchant_id,
            mcc=cp.mcc,
            channel=intent.channel,
            device_id=self._device_id if app else None,
            ip_address=refs.ip_address(r) if app else None,
            geo_city=geo[0] if geo else None,
            geo_lat=geo[1] if geo else None,
            geo_lng=geo[2] if geo else None,
            narration=_narration(intent, rrn, utr, reversed_),
            remarks=(f"{intent.remark} of {reversed_.txn.txn_id}" if reversed_ else intent.remark),
            initiated_at=at,
            posted_at=posted_at,
            value_date=(posted_at + refs.IST).date() if posted_at else None,
            balance_after_paise=None,
            risk_score=risk,
            is_flagged=risk >= 85 or final in (T.ON_HOLD, T.UNDER_REVIEW),
        )

    def _geo(self, intent: Intent) -> tuple[str, Decimal, Decimal] | None:
        if intent.channel is Channel.API:
            return None
        city = _CITIES.get(intent.counterparty.city or "", self._home)
        if intent.channel is not Channel.POS and intent.channel is not Channel.ATM:
            city = self._home
        jitter = Decimal(self._rng.randint(-3000, 3000)) / 100_000
        return city.name, city.lat + jitter, city.lng + jitter

    def _history(self, txn: Transaction, steps: list[tuple[TransactionStatus, datetime]]) -> None:
        previous: TransactionStatus | None = None
        for status, at in steps:
            reason = None
            if status in (T.FAILED, T.DECLINED, T.EXPIRED, T.TIMED_OUT, T.RETURNED):
                reason = txn.status_reason_code or txn.failure_reason_code
            actor = _ACTOR.get(status, Actor.NPCI if txn.rail is Rail.UPI else Actor.SYSTEM)
            if status is T.INITIATED:
                actor = Actor.CUSTOMER if txn.channel is not Channel.API else Actor.SYSTEM
            self.ledger.history.append(
                TransactionStatusChange(
                    history_id=new_id(IdPrefix.TRANSACTION_STATUS_CHANGE, at=at, rng=self._rng),
                    txn_id=txn.txn_id,
                    txn_initiated_at=txn.initiated_at,
                    from_status=previous,
                    to_status=status,
                    reason_code=reason,
                    actor=actor,
                    occurred_at=at,
                )
            )
            previous = status

    def _entry(
        self,
        txn_id: str | None,
        initiated_at: datetime | None,
        posted_at: datetime,
        description: str,
        legs: list[Leg],
    ) -> None:
        entry_id = new_id(IdPrefix.JOURNAL_ENTRY, at=posted_at, rng=self._rng)
        self.ledger.entries.append(
            JournalEntry(entry_id, txn_id, initiated_at, posted_at, description)
        )
        self.ledger.postings.extend(
            Posting(
                posting_id=new_id(IdPrefix.POSTING, at=posted_at, rng=self._rng),
                entry_id=entry_id,
                gl_account=leg.gl_account,
                account_id=leg.account_id,
                amount_paise=leg.amount_paise,
            )
            for leg in legs
        )


def _describe(intent: Intent) -> str:
    kind = intent.txn_type.value.replace("_", " ")
    rail = intent.rail.value.replace("_", " ").upper()
    return f"{rail} {kind} {intent.direction.value}"


def _clean(text: str, width: int = 20) -> str:
    return "".join(c for c in text.upper() if c.isalnum() or c == " ")[:width].strip()


def _narration(  # noqa: PLR0911 — one statement format per rail
    intent: Intent, rrn: str | None, utr: str | None, reverses: Booked | None
) -> str:
    """A statement line in the shape Indian banks print them."""
    if reverses is not None:
        original = reverses.txn.narration
        prefix = "REFUND" if intent.txn_type is TransactionType.REFUND else "REV"
        return f"{prefix}/{original}"[:120]
    cp = intent.counterparty
    name = _clean(cp.name)
    dr = "DR" if intent.direction is Direction.DEBIT else "CR"
    match intent.rail:
        case Rail.UPI:
            return f"UPI/{dr}/{rrn}/{name}/{cp.vpa or 'NA'}/{intent.remark}"
        case Rail.IMPS:
            return f"IMPS/P2A/{rrn}/{name}/{intent.remark}"
        case Rail.NEFT:
            return f"NEFT/{dr}/{utr}/{name}/{intent.remark}"
        case Rail.RTGS:
            return f"RTGS/{dr}/{utr}/{name}"
        case Rail.CARD_POS:
            return f"POS/{rrn}/{name}/{_clean(cp.city or '', 12)}"
        case Rail.CARD_ECOM:
            return f"ECOM/{rrn}/{name}"
        case Rail.ATM:
            return f"ATM/CASH WDL/{rrn}/{_clean(cp.city or '', 12)}"
        case Rail.NACH:
            return f"NACH/DR/{name}/{intent.remark}"
        case Rail.INTERNAL:
            return intent.remark.upper()
