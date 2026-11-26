"""Write tools: `raise_dispute` and `flag_transaction_for_review` (LLD §3, §6).

Each write happens only once the user has agreed to it (`mcp_gateway.confirmation`), and
carries the caller's ``idempotency_key``: core-api stores the first response under it, so a
retry, by the client or by the gateway's own core-api client, returns the original marked
``replayed`` instead of writing twice. Validation and the scope check come first, so nobody
is asked to agree to a write that would be refused.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastmcp import FastMCP
from fastmcp.server.context import Context
from mcp.types import ToolAnnotations
from mcp_types import InputRequiredResult
from pydantic import BaseModel, ConfigDict, Field, computed_field

from kosha_domain.lifecycles import DisputeStatus, TransactionReviewStatus
from kosha_domain.money import format_inr
from kosha_domain.vocabulary import DisputeReason, ReviewPriority
from mcp_gateway.confirmation import agreed
from mcp_gateway.runtime import core_api, principal
from mcp_gateway.tools.common import TransactionId, View

WRITE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

IdempotencyKey = Annotated[
    UUID,
    Field(description="A new UUID for each intended write; reuse it only to retry that write."),
]
Confirm = Annotated[
    bool,
    Field(
        description="Only for clients that cannot ask the user themselves: true once the user "
        "has agreed to this exact write. Clients that can ask always do."
    ),
]


class _RaiseDispute(BaseModel):
    model_config = ConfigDict(frozen=True)

    txn_id: str
    reason_code: DisputeReason
    amount_paise: int | None


class _FlagTransaction(BaseModel):
    model_config = ConfigDict(frozen=True)

    txn_id: str
    reason: str
    priority: ReviewPriority


class Dispute(View):
    dispute_id: str
    txn_id: str
    txn_initiated_at: datetime
    customer_id: str
    reason_code: DisputeReason
    amount_paise: int
    status: DisputeStatus
    tat_due_at: datetime
    """When a failed debit must be put right by (RBI turnaround time)."""
    compensation_paise: int
    created_by: str
    created_at: datetime
    replayed: bool = Field(
        default=False, description="True when this retry returned the dispute raised earlier."
    )

    @computed_field
    @property
    def amount_display(self) -> str:
        return format_inr(self.amount_paise)

    @computed_field
    @property
    def compensation_display(self) -> str:
        return format_inr(self.compensation_paise)


class TransactionReview(View):
    review_id: str
    txn_id: str
    txn_initiated_at: datetime
    reason: str
    priority: ReviewPriority
    status: TransactionReviewStatus
    created_by: str
    created_at: datetime
    replayed: bool = Field(
        default=False, description="True when this retry returned the review queued earlier."
    )


async def raise_dispute(
    ctx: Context,
    txn_id: TransactionId,
    *,
    reason_code: DisputeReason,
    idempotency_key: IdempotencyKey,
    amount_paise: Annotated[
        int | None,
        Field(gt=0, description="The disputed part; defaults to the whole Transaction."),
    ] = None,
    confirm: Confirm = False,
) -> Dispute | InputRequiredResult:
    """Raise a dispute on a debit, once the user agrees; due back by the RBI turnaround time.

    Pass a new idempotency_key per dispute and reuse it to retry: a retry returns the
    dispute already raised, marked replayed.
    """
    amount = "the whole amount" if amount_paise is None else format_inr(amount_paise)
    question = f"Raise a dispute on Transaction {txn_id} for {amount}, reason: {reason_code}?"
    if (ask := await agreed(ctx, question, confirm=confirm)) is not None:
        return ask
    caller = await principal(ctx)
    written = await core_api(ctx).post(
        caller.signed_as(),
        "/v1/disputes",
        _RaiseDispute(txn_id=txn_id, reason_code=reason_code, amount_paise=amount_paise),
        Dispute,
        idempotency_key=str(idempotency_key),
    )
    return written.value.model_copy(update={"replayed": written.replayed})


async def flag_transaction_for_review(
    ctx: Context,
    txn_id: TransactionId,
    *,
    reason: Annotated[str, Field(min_length=3, max_length=500)],
    idempotency_key: IdempotencyKey,
    priority: ReviewPriority = ReviewPriority.NORMAL,
    confirm: Confirm = False,
) -> TransactionReview | InputRequiredResult:
    """Flag a Transaction for review by the fraud team, once the user agrees.

    Pass a new idempotency_key per flag and reuse it to retry: a retry returns the review
    already queued, marked replayed.
    """
    question = f"Flag Transaction {txn_id} for {priority} priority review: {reason}?"
    if (ask := await agreed(ctx, question, confirm=confirm)) is not None:
        return ask
    caller = await principal(ctx)
    written = await core_api(ctx).post(
        caller.signed_as(),
        "/v1/reviews",
        _FlagTransaction(txn_id=txn_id, reason=reason, priority=priority),
        TransactionReview,
        idempotency_key=str(idempotency_key),
    )
    return written.value.model_copy(update={"replayed": written.replayed})


def register(mcp: FastMCP) -> None:
    mcp.tool(raise_dispute, title="Raise a dispute", annotations=WRITE)
    mcp.tool(flag_transaction_for_review, title="Flag a Transaction for review", annotations=WRITE)
