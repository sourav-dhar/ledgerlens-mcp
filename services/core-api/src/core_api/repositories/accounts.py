"""Accounts with their cards and VPAs, and the Transactions posted to them."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import LiteralString

from psycopg import sql

from core_api.db import Connection
from core_api.repositories.patterns import contains
from core_api.schemas.accounts import (
    AccountSummary,
    Card,
    KeysetPosition,
    StatusChange,
    Transaction,
    TransactionDetail,
    TransactionPage,
    Vpa,
)
from kosha_domain.lifecycles import TransactionStatus
from kosha_domain.vocabulary import Direction, Rail

_ACCOUNT = """
    SELECT account_id, customer_id, account_number, ifsc, product_code, status,
           status_reason, mode_of_operation, opened_at, closed_at, ledger_balance_paise,
           hold_amount_paise, available_balance_paise, minimum_balance_paise,
           interest_rate_bps, overdraft_limit_paise, nominee_registered, last_txn_at
    FROM core.accounts
    WHERE account_id = %s
"""

_CARDS = """
    SELECT card_id, network, card_type, pan_last4, status, expiry_month, expiry_year,
           atm_limit_paise, pos_limit_paise, ecom_limit_paise, contactless_enabled,
           international_enabled, issued_at
    FROM core.cards
    WHERE account_id = %s
    ORDER BY issued_at DESC, card_id
"""

_VPAS = """
    SELECT vpa_id, vpa, is_primary, status, created_at
    FROM core.vpas
    WHERE account_id = %s
    ORDER BY is_primary DESC, created_at, vpa_id
"""

_TRANSACTION_COLUMNS = sql.SQL("""
    txn_id, account_id, customer_id, direction, amount_paise, currency, rail, txn_type,
    status, status_reason_code, failure_reason_code, hold_reason, expected_credit_by, utr,
    rrn, npci_txn_id, counterparty_name, counterparty_vpa, counterparty_account_masked,
    counterparty_ifsc, merchant_id, mcc, channel, geo_city, narration, remarks,
    initiated_at, posted_at, value_date, balance_after_paise, risk_score, is_flagged
""")

_SEARCH = sql.SQL("""
    SELECT {columns}
    FROM core.transactions
    WHERE {conditions}
    ORDER BY initiated_at DESC, txn_id DESC
    LIMIT %(fetch)s
""")

# txn_id alone does not name a partition, so every partition's primary-key index is
# probed once; the history query then prunes to the row's own month.
_TRANSACTION = sql.SQL("""
    SELECT {columns}, device_id, host(ip_address) AS ip_address,
           geo_lat::float8 AS geo_lat, geo_lng::float8 AS geo_lng
    FROM core.transactions
    WHERE txn_id = %s
""").format(columns=_TRANSACTION_COLUMNS)

_HISTORY = """
    SELECT from_status, to_status, reason_code, actor, occurred_at
    FROM core.transaction_status_history
    WHERE txn_id = %s AND txn_initiated_at = %s
    ORDER BY occurred_at, history_id
"""


@dataclass(frozen=True, slots=True)
class TransactionSearch:
    """Validated criteria: the window is half-open, ``[initiated_from, initiated_before)``."""

    account_id: str
    initiated_from: datetime
    initiated_before: datetime | None = None
    direction: Direction | None = None
    statuses: Sequence[TransactionStatus] = ()
    rails: Sequence[Rail] = ()
    min_amount_paise: int | None = None
    max_amount_paise: int | None = None
    text: str | None = None
    after: KeysetPosition | None = None


def _conditions(search: TransactionSearch) -> tuple[list[sql.Composable], dict[str, object]]:
    # account_id plus a lower bound on initiated_at always: the timeline index serves the
    # order, and partitions older than the window are pruned.
    conditions: list[sql.Composable] = [
        sql.SQL("account_id = %(account_id)s"),
        sql.SQL("initiated_at >= %(initiated_from)s"),
    ]
    params: dict[str, object] = {
        "account_id": search.account_id,
        "initiated_from": search.initiated_from,
    }
    # Enum members go in as their values: psycopg would otherwise dump their names.
    optional: list[tuple[str, object, LiteralString]] = [
        ("initiated_before", search.initiated_before, "initiated_at < %(initiated_before)s"),
        (
            "direction",
            search.direction and search.direction.value,
            "direction::text = %(direction)s",
        ),
        (
            "statuses",
            [s.value for s in search.statuses] or None,
            "status::text = ANY(%(statuses)s)",
        ),
        ("rails", [r.value for r in search.rails] or None, "rail::text = ANY(%(rails)s)"),
        ("min_amount", search.min_amount_paise, "amount_paise >= %(min_amount)s"),
        ("max_amount", search.max_amount_paise, "amount_paise <= %(max_amount)s"),
        ("text", search.text and contains(search.text), "narration ILIKE %(text)s"),
    ]
    for name, value, condition in optional:
        if value is not None:
            conditions.append(sql.SQL(condition))
            params[name] = value
    if search.after is not None:
        conditions.append(
            sql.SQL("(initiated_at, txn_id) < (%(after_initiated_at)s, %(after_txn_id)s)")
        )
        params |= {
            "after_initiated_at": search.after.initiated_at,
            "after_txn_id": search.after.txn_id,
        }
    return conditions, params


class AccountRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    async def exists(self, account_id: str) -> bool:
        cursor = await self._conn.execute(
            "SELECT 1 AS found FROM core.accounts WHERE account_id = %s", [account_id]
        )
        return await cursor.fetchone() is not None

    async def summary(self, account_id: str) -> AccountSummary | None:
        row = await (await self._conn.execute(_ACCOUNT, [account_id])).fetchone()
        if row is None:
            return None
        cards = await (await self._conn.execute(_CARDS, [account_id])).fetchall()
        vpas = await (await self._conn.execute(_VPAS, [account_id])).fetchall()
        return AccountSummary.model_validate(
            row
            | {
                "cards": [Card.model_validate(c) for c in cards],
                "vpas": [Vpa.model_validate(v) for v in vpas],
            }
        )

    async def search(self, search: TransactionSearch, *, limit: int) -> TransactionPage:
        conditions, params = _conditions(search)
        query = _SEARCH.format(
            columns=_TRANSACTION_COLUMNS, conditions=sql.SQL(" AND ").join(conditions)
        )
        # One extra row says whether another page exists without a count(*).
        found = await (await self._conn.execute(query, params | {"fetch": limit + 1})).fetchall()
        items = [Transaction.model_validate(r) for r in found[:limit]]
        last = items[-1] if len(found) > limit else None
        return TransactionPage(
            items=items,
            next=None
            if last is None
            else KeysetPosition(initiated_at=last.initiated_at, txn_id=last.txn_id),
        )

    async def transaction(self, txn_id: str) -> TransactionDetail | None:
        row = await (await self._conn.execute(_TRANSACTION, [txn_id])).fetchone()
        if row is None:
            return None
        history = await (
            await self._conn.execute(_HISTORY, [txn_id, row["initiated_at"]])
        ).fetchall()
        return TransactionDetail.model_validate(
            row | {"status_history": [StatusChange.model_validate(h) for h in history]}
        )
