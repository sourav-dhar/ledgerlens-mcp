"""Money-laundering typologies: the rules, the planted patterns, and the alerts they raise.

A planted bad actor's pattern (structuring, a mule's burst, a round trip) is written as
ordinary intents, so it runs through the same timeline as everyone else's money. Alerts
are not planted: the rules below run over every Customer's posted Transactions with the
thresholds stored in ``risk.aml_rules.params``, and whatever trips them becomes an alert.
The planted actors are what fire the true positives; ordinary Customers whose behaviour
happens to look similar are the false positives an analyst closes.
"""

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from kosha_datagen import catalog, refs
from kosha_datagen.accounts import Holding
from kosha_datagen.chance import between, pick
from kosha_datagen.config import GenerationConfig
from kosha_datagen.outcomes import BATCHED, SETTLED, SUCCESS, Scenario
from kosha_datagen.parties import Profile
from kosha_datagen.payments import Booked, Counterparty, Intent
from kosha_datagen.rows import AmlAlert, AmlRule, Transaction
from kosha_domain.ids import IdPrefix, new_id
from kosha_domain.lifecycles import AmlAlertStatus
from kosha_domain.money import format_inr
from kosha_domain.vocabulary import Channel, Direction, Rail, Severity, TransactionType, Typology

HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
A = AmlAlertStatus
_SLA = {
    Severity.CRITICAL: DAY,
    Severity.HIGH: 3 * DAY,
    Severity.MEDIUM: 7 * DAY,
    Severity.LOW: 15 * DAY,
}
_MERGE_WITHIN = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class RuleSpec:
    name: str
    typology: Typology
    severity: Severity
    params: dict[str, Any]


RULES: tuple[RuleSpec, ...] = (
    RuleSpec(
        "Structured credits below the PAN reporting threshold",
        Typology.STRUCTURING,
        Severity.HIGH,
        {"min_paise": 4_000_000, "max_paise": 4_999_999, "min_count": 3, "window_days": 10},
    ),
    RuleSpec(
        "Large credit moved out within three days",
        Typology.RAPID_MOVEMENT,
        Severity.HIGH,
        {"min_credit_paise": 15_000_000, "outflow_percent": 80, "window_hours": 72},
    ),
    RuleSpec(
        "New account receiving from many unrelated senders",
        Typology.MULE_ACCOUNT,
        Severity.CRITICAL,
        {"min_senders": 8, "window_days": 10, "max_account_age_days": 120},
    ),
    RuleSpec(
        "Funds returned by the counterparty they were sent to",
        Typology.ROUND_TRIPPING,
        Severity.HIGH,
        {"min_paise": 100_000_000, "return_percent": 80, "window_days": 30},
    ),
    RuleSpec(
        "Dormant account reactivated with large credits",
        Typology.DORMANT_REACTIVATION,
        Severity.MEDIUM,
        {"dormant_days": 300, "min_credit_paise": 10_000_000, "within_days": 30},
    ),
    RuleSpec(
        "Card used in a FATF high-risk jurisdiction",
        Typology.HIGH_RISK_GEO,
        Severity.HIGH,
        {"cities": [name for name, _, _ in catalog.HIGH_RISK_CITIES]},
    ),
    RuleSpec(
        "Burst of debits within an hour",
        Typology.VELOCITY,
        Severity.MEDIUM,
        {"min_debits": 12, "window_minutes": 60},
    ),
)


def rule_rows(config: GenerationConfig) -> list[AmlRule]:
    rng = config.rng("aml_rules")
    return [
        AmlRule(
            rule_id=new_id(IdPrefix.AML_RULE, at=config.history_start, rng=rng),
            name=spec.name,
            typology=spec.typology,
            params=spec.params,
            severity=spec.severity,
            enabled=True,
        )
        for spec in RULES
    ]


# --- planting


def plant(
    config: GenerationConfig, profile: Profile, rng: random.Random, holding: Holding
) -> list[Intent]:
    """The intents that make up a bad actor's pattern."""
    if profile.typology is None:
        return []
    planter = _Planter(config, profile, rng, holding)
    return {
        Typology.STRUCTURING: planter.structuring,
        Typology.RAPID_MOVEMENT: planter.rapid_movement,
        Typology.MULE_ACCOUNT: planter.mule,
        Typology.ROUND_TRIPPING: planter.round_trip,
        Typology.DORMANT_REACTIVATION: planter.reactivation,
        Typology.HIGH_RISK_GEO: planter.high_risk_geo,
        Typology.VELOCITY: planter.velocity,
    }[profile.typology]()


@dataclass(slots=True)
class _Planter:
    config: GenerationConfig
    profile: Profile
    rng: random.Random
    holding: Holding

    def _start(self, lead: timedelta = 10 * DAY, tail: timedelta = 15 * DAY) -> datetime:
        earliest = max(self.holding.opened_at, self.config.window_start) + lead
        return between(self.rng, earliest, max(earliest, self.config.now - tail))

    def _stranger(self) -> str:
        r = self.rng
        surname = r.choice(catalog.SURNAMES[r.choice(list(catalog.SURNAMES))])
        return f"{r.choice(catalog.MALE_NAMES + catalog.FEMALE_NAMES)} {surname}"

    def _move(
        self,
        at: datetime,
        direction: Direction,
        rail: Rail,
        amount: int,
        name: str,
        *,
        sweep: bool = False,
        geo: tuple[str, Decimal, Decimal] | None = None,
    ) -> Intent:
        bank = self.rng.choice(catalog.BANKS)
        card = rail in (Rail.CARD_POS, Rail.CARD_ECOM)
        scenario: Scenario = SUCCESS
        if card:
            scenario = SETTLED
        elif rail in (Rail.NEFT, Rail.RTGS):
            scenario = BATCHED
        incoming = direction is Direction.CREDIT
        return Intent(
            at=at,
            holding=self.holding,
            direction=direction,
            rail=rail,
            txn_type=TransactionType.P2M if card else TransactionType.P2P,
            amount_paise=amount,
            counterparty=Counterparty(
                name,
                vpa=self._vpa(name, bank) if rail is Rail.UPI else None,
                account_masked=None
                if card or rail is Rail.UPI
                else refs.masked(refs.digits(self.rng, 14)),
                ifsc=None if card or rail is Rail.UPI else refs.ifsc(self.rng, bank.code),
                geo=geo,
            ),
            remark="Payment" if not incoming else "Transfer",
            channel=Channel.POS if card else (Channel.API if incoming else Channel.MOBILE_APP),
            customer_initiated=not incoming,
            sweep=sweep,
            scenario=scenario,
            pattern=self.profile.typology,
        )

    def _vpa(self, name: str, bank: catalog.Bank) -> str:
        return f"{name.split(maxsplit=1)[0].lower()}{self.rng.randint(10, 999)}@{bank.upi_handle}"

    def structuring(self) -> list[Intent]:
        r, out = self.rng, list[Intent]()
        for _ in range(r.randint(1, 2)):
            at = self._start()
            total = 0
            for _ in range(r.randint(5, 8)):
                amount = r.randint(45_000, 49_900) * 100
                total += amount
                out.append(self._move(at, Direction.CREDIT, Rail.IMPS, amount, self._stranger()))
                at += r.randint(10, 30) * HOUR
            supplier = f"{r.choice(catalog.SURNAMES['west'])} Traders"
            out.append(
                self._move(at + 2 * DAY, Direction.DEBIT, Rail.RTGS, total, supplier, sweep=True)
            )
        return out

    def rapid_movement(self) -> list[Intent]:
        r, out = self.rng, list[Intent]()
        for _ in range(r.randint(1, 2)):
            at = self._start()
            amount = r.randint(3, 12) * 10_000_000
            source = f"{r.choice(catalog.SURNAMES['north'])} Holdings Pvt Ltd"
            out.append(self._move(at, Direction.CREDIT, Rail.RTGS, amount, source))
            legs = r.randint(2, 4)
            for leg in range(legs):
                share = amount * r.randint(92, 98) // 100 // legs
                when = at + r.randint(4, 30) * HOUR + leg * HOUR
                out.append(
                    self._move(
                        when, Direction.DEBIT, Rail.IMPS, share, self._stranger(), sweep=True
                    )
                )
        return out

    def mule(self) -> list[Intent]:
        r, out = self.rng, list[Intent]()
        at = self.holding.opened_at + r.randint(5, 20) * DAY
        handlers = [self._stranger() for _ in range(2)]
        for _ in range(r.randint(10, 18)):
            amount = r.randint(4_000, 40_000) * 100
            out.append(self._move(at, Direction.CREDIT, Rail.UPI, amount, self._stranger()))
            out.append(
                self._move(
                    at + r.randint(1, 5) * HOUR,
                    Direction.DEBIT,
                    Rail.IMPS,
                    amount * 97 // 100,
                    r.choice(handlers),
                    sweep=True,
                )
            )
            at += r.randint(6, 14) * HOUR
        return out

    def round_trip(self) -> list[Intent]:
        r = self.rng
        at = self._start(tail=40 * DAY)
        amount = r.randint(10, 40) * 10_000_000
        partner = f"{r.choice(catalog.SURNAMES['south'])} Exports Pvt Ltd"
        contract = f"{r.choice(catalog.SURNAMES['north'])} Infra Projects Ltd"
        back = amount * r.randint(85, 98) // 100
        return [
            self._move(at - 2 * DAY, Direction.CREDIT, Rail.RTGS, amount * 105 // 100, contract),
            self._move(at, Direction.DEBIT, Rail.RTGS, amount, partner, sweep=True),
            self._move(at + r.randint(10, 25) * DAY, Direction.CREDIT, Rail.RTGS, back, partner),
        ]

    def reactivation(self) -> list[Intent]:
        r, out = self.rng, list[Intent]()
        at = (self.profile.fate_at or self._start()) + r.randint(1, 5) * DAY
        for _ in range(r.randint(2, 3)):
            amount = r.randint(15, 60) * 1_000_000
            out.append(self._move(at, Direction.CREDIT, Rail.IMPS, amount, self._stranger()))
            out.append(
                self._move(
                    at + r.randint(2, 20) * HOUR,
                    Direction.DEBIT,
                    Rail.IMPS,
                    amount,
                    self._stranger(),
                    sweep=True,
                )
            )
            at += r.randint(1, 4) * DAY
        return out

    def high_risk_geo(self) -> list[Intent]:
        r = self.rng
        at = self._start(lead=30 * DAY, tail=5 * DAY)
        city = r.choice(catalog.HIGH_RISK_CITIES)
        spends = [r.randint(8_000, 60_000) * 100 for _ in range(r.randint(2, 4))]
        out = [
            self._move(
                at - DAY,
                Direction.CREDIT,
                Rail.IMPS,
                sum(spends) * 12 // 10,
                self.profile.full_name,
            )
        ]
        for amount in spends:
            at += r.randint(3, 20) * HOUR
            merchant = r.choice(
                ("Shwe Gems Trading", "Golden Valley Exchange", "Bazaar Carpet House")
            )
            out.append(self._move(at, Direction.DEBIT, Rail.CARD_POS, amount, merchant, geo=city))
        return out

    def velocity(self) -> list[Intent]:
        r = self.rng
        at = self._start()
        debits = [r.randint(200, 2_000) * 100 for _ in range(r.randint(15, 25))]
        out = [
            self._move(
                at - HOUR,
                Direction.CREDIT,
                Rail.IMPS,
                sum(debits) * 12 // 10,
                self.profile.full_name,
            )
        ]
        for amount in debits:
            at += r.randint(60, 180) * timedelta(seconds=1)
            out.append(self._move(at, Direction.DEBIT, Rail.UPI, amount, self._stranger()))
        return out


# --- detection


@dataclass(frozen=True, slots=True)
class Hit:
    typology: Typology
    txns: tuple[Transaction, ...]
    note: str

    @property
    def at(self) -> datetime:
        return max(t.initiated_at for t in self.txns)


@dataclass(frozen=True, slots=True)
class Known:
    """What the rules know besides the Transactions themselves."""

    opened: dict[str, datetime]
    """Each Account's opening instant, for account-age conditions."""
    since: datetime
    """When the ledger went live: activity before it is unknown, so quiet periods start here."""


type Evaluator = Callable[[Sequence[Transaction], dict[str, Any], Known], list[Hit]]


def _structuring(txns: Sequence[Transaction], p: dict[str, Any], _: Known) -> list[Hit]:
    inbound = [
        t
        for t in txns
        if t.direction is Direction.CREDIT and p["min_paise"] <= t.amount_paise <= p["max_paise"]
    ]
    return _bursts(
        inbound,
        timedelta(days=p["window_days"]),
        p["min_count"],
        Typology.STRUCTURING,
        "credits just below ₹50,000",
    )


def _velocity(txns: Sequence[Transaction], p: dict[str, Any], _: Known) -> list[Hit]:
    debits = [t for t in txns if t.direction is Direction.DEBIT and t.rail is Rail.UPI]
    return _bursts(
        debits,
        timedelta(minutes=p["window_minutes"]),
        p["min_debits"],
        Typology.VELOCITY,
        "UPI debits",
    )


def _bursts(
    txns: list[Transaction], window: timedelta, minimum: int, typology: Typology, what: str
) -> list[Hit]:
    hits: list[Hit] = []
    i = 0
    while i < len(txns):
        j = i
        while j + 1 < len(txns) and txns[j + 1].initiated_at - txns[i].initiated_at <= window:
            j += 1
        if j - i + 1 >= minimum:
            group = tuple(txns[i : j + 1])
            total = format_inr(sum(t.amount_paise for t in group))
            hits.append(Hit(typology, group, f"{len(group)} {what} totalling {total}"))
            i = j + 1
        else:
            i += 1
    return hits


def _rapid_movement(txns: Sequence[Transaction], p: dict[str, Any], _: Known) -> list[Hit]:
    window = timedelta(hours=p["window_hours"])
    hits: list[Hit] = []
    for credit in txns:
        if credit.direction is not Direction.CREDIT or credit.amount_paise < p["min_credit_paise"]:
            continue
        out = [
            t
            for t in txns
            if t.direction is Direction.DEBIT
            and credit.initiated_at < t.initiated_at <= credit.initiated_at + window
        ]
        moved = sum(t.amount_paise for t in out)
        if moved * 100 >= credit.amount_paise * p["outflow_percent"]:
            note = (
                f"{format_inr(credit.amount_paise)} credited and {format_inr(moved)} "
                f"sent on within {p['window_hours']} hours"
            )
            hits.append(Hit(Typology.RAPID_MOVEMENT, (credit, *out), note))
    return hits


def _mule(txns: Sequence[Transaction], p: dict[str, Any], known: Known) -> list[Hit]:
    window = timedelta(days=p["window_days"])
    max_age = timedelta(days=p["max_account_age_days"])
    inbound = [
        t
        for t in txns
        if t.direction is Direction.CREDIT
        and t.txn_type is TransactionType.P2P
        and t.initiated_at - known.opened[t.account_id] <= max_age
    ]
    for i, first in enumerate(inbound):
        group = [t for t in inbound[i:] if t.initiated_at - first.initiated_at <= window]
        senders = {t.counterparty_name for t in group}
        if len(senders) >= p["min_senders"]:
            note = (
                f"{len(senders)} unrelated senders within {p['window_days']} days of a new account"
            )
            return [Hit(Typology.MULE_ACCOUNT, tuple(group), note)]
    return []


def _round_trip(txns: Sequence[Transaction], p: dict[str, Any], _: Known) -> list[Hit]:
    window = timedelta(days=p["window_days"])
    hits: list[Hit] = []
    for out in txns:
        if out.direction is not Direction.DEBIT or out.amount_paise < p["min_paise"]:
            continue
        for back in txns:
            if (
                back.direction is Direction.CREDIT
                and back.counterparty_name == out.counterparty_name
                and out.initiated_at < back.initiated_at <= out.initiated_at + window
                and back.amount_paise * 100 >= out.amount_paise * p["return_percent"]
            ):
                note = (
                    f"{format_inr(out.amount_paise)} sent to {out.counterparty_name} "
                    f"and {format_inr(back.amount_paise)} returned"
                )
                hits.append(Hit(Typology.ROUND_TRIPPING, (out, back), note))
                break
    return hits


def _reactivation(txns: Sequence[Transaction], p: dict[str, Any], known: Known) -> list[Hit]:
    quiet = timedelta(days=p["dormant_days"])
    hits: list[Hit] = []
    own = [t for t in txns if t.channel is not Channel.API]
    if not own:
        return hits
    last = max(min(known.opened.values()), known.since)
    for t in own:
        if t.initiated_at - last >= quiet:
            woke = t.initiated_at
            big = [
                c
                for c in txns
                if c.direction is Direction.CREDIT
                and c.amount_paise >= p["min_credit_paise"]
                and woke - DAY <= c.initiated_at <= woke + timedelta(days=p["within_days"])
            ]
            if big:
                total = format_inr(sum(c.amount_paise for c in big))
                note = f"Quiet {(woke - last).days} days, then {total} credited"
                hits.append(Hit(Typology.DORMANT_REACTIVATION, tuple(big), note))
        last = t.initiated_at
    return hits


def _high_risk_geo(txns: Sequence[Transaction], p: dict[str, Any], _: Known) -> list[Hit]:
    abroad = [t for t in txns if t.geo_city in p["cities"]]
    if not abroad:
        return []
    return [
        Hit(
            Typology.HIGH_RISK_GEO,
            tuple(abroad),
            f"{len(abroad)} card payments in {abroad[0].geo_city}",
        )
    ]


_EVALUATORS: dict[Typology, Evaluator] = {
    Typology.STRUCTURING: _structuring,
    Typology.RAPID_MOVEMENT: _rapid_movement,
    Typology.MULE_ACCOUNT: _mule,
    Typology.ROUND_TRIPPING: _round_trip,
    Typology.DORMANT_REACTIVATION: _reactivation,
    Typology.HIGH_RISK_GEO: _high_risk_geo,
    Typology.VELOCITY: _velocity,
}


def detect(booked: Sequence[Booked], known: Known) -> list[Hit]:
    """Run every rule over one Customer's posted Transactions."""
    txns = sorted(
        (b.txn for b in booked if b.txn.posted_at is not None), key=lambda t: t.initiated_at
    )
    hits: list[Hit] = []
    for spec in RULES:
        hits += _merge(_EVALUATORS[spec.typology](txns, spec.params, known))
    return hits


def _merge(hits: list[Hit]) -> list[Hit]:
    """One alert per pattern episode: hits within 30 days of each other become one."""
    merged: list[Hit] = []
    for hit in sorted(hits, key=lambda h: h.at):
        if merged and hit.at - merged[-1].at <= _MERGE_WITHIN:
            last = merged[-1]
            txns = tuple(dict.fromkeys((*last.txns, *hit.txns)))
            merged[-1] = Hit(last.typology, txns, last.note)
        else:
            merged.append(hit)
    return merged


# --- alerts


def alert_rows(
    config: GenerationConfig,
    profile: Profile,
    rng: random.Random,
    hits: list[Hit],
    rules: dict[Typology, AmlRule],
) -> list[AmlAlert]:
    alerts: list[AmlAlert] = []
    for hit in hits:
        # The monitoring batch runs nightly at 02:00 IST (20:30 UTC).
        created = hit.at.replace(hour=20, minute=30, second=0, microsecond=0)
        if created <= hit.at:
            created += DAY
        if created > config.now:
            continue
        rule = rules[hit.typology]
        planted = profile.typology is hit.typology
        status = _status(rng, config.now - created, planted=planted)
        closed_at = None
        if status in (A.CLOSED_FALSE_POSITIVE, A.CLOSED_NO_ACTION, A.CLOSED_STR_FILED):
            closed_at = min(created + rng.randint(2, 25) * DAY, config.now)
        alerts.append(
            AmlAlert(
                alert_id=new_id(IdPrefix.AML_ALERT, at=created, rng=rng),
                customer_id=profile.customer_id,
                rule_id=rule.rule_id,
                typology=hit.typology,
                score=Decimal(rng.randint(7_500, 9_800) if planted else rng.randint(4_000, 7_400))
                / 100,
                status=status,
                assigned_to=None if status is A.OPEN else f"staff-{rng.randint(200, 230):04d}",
                sla_due_at=created + _SLA[rule.severity],
                triggering_txn_ids=[t.txn_id for t in hit.txns[:50]],
                narrative=hit.note,
                disposition=_DISPOSITIONS.get(status),
                str_reference=f"FIU-STR-{created.year}-{refs.digits(rng, 6)}"
                if status is A.CLOSED_STR_FILED
                else None,
                created_at=created,
                closed_at=closed_at,
            )
        )
    return alerts


def _status(rng: random.Random, age: timedelta, *, planted: bool) -> AmlAlertStatus:
    if age < 3 * DAY:
        return pick(rng, {A.OPEN: 6, A.ASSIGNED: 3, A.IN_REVIEW: 1})
    if age < 14 * DAY:
        return pick(
            rng, {A.OPEN: 1, A.ASSIGNED: 2, A.IN_REVIEW: 4, A.PENDING_INFO: 2, A.ON_HOLD: 1}
        )
    if age < 45 * DAY:
        if planted:
            return pick(rng, {A.IN_REVIEW: 2, A.ESCALATED: 5, A.CLOSED_STR_FILED: 3})
        return pick(
            rng,
            {A.IN_REVIEW: 2, A.PENDING_INFO: 1, A.CLOSED_FALSE_POSITIVE: 6, A.CLOSED_NO_ACTION: 1},
        )
    if planted:
        return pick(rng, {A.CLOSED_STR_FILED: 8, A.CLOSED_NO_ACTION: 2})
    return pick(rng, {A.CLOSED_FALSE_POSITIVE: 85, A.CLOSED_NO_ACTION: 15})


_DISPOSITIONS = {
    A.CLOSED_FALSE_POSITIVE: "Activity consistent with the customer's business and income",
    A.CLOSED_NO_ACTION: "Explained by the customer with documents; no report required",
    A.CLOSED_STR_FILED: "Suspicion not dispelled; STR filed with FIU-IND",
}
