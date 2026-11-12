import pytest

from kosha_domain.validators import (
    gstin_check_character,
    is_valid_gstin,
    is_valid_ifsc,
    is_valid_mobile,
    is_valid_pan,
    is_valid_rrn,
    is_valid_utr,
    is_valid_vpa,
)
from kosha_domain.vocabulary import Rail

# ---------------------------------------------------------------- PAN


@pytest.mark.parametrize("pan", ["ABCPS1234D", "AAACI1234F", "BBBHK0001Z", "AAATG9999A"])
def test_well_formed_pans_are_valid(pan: str) -> None:
    assert is_valid_pan(pan)


@pytest.mark.parametrize(
    "pan",
    [
        "ABCXS1234D",  # X is not a holder type
        "abcps1234d",
        "ABCPS12345",
        "ABCPS123D",
        "1BCPS1234D",
        "",
    ],
)
def test_malformed_pans_are_invalid(pan: str) -> None:
    assert not is_valid_pan(pan)


def test_individual_pan_fifth_character_is_the_surname_initial() -> None:
    assert is_valid_pan("ABCPS1234D", surname="Sharma")
    assert not is_valid_pan("ABCPS1234D", surname="Verma")


# ---------------------------------------------------------------- IFSC


@pytest.mark.parametrize("ifsc", ["KOSH0000001", "SBIN0001234", "HDFC0ABC123"])
def test_well_formed_ifscs_are_valid(ifsc: str) -> None:
    assert is_valid_ifsc(ifsc)


@pytest.mark.parametrize("ifsc", ["SBIN1001234", "SBI00001234", "sbin0001234", "SBIN000123"])
def test_malformed_ifscs_are_invalid(ifsc: str) -> None:
    assert not is_valid_ifsc(ifsc)


# ---------------------------------------------------------------- UPI VPA


@pytest.mark.parametrize("vpa", ["ravi.k@kosha", "9876543210@ybl", "meera_iyer-22@okaxis"])
def test_well_formed_vpas_are_valid(vpa: str) -> None:
    assert is_valid_vpa(vpa)


@pytest.mark.parametrize(
    "vpa",
    ["ravi@", "@kosha", "ravi k@kosha", "ravi@@kosha", "ravi@ko sha", "r@kosha", "ravi@1bank"],
)
def test_malformed_vpas_are_invalid(vpa: str) -> None:
    assert not is_valid_vpa(vpa)


# ---------------------------------------------------------------- RRN: UPI, IMPS and card


def test_rrn_is_year_digit_julian_day_hour_and_sequence() -> None:
    assert is_valid_rrn("412312345678")  # 2024, day 123, 12:xx, sequence 345678


@pytest.mark.parametrize(
    "rrn",
    [
        "400012000001",  # day 000
        "436712000001",  # day 367
        "412325000001",  # hour 25
        "41231200000",  # 11 digits
        "41231200000A",
    ],
)
def test_malformed_rrns_are_invalid(rrn: str) -> None:
    assert not is_valid_rrn(rrn)


# ---------------------------------------------------------------- UTR


@pytest.mark.parametrize(
    ("utr", "rail"),
    [
        ("KOSHN61231234567", Rail.NEFT),  # bank, N, year digit, day 123, sequence
        ("KOSHR52026061500123456", Rail.RTGS),  # bank, R, channel, 2026-06-15, sequence
        ("612312345678", Rail.IMPS),  # IMPS references are RRN-shaped
    ],
)
def test_well_formed_utrs_are_valid(utr: str, rail: Rail) -> None:
    assert is_valid_utr(utr, rail)


@pytest.mark.parametrize(
    ("utr", "rail"),
    [
        ("KOSHR61231234567", Rail.NEFT),  # R marks RTGS
        ("KOSHN60001234567", Rail.NEFT),  # day 000
        ("KOSHR52026023000123456", Rail.RTGS),  # 30 February
        ("KOSHN61231234567", Rail.RTGS),  # NEFT shape on the RTGS rail
        ("61231234567", Rail.IMPS),
    ],
)
def test_malformed_utrs_are_invalid(utr: str, rail: Rail) -> None:
    assert not is_valid_utr(utr, rail)


@pytest.mark.parametrize("rail", [Rail.UPI, Rail.CARD_POS, Rail.ATM, Rail.INTERNAL])
def test_rails_without_utrs_are_refused(rail: Rail) -> None:
    with pytest.raises(ValueError, match="UTR"):
        is_valid_utr("KOSHN61231234567", rail)


# ---------------------------------------------------------------- GSTIN

PUBLISHED_GSTIN = "27AAPFU0939F1ZV"  # widely published worked example


def test_check_character_matches_a_published_gstin() -> None:
    assert gstin_check_character(PUBLISHED_GSTIN[:14]) == PUBLISHED_GSTIN[14]


def test_published_gstin_is_valid() -> None:
    assert is_valid_gstin(PUBLISHED_GSTIN)


@pytest.mark.parametrize(
    "gstin",
    [
        "27AAPFU0939F1ZW",  # wrong check character
        "27AAPFU0939F2ZV",  # entity digit changed, checksum no longer matches
        "28AAPFU0939F1ZV",  # state changed, checksum no longer matches
        "27AAPFU0939F1YV",  # 14th character must be Z
        "27aapfu0939f1zv",
        "27AAPFU0939F1Z",
    ],
)
def test_corrupted_gstins_are_invalid(gstin: str) -> None:
    assert not is_valid_gstin(gstin)


def test_gstin_needs_a_real_state_code() -> None:
    body = "99AAPFU0939F1Z"
    assert not is_valid_gstin(body + gstin_check_character(body))


def test_gstin_needs_a_well_formed_embedded_pan() -> None:
    body = "27AAPXU0939F1Z"  # X is not a PAN holder type
    assert not is_valid_gstin(body + gstin_check_character(body))


def test_check_character_rejects_malformed_bodies() -> None:
    with pytest.raises(ValueError, match="GSTIN"):
        gstin_check_character("27aapfu0939f1z")


# ---------------------------------------------------------------- mobile


@pytest.mark.parametrize("mobile", ["9876543210", "6000000000", "7012345678", "8123456789"])
def test_indian_mobile_numbers_are_valid(mobile: str) -> None:
    assert is_valid_mobile(mobile)


@pytest.mark.parametrize("mobile", ["5876543210", "987654321", "98765432100", "+919876543210"])
def test_other_numbers_are_invalid(mobile: str) -> None:
    assert not is_valid_mobile(mobile)
