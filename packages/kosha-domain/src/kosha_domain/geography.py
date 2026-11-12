"""Indian states and union territories, their GST codes, and pincode-to-state resolution.

A pincode's leading digits identify the India Post circle that serves it. The table below
maps three-digit prefixes to states at the granularity synthetic addresses need: every
city the generator uses resolves correctly, and a pincode never lands in the wrong state.
Prefixes shared across a border (for example 396 for Valsad and Silvassa) resolve to the
larger state.
"""

import re
from enum import StrEnum


class IndianState(StrEnum):
    """A state or union territory, valued by its English name."""

    JAMMU_AND_KASHMIR = "Jammu and Kashmir"
    HIMACHAL_PRADESH = "Himachal Pradesh"
    PUNJAB = "Punjab"
    CHANDIGARH = "Chandigarh"
    UTTARAKHAND = "Uttarakhand"
    HARYANA = "Haryana"
    DELHI = "Delhi"
    RAJASTHAN = "Rajasthan"
    UTTAR_PRADESH = "Uttar Pradesh"
    BIHAR = "Bihar"
    SIKKIM = "Sikkim"
    ARUNACHAL_PRADESH = "Arunachal Pradesh"
    NAGALAND = "Nagaland"
    MANIPUR = "Manipur"
    MIZORAM = "Mizoram"
    TRIPURA = "Tripura"
    MEGHALAYA = "Meghalaya"
    ASSAM = "Assam"
    WEST_BENGAL = "West Bengal"
    JHARKHAND = "Jharkhand"
    ODISHA = "Odisha"
    CHHATTISGARH = "Chhattisgarh"
    MADHYA_PRADESH = "Madhya Pradesh"
    GUJARAT = "Gujarat"
    DADRA_NAGAR_HAVELI_AND_DAMAN_DIU = "Dadra and Nagar Haveli and Daman and Diu"
    MAHARASHTRA = "Maharashtra"
    KARNATAKA = "Karnataka"
    GOA = "Goa"
    LAKSHADWEEP = "Lakshadweep"
    KERALA = "Kerala"
    TAMIL_NADU = "Tamil Nadu"
    PUDUCHERRY = "Puducherry"
    ANDAMAN_AND_NICOBAR_ISLANDS = "Andaman and Nicobar Islands"
    TELANGANA = "Telangana"
    ANDHRA_PRADESH = "Andhra Pradesh"
    LADAKH = "Ladakh"

    @property
    def gst_code(self) -> str:
        """The two-digit state code that opens every GSTIN registered in this state."""
        return _GST_CODES[self]


_S = IndianState

_GST_CODES: dict[IndianState, str] = {
    _S.JAMMU_AND_KASHMIR: "01",
    _S.HIMACHAL_PRADESH: "02",
    _S.PUNJAB: "03",
    _S.CHANDIGARH: "04",
    _S.UTTARAKHAND: "05",
    _S.HARYANA: "06",
    _S.DELHI: "07",
    _S.RAJASTHAN: "08",
    _S.UTTAR_PRADESH: "09",
    _S.BIHAR: "10",
    _S.SIKKIM: "11",
    _S.ARUNACHAL_PRADESH: "12",
    _S.NAGALAND: "13",
    _S.MANIPUR: "14",
    _S.MIZORAM: "15",
    _S.TRIPURA: "16",
    _S.MEGHALAYA: "17",
    _S.ASSAM: "18",
    _S.WEST_BENGAL: "19",
    _S.JHARKHAND: "20",
    _S.ODISHA: "21",
    _S.CHHATTISGARH: "22",
    _S.MADHYA_PRADESH: "23",
    _S.GUJARAT: "24",
    _S.DADRA_NAGAR_HAVELI_AND_DAMAN_DIU: "26",
    _S.MAHARASHTRA: "27",
    _S.KARNATAKA: "29",
    _S.GOA: "30",
    _S.LAKSHADWEEP: "31",
    _S.KERALA: "32",
    _S.TAMIL_NADU: "33",
    _S.PUDUCHERRY: "34",
    _S.ANDAMAN_AND_NICOBAR_ISLANDS: "35",
    _S.TELANGANA: "36",
    _S.ANDHRA_PRADESH: "37",
    _S.LADAKH: "38",
}

GST_STATE_CODES: frozenset[str] = frozenset(_GST_CODES.values())

# (first prefix, last prefix, state) over the pincode's first three digits.
# The first matching row wins, so enclaves are listed before the ranges that contain them.
_PINCODE_PREFIXES: tuple[tuple[int, int, IndianState], ...] = (
    (160, 160, _S.CHANDIGARH),
    (194, 194, _S.LADAKH),
    (246, 246, _S.UTTARAKHAND),
    (248, 249, _S.UTTARAKHAND),
    (262, 263, _S.UTTARAKHAND),
    (403, 403, _S.GOA),
    (605, 605, _S.PUDUCHERRY),
    (737, 737, _S.SIKKIM),
    (744, 744, _S.ANDAMAN_AND_NICOBAR_ISLANDS),
    (790, 792, _S.ARUNACHAL_PRADESH),
    (793, 794, _S.MEGHALAYA),
    (795, 795, _S.MANIPUR),
    (796, 796, _S.MIZORAM),
    (797, 798, _S.NAGALAND),
    (799, 799, _S.TRIPURA),
    (814, 816, _S.JHARKHAND),
    (822, 822, _S.JHARKHAND),
    (825, 835, _S.JHARKHAND),
    (110, 110, _S.DELHI),
    (120, 136, _S.HARYANA),
    (140, 159, _S.PUNJAB),
    (171, 177, _S.HIMACHAL_PRADESH),
    (180, 193, _S.JAMMU_AND_KASHMIR),
    (200, 285, _S.UTTAR_PRADESH),
    (301, 345, _S.RAJASTHAN),
    (360, 396, _S.GUJARAT),
    (400, 445, _S.MAHARASHTRA),
    (450, 488, _S.MADHYA_PRADESH),
    (490, 497, _S.CHHATTISGARH),
    (500, 509, _S.TELANGANA),
    (515, 535, _S.ANDHRA_PRADESH),
    (560, 591, _S.KARNATAKA),
    (600, 643, _S.TAMIL_NADU),
    (670, 695, _S.KERALA),
    (700, 743, _S.WEST_BENGAL),
    (751, 770, _S.ODISHA),
    (781, 788, _S.ASSAM),
    (800, 855, _S.BIHAR),
)

# Civilian pincodes start 1-8; 9 is reserved for the Army Postal Service.
_PINCODE = re.compile(r"[1-8]\d{5}")


def state_for_pincode(pincode: str) -> IndianState | None:
    """The state a civilian pincode belongs to, or None if it is malformed or unassigned."""
    if not _PINCODE.fullmatch(pincode):
        return None
    prefix = int(pincode[:3])
    return next((state for lo, hi, state in _PINCODE_PREFIXES if lo <= prefix <= hi), None)


def is_valid_pincode(pincode: str) -> bool:
    return state_for_pincode(pincode) is not None
