"""The generator's entry point: a config in, a stream of batches out, no I/O."""

import random
from collections.abc import Iterator

from kosha_datagen import refs
from kosha_datagen.accounts import Holding, Payee, card_rows, plan_holdings, plan_payees, vpa_rows
from kosha_datagen.aml import Known, alert_rows, detect, plant, rule_rows
from kosha_datagen.batch import Batch
from kosha_datagen.behaviour import CustomerBehaviour, MerchantDirectory
from kosha_datagen.cases import dispute_rows, review_rows
from kosha_datagen.config import GenerationConfig
from kosha_datagen.kyc import kyc_rows, screening_rows
from kosha_datagen.merchants import generate_merchants
from kosha_datagen.parties import Profile, address_rows, customer_row, plan_customer
from kosha_datagen.payments import Ledger, Timeline
from kosha_datagen.rows import AmlRule
from kosha_domain.lifecycles import AccountStatus
from kosha_domain.vocabulary import Typology

CUSTOMERS_PER_BATCH = 200
"""Customers whose rows commit together; small enough to keep deferred-trigger queues short."""


def generate(config: GenerationConfig) -> Iterator[Batch]:
    """Reference data first, then Customers in batches, each with everything they own."""
    merchants = generate_merchants(config)
    directory = MerchantDirectory(merchants)
    rules = rule_rows(config)
    yield Batch(merchants=merchants, aml_rules=rules)
    by_typology = {r.typology: r for r in rules}
    batch = Batch()
    for index in range(config.customers):
        batch.extend(_customer(config, index, directory, by_typology))
        if (index + 1) % CUSTOMERS_PER_BATCH == 0:
            yield batch
            batch = Batch()
    if batch.customers:
        yield batch


def _customer(
    config: GenerationConfig,
    index: int,
    merchants: MerchantDirectory,
    rules: dict[Typology, AmlRule],
) -> Batch:
    rng = config.rng("customer", index)
    profile = plan_customer(config, index, rng)
    customer = customer_row(config, profile, rng)
    holdings = plan_holdings(config, profile, rng)
    payees = plan_payees(config, profile, rng)
    kyc, kyc_events, kyc_documents = kyc_rows(config, profile, rng)
    ledger = _transact(
        config, profile=profile, rng=rng, holdings=holdings, payees=payees, merchants=merchants
    )
    holdings = [h for h in holdings if not h.is_deposit or h.funded]
    known = Known({h.account_id: h.opened_at for h in holdings}, config.window_start)
    alerts = alert_rows(config, profile, rng, detect(ledger.booked, known), rules)
    escalated = {t for a in alerts for t in a.triggering_txn_ids}
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
        transactions=ledger.transactions,
        transaction_status_history=ledger.history,
        journal_entries=ledger.entries,
        postings=ledger.postings,
        aml_alerts=alerts,
        disputes=dispute_rows(config, rng, ledger.booked),
        transaction_reviews=review_rows(config, rng, ledger.booked, escalated),
    )


def _transact(
    config: GenerationConfig,
    *,
    profile: Profile,
    rng: random.Random,
    holdings: list[Holding],
    payees: list[Payee],
    merchants: MerchantDirectory,
) -> Ledger:
    timeline = Timeline(config, rng, f"dev-{refs.hex_token(rng, 16)}", profile.city)
    behaviour = CustomerBehaviour(config, profile, rng, holdings, payees, merchants)
    for holding, amount in behaviour.opening_balances():
        timeline.bring_forward(holding, amount)
    for intent in behaviour.intents() + plant(config, profile, rng, holdings[0]):
        timeline.schedule(intent)
    ledger = timeline.run()
    primary = holdings[0]
    if primary.status is AccountStatus.LIEN_MARKED:
        primary.hold_paise += min(primary.available_paise, rng.randint(50, 500) * 10_000)
    return ledger
