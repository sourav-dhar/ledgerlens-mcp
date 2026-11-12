"""Customers, their Addresses and Merchants look real to anyone who knows Indian banking."""

from collections import Counter
from datetime import date

from kosha_datagen import Batch, GenerationConfig, generate
from kosha_domain.geography import IndianState, state_for_pincode
from kosha_domain.ids import IdPrefix, is_valid_id
from kosha_domain.validators import is_valid_gstin, is_valid_mobile, is_valid_vpa
from kosha_domain.vocabulary import Persona

AS_OF = date(2026, 11, 12)


def test_the_default_scale_is_the_planned_volume() -> None:
    config = GenerationConfig(as_of=AS_OF)

    assert (config.customers, config.merchants) == (5_000, 1_200)


def test_a_seed_reproduces_every_row() -> None:
    config = GenerationConfig(as_of=AS_OF, seed=11, scale=0.002)

    assert Batch.merge(generate(config)) == Batch.merge(generate(config))


def test_a_different_seed_gives_different_people() -> None:
    def names(seed: int) -> list[str]:
        batch = Batch.merge(generate(GenerationConfig(as_of=AS_OF, seed=seed, scale=0.002)))
        return [c.first_name + c.last_name for c in batch.customers]

    assert names(1) != names(2)


def test_a_smaller_scale_is_a_prefix_of_a_larger_one() -> None:
    small = Batch.merge(generate(GenerationConfig(as_of=AS_OF, seed=3, scale=0.002)))
    large = Batch.merge(generate(GenerationConfig(as_of=AS_OF, seed=3, scale=0.004)))

    assert small.customers == large.customers[: len(small.customers)]
    assert small.transactions == large.transactions[: len(small.transactions)]


def test_customers_carry_valid_identifiers(dataset: Batch) -> None:
    customers = dataset.customers

    assert len(customers) == 150
    assert all(is_valid_id(c.customer_id, IdPrefix.CUSTOMER) for c in customers)
    assert all(len(c.cif_number) == 10 and c.cif_number.isdigit() for c in customers)
    assert all(is_valid_mobile(c.mobile) for c in customers)
    assert len({c.cif_number for c in customers}) == len(customers)
    assert len({c.mobile for c in customers}) == len(customers)


def test_customers_are_adults_onboarded_before_the_as_of_date(dataset: Batch) -> None:
    for c in dataset.customers:
        assert c.relationship_start_date <= AS_OF
        age_at_onboarding = (c.relationship_start_date - c.date_of_birth).days / 365.25
        assert age_at_onboarding >= 18, c


def test_personas_follow_the_neobank_mix(dataset: Batch) -> None:
    mix = Counter(c.persona for c in dataset.customers)

    assert set(mix) == set(Persona)
    assert mix[Persona.SALARIED] == max(mix.values())


def test_nris_are_non_resident_and_others_resident(dataset: Batch) -> None:
    for c in dataset.customers:
        assert (c.persona is Persona.NRI) == (c.residential_status == "nri")


def test_every_pincode_belongs_to_its_addresses_state(dataset: Batch) -> None:
    addresses = dataset.addresses

    assert {a.customer_id for a in addresses} == {c.customer_id for c in dataset.customers}
    for a in addresses:
        state = state_for_pincode(a.pincode)
        assert state is not None, a
        assert (a.state, a.state_code) == (state.value, state.gst_code), a


def test_each_customer_has_exactly_one_permanent_address(dataset: Batch) -> None:
    permanent = Counter(a.customer_id for a in dataset.addresses if a.address_type == "permanent")

    assert set(permanent.values()) == {1}


def test_merchants_have_valid_gstins_vpas_and_mccs(dataset: Batch) -> None:
    merchants = dataset.merchants

    assert len(merchants) == 40
    assert all(is_valid_id(m.merchant_id, IdPrefix.MERCHANT) for m in merchants)
    assert all(m.vpa is None or is_valid_vpa(m.vpa) for m in merchants)
    assert all(m.gstin is None or is_valid_gstin(m.gstin) for m in merchants)
    assert all(m.gstin is None or m.gstin[:2] == IndianState(m.state).gst_code for m in merchants)
    assert all(0 < m.mcc < 10_000 for m in merchants)
    assert len({m.vpa for m in merchants if m.vpa}) == sum(1 for m in merchants if m.vpa)
