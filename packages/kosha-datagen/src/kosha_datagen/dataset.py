"""The generator's entry point: a config in, a stream of batches out, no I/O."""

from collections.abc import Iterator

from kosha_datagen.accounts import card_rows, plan_holdings, plan_payees, vpa_rows
from kosha_datagen.batch import Batch
from kosha_datagen.config import GenerationConfig
from kosha_datagen.kyc import kyc_rows, screening_rows
from kosha_datagen.merchants import generate_merchants
from kosha_datagen.parties import address_rows, customer_row, plan_customer

CUSTOMERS_PER_BATCH = 200
"""Customers whose rows commit together; small enough to keep deferred-trigger queues short."""


def generate(config: GenerationConfig) -> Iterator[Batch]:
    """Reference data first, then Customers in batches, each with everything they own."""
    merchants = generate_merchants(config)
    yield Batch(merchants=merchants)
    batch = Batch()
    for index in range(config.customers):
        batch.extend(_customer(config, index))
        if (index + 1) % CUSTOMERS_PER_BATCH == 0:
            yield batch
            batch = Batch()
    if batch.customers:
        yield batch


def _customer(config: GenerationConfig, index: int) -> Batch:
    rng = config.rng("customer", index)
    profile = plan_customer(config, index, rng)
    customer = customer_row(config, profile, rng)
    holdings = plan_holdings(config, profile, rng)
    payees = plan_payees(config, profile, rng)
    kyc, kyc_events, kyc_documents = kyc_rows(config, profile, rng)
    return Batch(
        customers=[customer],
        addresses=address_rows(profile, rng),
        accounts=[h.row() for h in holdings],
        cards=[card for h in holdings for card in card_rows(config, h, rng)],
        vpas=vpa_rows(profile, holdings[0], customer.mobile, rng),
        beneficiaries=[p.row for p in payees],
        kyc_profiles=[kyc],
        kyc_documents=kyc_documents,
        kyc_events=kyc_events,
        screening_results=screening_rows(config, profile, rng),
    )
