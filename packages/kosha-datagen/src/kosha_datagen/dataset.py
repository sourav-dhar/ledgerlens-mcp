"""The generator's entry point: a config in, a stream of batches out, no I/O."""

from collections.abc import Iterator

from kosha_datagen.batch import Batch
from kosha_datagen.config import GenerationConfig
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
    return Batch(
        customers=[customer_row(config, profile, rng)],
        addresses=address_rows(profile, rng),
    )
