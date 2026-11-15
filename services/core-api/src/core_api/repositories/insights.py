"""Monthly totals of an Account's posted Transactions, by direction and category."""

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from core_api.db import Connection
from core_api.schemas.insights import CategorySpend, MonthlySpend

# A statement month is a local idea: a debit at 00:30 IST on the 1st belongs to the new
# month although it is still the previous day in UTC. This is the one place core-api
# buckets by IST; storage and every other value stay UTC.
KOLKATA = ZoneInfo("Asia/Kolkata")

# Only posted Transactions moved money. The lower bound prunes older monthly partitions.
_TOTALS = """
    SELECT to_char(date_trunc('month', t.initiated_at AT TIME ZONE 'Asia/Kolkata'), 'YYYY-MM')
               AS month,
           t.direction::text AS direction,
           coalesce(m.category, t.txn_type::text) AS category,
           sum(t.amount_paise)::bigint AS amount_paise,
           count(*)::integer AS transactions
    FROM core.transactions t
    LEFT JOIN core.merchants m ON m.merchant_id = t.merchant_id
    WHERE t.account_id = %(account_id)s
      AND t.initiated_at >= %(since)s
      AND t.posted_at IS NOT NULL
    GROUP BY 1, 2, 3
"""


def month_starts(now: datetime, months: int) -> list[datetime]:
    """The first instant of each of the last ``months`` Kolkata months, oldest first."""
    start = now.astimezone(KOLKATA).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    starts = [start]
    for _ in range(months - 1):
        previous = starts[-1]
        if previous.month == 1:
            starts.append(previous.replace(year=previous.year - 1, month=12))
        else:
            starts.append(previous.replace(month=previous.month - 1))
    return starts[::-1]


class InsightsRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    async def monthly(self, account_id: str, starts: list[datetime]) -> list[MonthlySpend]:
        rows = await (
            await self._conn.execute(_TOTALS, {"account_id": account_id, "since": starts[0]})
        ).fetchall()
        credits_paise: dict[str, int] = defaultdict(int)
        debits: dict[str, list[CategorySpend]] = defaultdict(list)
        for row in rows:
            if row["direction"] == "credit":
                credits_paise[row["month"]] += row["amount_paise"]
            else:
                debits[row["month"]].append(
                    CategorySpend(
                        category=row["category"],
                        debits_paise=row["amount_paise"],
                        transactions=row["transactions"],
                    )
                )
        result: list[MonthlySpend] = []
        for start in starts:
            label = start.strftime("%Y-%m")
            categories = sorted(debits[label], key=lambda c: (-c.debits_paise, c.category))
            result.append(
                MonthlySpend(
                    month=label,
                    credits_paise=credits_paise[label],
                    debits_paise=sum(c.debits_paise for c in categories),
                    categories=categories,
                )
            )
        return result
