"""Closed vocabularies of the banking domain that are not status lifecycles."""

from enum import StrEnum


class Rail(StrEnum):
    """The payment network a Transaction travels on (see GLOSSARY: Rail)."""

    UPI = "upi"
    IMPS = "imps"
    NEFT = "neft"
    RTGS = "rtgs"
    CARD_POS = "card_pos"
    CARD_ECOM = "card_ecom"
    ATM = "atm"
    NACH = "nach"
    INTERNAL = "internal"
