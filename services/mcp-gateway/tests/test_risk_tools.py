"""Risk tools: the AML alert queue and one alert with its rule and evidence.

Only Roles holding aml:read reach them. The queue pages soonest-SLA first through signed
cursors over ``(sla_due_at, alert_id)``, bound to the filters and the caller (LLD §5). An
alert's triggering Transactions use the payments view, so they carry ``amount_display`` and
the same masking rules.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastmcp import Client
from fastmcp.server.auth import AccessToken
from gateway_harness import FakeCoreApi, access_token, core_api_error, gateway

from core_api.schemas.accounts import Transaction
from core_api.schemas.aml import AmlAlert, AmlAlertPage, AmlAlertSummary, AmlRule, QueuePosition
from kosha_domain.ids import IdPrefix, new_id
from kosha_domain.lifecycles import AmlAlertStatus, TransactionStatus
from kosha_domain.vocabulary import (
    Channel,
    Direction,
    Rail,
    Severity,
    TransactionType,
    Typology,
)
from mcp_gateway.auth.scopes import ROLE_SCOPES, Role, Scope

pytestmark = pytest.mark.anyio

ALERT_ID = new_id(IdPrefix.AML_ALERT)
CUSTOMER_ID = new_id(IdPrefix.CUSTOMER)
RULE_ID = new_id(IdPrefix.AML_RULE)
DUE = datetime(2026, 11, 21, 13, 0, tzinfo=UTC)
NOW = DUE - timedelta(days=1)

QUEUE = "/v1/aml/alerts"
ALERT_PATH = f"{QUEUE}/{ALERT_ID}"

SUMMARY = AmlAlertSummary(
    alert_id=ALERT_ID,
    customer_id=CUSTOMER_ID,
    rule_id=RULE_ID,
    rule_name="Cash just below ₹10 lakh",
    typology=Typology.STRUCTURING,
    severity=Severity.HIGH,
    score=82.5,
    status=AmlAlertStatus.OPEN,
    assigned_to=None,
    sla_due_at=DUE,
    created_at=NOW,
    closed_at=None,
)
TRIGGER = Transaction(
    txn_id=new_id(IdPrefix.TRANSACTION),
    account_id=new_id(IdPrefix.ACCOUNT),
    customer_id=CUSTOMER_ID,
    direction=Direction.CREDIT,
    amount_paise=95_000_000,
    currency="INR",
    rail=Rail.UPI,
    txn_type=TransactionType.P2P,
    status=TransactionStatus.SUCCESS,
    status_reason_code=None,
    failure_reason_code=None,
    hold_reason=None,
    expected_credit_by=None,
    utr="433012345678",
    rrn=None,
    npci_txn_id=None,
    counterparty_name="Ravi Kumar",
    counterparty_vpa="ravi.kumar@okaxis",
    counterparty_account_masked=None,
    counterparty_ifsc=None,
    merchant_id=None,
    mcc=None,
    channel=Channel.MOBILE_APP,
    geo_city="Bengaluru",
    narration="UPI/ravi.kumar@okaxis/rent",
    remarks=None,
    initiated_at=NOW,
    posted_at=NOW,
    value_date=date(2026, 11, 20),
    balance_after_paise=96_000_000,
    risk_score=71,
    is_flagged=True,
)
ALERT = AmlAlert(
    **SUMMARY.model_dump(),
    narrative="Two credits just under the reporting threshold within a week",
    disposition=None,
    str_reference=None,
    rule=AmlRule(
        rule_id=RULE_ID,
        name="Cash just below ₹10 lakh",
        typology=Typology.STRUCTURING,
        severity=Severity.HIGH,
        params={"threshold_paise": 100_000_000, "window_days": 7},
        enabled=True,
    ),
    triggering_transactions=[TRIGGER],
)
FIRST_PAGE = AmlAlertPage(items=[SUMMARY], next=QueuePosition(sla_due_at=DUE, alert_id=ALERT_ID))
LAST_PAGE = AmlAlertPage(items=[SUMMARY], next=None)

INVESTIGATORS = [Role.ANALYST, Role.COMPLIANCE_OFFICER]
NOT_INVESTIGATORS = [Role.SUPPORT_AGENT, Role.DEMO_READONLY]


@pytest.fixture
def core() -> FakeCoreApi:
    return FakeCoreApi({f"GET {QUEUE}": FIRST_PAGE, f"GET {ALERT_PATH}": ALERT})


async def _call(
    core: httpx.AsyncBaseTransport, token: AccessToken | None, tool: str, args: dict[str, Any]
) -> Any:
    async with Client(gateway(core, token)) as client:
        return await client.call_tool(tool, args, raise_on_error=False)


async def _ok(
    core: FakeCoreApi, token: AccessToken | Role, tool: str, args: dict[str, Any]
) -> dict[str, Any]:
    caller = access_token(token) if isinstance(token, Role) else token
    result = await _call(core, caller, tool, args)
    assert not result.is_error, result.content
    content: dict[str, Any] = result.structured_content
    return content


async def _error(
    core: FakeCoreApi, token: AccessToken | None, tool: str, args: dict[str, Any]
) -> dict[str, Any]:
    result = await _call(core, token, tool, args)
    assert result.is_error
    body: dict[str, Any] = result.structured_content["error"]
    return body


# --------------------------------------------------------------- list_aml_alerts


@pytest.mark.parametrize("role", INVESTIGATORS)
async def test_the_queue_lists_alerts_with_their_rule_and_severity(
    core: FakeCoreApi, role: Role
) -> None:
    queue = await _ok(core, role, "list_aml_alerts", {})

    [item] = queue["items"]
    assert (item["alert_id"], item["rule_name"], item["severity"], item["score"]) == (
        ALERT_ID,
        "Cash just below ₹10 lakh",
        "high",
        82.5,
    )
    assert isinstance(queue["next_cursor"], str)


async def test_every_queue_filter_reaches_core_api(core: FakeCoreApi) -> None:
    await _ok(
        core,
        Role.ANALYST,
        "list_aml_alerts",
        {
            "customer_id": CUSTOMER_ID,
            "statuses": ["open", "escalated"],
            "typologies": ["velocity", "structuring"],
            "assigned_to": "staff-0042",
            "limit": 10,
        },
    )

    params = core.last.url.params
    assert params.get_list("status") == ["escalated", "open"]
    assert params.get_list("typology") == ["structuring", "velocity"]
    assert (params["customer_id"], params["assigned_to"], params["limit"]) == (
        CUSTOMER_ID,
        "staff-0042",
        "10",
    )
    assert "after_alert_id" not in params


async def test_the_next_cursor_continues_after_the_last_alert(core: FakeCoreApi) -> None:
    first = await _ok(core, Role.ANALYST, "list_aml_alerts", {"statuses": ["open"]})
    core.route(f"GET {QUEUE}", LAST_PAGE)

    last = await _ok(
        core,
        Role.ANALYST,
        "list_aml_alerts",
        {"statuses": ["open"], "cursor": first["next_cursor"]},
    )

    params = core.last.url.params
    assert (params["after_sla_due_at"], params["after_alert_id"]) == (DUE.isoformat(), ALERT_ID)
    assert last["next_cursor"] is None


async def test_a_queue_cursor_only_continues_the_same_filters(core: FakeCoreApi) -> None:
    first = await _ok(core, Role.ANALYST, "list_aml_alerts", {"statuses": ["open"]})
    asked = len(core.requests)

    body = await _error(
        core,
        access_token(Role.ANALYST),
        "list_aml_alerts",
        {"statuses": ["escalated"], "cursor": first["next_cursor"]},
    )

    assert body["code"] == "invalid_argument"
    assert "another query" in body["message"]
    assert len(core.requests) == asked, "nothing reaches core-api"


async def test_a_queue_cursor_cannot_be_handed_to_someone_else(core: FakeCoreApi) -> None:
    first = await _ok(core, Role.ANALYST, "list_aml_alerts", {})

    body = await _error(
        core,
        access_token(Role.COMPLIANCE_OFFICER, sub="staff-0099"),
        "list_aml_alerts",
        {"cursor": first["next_cursor"]},
    )

    assert (body["code"], body["message"]) == (
        "invalid_argument",
        "the cursor was issued to someone else",
    )


async def test_a_transaction_cursor_does_not_page_the_queue(core: FakeCoreApi) -> None:
    """Both searches sign with the same keys; the query hash keeps their cursors apart."""
    account_id = new_id(IdPrefix.ACCOUNT)
    position = {"initiated_at": NOW.isoformat(), "txn_id": TRIGGER.txn_id}
    core.route(
        f"GET /v1/accounts/{account_id}/transactions",
        httpx.Response(200, json={"items": [], "next": position}),
    )
    other = await _ok(core, Role.ANALYST, "search_transactions", {"account_id": account_id})

    body = await _error(
        core, access_token(Role.ANALYST), "list_aml_alerts", {"cursor": other["next_cursor"]}
    )

    assert body["code"] == "invalid_argument"


@pytest.mark.parametrize(
    "args",
    [
        {"customer_id": new_id(IdPrefix.ACCOUNT)},
        {"statuses": ["dismissed"]},
        {"typologies": ["smurfing"]},
        {"assigned_to": "x" * 129},
        {"limit": 0},
        {"limit": 101},
    ],
)
async def test_malformed_queue_filters_are_invalid_arguments(
    core: FakeCoreApi, args: dict[str, Any]
) -> None:
    body = await _error(core, access_token(Role.ANALYST), "list_aml_alerts", args)

    assert body["code"] == "invalid_argument"
    assert core.requests == []


# --------------------------------------------------------------- get_aml_alert


async def test_an_alert_carries_its_rule_thresholds_and_narrative(core: FakeCoreApi) -> None:
    alert = await _ok(core, Role.ANALYST, "get_aml_alert", {"alert_id": ALERT_ID})

    assert (alert["alert_id"], alert["status"], alert["typology"]) == (
        ALERT_ID,
        "open",
        "structuring",
    )
    assert alert["rule"]["params"] == {"threshold_paise": 100_000_000, "window_days": 7}
    assert alert["narrative"].startswith("Two credits")
    assert alert["str_reference"] is None


@pytest.mark.parametrize("role", INVESTIGATORS)
async def test_the_evidence_shows_amounts_and_unmasked_counterparties(
    core: FakeCoreApi, role: Role
) -> None:
    alert = await _ok(core, role, "get_aml_alert", {"alert_id": ALERT_ID})

    [txn] = alert["triggering_transactions"]
    assert (txn["txn_id"], txn["amount_display"]) == (TRIGGER.txn_id, "₹9,50,000.00")
    assert txn["counterparty_vpa"] == "ravi.kumar@okaxis", "aml:read reveals counterparties"


# --------------------------------------------------------------- failure matrix, every tool

TOOLS: list[tuple[str, dict[str, Any], str]] = [
    ("list_aml_alerts", {}, f"GET {QUEUE}"),
    ("get_aml_alert", {"alert_id": ALERT_ID}, f"GET {ALERT_PATH}"),
]


@pytest.mark.parametrize("role", NOT_INVESTIGATORS)
@pytest.mark.parametrize(("tool", "args", "route"), TOOLS)
async def test_roles_without_aml_read_are_refused(
    core: FakeCoreApi, tool: str, args: dict[str, Any], route: str, role: Role
) -> None:
    body = await _error(core, access_token(role), tool, args)

    assert (body["code"], body["message"]) == ("forbidden", "the aml:read scope is required")
    assert core.requests == []


@pytest.mark.parametrize(("tool", "args", "route"), TOOLS)
async def test_a_token_narrowed_below_aml_read_is_refused(
    core: FakeCoreApi, tool: str, args: dict[str, Any], route: str
) -> None:
    scopes = ROLE_SCOPES[Role.COMPLIANCE_OFFICER] - {Scope.AML_READ}

    body = await _error(core, access_token(Role.COMPLIANCE_OFFICER, scopes=scopes), tool, args)

    assert body["code"] == "forbidden"
    assert core.requests == []


async def test_a_malformed_alert_id_never_reaches_core_api(core: FakeCoreApi) -> None:
    body = await _error(
        core, access_token(Role.ANALYST), "get_aml_alert", {"alert_id": new_id(IdPrefix.AML_RULE)}
    )

    assert body["code"] == "invalid_argument"
    assert core.requests == []


async def test_an_alert_core_api_cannot_find_is_not_found(core: FakeCoreApi) -> None:
    core.route(f"GET {ALERT_PATH}", core_api_error(404, "not_found", "no such alert"))

    body = await _error(core, access_token(Role.ANALYST), "get_aml_alert", {"alert_id": ALERT_ID})

    assert (body["code"], body["message"]) == ("not_found", "no such alert")


@pytest.mark.parametrize(("tool", "args", "route"), TOOLS)
async def test_core_api_being_unavailable_is_a_dependency_failure(
    core: FakeCoreApi, tool: str, args: dict[str, Any], route: str
) -> None:
    core.route(route, core_api_error(503, "unavailable"))

    body = await _error(core, access_token(Role.ANALYST), tool, args)

    assert (body["code"], body["dependency"], body["retry_after_s"]) == (
        "dependency_unavailable",
        "core-api",
        1.0,
    )
