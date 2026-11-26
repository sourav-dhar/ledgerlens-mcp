"""Risk tools: `list_aml_alerts` and `get_aml_alert` (LLD §6).

Both need aml:read, which only investigating Roles hold. The queue is worked soonest SLA
first and pages through signed cursors over ``(sla_due_at, alert_id)``. An alert's evidence
uses the payments `Transaction` view, so it carries the same masking rules and display
amounts as a transaction search.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.server.context import Context
from pydantic import Field

from kosha_domain.lifecycles import AmlAlertStatus
from kosha_domain.vocabulary import Severity, Typology
from mcp_gateway.masking import mask
from mcp_gateway.runtime import core_api, cursors, principal
from mcp_gateway.tools.common import READ_ONLY, AlertId, CustomerId, View
from mcp_gateway.tools.payments import Transaction


class AmlAlertSummary(View):
    alert_id: str
    customer_id: str
    rule_id: str
    rule_name: str
    typology: Typology
    severity: Severity
    score: float
    status: AmlAlertStatus
    assigned_to: str | None
    sla_due_at: datetime
    created_at: datetime
    closed_at: datetime | None


class AmlRule(View):
    rule_id: str
    name: str
    typology: Typology
    severity: Severity
    params: dict[str, Any]
    """The thresholds the rule fires on, e.g. ``{"threshold_paise": ..., "window_days": 7}``."""
    enabled: bool


class AmlAlert(AmlAlertSummary):
    narrative: str | None
    disposition: str | None
    str_reference: str | None
    """Set once a Suspicious Transaction Report has been filed with FIU-IND."""
    rule: AmlRule
    triggering_transactions: list[Transaction]
    """The evidence the rule fired on, oldest first."""


class _Position(View):
    sla_due_at: datetime
    alert_id: str


class _Page(View):
    items: list[AmlAlertSummary]
    next: _Position | None


class AlertQueue(View):
    items: list[AmlAlertSummary]
    """Soonest SLA first, then by alert ID."""
    next_cursor: str | None = Field(
        description="Pass back with the same filters for the next page; null on the last."
    )


async def list_aml_alerts(
    ctx: Context,
    *,
    customer_id: CustomerId | None = None,
    statuses: list[AmlAlertStatus] | None = None,
    typologies: list[Typology] | None = None,
    assigned_to: Annotated[
        str | None, Field(max_length=128, description="A Staff member's ID.")
    ] = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 25,
    cursor: Annotated[
        str | None,
        Field(max_length=2048, description="next_cursor from the previous page."),
    ] = None,
) -> AlertQueue:
    """The AML alert queue, soonest SLA first, a page at a time.

    Each alert names the rule it fired on and its severity. To read the next page, call
    again with the same filters and the previous page's next_cursor.
    """
    caller = await principal(ctx)
    pages = cursors(ctx)
    filters: Mapping[str, Any] = {
        "customer_id": customer_id,
        "status": sorted(statuses or []),
        "typology": sorted(typologies or []),
        "assigned_to": assigned_to,
    }
    after = {} if cursor is None else pages.open(cursor, query=filters, sub=caller.sub)
    page = await core_api(ctx).get(
        caller.signed_as(),
        "/v1/aml/alerts",
        _Page,
        params={
            **filters,
            "limit": limit,
            "after_sla_due_at": after.get("sla_due_at"),
            "after_alert_id": after.get("alert_id"),
        },
    )
    next_cursor = (
        None
        if page.next is None
        else pages.issue(
            {"sla_due_at": page.next.sla_due_at.isoformat(), "alert_id": page.next.alert_id},
            query=filters,
            sub=caller.sub,
        )
    )
    return mask(AlertQueue(items=page.items, next_cursor=next_cursor), caller.scopes)


async def get_aml_alert(ctx: Context, alert_id: AlertId) -> AmlAlert:
    """One AML alert: the rule and thresholds it fired on, and the Transactions it cites."""
    caller = await principal(ctx)
    alert = await core_api(ctx).get(caller.signed_as(), f"/v1/aml/alerts/{alert_id}", AmlAlert)
    return mask(alert, caller.scopes)


def register(mcp: FastMCP) -> None:
    mcp.tool(list_aml_alerts, title="AML alert queue", annotations=READ_ONLY)
    mcp.tool(get_aml_alert, title="AML alert", annotations=READ_ONLY)
