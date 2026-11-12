"""Merchants Customers pay: national chains and neighbourhood shops across the cities."""

import random
import re

from kosha_datagen import catalog, refs
from kosha_datagen.config import GenerationConfig
from kosha_datagen.rows import Merchant
from kosha_domain.ids import IdPrefix, new_id
from kosha_domain.vocabulary import RiskCategory

_CITY_WEIGHTS = [c.weight for c in catalog.CITIES]
_KIND_WEIGHTS = [k.weight for k in catalog.MERCHANT_KINDS]
_ALL_SURNAMES = tuple(s for names in catalog.SURNAMES.values() for s in names)


def generate_merchants(config: GenerationConfig) -> list[Merchant]:
    rng = config.rng("merchants")
    return [_merchant(config, rng, index) for index in range(config.merchants)]


def _merchant(config: GenerationConfig, rng: random.Random, index: int) -> Merchant:
    kind = rng.choices(catalog.MERCHANT_KINDS, _KIND_WEIGHTS)[0]
    city = rng.choices(catalog.CITIES, _CITY_WEIGHTS)[0]
    if kind.local_shops and rng.random() < 0.45:
        owner = rng.choice(_ALL_SURNAMES)
        display = f"{owner} {rng.choice(kind.local_shops)}"
        legal = f"{display} (Prop. {rng.choice(catalog.MALE_NAMES)} {owner})"
        registered = rng.random() < 0.55
    else:
        brand = rng.choice(kind.brands)
        display = f"{brand} {city.name}" if not kind.online else brand
        legal = f"{brand} {rng.choice(('Pvt Ltd', 'Retail Pvt Ltd', 'Services LLP'))}"
        registered = True
    acquirer, handle = rng.choice(catalog.ACQUIRERS)
    slug = re.sub(r"[^a-z0-9]", "", display.lower())[:16]
    created = config.history_start
    return Merchant(
        merchant_id=new_id(IdPrefix.MERCHANT, at=created, rng=rng),
        display_name=display,
        legal_name=legal,
        mcc=kind.mcc,
        category=kind.category,
        sub_category=kind.sub_category,
        city=city.name,
        state=city.state.value,
        vpa=f"{slug}.{index}@{handle}" if rng.random() < 0.9 else None,
        gstin=refs.gstin(rng, city.state, legal) if registered else None,
        acquirer_bank=acquirer,
        risk_level=rng.choices(list(RiskCategory), (90, 9, 1))[0],
    )
