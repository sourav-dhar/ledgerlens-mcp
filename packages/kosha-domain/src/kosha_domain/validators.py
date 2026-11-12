"""Format validators for Indian banking identifiers.

Each check accepts exactly the shapes real systems issue, so synthetic data cannot be told
apart from real data by format alone. Where a structure is a market convention rather than
a published standard (NEFT and RTGS UTRs), the docstring says so.
"""

import re
from datetime import date

from kosha_domain.geography import GST_STATE_CODES
from kosha_domain.vocabulary import Rail

_DAYS_IN_LEAP_YEAR = 366
_HOURS_IN_DAY = 24

# PAN: 3 letters, holder type, name initial, 4 digits, check letter. Holder types:
# P person, C company, H HUF, F firm, A AOP, T trust, B BOI, L local authority,
# J artificial juridical person, G government.
_PAN = re.compile(r"[A-Z]{3}[ABCFGHLJPT][A-Z]\d{4}[A-Z]")
_IFSC = re.compile(r"[A-Z]{4}0[A-Z0-9]{6}")
_VPA = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{1,255}@[A-Za-z][A-Za-z0-9]{1,63}")
_MOBILE = re.compile(r"[6-9]\d{9}")
_RRN = re.compile(r"\d{12}")
_NEFT_UTR = re.compile(r"[A-Z]{4}N\d{11}")
_RTGS_UTR = re.compile(r"[A-Z]{4}R[A-Z0-9]\d{16}")
_GSTIN = re.compile(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]")
_GSTIN_BODY = re.compile(r"[0-9A-Z]{14}")
_BASE36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def is_valid_pan(pan: str, *, surname: str | None = None) -> bool:
    """A Permanent Account Number such as ``ABCPS1234D``.

    Args:
        surname: when given, the fifth character must be its initial (for individuals the
            surname; for other holders the first letter of the entity name).
    """
    if not _PAN.fullmatch(pan):
        return False
    return surname is None or pan[4] == surname[:1].upper()


def is_valid_ifsc(ifsc: str) -> bool:
    """An Indian Financial System Code: bank code, a literal ``0``, then the branch code."""
    return _IFSC.fullmatch(ifsc) is not None


def is_valid_vpa(vpa: str) -> bool:
    """A UPI virtual payment address such as ``ravi.k@kosha``."""
    return _VPA.fullmatch(vpa) is not None


def is_valid_mobile(mobile: str) -> bool:
    """A ten-digit Indian mobile number as stored (no ``+91``), starting 6-9."""
    return _MOBILE.fullmatch(mobile) is not None


def is_valid_rrn(rrn: str) -> bool:
    """A 12-digit retrieval reference number: ``Y DDD HH nnnnnn``.

    Last digit of the year, Julian day (001-366), hour (00-23), then a six-digit sequence.
    UPI, IMPS and card switches all issue references in this shape.
    """
    if not _RRN.fullmatch(rrn):
        return False
    return 1 <= int(rrn[1:4]) <= _DAYS_IN_LEAP_YEAR and int(rrn[4:6]) < _HOURS_IN_DAY


def is_valid_utr(utr: str, rail: Rail) -> bool:
    """A Unique Transaction Reference for an IMPS, NEFT or RTGS Transaction.

    Conventional shapes (banks follow them; RBI does not publish one):

    - NEFT, 16 characters: bank code, ``N``, year digit, Julian day, 7-digit sequence.
    - RTGS, 22 characters: bank code, ``R``, channel, ``YYYYMMDD``, 8-digit sequence.
    - IMPS: the 12-digit RRN.

    Raises:
        ValueError: for rails that do not assign UTRs (UPI and cards use RRNs).
    """
    match rail:
        case Rail.NEFT:
            return _NEFT_UTR.fullmatch(utr) is not None and 1 <= int(utr[6:9]) <= _DAYS_IN_LEAP_YEAR
        case Rail.RTGS:
            return _RTGS_UTR.fullmatch(utr) is not None and _is_calendar_date(utr[6:14])
        case Rail.IMPS:
            return is_valid_rrn(utr)
        case _:
            msg = f"{rail.value} transactions carry no UTR"
            raise ValueError(msg)


def gstin_check_character(body: str) -> str:
    """The 15th character of a GSTIN, computed from its first 14 (mod-36 checksum).

    Raises:
        ValueError: if ``body`` is not 14 uppercase alphanumerics.
    """
    if not _GSTIN_BODY.fullmatch(body):
        msg = f"not a GSTIN body: {body!r}"
        raise ValueError(msg)
    total = 0
    for position, char in enumerate(body):
        product = _BASE36.index(char) * (2 if position % 2 else 1)
        total += product // 36 + product % 36
    return _BASE36[(36 - total % 36) % 36]


def is_valid_gstin(gstin: str) -> bool:
    """A Goods and Services Tax Identification Number such as ``27AAPFU0939F1ZV``.

    State code, the holder's PAN, entity number, a literal ``Z``, then the check character.
    """
    return (
        _GSTIN.fullmatch(gstin) is not None
        and gstin[:2] in GST_STATE_CODES
        and is_valid_pan(gstin[2:12])
        and gstin_check_character(gstin[:14]) == gstin[14]
    )


def _is_calendar_date(yyyymmdd: str) -> bool:
    try:
        date(int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:]))
    except ValueError:
        return False
    return True
