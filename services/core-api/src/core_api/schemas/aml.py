"""AML alerts as the API returns them: the analyst's queue and one alert's evidence."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from core_api.schemas.accounts import Transaction
from kosha_domain.lifecycles import AmlAlertStatus
from kosha_domain.vocabulary import Severity, Typology


class AmlAlertSummary(BaseModel):
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


class QueuePosition(BaseModel):
    """The last alert of a page; pass it back as ``after_*`` to read the next one."""

    sla_due_at: datetime
    alert_id: str


class AmlAlertPage(BaseModel):
    items: list[AmlAlertSummary]
    """Soonest SLA first, then by ``alert_id``."""
    next: QueuePosition | None


class AmlRule(BaseModel):
    rule_id: str
    name: str
    typology: Typology
    severity: Severity
    params: dict[str, Any]
    """The thresholds the rule fired on, e.g. ``{"threshold_paise": ..., "window_days": 7}``."""
    enabled: bool


class AmlAlert(AmlAlertSummary):
    narrative: str | None
    disposition: str | None
    str_reference: str | None
    """Set once a Suspicious Transaction Report has been filed with FIU-IND."""
    rule: AmlRule
    triggering_transactions: list[Transaction]
    """The evidence the rule fired on, oldest first."""
