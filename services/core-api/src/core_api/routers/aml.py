"""`/v1/aml/alerts`: the analyst's alert queue and one alert with its evidence."""

from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from core_api.deps import CallerDep, DatabaseDep, checked_id, require
from core_api.errors import InvalidArgumentError, NotFoundError
from core_api.repositories.aml import AlertQueueQuery, AmlRepository
from core_api.schemas.aml import AmlAlert, AmlAlertPage, QueuePosition
from kosha_domain.ids import IdPrefix
from kosha_domain.lifecycles import AmlAlertStatus
from kosha_domain.vocabulary import Typology

router = APIRouter(prefix="/v1/aml/alerts", tags=["aml"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"description": "Invalid argument"},
    503: {"description": "Database unavailable; retry shortly"},
    504: {"description": "Deadline exceeded"},
}


def _position(at: AwareDatetime | None, alert_id: str | None) -> QueuePosition | None:
    if (at is None) != (alert_id is None):
        msg = "after_sla_due_at and after_alert_id go together"
        raise InvalidArgumentError(msg)
    if at is None or alert_id is None:
        return None
    checked_id(alert_id, IdPrefix.AML_ALERT, name="after_alert_id")
    return QueuePosition(sla_due_at=at, alert_id=alert_id)


@router.get("", summary="List AML alerts", responses=_ERRORS)
async def list_aml_alerts(  # noqa: PLR0917 — one parameter per filter
    caller: CallerDep,
    database: DatabaseDep,
    customer_id: str | None = None,
    status: Annotated[list[AmlAlertStatus] | None, Query()] = None,
    typology: Annotated[list[Typology] | None, Query()] = None,
    assigned_to: Annotated[str | None, Query(max_length=128)] = None,
    after_sla_due_at: Annotated[
        AwareDatetime | None, Query(description="From the previous page's `next`.")
    ] = None,
    after_alert_id: Annotated[
        str | None, Query(description="From the previous page's `next`.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AmlAlertPage:
    """Alerts soonest-SLA first, a page at a time, with each rule's name and severity."""
    if customer_id is not None:
        checked_id(customer_id, IdPrefix.CUSTOMER, name="customer_id")
    query = AlertQueueQuery(
        customer_id=customer_id,
        statuses=status or (),
        typologies=typology or (),
        assigned_to=assigned_to,
        after=_position(after_sla_due_at, after_alert_id),
    )
    async with require(database).unit_of_work(caller, read_only=True) as conn:
        return await AmlRepository(conn).queue(query, limit=limit)


@router.get(
    "/{alert_id}",
    summary="Get an AML alert",
    responses={**_ERRORS, 404: {"description": "No such alert"}},
)
async def get_aml_alert(alert_id: str, caller: CallerDep, database: DatabaseDep) -> AmlAlert:
    """The alert, the rule and thresholds it fired on, and the Transactions it cites."""
    checked_id(alert_id, IdPrefix.AML_ALERT, name="alert_id")
    async with require(database).unit_of_work(caller, read_only=True) as conn:
        alert = await AmlRepository(conn).alert(alert_id)
    if alert is None:
        msg = f"AML alert {alert_id} not found"
        raise NotFoundError(msg)
    return alert
