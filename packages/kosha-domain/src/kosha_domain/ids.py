"""Prefixed ULID identifiers such as ``txn_01JC3W4Q8Z9X7V5T3R1N0M2K4P``.

A ULID is 48 bits of millisecond timestamp followed by 80 random bits, written in Crockford
base32. IDs therefore sort by creation time, cannot be guessed, and the prefix names the
entity in any log line. The synthetic data generator passes its own clock and seeded RNG so
that a given ``--seed`` reproduces every identifier.
"""

import random
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DECODE = {char: value for value, char in enumerate(_ALPHABET)}
_ULID_LENGTH = 26
_TIME_LENGTH = 10
_RANDOM_BITS = 80
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MILLISECOND = timedelta(milliseconds=1)


class IdPrefix(StrEnum):
    """The entity an identifier names."""

    CUSTOMER = "cus"
    ADDRESS = "adr"
    ACCOUNT = "acc"
    CARD = "crd"
    VPA = "vpa"
    BENEFICIARY = "ben"
    MERCHANT = "mer"
    TRANSACTION = "txn"
    TRANSACTION_STATUS_CHANGE = "tsh"
    JOURNAL_ENTRY = "jrn"
    POSTING = "pst"
    KYC_PROFILE = "kyc"
    KYC_DOCUMENT = "kdc"
    KYC_EVENT = "kev"
    AML_RULE = "rul"
    AML_ALERT = "alr"
    SCREENING = "scr"
    DISPUTE = "dsp"
    TRANSACTION_REVIEW = "rev"
    OUTBOX_EVENT = "evt"
    AUDIT_RECORD = "aud"
    DOCUMENT = "doc"
    CHUNK = "chk"


@dataclass(frozen=True, slots=True)
class ParsedId:
    prefix: IdPrefix
    issued_at: datetime


def new_id(
    prefix: IdPrefix, *, at: datetime | None = None, rng: random.Random | None = None
) -> str:
    """Mint an identifier.

    Args:
        prefix: the entity type.
        at: creation instant (timezone-aware); defaults to now.
        rng: source of the 80 random bits; defaults to the OS CSPRNG. Pass a seeded
            ``random.Random`` only for reproducible synthetic data.
    """
    if at is None:
        at = datetime.now(UTC)
    elif at.tzinfo is None:
        msg = "identifier timestamps must be timezone-aware"
        raise ValueError(msg)
    millis = (at - _EPOCH) // _MILLISECOND
    entropy = rng.getrandbits(_RANDOM_BITS) if rng else secrets.randbits(_RANDOM_BITS)
    return f"{prefix}_{_encode((millis << _RANDOM_BITS) | entropy)}"


def parse_id(value: str) -> ParsedId:
    """Split an identifier into its prefix and creation instant.

    Raises:
        ValueError: if ``value`` is not a well-formed prefixed ULID.
    """
    prefix, sep, ulid = value.partition("_")
    if (
        not sep
        or prefix not in IdPrefix._value2member_map_
        or len(ulid) != _ULID_LENGTH
        or any(char not in _DECODE for char in ulid)
        or _DECODE[ulid[0]] > 7  # noqa: PLR2004 — 26 chars carry 130 bits; only 128 are used
    ):
        msg = f"not a Kosha identifier: {value!r}"
        raise ValueError(msg)
    millis = _decode(ulid[:_TIME_LENGTH])
    return ParsedId(IdPrefix(prefix), _EPOCH + millis * _MILLISECOND)


def is_valid_id(value: str, prefix: IdPrefix | None = None) -> bool:
    """Whether ``value`` is a well-formed identifier, optionally of a specific entity type."""
    try:
        parsed = parse_id(value)
    except ValueError:
        return False
    return prefix is None or parsed.prefix is prefix


def _encode(number: int) -> str:
    chars = [""] * _ULID_LENGTH
    for i in reversed(range(_ULID_LENGTH)):
        number, digit = divmod(number, 32)
        chars[i] = _ALPHABET[digit]
    return "".join(chars)


def _decode(text: str) -> int:
    number = 0
    for char in text:
        number = number * 32 + _DECODE[char]
    return number
