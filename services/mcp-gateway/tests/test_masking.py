"""Personal data is masked by a pure function of the payload and the caller's scopes (LLD §7).

A view model declares how each sensitive field is masked, and which scope reveals it, in
the field's type; `mask` applies the declarations to any model, nested ones included.
"""

from typing import Any, cast

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel, ConfigDict

from mcp_gateway.auth.scopes import ROLE_SCOPES, Role, Scope
from mcp_gateway.masking import (
    Aadhaar,
    AccountNumber,
    BirthDate,
    CounterpartyVpa,
    Email,
    Mobile,
    Pan,
    mask,
    masked_fields,
)

NONE: frozenset[Scope] = frozenset()


class Contact(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    mobile: Mobile
    email: Email | None
    date_of_birth: BirthDate


class Holder(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_number: AccountNumber
    pan: Pan | None
    aadhaar: Aadhaar | None
    counterparty_vpa: CounterpartyVpa | None
    contacts: list[Contact]


RAVI = Contact(
    name="Ravi Kumar",
    mobile="9876547890",
    email="ravi.kumar@example.com",
    date_of_birth="1987-04-12",
)
HOLDER = Holder(
    account_number="77310000004321",
    pan="ABCPE1234X",
    aadhaar="1234",
    counterparty_vpa="ravi.kumar@okaxis",
    contacts=[RAVI],
)


def test_without_scopes_every_rule_applies() -> None:
    masked = mask(HOLDER, NONE)

    assert masked.model_dump() == {
        "account_number": "XXXXXX4321",
        "pan": "******234X",
        "aadhaar": "XXXX XXXX 1234",
        "counterparty_vpa": "ra***@okaxis",
        "contacts": [
            {
                "name": "Ravi Kumar",
                "mobile": "******7890",
                "email": "r****@example.com",
                "date_of_birth": "1987",
            }
        ],
    }


def test_kyc_pii_reveals_contact_details_and_the_pan_but_never_aadhaar_or_the_account() -> None:
    masked = mask(HOLDER, {Scope.KYC_PII})

    assert masked.contacts == [RAVI]
    assert masked.pan == "ABCPE1234X"
    assert (masked.aadhaar, masked.account_number) == ("XXXX XXXX 1234", "XXXXXX4321")
    assert masked.counterparty_vpa == "ra***@okaxis"


def test_aml_read_reveals_the_counterparty_vpa() -> None:
    masked = mask(HOLDER, {Scope.AML_READ})

    assert masked.counterparty_vpa == "ravi.kumar@okaxis"
    assert masked.contacts[0].mobile == "******7890"


def test_absent_values_stay_absent() -> None:
    empty = Holder(
        account_number="77310000004321",
        pan=None,
        aadhaar=None,
        counterparty_vpa=None,
        contacts=[RAVI.model_copy(update={"email": None})],
    )

    masked = mask(empty, NONE)

    assert (masked.pan, masked.aadhaar, masked.counterparty_vpa) == (None, None, None)
    assert masked.contacts[0].email is None


def test_masking_leaves_the_input_untouched() -> None:
    mask(HOLDER, NONE)

    assert HOLDER.contacts[0].mobile == "9876547890"


@pytest.mark.parametrize(
    ("email", "masked"),
    [("a@b.in", "a****@b.in"), ("no-at-sign", "****"), ("first@last@kosha.in", "f****@kosha.in")],
)
def test_odd_emails_still_hide_the_local_part(email: str, masked: str) -> None:
    contact = RAVI.model_copy(update={"email": email})

    assert mask(contact, NONE).email == masked


def test_a_vpa_without_a_handle_separator_is_hidden_entirely() -> None:
    holder = HOLDER.model_copy(update={"counterparty_vpa": "not-a-vpa"})

    assert mask(holder, NONE).counterparty_vpa == "***"


def test_masked_fields_lists_each_rule_by_field_name() -> None:
    rules = masked_fields(Contact)

    assert set(rules) == {"mobile", "email", "date_of_birth"}
    assert rules["mobile"].unless is Scope.KYC_PII


# --------------------------------------------------------------- properties

digits = st.text(alphabet="0123456789", min_size=4, max_size=16)
handles = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789._-", min_size=1, max_size=20)


def _address(handle: str, host: str) -> str:
    return f"{handle}@{host}"


emails = st.builds(_address, handles, handles.map(lambda host: f"{host}.in"))
contacts = st.builds(
    Contact,
    name=st.text(max_size=20),
    mobile=digits,
    email=st.none() | emails,
    date_of_birth=st.dates().map(lambda d: d.isoformat()),
)
holders = st.builds(
    Holder,
    account_number=digits,
    pan=st.none() | st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=10),
    aadhaar=st.none() | digits,
    counterparty_vpa=st.none() | st.builds(_address, handles, handles),
    contacts=st.lists(contacts, max_size=3),
)


def _revealed(original: BaseModel, masked: BaseModel, scopes: frozenset[Scope]) -> None:
    """Every field is either revealed by a held scope or exactly its masked form."""
    rules = masked_fields(type(original))
    for name in type(original).model_fields:
        before: Any = getattr(original, name)
        after: Any = getattr(masked, name)
        if name in rules and before is not None:
            rule = rules[name]
            expected = before if rule.unless in scopes else rule.style(before)
            assert after == expected, name
        elif isinstance(before, list):
            pairs = zip(cast("list[BaseModel]", before), after, strict=True)
            for nested_before, nested_after in pairs:
                _revealed(nested_before, nested_after, scopes)
        else:
            assert after == before, name


@given(holder=holders, role=st.sampled_from(Role))
def test_no_role_sees_a_field_its_scopes_do_not_reveal(holder: Holder, role: Role) -> None:
    scopes = ROLE_SCOPES[role]

    _revealed(holder, mask(holder, scopes), scopes)


@given(holder=holders, scopes=st.frozensets(st.sampled_from(Scope)))
def test_masking_twice_changes_nothing_more(holder: Holder, scopes: frozenset[Scope]) -> None:
    once = mask(holder, scopes)

    assert mask(once, scopes) == once


@given(number=digits)
def test_numbers_reveal_at_most_their_last_four_digits(number: str) -> None:
    holder = HOLDER.model_copy(update={"account_number": number, "aadhaar": number, "pan": number})

    masked = mask(holder, frozenset(Scope) - {Scope.KYC_PII})

    for shown in (masked.account_number, masked.aadhaar, masked.pan):
        assert shown is not None
        assert shown.endswith(number[-4:])
        assert sum(c.isdigit() for c in shown) <= 4
