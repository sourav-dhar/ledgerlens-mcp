"""What each persona does with money, month by month, as intents for the timeline.

Salaried Customers are paid on the last working day and pay rent and EMIs early in the
month; gig workers are paid weekly; SME owners collect many small UPI payments and pay
suppliers by NEFT or RTGS; seniors draw a pension. Spending rises in the Diwali months.
Amounts scale with segment, and discretionary spending backs off when the balance is low.
"""

import math
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from kosha_datagen import catalog, refs
from kosha_datagen.accounts import Holding, Payee
from kosha_datagen.chance import between, pick
from kosha_datagen.config import GenerationConfig
from kosha_datagen.ledger import charge_with_gst
from kosha_datagen.outcomes import BATCHED
from kosha_datagen.parties import Fate, Profile
from kosha_datagen.payments import Booked, Counterparty, Intent
from kosha_datagen.rows import Merchant
from kosha_domain.vocabulary import (
    Channel,
    Direction,
    IncomeBand,
    Persona,
    ProductCode,
    Rail,
    Segment,
    TransactionType,
    Typology,
)

DAY = timedelta(days=1)
IST = refs.IST
RTGS_MINIMUM_PAISE = 20_000_000  # ₹2 lakh
SMS_CHARGE_PAISE = charge_with_gst(1_500)  # ₹15 + GST
_ANNUAL_LAKH = {
    IncomeBand.UP_TO_3_LAKH: 2.4,
    IncomeBand.FROM_3_TO_6_LAKH: 4.5,
    IncomeBand.FROM_6_TO_12_LAKH: 9,
    IncomeBand.FROM_12_TO_25_LAKH: 18,
    IncomeBand.FROM_25_TO_50_LAKH: 36,
    IncomeBand.ABOVE_50_LAKH: 70,
}
_SEGMENT_FACTOR = {Segment.MASS: 1.0, Segment.AFFLUENT: 1.6, Segment.PREMIUM: 2.5}
_LIFE_EVENTS = (
    ("Lakshya Home Finance", "Developers"),
    ("Udaan Auto Loans", "Motors"),
    ("Pragati Consumer Finance", "Realty"),
)
_FESTIVE = {10: 1.35, 11: 1.3, 12: 1.15, 3: 1.05}  # Navratri-Diwali, year end, Holi


@dataclass(frozen=True, slots=True)
class Habits:
    """Monthly counts of each kind of spending."""

    upi_p2m: float
    card: float
    atm: float
    p2p_out: float
    bills: float


_HABITS = {
    Persona.SALARIED: Habits(14, 3.5, 1.0, 2.0, 2.5),
    Persona.STUDENT: Habits(17, 1.2, 0.8, 2.5, 1.0),
    Persona.GIG_WORKER: Habits(17, 0.4, 2.0, 1.5, 1.5),
    Persona.SME_OWNER: Habits(8, 2.5, 0.8, 1.5, 3.0),
    Persona.NRI: Habits(4, 1.5, 0.3, 1.5, 2.0),
    Persona.SENIOR_CITIZEN: Habits(6, 0.8, 1.5, 1.0, 2.5),
}
_UPI_SPEND = {
    "supermarket": 26,
    "food_delivery": 18,
    "restaurant": 9,
    "ride_hailing": 13,
    "pharmacy": 7,
    "fuel_station": 7,
    "apparel": 4,
    "marketplace": 9,
    "cinema": 3,
    "coaching": 1,
    "electronics": 1,
}
_CARD_SPEND = {
    "marketplace": 22,
    "supermarket": 18,
    "apparel": 12,
    "restaurant": 12,
    "fuel_station": 10,
    "electronics": 8,
    "airline": 4,
    "hotel": 4,
    "cinema": 6,
    "jewellery": 2,
    "pharmacy": 2,
}
_BILLS = {"electricity": 5, "telecom": 6, "insurance": 1}
_ONLINE = {k.sub_category for k in catalog.MERCHANT_KINDS if k.online}
_MEDIAN = {k.sub_category: k.median_rupees for k in catalog.MERCHANT_KINDS}


class MerchantDirectory:
    """Merchants by line of business, preferring ones in the Customer's city."""

    def __init__(self, merchants: list[Merchant]) -> None:
        self._by_kind: dict[str, list[Merchant]] = defaultdict(list)
        self._local: dict[tuple[str, str], list[Merchant]] = defaultdict(list)
        for m in merchants:
            sub = m.sub_category or m.category
            self._by_kind[sub].append(m)
            self._local[sub, m.city].append(m)

    def choose(self, rng: random.Random, sub: str, city: str, *, needs_vpa: bool) -> Merchant:
        pool = self._local.get((sub, city)) if sub not in _ONLINE else None
        pool = pool or self._by_kind.get(sub) or [m for ms in self._by_kind.values() for m in ms]
        if needs_vpa:
            pool = [m for m in pool if m.vpa] or pool
        return rng.choice(pool)


@dataclass(slots=True)
class CustomerBehaviour:
    config: GenerationConfig
    profile: Profile
    rng: random.Random
    holdings: list[Holding]
    payees: list[Payee]
    merchants: MerchantDirectory

    @property
    def primary(self) -> Holding:
        return self.holdings[0]

    def opening_balances(self) -> list[tuple[Holding, int]]:
        """Balances to bring forward for Accounts that predate the ledger."""
        out: list[tuple[Holding, int]] = []
        factor = _SEGMENT_FACTOR[self.profile.segment]
        for h in self.holdings:
            if h.opened_at >= self.config.window_start:
                continue
            if h.product is ProductCode.FIXED_DEPOSIT:
                amount = h.principal_paise
            elif h.product is ProductCode.RECURRING_DEPOSIT:
                months = (self.config.window_start - h.opened_at).days // 30
                amount = h.principal_paise * min(months, 60)
            elif h.product is ProductCode.CURRENT:
                amount = self._lognormal(300_000 * factor, 0.8) * 100
            else:
                amount = self._lognormal(25_000 * factor**2, 0.9) * 100
            h.funded = True
            out.append((h, amount))
        return out

    def intents(self) -> list[Intent]:
        """Every intent over the window, in no particular order."""
        start, end = self._active_span()
        intents: list[Intent] = []
        if start < end:
            for month_start, month_end in _months(self.config):
                lo, hi = max(month_start, start), min(month_end, end)
                if lo < hi:
                    intents += self._month(lo, hi, month_start)
        intents += self._deposits(end)
        intents += self._bank_initiated()
        if (
            self.profile.fate is Fate.ACTIVE
            and not self.profile.typology
            and end - start > 90 * DAY
        ):
            intents += self._life_event(start, end)
        if self.profile.fate is Fate.CLOSED and self.profile.fate_at is not None:
            intents.append(self._closure(self.profile.fate_at))
        return intents

    # --- spans

    def _active_span(self) -> tuple[datetime, datetime]:
        """When the Customer moves money themselves."""
        p, cfg = self.profile, self.config
        start = max(self.primary.opened_at + DAY, cfg.window_start)
        if p.typology is Typology.DORMANT_REACTIVATION and p.fate_at is not None:
            return p.fate_at, cfg.now
        match p.fate:
            case Fate.PROSPECT | Fate.INOPERATIVE:
                return start, start
            case Fate.DORMANT:
                return start, p.fate_at or start
            case Fate.CLOSED:
                # Quiet for a few weeks before closing, so refunds land before closure.
                return start, (p.fate_at or start) - 25 * DAY
            case _:
                return start, cfg.now

    # --- months

    def _month(self, lo: datetime, hi: datetime, month_start: datetime) -> list[Intent]:
        p, r = self.profile, self.rng
        share = (hi - lo) / (_month_end(month_start) - month_start)
        festive = _FESTIVE.get(month_start.month, 1.0)
        habits = _HABITS[p.persona]
        out = self._income(lo, hi, month_start)
        for _ in range(self._count(habits.upi_p2m * share * festive)):
            out.append(self._merchant_payment(lo, hi, Rail.UPI))
        for _ in range(self._count(habits.card * share * festive)):
            out.append(self._merchant_payment(lo, hi, r.choice((Rail.CARD_POS, Rail.CARD_ECOM))))
        for _ in range(self._count(habits.atm * share)):
            out.append(self._atm(lo, hi))
        for _ in range(self._count(habits.bills * share)):
            out.append(self._bill(lo, hi))
        for _ in range(self._count(habits.p2p_out * share)):
            out.append(self._p2p_out(lo, hi))
        out += self._fixed_outgoings(lo, hi, month_start)
        return [i for i in out if lo <= i.at <= hi]

    def _count(self, mean: float) -> int:
        if mean <= 0:
            return 0
        return max(0, round(self.rng.gauss(mean, math.sqrt(mean))))

    def _income(self, lo: datetime, hi: datetime, month_start: datetime) -> list[Intent]:
        p, r = self.profile, self.rng
        # Take-home pay in paise: annual income, net of tax and provident fund.
        monthly = int(_ANNUAL_LAKH[p.income_band] * 100_000 / 12 * 0.82) * 100
        out: list[Intent] = []
        match p.persona:
            case Persona.SALARIED:
                payday = _last_working_day(month_start)
                at = payday + timedelta(hours=r.randint(4, 8), minutes=r.randint(0, 59))
                employer = p.employer or "Employer"
                bonus = 2 if month_start.month == 3 and r.random() < 0.3 else 1
                amount = int(monthly * r.uniform(0.97, 1.03)) * bonus
                out.append(
                    self._credit_neft(at, amount, employer, "SALARY", TransactionType.SALARY)
                )
            case Persona.SENIOR_CITIZEN:
                at = month_start + timedelta(hours=r.randint(4, 7))
                amount = int(monthly * 0.7)
                out.append(
                    self._credit_neft(
                        at, amount, "State Treasury Pension", "PENSION", TransactionType.SALARY
                    )
                )
            case Persona.NRI:
                if r.random() < 0.75:
                    amount = int(monthly * r.uniform(0.3, 0.8))
                    name = f"{p.first_name} {p.last_name} via Gulf Remit Exchange"
                    out.append(
                        self._credit_neft(
                            between(r, lo, hi),
                            amount,
                            name,
                            "INWARD REMITTANCE",
                            TransactionType.P2P,
                        )
                    )
            case Persona.STUDENT:
                parent = f"{r.choice(catalog.MALE_NAMES)} {p.last_name}"
                for _ in range(r.randint(1, 3)):
                    amount = r.randint(15, 80) * 10_000 * _SEGMENT_FACTOR[p.segment]
                    out.append(
                        self._credit_upi(between(r, lo, hi), int(amount), parent, "Pocket money")
                    )
            case Persona.GIG_WORKER:
                platform = r.choice(catalog.GIG_PLATFORMS)
                week = lo
                while week < hi:
                    amount = r.randint(1_500, 7_000) * 100
                    out.append(
                        self._credit_imps(
                            week + r.randint(0, 2) * DAY, amount, platform, "Weekly payout"
                        )
                    )
                    week += 7 * DAY
            case Persona.SME_OWNER:
                for _ in range(self._count(30 * ((hi - lo) / (30 * DAY)))):
                    amount = self._lognormal(900, 0.8) * 100
                    first = r.choice(catalog.MALE_NAMES + catalog.FEMALE_NAMES)
                    payer = f"{first} {r.choice(catalog.SURNAMES['west'])}"
                    out.append(
                        self._credit_upi(
                            between(r, lo, hi), amount, payer, "Payment", TransactionType.P2M
                        )
                    )
                for _ in range(r.randint(1, 3)):
                    amount = self._lognormal(60_000, 0.7) * 100
                    client = f"{r.choice(catalog.SURNAMES['north'])} Enterprises"
                    out.append(
                        self._credit_neft(
                            between(r, lo, hi), amount, client, "INVOICE", TransactionType.P2P
                        )
                    )
        return [i for i in out if lo <= i.at <= hi]

    def _fixed_outgoings(self, lo: datetime, hi: datetime, month_start: datetime) -> list[Intent]:
        """Rent, EMIs and supplier payments: the same payee, roughly the same day."""
        p, r = self.profile, self.rng
        out: list[Intent] = []
        landlord = next((x for x in self.payees if x.is_landlord), None)
        if landlord is not None:
            at = month_start + timedelta(days=r.randint(0, 4), hours=r.randint(3, 14))
            rent = (8_000 if p.persona is Persona.STUDENT else 15_000) * _SEGMENT_FACTOR[p.segment]
            rent_paise = int(rent * (1 + (p.index % 7) / 10)) * 100
            out.append(self._to_payee(at, landlord, rent_paise, f"Rent {month_start:%b%y}"))
        if p.index % 10 < 3 and p.persona in (Persona.SALARIED, Persona.SME_OWNER):
            lender = catalog.LENDERS[p.index % len(catalog.LENDERS)]
            emi = (6_000 + (p.index % 17) * 2_000) * 100
            at = month_start + timedelta(days=4, hours=r.randint(1, 4))
            out.append(
                Intent(
                    at=at,
                    holding=self.primary,
                    direction=Direction.DEBIT,
                    rail=Rail.NACH,
                    txn_type=TransactionType.EMI,
                    amount_paise=emi,
                    counterparty=Counterparty(
                        lender, account_masked=refs.masked(refs.digits(r, 14))
                    ),
                    remark=f"EMI {month_start:%b%y}".upper(),
                    channel=Channel.API,
                )
            )
        if p.persona is Persona.SME_OWNER:
            suppliers = [x for x in self.payees if not x.is_landlord]
            for _ in range(self._count(4 * ((hi - lo) / (30 * DAY)))):
                if suppliers:
                    amount = self._lognormal(40_000, 0.9) * 100
                    out.append(
                        self._to_payee(
                            between(r, lo, hi), r.choice(suppliers), amount, "Supplier payment"
                        )
                    )
        return [i for i in out if lo <= i.at <= hi]

    # --- single intents

    def _when(self, lo: datetime, hi: datetime) -> datetime:
        """A moment in the range, at an hour people are awake (IST)."""
        at = between(self.rng, lo, hi)
        local_hour = (at + IST).hour
        if local_hour < 8:
            at += timedelta(hours=8 - local_hour + self.rng.randint(0, 3))
        return min(at, hi)

    def _merchant_payment(self, lo: datetime, hi: datetime, rail: Rail) -> Intent:
        r, p = self.rng, self.profile
        sub = pick(r, _UPI_SPEND if rail is Rail.UPI else _CARD_SPEND)
        if rail is Rail.CARD_POS and sub in _ONLINE and sub not in ("restaurant", "apparel"):
            rail = Rail.CARD_ECOM
        merchant = self.merchants.choose(r, sub, p.city.name, needs_vpa=rail is Rail.UPI)
        amount = self._lognormal(_MEDIAN.get(sub, 500) * _SEGMENT_FACTOR[p.segment], 0.7) * 100
        channel = {Rail.UPI: Channel.MOBILE_APP, Rail.CARD_POS: Channel.POS}.get(rail, Channel.WEB)
        return Intent(
            at=self._when(lo, hi),
            holding=self.primary,
            direction=Direction.DEBIT,
            rail=rail,
            txn_type=TransactionType.P2M,
            amount_paise=amount,
            counterparty=Counterparty(
                merchant.display_name,
                vpa=merchant.vpa if rail is Rail.UPI else None,
                merchant_id=merchant.merchant_id,
                mcc=merchant.mcc,
                city=merchant.city,
            ),
            remark="Payment" if rail is Rail.UPI else merchant.category,
            channel=channel,
            discretionary=True,
        )

    def _bill(self, lo: datetime, hi: datetime) -> Intent:
        r = self.rng
        sub = pick(r, _BILLS)
        merchant = self.merchants.choose(r, sub, self.profile.city.name, needs_vpa=True)
        amount = self._lognormal(_MEDIAN.get(sub, 1_000), 0.4) * 100
        return Intent(
            at=self._when(lo, hi),
            holding=self.primary,
            direction=Direction.DEBIT,
            rail=Rail.UPI,
            txn_type=TransactionType.BILL_PAY,
            amount_paise=amount,
            counterparty=Counterparty(
                merchant.display_name,
                vpa=merchant.vpa,
                merchant_id=merchant.merchant_id,
                mcc=merchant.mcc,
            ),
            remark="Bill payment",
        )

    def _atm(self, lo: datetime, hi: datetime) -> Intent:
        amount = self.rng.choice((5, 10, 20, 20, 30, 50, 100)) * 10_000
        return Intent(
            at=self._when(lo, hi),
            holding=self.primary,
            direction=Direction.DEBIT,
            rail=Rail.ATM,
            txn_type=TransactionType.CASH_WITHDRAWAL,
            amount_paise=amount,
            counterparty=Counterparty("ATM", city=self.profile.city.name),
            remark="Cash withdrawal",
            channel=Channel.ATM,
            discretionary=True,
        )

    def _p2p_out(self, lo: datetime, hi: datetime) -> Intent:
        r = self.rng
        family = [x for x in self.payees if not x.is_landlord]
        if family and r.random() < 0.4:
            amount = r.randint(20, 150) * 10_000
            return self._to_payee(self._when(lo, hi), r.choice(family), amount, "Family support")
        first = r.choice(catalog.MALE_NAMES + catalog.FEMALE_NAMES)
        bank = r.choice(catalog.BANKS)
        return Intent(
            at=self._when(lo, hi),
            holding=self.primary,
            direction=Direction.DEBIT,
            rail=Rail.UPI,
            txn_type=TransactionType.P2P,
            amount_paise=self._lognormal(600, 0.9) * 100,
            counterparty=Counterparty(
                f"{first} {r.choice(catalog.SURNAMES['north'])}",
                vpa=f"{first.lower()}{r.randint(10, 99)}@{bank.upi_handle}",
            ),
            remark=r.choice(("Paid", "Dinner split", "Tickets", "Gift")),
            discretionary=True,
        )

    def _to_payee(self, at: datetime, payee: Payee, amount: int, remark: str) -> Intent:
        rail = (
            Rail.RTGS if amount >= RTGS_MINIMUM_PAISE else self.rng.choice((Rail.IMPS, Rail.NEFT))
        )
        holding = self.primary
        return Intent(
            at=max(at, payee.row.cooling_period_ends_at),
            holding=holding,
            direction=Direction.DEBIT,
            rail=rail,
            txn_type=TransactionType.P2P,
            amount_paise=amount,
            counterparty=Counterparty(
                payee.name, account_masked=payee.row.account_number_masked, ifsc=payee.row.ifsc
            ),
            remark=remark,
        )

    def _credit_neft(
        self, at: datetime, amount: int, name: str, remark: str, txn_type: TransactionType
    ) -> Intent:
        bank = self.rng.choice(catalog.BANKS)
        rail = Rail.RTGS if amount >= RTGS_MINIMUM_PAISE and self.rng.random() < 0.5 else Rail.NEFT
        return Intent(
            at=at,
            holding=self.primary,
            direction=Direction.CREDIT,
            rail=rail,
            txn_type=txn_type,
            amount_paise=amount,
            counterparty=Counterparty(
                name,
                account_masked=refs.masked(refs.digits(self.rng, 14)),
                ifsc=refs.ifsc(self.rng, bank.code),
            ),
            remark=remark,
            channel=Channel.API,
            customer_initiated=False,
        )

    def _credit_imps(self, at: datetime, amount: int, name: str, remark: str) -> Intent:
        bank = self.rng.choice(catalog.BANKS)
        return Intent(
            at=at,
            holding=self.primary,
            direction=Direction.CREDIT,
            rail=Rail.IMPS,
            txn_type=TransactionType.P2P,
            amount_paise=amount,
            counterparty=Counterparty(
                name,
                account_masked=refs.masked(refs.digits(self.rng, 14)),
                ifsc=refs.ifsc(self.rng, bank.code),
            ),
            remark=remark,
            channel=Channel.API,
            customer_initiated=False,
        )

    def _credit_upi(
        self,
        at: datetime,
        amount: int,
        name: str,
        remark: str,
        txn_type: TransactionType = TransactionType.P2P,
    ) -> Intent:
        bank = self.rng.choice(catalog.BANKS)
        handle = name.split(maxsplit=1)[0].lower() + str(self.rng.randint(10, 999))
        return Intent(
            at=at,
            holding=self.primary,
            direction=Direction.CREDIT,
            rail=Rail.UPI,
            txn_type=txn_type,
            amount_paise=amount,
            counterparty=Counterparty(name, vpa=f"{handle}@{bank.upi_handle}"),
            remark=remark,
            channel=Channel.API,
            customer_initiated=False,
        )

    def _life_event(self, start: datetime, end: datetime) -> list[Intent]:
        """A large sum in and straight back out: a home or car down payment.

        Ordinary, and exactly what a rapid-movement rule cannot tell from laundering, so it
        is where most of that rule's false positives come from.
        """
        r = self.rng
        if r.random() > 0.07:
            return []
        source, payee = r.choice(_LIFE_EVENTS)
        at = between(r, start + 30 * DAY, end - 5 * DAY)
        amount = r.randint(3, 15) * 10_000_000 * round(_SEGMENT_FACTOR[self.profile.segment])
        credit = self._credit_neft(at, amount, source, "DISBURSAL", TransactionType.P2P)
        bank = r.choice(catalog.BANKS)
        builder = f"{r.choice(catalog.SURNAMES['west'])} {payee}"
        debit = Intent(
            at=at + r.randint(3, 40) * timedelta(hours=1),
            holding=self.primary,
            direction=Direction.DEBIT,
            rail=Rail.RTGS,
            txn_type=TransactionType.P2P,
            amount_paise=amount * r.randint(90, 100) // 100,
            counterparty=Counterparty(
                builder,
                account_masked=refs.masked(refs.digits(r, 14)),
                ifsc=refs.ifsc(r, bank.code),
            ),
            remark="Down payment",
            sweep=True,
        )
        return [credit, debit]

    # --- deposits, interest, charges, closure

    def _deposits(self, end: datetime) -> list[Intent]:
        out: list[Intent] = []
        for h in self.holdings[1:]:
            if not h.is_deposit:
                continue
            if self.config.window_start <= h.opened_at <= end:
                booking = self._book(h, h.opened_at, h.principal_paise, "FD BOOKING")
                booking.budget_share = 0.6
                out.append(booking)
            if h.product is ProductCode.RECURRING_DEPOSIT:
                at = max(h.opened_at, self.config.window_start) + 30 * DAY
                while at < end:
                    out.append(self._book(h, at, h.principal_paise, "RD INSTALMENT"))
                    at += 30 * DAY
        return out

    def _book(self, deposit: Holding, at: datetime, amount: int, remark: str) -> Intent:
        def funded(booked: Booked | None) -> None:
            if booked is not None and booked.txn.posted_at is not None:
                deposit.funded = True

        return Intent(
            at=at,
            holding=self.primary,
            direction=Direction.DEBIT,
            rail=Rail.INTERNAL,
            txn_type=TransactionType.FD_BOOKING,
            amount_paise=amount,
            counterparty=Counterparty(f"Kosha {deposit.product.value.replace('_', ' ')}"),
            remark=f"{remark} {deposit.account_number[-4:]}",
            channel=Channel.MOBILE_APP,
            counter_holding=deposit,
            then=funded,
        )

    def _bank_initiated(self) -> list[Intent]:
        """Quarterly interest on savings and deposits, and SMS charges while in use."""
        out: list[Intent] = []
        for quarter_end in _quarter_ends(self.config):
            for h in self.holdings:
                if h.product is not ProductCode.CURRENT:
                    out.append(self._interest(h, quarter_end))
                if not h.is_deposit and self._in_use(quarter_end):
                    out.append(self._charge(h, quarter_end + 2 * DAY))
        return out

    def _in_use(self, at: datetime) -> bool:
        start, end = self._active_span()
        return start <= at <= end

    def _interest(self, holding: Holding, at: datetime) -> Intent:
        return Intent(
            at=at,
            holding=holding,
            direction=Direction.CREDIT,
            rail=Rail.INTERNAL,
            txn_type=TransactionType.INTEREST_CREDIT,
            amount_paise=0,
            interest_bps=holding.row().interest_rate_bps,
            counterparty=Counterparty("Kosha Financial"),
            remark=f"Interest credit Q ending {at:%d%b%y}",
            channel=Channel.API,
            customer_initiated=False,
        )

    def _charge(self, holding: Holding, at: datetime) -> Intent:
        quarter = (at.month - 1) // 3 + 1
        return Intent(
            at=at,
            holding=holding,
            direction=Direction.DEBIT,
            rail=Rail.INTERNAL,
            txn_type=TransactionType.CHARGES,
            amount_paise=SMS_CHARGE_PAISE,
            counterparty=Counterparty("Kosha Financial"),
            remark=f"SMS alert charges Q{quarter} incl GST",
            channel=Channel.API,
            customer_initiated=False,
            discretionary=True,
        )

    def _closure(self, at: datetime) -> Intent:
        bank = self.rng.choice(catalog.BANKS)
        return Intent(
            at=at,
            holding=self.primary,
            direction=Direction.DEBIT,
            rail=Rail.NEFT,
            txn_type=TransactionType.P2P,
            amount_paise=10**15,
            counterparty=Counterparty(
                self.profile.full_name,
                account_masked=refs.masked(refs.digits(self.rng, 14)),
                ifsc=refs.ifsc(self.rng, bank.code),
            ),
            remark="ACCOUNT CLOSURE PROCEEDS",
            sweep=True,
            scenario=BATCHED,
        )

    def _lognormal(self, median_rupees: float, sigma: float) -> int:
        """A whole-rupee amount around the median; banks see few round numbers below ₹100."""
        rupees = median_rupees * math.exp(self.rng.gauss(0, sigma))
        if rupees >= 1_000:
            rupees = round(rupees, -1)
        return max(10, int(rupees))


def _months(config: GenerationConfig) -> list[tuple[datetime, datetime]]:
    months: list[tuple[datetime, datetime]] = []
    start = config.window_start
    while start < config.now:
        end = _month_end(start)
        months.append((start, min(end, config.now)))
        start = end
    return months


def _month_end(start: datetime) -> datetime:
    year, month = (start.year + 1, 1) if start.month == 12 else (start.year, start.month + 1)
    return datetime(year, month, 1, tzinfo=UTC)


def _last_working_day(month_start: datetime) -> datetime:
    day = _month_end(month_start) - DAY
    while day.weekday() >= 5:
        day -= DAY
    return day


def _quarter_ends(config: GenerationConfig) -> list[datetime]:
    ends: list[datetime] = []
    for month_start, _ in _months(config):
        if month_start.month in (3, 6, 9, 12):
            ends.append(_month_end(month_start) - DAY + timedelta(hours=14, minutes=30))
    return [e for e in ends if e <= config.now]
