"""Disputes and Transaction reviews: the requests that open them and what comes back."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from kosha_domain.lifecycles import DisputeStatus, TransactionReviewStatus
from kosha_domain.vocabulary import DisputeReason, ReviewPriority


class RaiseDispute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    txn_id: str
    reason_code: DisputeReason
    amount_paise: int | None = Field(
        default=None, gt=0, description="The disputed part; defaults to the whole Transaction."
    )


class Dispute(BaseModel):
    dispute_id: str
    txn_id: str
    txn_initiated_at: datetime
    customer_id: str
    reason_code: DisputeReason
    amount_paise: int
    status: DisputeStatus
    tat_due_at: datetime
    """When a failed debit must be put right by (RBI TAT: T+1, or T+5 for ATM and cards)."""
    compensation_paise: int
    created_by: str
    created_at: datetime


class FlagTransaction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    txn_id: str
    reason: str = Field(min_length=3, max_length=500)
    priority: ReviewPriority = ReviewPriority.NORMAL


class TransactionReview(BaseModel):
    review_id: str
    txn_id: str
    txn_initiated_at: datetime
    reason: str
    priority: ReviewPriority
    status: TransactionReviewStatus
    created_by: str
    created_at: datetime
