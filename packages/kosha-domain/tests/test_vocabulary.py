"""Closed vocabularies are stored as Postgres enums, so their values must suit enum labels."""

import re
from enum import StrEnum

import pytest

from kosha_domain import vocabulary
from kosha_domain.vocabulary import Classification, GlAccount

VOCABULARIES = [
    member
    for member in vars(vocabulary).values()
    if isinstance(member, type) and issubclass(member, StrEnum) and member is not StrEnum
]
_LABEL = re.compile(r"[a-z0-9]+(_[a-z0-9]+)*")


def test_every_schema_vocabulary_is_declared() -> None:
    names = {vocab.__name__ for vocab in VOCABULARIES}

    assert {
        "Persona",
        "Segment",
        "CustomerStatus",
        "ProductCode",
        "TransactionType",
        "Channel",
        "Direction",
        "GlAccount",
        "Typology",
        "Classification",
    } <= names


@pytest.mark.parametrize("vocab", VOCABULARIES, ids=lambda v: v.__name__)
def test_values_are_lower_snake_enum_labels(vocab: type[StrEnum]) -> None:
    for member in vocab:
        assert _LABEL.fullmatch(member.value), member
        assert len(member.value.encode()) <= 63, member


def test_classification_is_declared_from_least_to_most_sensitive() -> None:
    # Row-level security compares enum positions: a caller sees chunks at or below a ceiling.
    assert list(Classification) == [
        Classification.PUBLIC,
        Classification.INTERNAL,
        Classification.CONFIDENTIAL,
        Classification.RESTRICTED,
    ]


def test_customer_deposits_is_the_only_gl_account_that_names_an_account() -> None:
    assert [gl for gl in GlAccount if gl.holds_customer_accounts] == [GlAccount.CUSTOMER_DEPOSITS]
