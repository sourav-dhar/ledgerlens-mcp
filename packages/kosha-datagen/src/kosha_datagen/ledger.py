"""Posting rules: which GL accounts a Transaction moves, and by how much (core-api LLD §5)."""

from dataclasses import dataclass

from kosha_domain.vocabulary import Direction, GlAccount, Rail, TransactionType

GST_RATE_PERCENT = 18

_SETTLEMENT = {
    Rail.UPI: GlAccount.UPI_SETTLEMENT,
    Rail.IMPS: GlAccount.IMPS_SETTLEMENT,
    Rail.NEFT: GlAccount.NEFT_SETTLEMENT,
    Rail.RTGS: GlAccount.RTGS_SETTLEMENT,
    Rail.CARD_POS: GlAccount.CARD_SETTLEMENT,
    Rail.CARD_ECOM: GlAccount.CARD_SETTLEMENT,
    Rail.ATM: GlAccount.ATM_SETTLEMENT,
    Rail.NACH: GlAccount.NACH_SETTLEMENT,
}


@dataclass(frozen=True, slots=True)
class Leg:
    """One Posting before it has an identifier."""

    gl_account: GlAccount
    account_id: str | None
    amount_paise: int


class UnbalancedEntryError(ValueError):
    pass


def legs_for(
    *,
    account_id: str,
    direction: Direction,
    rail: Rail,
    txn_type: TransactionType,
    amount_paise: int,
    counter_account_id: str | None = None,
) -> list[Leg]:
    """The balanced Postings for a Transaction on ``account_id``.

    External rails post against their settlement account; charges split into fee income
    and GST; interest is an expense; an internal transfer moves money between two of the
    Customer's own Accounts, both sub-ledgers of customer deposits.
    """
    sign = -1 if direction is Direction.DEBIT else 1
    customer = Leg(GlAccount.CUSTOMER_DEPOSITS, account_id, sign * amount_paise)
    match txn_type:
        case TransactionType.CHARGES:
            fee = amount_paise * 100 // (100 + GST_RATE_PERCENT)
            legs = [
                customer,
                Leg(GlAccount.FEE_INCOME, None, fee),
                Leg(GlAccount.GST_PAYABLE, None, amount_paise - fee),
            ]
        case TransactionType.INTEREST_CREDIT:
            legs = [Leg(GlAccount.INTEREST_EXPENSE, None, -amount_paise), customer]
        case _ if rail is Rail.INTERNAL:
            if counter_account_id is None:
                msg = "an internal transfer needs the counter Account"
                raise ValueError(msg)
            legs = [
                customer,
                Leg(GlAccount.CUSTOMER_DEPOSITS, counter_account_id, -sign * amount_paise),
            ]
        case _:
            legs = [customer, Leg(_SETTLEMENT[rail], None, -sign * amount_paise)]
    if sum(leg.amount_paise for leg in legs) != 0:  # pragma: no cover — rules above balance
        raise UnbalancedEntryError(legs)
    return legs


def opening_legs(account_id: str, amount_paise: int) -> list[Leg]:
    """A balance brought forward when the ledger went live."""
    return [
        Leg(GlAccount.CUSTOMER_DEPOSITS, account_id, amount_paise),
        Leg(GlAccount.OPENING_BALANCES, None, -amount_paise),
    ]


def charge_with_gst(fee_paise: int) -> int:
    """A fee plus 18% GST, in paise: ₹15.00 becomes ₹17.70."""
    return fee_paise + fee_paise * GST_RATE_PERCENT // 100
