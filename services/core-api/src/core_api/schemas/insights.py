"""Spending insights: aggregates only, so nothing in them needs masking."""

from pydantic import BaseModel


class CategorySpend(BaseModel):
    category: str
    """The merchant's category, or the Transaction's purpose when there is no merchant."""
    debits_paise: int
    transactions: int


class MonthlySpend(BaseModel):
    month: str
    """A Kolkata calendar month, ``YYYY-MM``."""
    credits_paise: int
    debits_paise: int
    categories: list[CategorySpend]
    """Debits by category, largest first."""


class SpendingInsights(BaseModel):
    account_id: str
    months: list[MonthlySpend]
    """Oldest first, ending with the current month; quiet months are present as zeros."""
