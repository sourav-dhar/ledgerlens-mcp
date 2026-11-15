"""AML alerts are worked as a queue by SLA, and read with their rule and evidence."""

from datetime import UTC, datetime, timedelta
from typing import Any

import db_rows as rows
import psycopg
import pytest
from httpx import AsyncClient

from kosha_domain.ids import IdPrefix, new_id

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

NOW = datetime.now(UTC).replace(microsecond=0)


async def _alert_ids(api: AsyncClient, **params: Any) -> list[str]:
    response = await api.get("/v1/aml/alerts", params=params)
    assert response.status_code == 200, response.text
    return [a["alert_id"] for a in response.json()["items"]]


async def test_the_queue_orders_by_sla_and_filters_by_customer_status_and_typology(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    customer_id = rows.customer(committed)
    rule_id = rows.aml_rule(committed)
    velocity = rows.aml_rule(committed, typology="velocity", severity="medium")
    late = rows.aml_alert(committed, customer_id, rule_id, sla_due_at=NOW + timedelta(days=3))
    soon = rows.aml_alert(committed, customer_id, rule_id, sla_due_at=NOW + timedelta(hours=4))
    closed = rows.aml_alert(
        committed,
        customer_id,
        rule_id,
        status="closed_false_positive",
        closed_at=NOW,
        sla_due_at=NOW - timedelta(days=1),
    )
    fast = rows.aml_alert(
        committed, customer_id, velocity, typology="velocity", sla_due_at=NOW + timedelta(days=1)
    )

    assert await _alert_ids(api, customer_id=customer_id) == [closed, soon, fast, late]
    assert await _alert_ids(api, customer_id=customer_id, status=["open"]) == [soon, fast, late]
    assert await _alert_ids(api, customer_id=customer_id, typology=["velocity"]) == [fast]


async def test_queue_items_carry_the_rules_name_and_severity(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    customer_id = rows.customer(committed)
    rule_id = rows.aml_rule(committed, name="Cash just below ₹10 lakh", severity="critical")
    rows.aml_alert(committed, customer_id, rule_id)

    item = (await api.get("/v1/aml/alerts", params={"customer_id": customer_id})).json()["items"][0]

    assert (item["rule_name"], item["severity"], item["score"]) == (
        "Cash just below ₹10 lakh",
        "critical",
        82.5,
    )


async def test_pages_walk_the_queue_exactly_once(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    customer_id = rows.customer(committed)
    rule_id = rows.aml_rule(committed)
    due = NOW + timedelta(hours=1)
    made = [rows.aml_alert(committed, customer_id, rule_id, sla_due_at=due) for _ in range(3)]
    made.append(rows.aml_alert(committed, customer_id, rule_id, sla_due_at=due + timedelta(1)))

    seen: list[str] = []
    params: dict[str, Any] = {"customer_id": customer_id, "limit": 2}
    while True:
        page = (await api.get("/v1/aml/alerts", params=params)).json()
        seen += [a["alert_id"] for a in page["items"]]
        if page["next"] is None:
            break
        params |= {
            "after_sla_due_at": page["next"]["sla_due_at"],
            "after_alert_id": page["next"]["alert_id"],
        }

    assert seen == [*sorted(made[:3]), made[3]]


async def test_an_alert_carries_its_rule_and_triggering_transactions(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    customer_id = rows.customer(committed)
    account_id = rows.account(committed, customer_id)
    triggers = [
        rows.transaction(
            committed,
            account_id,
            customer_id,
            amount_paise=950_000_00,
            initiated_at=NOW - timedelta(days=d),
        )[0]
        for d in (3, 1)
    ]
    rule_id = rows.aml_rule(committed)
    alert_id = rows.aml_alert(
        committed,
        customer_id,
        rule_id,
        triggering_txn_ids=triggers,
        narrative="Two cash deposits just under the reporting threshold",
    )

    response = await api.get(f"/v1/aml/alerts/{alert_id}")

    assert response.status_code == 200
    body = response.json()
    assert (body["alert_id"], body["typology"], body["status"]) == (alert_id, "structuring", "open")
    assert (body["rule"]["rule_id"], body["rule"]["params"]["window_days"]) == (rule_id, 7)
    assert [t["txn_id"] for t in body["triggering_transactions"]] == triggers


async def test_an_unknown_alert_is_not_found(api: AsyncClient) -> None:
    response = await api.get(f"/v1/aml/alerts/{new_id(IdPrefix.AML_ALERT)}")

    assert response.status_code == 404
