from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kosha_domain.money import format_inr, paise_from_rupees


@pytest.mark.parametrize(
    ("rupees", "paise"),
    [("0", 0), ("1", 100), ("0.01", 1), ("1234.5", 123450), ("99999.99", 9999999)],
)
def test_rupees_convert_to_exact_paise(rupees: str, paise: int) -> None:
    assert paise_from_rupees(rupees) == paise


def test_decimal_rupees_are_accepted() -> None:
    assert paise_from_rupees(Decimal("250.75")) == 25075


@pytest.mark.parametrize("rupees", ["0.001", "10.555", "1e-3"])
def test_fractions_of_a_paisa_are_rejected(rupees: str) -> None:
    with pytest.raises(ValueError, match="paisa"):
        paise_from_rupees(rupees)


@pytest.mark.parametrize("rupees", ["abc", "", "NaN", "Infinity"])
def test_non_numeric_rupees_are_rejected(rupees: str) -> None:
    with pytest.raises(ValueError, match="rupee"):
        paise_from_rupees(rupees)


def test_float_rupees_are_refused_to_prevent_rounding_errors() -> None:
    with pytest.raises(TypeError, match="float"):
        paise_from_rupees(0.1)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("paise", "text"),
    [
        (0, "₹0.00"),
        (5, "₹0.05"),
        (100, "₹1.00"),
        (99999, "₹999.99"),
        (100000, "₹1,000.00"),
        (12345678, "₹1,23,456.78"),
        (1234567890, "₹1,23,45,678.90"),
        (-250075, "-₹2,500.75"),
    ],
)
def test_amounts_render_with_indian_digit_grouping(paise: int, text: str) -> None:
    assert format_inr(paise) == text


@given(st.integers(min_value=-(10**15), max_value=10**15))
def test_formatting_round_trips_through_conversion(paise: int) -> None:
    text = format_inr(paise).replace("₹", "").replace(",", "")

    assert paise_from_rupees(text) == paise
