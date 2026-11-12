"""Accounts, the cards and VPAs that reach them, and the Beneficiaries Customers pay.

An Account is a `Holding` while its Transactions are generated: the timeline moves its
balance and holds, and only then does it become a row, so the cached balance is exactly
what its Postings add up to.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from kosha_datagen import catalog, refs
from kosha_datagen.chance import between, pick
from kosha_datagen.config import GenerationConfig
from kosha_datagen.parties import Fate, Profile
from kosha_datagen.rows import Account, Beneficiary, Card, Vpa
from kosha_domain.ids import IdPrefix, new_id
from kosha_domain.lifecycles import AccountStatus, BeneficiaryStatus, CardStatus
from kosha_domain.vocabulary import (
    CardNetwork,
    CardType,
    Direction,
    ModeOfOperation,
    Persona,
    ProductCode,
    Segment,
    Typology,
    VpaStatus,
)

DAY = timedelta(days=1)
COOLING_PERIOD = timedelta(hours=24)
DEPOSITS = frozenset({ProductCode.FIXED_DEPOSIT, ProductCode.RECURRING_DEPOSIT})

_RESTRICTION = {
    Fate.FROZEN: (AccountStatus.TOTAL_FREEZE, "Freeze requested by state cyber crime cell"),
    Fate.DECEASED: (AccountStatus.DEBIT_FREEZE, "Death intimation received; claim pending"),
    Fate.ON_HOLD: (AccountStatus.ON_HOLD, "Under review: activity inconsistent with profile"),
}
_RATE_BPS = {
    ProductCode.SAVINGS_REGULAR: 300,
    ProductCode.SAVINGS_SALARY: 300,
    ProductCode.CURRENT: 0,
    ProductCode.FIXED_DEPOSIT: 710,
    ProductCode.RECURRING_DEPOSIT: 650,
}
_MINIMUM_BALANCE = {
    ProductCode.SAVINGS_REGULAR: 500_000,
    ProductCode.CURRENT: 1_000_000,
}


@dataclass(slots=True)
class Holding:
    """An Account whose balance the Transaction timeline is still moving."""

    account_id: str
    customer_id: str
    account_number: str
    product: ProductCode
    opened_at: datetime
    status: AccountStatus = AccountStatus.ACTIVE
    status_reason: str | None = None
    restricted_at: datetime | None = None
    """From this instant the status blocks money in, out, or both."""
    closed_at: datetime | None = None
    nominee: bool = False
    principal_paise: int = 0
    """For a deposit: the amount booked into it (monthly instalment for a recurring one)."""
    balance_paise: int = 0
    hold_paise: int = 0
    last_txn_at: datetime | None = None
    funded: bool = field(default=False)

    @property
    def is_deposit(self) -> bool:
        return self.product in DEPOSITS

    @property
    def available_paise(self) -> int:
        return self.balance_paise - self.hold_paise

    def accepts(self, direction: Direction, at: datetime) -> bool:
        """Whether money may move in ``direction`` at ``at``, given the Account's standing."""
        if at < self.opened_at or (self.closed_at is not None and at > self.closed_at):
            return False
        if self.restricted_at is None or at < self.restricted_at:
            return True
        blocked = {
            AccountStatus.TOTAL_FREEZE: {Direction.DEBIT, Direction.CREDIT},
            AccountStatus.DEBIT_FREEZE: {Direction.DEBIT},
            AccountStatus.CREDIT_FREEZE: {Direction.CREDIT},
            AccountStatus.ON_HOLD: {Direction.DEBIT},
        }.get(self.status, set[Direction]())
        return direction not in blocked

    def row(self) -> Account:
        return Account(
            account_id=self.account_id,
            customer_id=self.customer_id,
            account_number=self.account_number,
            ifsc=catalog.KOSHA_IFSC,
            product_code=self.product,
            status=self.status,
            status_reason=self.status_reason,
            mode_of_operation=ModeOfOperation.SINGLE,
            opened_at=self.opened_at,
            closed_at=self.closed_at,
            ledger_balance_paise=self.balance_paise,
            hold_amount_paise=self.hold_paise,
            minimum_balance_paise=_MINIMUM_BALANCE.get(self.product, 0),
            interest_rate_bps=_RATE_BPS[self.product],
            overdraft_limit_paise=0,
            nominee_registered=self.nominee,
            last_txn_at=self.last_txn_at,
        )


def plan_holdings(config: GenerationConfig, profile: Profile, rng: random.Random) -> list[Holding]:
    """The primary Account first, then any second savings Account and deposits."""
    opened = profile.onboarded_at + timedelta(minutes=rng.randint(5, 240))
    primary = _holding(profile, rng, 0, _primary_product(profile, rng), opened)
    holdings = [primary]
    if profile.fate not in (Fate.PROSPECT, Fate.CLOSED) and not profile.typology:
        if rng.random() < 0.05:
            holdings.append(
                _holding(profile, rng, 1, ProductCode.SAVINGS_REGULAR, opened + 30 * DAY)
            )
        fd_share = {Persona.SENIOR_CITIZEN: 0.6, Persona.NRI: 0.45}.get(profile.persona, 0.22)
        if rng.random() < fd_share:
            holdings.append(_deposit(config, profile, rng, 2, ProductCode.FIXED_DEPOSIT))
        if profile.persona is Persona.SALARIED and rng.random() < 0.18:
            holdings.append(_deposit(config, profile, rng, 3, ProductCode.RECURRING_DEPOSIT))
    _apply_fate(config, profile, rng, holdings)
    return holdings


def _primary_product(profile: Profile, rng: random.Random) -> ProductCode:
    if profile.persona is Persona.SME_OWNER:
        return ProductCode.CURRENT
    if profile.persona is Persona.SALARIED and rng.random() < 0.7:
        return ProductCode.SAVINGS_SALARY
    return ProductCode.SAVINGS_REGULAR


def _holding(
    profile: Profile, rng: random.Random, slot: int, product: ProductCode, opened: datetime
) -> Holding:
    return Holding(
        account_id=new_id(IdPrefix.ACCOUNT, at=opened, rng=rng),
        customer_id=profile.customer_id,
        account_number=refs.account_number(profile.index, slot),
        product=product,
        opened_at=opened,
        nominee=rng.random() < 0.55,
    )


def _deposit(
    config: GenerationConfig, profile: Profile, rng: random.Random, slot: int, product: ProductCode
) -> Holding:
    earliest = max(profile.onboarded_at + 7 * DAY, config.history_start)
    opened = between(rng, earliest, config.now - 20 * DAY)
    holding = _holding(profile, rng, slot, product, opened)
    rich = profile.segment is not Segment.MASS
    if product is ProductCode.FIXED_DEPOSIT:
        holding.principal_paise = rng.choice((25, 50, 100, 200, 500)) * 100_000 * (4 if rich else 1)
    else:
        holding.principal_paise = rng.choice((2_000, 3_000, 5_000, 10_000)) * 100
    return holding


def _apply_fate(
    config: GenerationConfig, profile: Profile, rng: random.Random, holdings: list[Holding]
) -> None:
    primary = holdings[0]
    match profile.fate:
        case Fate.PROSPECT:
            primary.status = rng.choice(
                (AccountStatus.PENDING_ACTIVATION, AccountStatus.KYC_PENDING)
            )
        case Fate.DORMANT:
            primary.status = AccountStatus.DORMANT
            primary.status_reason = "No customer-initiated transaction for 12 months"
        case Fate.INOPERATIVE:
            primary.status = AccountStatus.INOPERATIVE
            primary.status_reason = "No customer-initiated transaction for 24 months"
        case Fate.CLOSED:
            primary.status = AccountStatus.CLOSED
            primary.status_reason = rng.choice(("Customer request", "Moved to another bank"))
            primary.closed_at = profile.fate_at
        case Fate.FROZEN | Fate.DECEASED | Fate.ON_HOLD:
            status, reason = _RESTRICTION[profile.fate]
            for holding in holdings:
                holding.status, holding.status_reason = status, reason
                holding.restricted_at = profile.fate_at
        case Fate.ACTIVE:
            if profile.typology is Typology.MULE_ACCOUNT:
                primary.status = AccountStatus.DEBIT_FREEZE
                primary.status_reason = "Suspected mule account under investigation"
                primary.restricted_at = config.now - rng.randint(1, 5) * DAY
            elif rng.random() < 0.012:
                status, reason = pick(rng, _ACTIVE_RESTRICTIONS)
                primary.status, primary.status_reason = status, reason
                primary.restricted_at = config.now - rng.randint(3, 60) * DAY


_ACTIVE_RESTRICTIONS = {
    (AccountStatus.LIEN_MARKED, "Lien marked under recovery order"): 4,
    (AccountStatus.DEBIT_FREEZE, "PAN not linked with Aadhaar"): 3,
    (AccountStatus.CREDIT_FREEZE, "Min-KYC balance limit reached"): 2,
    (AccountStatus.PENDING_CLOSURE, "Closure requested by customer"): 2,
}


def card_rows(config: GenerationConfig, holding: Holding, rng: random.Random) -> list[Card]:
    """A debit card on most transactional Accounts, renewed at expiry, replaced when lost."""
    if holding.is_deposit or holding.status in (
        AccountStatus.PENDING_ACTIVATION,
        AccountStatus.KYC_PENDING,
    ):
        return []
    if rng.random() > 0.82:
        return []
    network = pick(rng, {CardNetwork.RUPAY: 55, CardNetwork.VISA: 30, CardNetwork.MASTERCARD: 15})
    cards: list[Card] = []
    issued = holding.opened_at + rng.randint(1, 6) * DAY
    while True:
        expires = issued.replace(year=issued.year + 5, day=1)
        if expires.date() <= config.as_of:
            cards.append(_card(holding, rng, network, issued, CardStatus.REPLACED))
            issued = expires - rng.randint(5, 20) * DAY
            continue
        break
    status = _final_card_status(config, holding, rng, issued)
    replaceable = issued < config.now - 40 * DAY
    if status in (CardStatus.HOTLISTED, CardStatus.BLOCKED) and replaceable and rng.random() < 0.5:
        cards.append(_card(holding, rng, network, issued, CardStatus.REPLACED))
        issued = between(rng, issued + 30 * DAY, config.now - DAY)
        status = CardStatus.ACTIVE
    cards.append(_card(holding, rng, network, issued, status))
    return cards


def _final_card_status(
    config: GenerationConfig, holding: Holding, rng: random.Random, issued: datetime
) -> CardStatus:
    if holding.status is AccountStatus.CLOSED or holding.status is AccountStatus.TOTAL_FREEZE:
        return CardStatus.BLOCKED
    if issued > config.now - 20 * DAY:
        return CardStatus.INACTIVE
    return pick(
        rng,
        {
            CardStatus.ACTIVE: 88,
            CardStatus.TEMP_BLOCKED: 4,
            CardStatus.PIN_BLOCKED: 2,
            CardStatus.BLOCKED: 2,
            CardStatus.HOTLISTED: 4,
        },
    )


def _card(
    holding: Holding,
    rng: random.Random,
    network: CardNetwork,
    issued: datetime,
    status: CardStatus,
) -> Card:
    premium = holding.product is ProductCode.CURRENT
    return Card(
        card_id=new_id(IdPrefix.CARD, at=issued, rng=rng),
        account_id=holding.account_id,
        network=network,
        card_type=CardType.DEBIT,
        pan_last4=refs.digits(rng, 4),
        token_ref=f"tok_{network.value}_{refs.hex_token(rng, 16)}",
        status=status,
        expiry_month=issued.month,
        expiry_year=issued.year + 5,
        atm_limit_paise=(10_000_000 if premium else 5_000_000),
        pos_limit_paise=(50_000_000 if premium else 20_000_000),
        ecom_limit_paise=(25_000_000 if premium else 10_000_000),
        contactless_enabled=rng.random() < 0.8,
        international_enabled=rng.random() < 0.12,
        issued_at=issued,
    )


def vpa_rows(profile: Profile, holding: Holding, mobile: str, rng: random.Random) -> list[Vpa]:
    """``name.x123@kosha`` on the primary Account, and sometimes the mobile number too."""
    if holding.status in (AccountStatus.PENDING_ACTIVATION, AccountStatus.KYC_PENDING):
        return []
    status = {
        AccountStatus.CLOSED: VpaStatus.DEREGISTERED,
        AccountStatus.TOTAL_FREEZE: VpaStatus.SUSPENDED,
    }.get(holding.status, VpaStatus.ACTIVE)
    handle = f"{profile.first_name.lower()}.{profile.last_name[0].lower()}{profile.index}"
    names = [handle] + ([mobile] if rng.random() < 0.35 else [])
    return [
        Vpa(
            vpa_id=new_id(IdPrefix.VPA, at=holding.opened_at, rng=rng),
            customer_id=profile.customer_id,
            account_id=holding.account_id,
            vpa=f"{name}@{catalog.KOSHA_UPI_HANDLE}",
            is_primary=position == 0,
            status=status,
            created_at=holding.opened_at + timedelta(minutes=position * 7 + 3),
        )
        for position, name in enumerate(names)
    ]


@dataclass(frozen=True, slots=True)
class Payee:
    """A Beneficiary as the timeline sees it: who gets paid, from when."""

    row: Beneficiary
    name: str
    bank: catalog.Bank
    is_landlord: bool

    def payable_at(self, at: datetime) -> bool:
        return self.row.added_at <= at and self.row.status is not BeneficiaryStatus.DELETED


_RELATIONS = ("Amma", "Papa", "Didi", "Bhaiya", "Chotu", "Mama", "Nani")


def plan_payees(config: GenerationConfig, profile: Profile, rng: random.Random) -> list[Payee]:
    if profile.fate is Fate.PROSPECT:
        return []
    count = rng.randint(3, 8) if profile.persona is Persona.SME_OWNER else rng.randint(0, 5)
    payees: list[Payee] = []
    for position in range(count):
        landlord = position == 0 and profile.persona in (Persona.SALARIED, Persona.STUDENT)
        surname = rng.choice(catalog.SURNAMES["north"] + catalog.SURNAMES["south"])
        name = f"{rng.choice(catalog.MALE_NAMES + catalog.FEMALE_NAMES)} {surname}"
        if profile.persona is Persona.SME_OWNER:
            nickname = f"{surname} Traders"
        elif landlord:
            nickname = f"Rent - {name.split(maxsplit=1)[0]}"
        else:
            nickname = rng.choice(_RELATIONS) if rng.random() < 0.6 else name.split(maxsplit=1)[0]
        bank = rng.choice(catalog.BANKS)
        added = between(rng, profile.onboarded_at + DAY, config.now - DAY / 2)
        if landlord:
            added = profile.onboarded_at + rng.randint(1, 10) * DAY
        status = _payee_status(config, rng, added)
        account_number = refs.digits(rng, rng.randint(11, 16))
        row = Beneficiary(
            beneficiary_id=new_id(IdPrefix.BENEFICIARY, at=added, rng=rng),
            customer_id=profile.customer_id,
            nickname=nickname,
            account_number_masked=refs.masked(account_number),
            ifsc=refs.ifsc(rng, bank.code),
            bank_name=bank.name,
            added_at=added,
            cooling_period_ends_at=added + COOLING_PERIOD,
            status=status,
        )
        payees.append(Payee(row, name, bank, landlord))
    return payees


def _payee_status(
    config: GenerationConfig, rng: random.Random, added: datetime
) -> BeneficiaryStatus:
    if added + COOLING_PERIOD > config.now:
        return BeneficiaryStatus.PENDING_COOLING
    return pick(
        rng,
        {
            BeneficiaryStatus.ACTIVE: 88,
            BeneficiaryStatus.DISABLED: 4,
            BeneficiaryStatus.DELETED: 8,
        },
    )
