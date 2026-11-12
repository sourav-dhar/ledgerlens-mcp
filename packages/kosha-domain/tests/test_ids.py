import random
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kosha_domain.ids import IdPrefix, is_valid_id, new_id, parse_id

# Worked example from the ULID specification: this instant encodes as "01ARYZ6S41".
SPEC_INSTANT = datetime.fromtimestamp(1469918176385 / 1000, tz=UTC)


def test_id_is_prefix_then_26_character_ulid() -> None:
    value = new_id(IdPrefix.CUSTOMER)

    prefix, ulid = value.split("_")
    assert prefix == "cus"
    assert len(ulid) == 26


def test_time_component_matches_the_ulid_specification() -> None:
    assert new_id(IdPrefix.TRANSACTION, at=SPEC_INSTANT).startswith("txn_01ARYZ6S41")


def test_same_instant_and_seed_give_the_same_id() -> None:
    first = new_id(IdPrefix.ACCOUNT, at=SPEC_INSTANT, rng=random.Random(7))
    second = new_id(IdPrefix.ACCOUNT, at=SPEC_INSTANT, rng=random.Random(7))

    assert first == second


def test_unseeded_ids_differ() -> None:
    assert new_id(IdPrefix.ACCOUNT, at=SPEC_INSTANT) != new_id(IdPrefix.ACCOUNT, at=SPEC_INSTANT)


def test_naive_timestamps_are_refused() -> None:
    with pytest.raises(ValueError, match="timezone"):
        new_id(IdPrefix.CUSTOMER, at=datetime(2026, 1, 1))  # noqa: DTZ001


# Hypothesis takes naive bounds and attaches the zone itself.
@given(
    st.datetimes(
        min_value=datetime(2000, 1, 1),  # noqa: DTZ001
        max_value=datetime(2100, 1, 1),  # noqa: DTZ001
        timezones=st.just(UTC),
    )
)
def test_ids_sort_in_time_order(earlier: datetime) -> None:
    later = earlier + timedelta(milliseconds=1)

    assert new_id(IdPrefix.TRANSACTION, at=earlier) < new_id(IdPrefix.TRANSACTION, at=later)


def test_parse_recovers_prefix_and_instant() -> None:
    parsed = parse_id(new_id(IdPrefix.DISPUTE, at=SPEC_INSTANT))

    assert parsed.prefix is IdPrefix.DISPUTE
    assert parsed.issued_at == SPEC_INSTANT


@pytest.mark.parametrize(
    "value",
    [
        "cus_01ARYZ6S41TSV4RRFFQ69G5FA",  # 25 characters
        "cus_01ARYZ6S41TSV4RRFFQ69G5FAVX",  # 27 characters
        "cus_01ARYZ6S41TSV4RRFFQ69G5FAU",  # U is not in Crockford base32
        "cus_01arYZ6S41TSV4RRFFQ69G5FAV",  # lowercase
        "zzz_01ARYZ6S41TSV4RRFFQ69G5FAV",  # unknown prefix
        "cus01ARYZ6S41TSV4RRFFQ69G5FAV",  # no separator
        "cus_81ARYZ6S41TSV4RRFFQ69G5FAV",  # timestamp overflows 48 bits
    ],
)
def test_malformed_ids_are_invalid(value: str) -> None:
    assert not is_valid_id(value)
    with pytest.raises(ValueError, match="identifier"):
        parse_id(value)


def test_validity_can_require_a_specific_prefix() -> None:
    value = new_id(IdPrefix.CUSTOMER)

    assert is_valid_id(value, IdPrefix.CUSTOMER)
    assert not is_valid_id(value, IdPrefix.ACCOUNT)
