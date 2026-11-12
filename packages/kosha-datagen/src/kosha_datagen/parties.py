"""Customers: who they are, where they live, and what becomes of their relationship.

Each Customer is planned as a `Profile` before any row is written. The profile fixes the
Customer's fate (dormant, closed, frozen, ...) and onboarding date together, so every row
derived from it later agrees: a dormant Customer was onboarded long enough ago to go quiet,
and an inoperative one predates the Transaction window.
"""

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from kosha_datagen import catalog, refs
from kosha_datagen.chance import between, pick
from kosha_datagen.config import GenerationConfig
from kosha_datagen.rows import Address, Customer
from kosha_domain.ids import IdPrefix, new_id
from kosha_domain.vocabulary import (
    AddressType,
    CustomerStatus,
    Gender,
    IncomeBand,
    OnboardingChannel,
    Persona,
    ResidentialStatus,
    RiskCategory,
    Segment,
    Typology,
)

DAY = timedelta(days=1)


class Fate(StrEnum):
    """How a Customer's relationship stands on the as-of date."""

    ACTIVE = "active"
    PROSPECT = "prospect"  # onboarding unfinished: no Transactions
    DORMANT = "dormant"  # no Customer-initiated activity for 12+ months
    INOPERATIVE = "inoperative"  # none for 24+ months, so none in the window at all
    CLOSED = "closed"  # balance paid out, Accounts closed
    FROZEN = "frozen"  # law-enforcement freeze: total freeze on every Account
    DECEASED = "deceased"  # claim pending: debits frozen
    ON_HOLD = "on_hold"  # bank-initiated hold pending review


_FATE_WEIGHTS = {
    Fate.ACTIVE: 885,
    Fate.PROSPECT: 15,
    Fate.DORMANT: 45,
    Fate.INOPERATIVE: 10,
    Fate.CLOSED: 25,
    Fate.FROZEN: 5,
    Fate.DECEASED: 5,
    Fate.ON_HOLD: 10,
}
_CUSTOMER_STATUS = {
    Fate.ACTIVE: CustomerStatus.ACTIVE,
    Fate.PROSPECT: CustomerStatus.PROSPECT,
    Fate.DORMANT: CustomerStatus.DORMANT,
    Fate.INOPERATIVE: CustomerStatus.DORMANT,
    Fate.CLOSED: CustomerStatus.CLOSED,
    Fate.FROZEN: CustomerStatus.FROZEN,
    Fate.DECEASED: CustomerStatus.DECEASED_CLAIM_PENDING,
    Fate.ON_HOLD: CustomerStatus.ON_HOLD,
}
_PERSONA_WEIGHTS = {
    Persona.SALARIED: 42,
    Persona.STUDENT: 12,
    Persona.GIG_WORKER: 14,
    Persona.SME_OWNER: 12,
    Persona.NRI: 6,
    Persona.SENIOR_CITIZEN: 14,
}
_AGE_RANGE = {
    Persona.SALARIED: (23, 55),
    Persona.STUDENT: (18, 24),
    Persona.GIG_WORKER: (21, 45),
    Persona.SME_OWNER: (28, 62),
    Persona.NRI: (25, 55),
    Persona.SENIOR_CITIZEN: (60, 82),
}
_INCOME = {
    Persona.SALARIED: (IncomeBand.FROM_3_TO_6_LAKH, IncomeBand.FROM_25_TO_50_LAKH),
    Persona.STUDENT: (IncomeBand.UP_TO_3_LAKH, IncomeBand.UP_TO_3_LAKH),
    Persona.GIG_WORKER: (IncomeBand.UP_TO_3_LAKH, IncomeBand.FROM_6_TO_12_LAKH),
    Persona.SME_OWNER: (IncomeBand.FROM_6_TO_12_LAKH, IncomeBand.ABOVE_50_LAKH),
    Persona.NRI: (IncomeBand.FROM_12_TO_25_LAKH, IncomeBand.ABOVE_50_LAKH),
    Persona.SENIOR_CITIZEN: (IncomeBand.UP_TO_3_LAKH, IncomeBand.FROM_12_TO_25_LAKH),
}
_BANDS = list(IncomeBand)
_ADULT_DAYS = 6_576  # 18 years, leap days included
BAD_ACTOR_SHARE = 0.02
"""Share of Customers planted with a money-laundering or fraud typology (plan v0.2 §1)."""


@dataclass(frozen=True, slots=True)
class Profile:
    """A planned Customer; every row about them is derived from it."""

    index: int
    customer_id: str
    persona: Persona
    gender: Gender
    first_name: str
    middle_name: str | None
    last_name: str
    date_of_birth: date
    city: catalog.City
    onboarded_at: datetime
    segment: Segment
    income_band: IncomeBand
    risk_category: RiskCategory
    pep: bool
    fate: Fate
    fate_at: datetime | None
    """When the fate took effect: last Customer activity, closure, freeze or hold."""
    typology: Typology | None
    """The planted typology of a bad actor."""
    employer: str | None
    occupation: str

    @property
    def full_name(self) -> str:
        return " ".join(n for n in (self.first_name, self.middle_name, self.last_name) if n)

    @property
    def is_individual_resident(self) -> bool:
        return self.persona is not Persona.NRI


def plan_customer(config: GenerationConfig, index: int, rng: random.Random) -> Profile:
    """Plan Customer number ``index`` from its own random stream."""
    typology = rng.choice(list(Typology)) if rng.random() < BAD_ACTOR_SHARE else None
    persona = _persona_for(rng, typology)
    fate = Fate.ACTIVE if typology else pick(rng, _FATE_WEIGHTS)
    if typology is Typology.MULE_ACCOUNT and rng.random() < 0.5:
        fate = Fate.FROZEN  # caught: law enforcement asked for a freeze
    if fate is Fate.DECEASED:
        persona = Persona.SENIOR_CITIZEN
    onboarded_at, fate_at = _timeline(config, rng, fate, typology)
    gender = rng.choices(list(Gender), (46, 53.8, 0.2))[0]
    city = rng.choices(catalog.CITIES, [c.weight for c in catalog.CITIES])[0]
    last = rng.choice(catalog.SURNAMES[city.region if city.region in catalog.SURNAMES else "north"])
    pool = catalog.FEMALE_NAMES if gender is Gender.FEMALE else catalog.MALE_NAMES
    if gender is Gender.TRANSGENDER:
        pool = catalog.FEMALE_NAMES + catalog.MALE_NAMES
    middle = rng.choice(catalog.MALE_NAMES) if rng.random() < 0.15 else None
    low, high = _AGE_RANGE[persona]
    dob = config.as_of - timedelta(days=rng.randint(low * 365 + 30, high * 365 + 300))
    # Only adults open accounts: age the Customer rather than move the fate's timeline.
    latest_dob = onboarded_at.date() - timedelta(days=_ADULT_DAYS + rng.randint(30, 900))
    dob = min(dob, latest_dob)
    band_low, band_high = _INCOME[persona]
    band = _BANDS[rng.randint(_BANDS.index(band_low), _BANDS.index(band_high))]
    segment = _segment(rng, band)
    pep = segment is not Segment.MASS and rng.random() < 0.02
    risk = _risk(rng, persona, pep, typology)
    occupation = rng.choice(catalog.OCCUPATIONS[persona.value])
    employer = rng.choice(catalog.EMPLOYERS) if persona is Persona.SALARIED else None
    return Profile(
        index=index,
        customer_id=new_id(IdPrefix.CUSTOMER, at=onboarded_at, rng=rng),
        persona=persona,
        gender=gender,
        first_name=rng.choice(pool),
        middle_name=middle,
        last_name=last,
        date_of_birth=dob,
        city=city,
        onboarded_at=onboarded_at,
        segment=segment,
        income_band=band,
        risk_category=risk,
        pep=pep,
        fate=fate,
        fate_at=fate_at,
        typology=typology,
        employer=employer,
        occupation=occupation,
    )


def _persona_for(rng: random.Random, typology: Typology | None) -> Persona:
    if typology is Typology.MULE_ACCOUNT:
        return rng.choice((Persona.STUDENT, Persona.GIG_WORKER))
    if typology in (Typology.STRUCTURING, Typology.ROUND_TRIPPING):
        return Persona.SME_OWNER
    return pick(rng, _PERSONA_WEIGHTS)


def _timeline(  # noqa: PLR0911 — one return per fate
    config: GenerationConfig, rng: random.Random, fate: Fate, typology: Typology | None
) -> tuple[datetime, datetime | None]:
    """Onboarding instant and fate instant, chosen so that the fate is possible."""
    now, window, history = config.now, config.window_start, config.history_start
    if typology is Typology.MULE_ACCOUNT:
        # Mules are recruited and used fast: a young Account, emptied within weeks.
        return between(rng, window, now - 60 * DAY), None
    if typology is Typology.DORMANT_REACTIVATION:
        return between(rng, history, window - 90 * DAY), None
    match fate:
        case Fate.PROSPECT:
            return between(rng, now - 30 * DAY, now - DAY), None
        case Fate.INOPERATIVE:
            return between(rng, history, window - 200 * DAY), None
        case Fate.DORMANT:
            onboarded = between(rng, history, now - 420 * DAY)
            last_activity = between(rng, max(onboarded + 30 * DAY, window), now - 370 * DAY)
            return onboarded, last_activity
        case Fate.CLOSED:
            onboarded = between(rng, history, now - 150 * DAY)
            return onboarded, between(rng, max(onboarded, window) + 90 * DAY, now - 7 * DAY)
        case Fate.FROZEN | Fate.DECEASED | Fate.ON_HOLD:
            onboarded = between(rng, history, now - 150 * DAY)
            return onboarded, between(rng, now - 90 * DAY, now - 2 * DAY)
        case Fate.ACTIVE:
            # A growing bank: a third of relationships predate the window, and sign-ups
            # inside it accelerate towards the as-of date.
            if rng.random() < 0.33:
                return between(rng, history, window), None
            span = (now - 14 * DAY - window).total_seconds()
            return window + timedelta(seconds=span * rng.random() ** 0.8), None


def _segment(rng: random.Random, band: IncomeBand) -> Segment:
    rank = _BANDS.index(band)
    if rank >= 4:
        return rng.choices(list(Segment), (10, 40, 50))[0]
    if rank >= 2:
        return rng.choices(list(Segment), (60, 35, 5))[0]
    return Segment.MASS


def _risk(
    rng: random.Random, persona: Persona, pep: bool, typology: Typology | None
) -> RiskCategory:
    if pep:
        return RiskCategory.HIGH
    if typology:
        return rng.choices(list(RiskCategory), (50, 35, 15))[0]  # bad actors pass onboarding
    if persona in (Persona.NRI, Persona.SME_OWNER):
        return rng.choices(list(RiskCategory), (45, 45, 10))[0]
    return rng.choices(list(RiskCategory), (78, 19, 3))[0]


def customer_row(config: GenerationConfig, profile: Profile, rng: random.Random) -> Customer:
    under_investigation = profile.typology is Typology.MULE_ACCOUNT and profile.fate is Fate.ACTIVE
    status = (
        CustomerStatus.UNDER_INVESTIGATION
        if under_investigation
        else _CUSTOMER_STATUS[profile.fate]
    )
    handle = f"{profile.first_name}.{profile.last_name}{rng.randint(1, 999)}".lower()
    updated = profile.fate_at or profile.onboarded_at
    return Customer(
        customer_id=profile.customer_id,
        cif_number=refs.cif_number(profile.index),
        first_name=profile.first_name,
        middle_name=profile.middle_name,
        last_name=profile.last_name,
        date_of_birth=profile.date_of_birth,
        gender=profile.gender,
        email=f"{handle}@example.com" if rng.random() < 0.92 else None,
        mobile=refs.mobile(profile.index, rng),
        mobile_verified=profile.fate is not Fate.PROSPECT or rng.random() < 0.6,
        persona=profile.persona,
        occupation=profile.occupation,
        employer_name=profile.employer,
        annual_income_band=profile.income_band,
        segment=profile.segment,
        residential_status=(
            ResidentialStatus.NRI if profile.persona is Persona.NRI else ResidentialStatus.RESIDENT
        ),
        preferred_language=(
            catalog.LANGUAGE_BY_REGION.get(profile.city.region, "en")
            if rng.random() < 0.3
            else "en"
        ),
        onboarding_channel=rng.choices(list(OnboardingChannel), (70, 12, 10, 8))[0],
        relationship_start_date=profile.onboarded_at.date(),
        status=status,
        risk_category=profile.risk_category,
        created_at=profile.onboarded_at,
        updated_at=min(updated, config.now),
    )


def address_rows(profile: Profile, rng: random.Random) -> list[Address]:
    """A permanent address, and for a quarter of Customers a correspondence address in a metro."""
    addresses = [_address(profile, rng, AddressType.PERMANENT, profile.city)]
    if rng.random() < 0.25:
        metro = rng.choice([c for c in catalog.CITIES if c.weight >= 8 and c != profile.city])
        addresses.append(_address(profile, rng, AddressType.CORRESPONDENCE, metro))
    return addresses


def _address(
    profile: Profile, rng: random.Random, kind: AddressType, city: catalog.City
) -> Address:
    pincode = rng.randint(*city.pincodes)
    if rng.random() < 0.6:
        line1 = f"Flat {rng.randint(1, 18)}{rng.randint(1, 12):02d}, {rng.choice(_BUILDINGS)}"
    else:
        line1 = f"{rng.randint(1, 240)}, {rng.choice(_STREETS)}"
    return Address(
        address_id=new_id(IdPrefix.ADDRESS, at=profile.onboarded_at, rng=rng),
        customer_id=profile.customer_id,
        address_type=kind,
        line1=line1,
        line2=rng.choice(city.localities),
        city=city.name,
        district=city.district,
        state=city.state.value,
        state_code=city.state.gst_code,
        pincode=str(pincode),
        country="IN",
        is_verified=profile.fate is not Fate.PROSPECT,
        valid_from=profile.onboarded_at.date(),
        valid_to=None,
    )


_BUILDINGS = (
    "Shanti Kunj Apartments",
    "Sai Krupa Residency",
    "Green Valley Towers",
    "Lakeview Heights",
    "Ganesh Co-operative Housing Society",
    "Silver Oak Enclave",
    "Royal Palms",
)
_STREETS = (
    "MG Road",
    "Station Road",
    "Temple Street",
    "Nehru Nagar Main Road",
    "Gandhi Marg",
    "2nd Cross Road",
    "Ring Road",
)
