"""Banking reference numbers in the shapes real systems issue.

Numbers that must be unique (CIF, mobile, account number) come from an affine bijection
of the row's index rather than from chance, so uniqueness holds at any scale without
bookkeeping. Everything else draws from the caller's seeded random stream.
"""

import hashlib
import random
import string
from datetime import UTC, datetime, timedelta

from kosha_domain.geography import IndianState
from kosha_domain.validators import gstin_check_character

IST = timedelta(hours=5, minutes=30)
_UPPER = string.ascii_uppercase
_HEX = "0123456789abcdef"
# Public /16 blocks of large Indian ISPs, so IP addresses geolocate to India.
_ISP_BLOCKS = ("49.36", "106.51", "117.96", "122.161", "157.32", "182.70", "223.181")


def _scramble(index: int, digits: int, multiplier: int, offset: int) -> int:
    """A bijection on ``[0, 10**digits)``; the multiplier must be coprime to 10."""
    return (index * multiplier + offset) % 10**digits


def cif_number(customer_index: int) -> str:
    return f"3{_scramble(customer_index, 9, 7_919_317, 104_729):09d}"


def mobile(customer_index: int, rng: random.Random) -> str:
    return f"{rng.choice('6789')}{_scramble(customer_index, 9, 48_271_021, 39_916_801):09d}"


def account_number(customer_index: int, slot: int) -> str:
    """A 14-digit Kosha account number; each Customer has up to eight slots."""
    return f"7731{_scramble(customer_index * 8 + slot, 10, 2_654_435_761, 1_013_904_223):010d}"


def digits(rng: random.Random, count: int) -> str:
    return "".join(rng.choice(string.digits) for _ in range(count))


def hex_token(rng: random.Random, count: int) -> str:
    return "".join(rng.choice(_HEX) for _ in range(count))


def pan(rng: random.Random, holder_type: str, name: str) -> str:
    """A PAN such as ``ABCPS1234D``: holder type 4th, name initial 5th."""
    letters = "".join(rng.choice(_UPPER) for _ in range(3))
    return f"{letters}{holder_type}{name[0].upper()}{digits(rng, 4)}{rng.choice(_UPPER)}"


def gstin(rng: random.Random, state: IndianState, legal_name: str) -> str:
    """A GSTIN for a business in ``state``: its PAN, entity number 1, ``Z``, check character."""
    body = f"{state.gst_code}{pan(rng, rng.choice('CF'), legal_name)}1Z"
    return body + gstin_check_character(body)


def ifsc(rng: random.Random, bank_code: str) -> str:
    return f"{bank_code}0{digits(rng, 6)}"


def rrn(rng: random.Random, at: datetime) -> str:
    """12 digits: year digit, Julian day and hour in IST, then a six-digit sequence."""
    local = at.astimezone(UTC) + IST
    return f"{local.year % 10}{local.timetuple().tm_yday:03d}{local.hour:02d}{digits(rng, 6)}"


def neft_utr(rng: random.Random, bank_code: str, at: datetime) -> str:
    local = at.astimezone(UTC) + IST
    return f"{bank_code}N{local.year % 10}{local.timetuple().tm_yday:03d}{digits(rng, 7)}"


def rtgs_utr(rng: random.Random, bank_code: str, at: datetime) -> str:
    local = at.astimezone(UTC) + IST
    return f"{bank_code}R{rng.choice('CH')}{local:%Y%m%d}{digits(rng, 8)}"


def npci_txn_id(rng: random.Random) -> str:
    return f"KOS{hex_token(rng, 32).upper()}"


def ckyc_number(rng: random.Random) -> str:
    return f"{rng.randint(1, 9)}{digits(rng, 13)}"


def ip_address(rng: random.Random) -> str:
    return f"{rng.choice(_ISP_BLOCKS)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


def masked(account_number: str) -> str:
    return "X" * (len(account_number) - 4) + account_number[-4:]


def sha256_of(*parts: object) -> str:
    return hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()
