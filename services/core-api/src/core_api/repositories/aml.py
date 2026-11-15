"""AML alerts, the rules that raised them and the Transactions they cite."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import LiteralString

from psycopg import sql

from core_api.db import Connection
from core_api.repositories.accounts import TRANSACTION_COLUMNS
from core_api.schemas.accounts import Transaction
from core_api.schemas.aml import AmlAlert, AmlAlertPage, AmlAlertSummary, AmlRule, QueuePosition
from kosha_domain.lifecycles import AmlAlertStatus
from kosha_domain.vocabulary import Typology

_SUMMARY_COLUMNS = sql.SQL("""
    a.alert_id, a.customer_id, a.rule_id, r.name AS rule_name, a.typology, r.severity,
    a.score::float8 AS score, a.status, a.assigned_to, a.sla_due_at, a.created_at, a.closed_at
""")

# The queue order matches aml_alerts_queue_idx (status, sla_due_at) when filtered by status.
_QUEUE = sql.SQL("""
    SELECT {columns}
    FROM risk.aml_alerts a
    JOIN risk.aml_rules r USING (rule_id, typology)
    WHERE {conditions}
    ORDER BY a.sla_due_at, a.alert_id
    LIMIT %(fetch)s
""")

_ALERT = sql.SQL("""
    SELECT {columns}, a.narrative, a.disposition, a.str_reference, a.triggering_txn_ids,
           r.params, r.enabled
    FROM risk.aml_alerts a
    JOIN risk.aml_rules r USING (rule_id, typology)
    WHERE a.alert_id = %s
""").format(columns=_SUMMARY_COLUMNS)

# customer_id is the alert's own: an alert can only cite its Customer's Transactions.
_EVIDENCE = sql.SQL("""
    SELECT {columns}
    FROM core.transactions
    WHERE customer_id = %s AND txn_id = ANY(%s)
    ORDER BY initiated_at, txn_id
""").format(columns=TRANSACTION_COLUMNS)


@dataclass(frozen=True, slots=True)
class AlertQueueQuery:
    customer_id: str | None = None
    statuses: Sequence[AmlAlertStatus] = ()
    typologies: Sequence[Typology] = ()
    assigned_to: str | None = None
    after: QueuePosition | None = None


def _conditions(query: AlertQueueQuery) -> tuple[list[sql.Composable], dict[str, object]]:
    conditions: list[sql.Composable] = [sql.SQL("true")]
    params: dict[str, object] = {}
    optional: list[tuple[str, object, LiteralString]] = [
        ("customer_id", query.customer_id, "a.customer_id = %(customer_id)s"),
        (
            "statuses",
            [s.value for s in query.statuses] or None,
            "a.status::text = ANY(%(statuses)s)",
        ),
        (
            "typologies",
            [t.value for t in query.typologies] or None,
            "a.typology::text = ANY(%(typologies)s)",
        ),
        ("assigned_to", query.assigned_to, "a.assigned_to = %(assigned_to)s"),
    ]
    for name, value, condition in optional:
        if value is not None:
            conditions.append(sql.SQL(condition))
            params[name] = value
    if query.after is not None:
        conditions.append(sql.SQL("(a.sla_due_at, a.alert_id) > (%(after_at)s, %(after_id)s)"))
        params |= {"after_at": query.after.sla_due_at, "after_id": query.after.alert_id}
    return conditions, params


class AmlRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    async def queue(self, query: AlertQueueQuery, *, limit: int) -> AmlAlertPage:
        conditions, params = _conditions(query)
        statement = _QUEUE.format(
            columns=_SUMMARY_COLUMNS, conditions=sql.SQL(" AND ").join(conditions)
        )
        found = await (
            await self._conn.execute(statement, params | {"fetch": limit + 1})
        ).fetchall()
        items = [AmlAlertSummary.model_validate(r) for r in found[:limit]]
        last = items[-1] if len(found) > limit else None
        return AmlAlertPage(
            items=items,
            next=None
            if last is None
            else QueuePosition(sla_due_at=last.sla_due_at, alert_id=last.alert_id),
        )

    async def alert(self, alert_id: str) -> AmlAlert | None:
        row = await (await self._conn.execute(_ALERT, [alert_id])).fetchone()
        if row is None:
            return None
        evidence = await (
            await self._conn.execute(_EVIDENCE, [row["customer_id"], row["triggering_txn_ids"]])
        ).fetchall()
        rule = AmlRule(
            rule_id=row["rule_id"],
            name=row["rule_name"],
            typology=row["typology"],
            severity=row["severity"],
            params=row["params"],
            enabled=row["enabled"],
        )
        return AmlAlert.model_validate(
            row
            | {
                "rule": rule,
                "triggering_transactions": [Transaction.model_validate(t) for t in evidence],
            }
        )
