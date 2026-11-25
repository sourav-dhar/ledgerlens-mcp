"""Payments tools: account summary, transaction search and detail, spending insights.

Money stays integer paise with a display string beside it. The account number never
leaves unmasked; a counterparty's VPA needs aml:read, the Customer's own VPA kyc:pii, and a
Transaction's device and location are withheld without aml:read. Search pages through
signed cursors bound to the filters and the caller (LLD §5).
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastmcp import Client
from fastmcp.server.auth import AccessToken
from gateway_harness import FakeCoreApi, access_token, core_api_error, gateway

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
from core_api.schemas.insights import CategorySpend, MonthlySpend, SpendingInsights
from kosha_domain.ids import IdPrefix, new_id
from kosha_domain.lifecycles import AccountStatus, CardStatus, TransactionStatus
from kosha_domain.vocabulary import (
    Actor,
    CardNetwork,
    CardType,
    Channel,
    Direction,
    ModeOfOperation,
    ProductCode,
    Rail,
    TransactionType,
    VpaStatus,
)
from mcp_gateway.auth.scopes import ROLE_SCOPES, Role, Scope

pytestmark = pytest.mark.anyio

ACCOUNT_ID = new_id(IdPrefix.ACCOUNT)
CUSTOMER_ID = new_id(IdPrefix.CUSTOMER)
TXN_ID = new_id(IdPrefix.TRANSACTION)
NOW = datetime(2026, 11, 20, 9, 30, tzinfo=UTC)

ACCOUNT = f"/v1/accounts/{ACCOUNT_ID}"
SEARCH = f"{ACCOUNT}/transactions"
DETAIL_PATH = f"/v1/transactions/{TXN_ID}"
INSIGHTS_PATH = f"{ACCOUNT}/insights"

SUMMARY = AccountSummary(
    account_id=ACCOUNT_ID,
    customer_id=CUSTOMER_ID,
    account_number="77310000004321",
    ifsc="KOSH0000001",
    product_code=ProductCode.SAVINGS_REGULAR,
    status=AccountStatus.ACTIVE,
    status_reason=None,
    mode_of_operation=ModeOfOperation.SINGLE,
    opened_at=NOW - timedelta(days=400),
    closed_at=None,
    ledger_balance_paise=12_345_678,
    hold_amount_paise=50_000,
    available_balance_paise=12_295_678,
    minimum_balance_paise=1_000_000,
    interest_rate_bps=275,
    overdraft_limit_paise=0,
    nominee_registered=True,
    last_txn_at=NOW,
    cards=[
        Card(
            card_id=new_id(IdPrefix.CARD),
            network=CardNetwork.RUPAY,
            card_type=CardType.DEBIT,
            pan_last4="4242",
            status=CardStatus.ACTIVE,
            expiry_month=8,
            expiry_year=2030,
            atm_limit_paise=4_000_000,
            pos_limit_paise=10_000_000,
            ecom_limit_paise=5_000_000,
            contactless_enabled=True,
            international_enabled=False,
            issued_at=NOW - timedelta(days=400),
        )
    ],
    vpas=[
        Vpa(
            vpa_id=new_id(IdPrefix.VPA),
            vpa="9876547890@kosha",
            is_primary=True,
            status=VpaStatus.ACTIVE,
            created_at=NOW - timedelta(days=400),
        )
    ],
)
TXN = Transaction(
    txn_id=TXN_ID,
    account_id=ACCOUNT_ID,
    customer_id=CUSTOMER_ID,
    direction=Direction.DEBIT,
    amount_paise=25_000,
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
    narration="UPI/ravi.kumar@okaxis/dinner",
    remarks=None,
    initiated_at=NOW,
    posted_at=NOW,
    value_date=date(2026, 11, 20),
    balance_after_paise=12_295_678,
    risk_score=12,
    is_flagged=False,
)
DETAIL = TransactionDetail(
    **TXN.model_dump(),
    device_id="device-7f3c",
    ip_address="203.0.113.7",
    geo_lat=12.9716,
    geo_lng=77.5946,
    status_history=[
        StatusChange(
            from_status=None,
            to_status=TransactionStatus.SUCCESS,
            reason_code=None,
            actor=Actor.NPCI,
            occurred_at=NOW,
        )
    ],
)
POSITION = KeysetPosition(initiated_at=NOW, txn_id=TXN_ID)
FIRST_PAGE = TransactionPage(items=[TXN], next=POSITION)
LAST_PAGE = TransactionPage(items=[TXN], next=None)
INSIGHTS = SpendingInsights(
    account_id=ACCOUNT_ID,
    months=[
        MonthlySpend(
            month="2026-11",
            credits_paise=8_500_000,
            debits_paise=25_000,
            categories=[CategorySpend(category="dining", debits_paise=25_000, transactions=1)],
        )
    ],
)


@pytest.fixture
def core() -> FakeCoreApi:
    return FakeCoreApi(
        {
            f"GET {ACCOUNT}": SUMMARY,
            f"GET {SEARCH}": FIRST_PAGE,
            f"GET {DETAIL_PATH}": DETAIL,
            f"GET {INSIGHTS_PATH}": INSIGHTS,
        }
    )


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


# --------------------------------------------------------------- get_account_summary


@pytest.mark.parametrize("role", list(Role))
async def test_the_account_number_is_never_revealed(core: FakeCoreApi, role: Role) -> None:
    summary = await _ok(core, role, "get_account_summary", {"account_id": ACCOUNT_ID})

    assert summary["account_number"] == "XXXXXX4321"


async def test_balances_are_paise_with_a_display_string(core: FakeCoreApi) -> None:
    summary = await _ok(core, Role.SUPPORT_AGENT, "get_account_summary", {"account_id": ACCOUNT_ID})

    assert summary["available_balance_paise"] == 12_295_678
    assert summary["available_balance_display"] == "₹1,22,956.78"
    assert summary["ledger_balance_display"] == "₹1,23,456.78"
    assert summary["cards"][0]["pan_last4"] == "4242"


@pytest.mark.parametrize(
    ("role", "vpa"),
    [(Role.SUPPORT_AGENT, "98***@kosha"), (Role.COMPLIANCE_OFFICER, "9876547890@kosha")],
)
async def test_the_customers_own_vpa_is_masked_like_their_mobile(
    core: FakeCoreApi, role: Role, vpa: str
) -> None:
    summary = await _ok(core, role, "get_account_summary", {"account_id": ACCOUNT_ID})

    assert summary["vpas"][0]["vpa"] == vpa


# --------------------------------------------------------------- search_transactions


@pytest.mark.parametrize(
    ("role", "vpa"),
    [(Role.SUPPORT_AGENT, "ra***@okaxis"), (Role.ANALYST, "ravi.kumar@okaxis")],
)
async def test_a_search_masks_the_counterparty_vpa_without_aml_read(
    core: FakeCoreApi, role: Role, vpa: str
) -> None:
    page = await _ok(core, role, "search_transactions", {"account_id": ACCOUNT_ID})

    [item] = page["items"]
    assert (item["txn_id"], item["counterparty_vpa"]) == (TXN_ID, vpa)
    assert (item["amount_paise"], item["amount_display"]) == (25_000, "₹250.00")
    assert isinstance(page["next_cursor"], str)


async def test_every_filter_reaches_core_api(core: FakeCoreApi) -> None:
    await _ok(
        core,
        Role.ANALYST,
        "search_transactions",
        {
            "account_id": ACCOUNT_ID,
            "initiated_from": "2026-10-01T00:00:00+05:30",
            "initiated_before": "2026-11-01T00:00:00+05:30",
            "direction": "debit",
            "statuses": ["success", "pending"],
            "rails": ["upi"],
            "min_amount_paise": 100,
            "max_amount_paise": 500_000,
            "text": "dinner",
            "limit": 10,
        },
    )

    params = core.last.url.params
    assert params.get_list("status") == ["pending", "success"]
    assert params["initiated_from"] == "2026-10-01T00:00:00+05:30"
    assert (params["direction"], params["rail"], params["text"], params["limit"]) == (
        "debit",
        "upi",
        "dinner",
        "10",
    )
    assert (params["min_amount_paise"], params["max_amount_paise"]) == ("100", "500000")


async def test_the_next_cursor_continues_after_the_last_row(core: FakeCoreApi) -> None:
    first = await _ok(core, Role.ANALYST, "search_transactions", {"account_id": ACCOUNT_ID})
    core.route(f"GET {SEARCH}", LAST_PAGE)

    last = await _ok(
        core,
        Role.ANALYST,
        "search_transactions",
        {"account_id": ACCOUNT_ID, "cursor": first["next_cursor"]},
    )

    params = core.last.url.params
    assert (params["after_initiated_at"], params["after_txn_id"]) == (NOW.isoformat(), TXN_ID)
    assert last["next_cursor"] is None


async def test_a_cursor_only_continues_the_same_filters(core: FakeCoreApi) -> None:
    first = await _ok(core, Role.ANALYST, "search_transactions", {"account_id": ACCOUNT_ID})
    asked = len(core.requests)

    body = await _error(
        core,
        access_token(Role.ANALYST),
        "search_transactions",
        {"account_id": ACCOUNT_ID, "rails": ["neft"], "cursor": first["next_cursor"]},
    )

    assert body["code"] == "invalid_argument"
    assert "another query" in body["message"]
    assert len(core.requests) == asked, "nothing reaches core-api"


async def test_a_cursor_cannot_be_handed_to_someone_else(core: FakeCoreApi) -> None:
    first = await _ok(core, Role.ANALYST, "search_transactions", {"account_id": ACCOUNT_ID})

    body = await _error(
        core,
        access_token(Role.ANALYST, sub="staff-0099"),
        "search_transactions",
        {"account_id": ACCOUNT_ID, "cursor": first["next_cursor"]},
    )

    assert (body["code"], body["message"]) == (
        "invalid_argument",
        "the cursor was issued to someone else",
    )


async def test_a_tampered_cursor_is_an_invalid_argument(core: FakeCoreApi) -> None:
    first = await _ok(core, Role.ANALYST, "search_transactions", {"account_id": ACCOUNT_ID})
    payload, signature = first["next_cursor"].split(".")
    tampered = f"{payload[:-2]}AA.{signature}"

    body = await _error(
        core,
        access_token(Role.ANALYST),
        "search_transactions",
        {"account_id": ACCOUNT_ID, "cursor": tampered},
    )

    assert body["code"] == "invalid_argument"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ({"min_amount_paise": 500, "max_amount_paise": 100}, "min_amount_paise"),
        (
            {
                "initiated_from": "2026-11-01T00:00:00Z",
                "initiated_before": "2026-10-01T00:00:00Z",
            },
            "initiated_before",
        ),
        (
            {
                "initiated_from": "2025-01-01T00:00:00Z",
                "initiated_before": "2026-11-01T00:00:00Z",
            },
            "366 days",
        ),
    ],
)
async def test_inconsistent_criteria_never_reach_core_api(
    core: FakeCoreApi, args: dict[str, Any], message: str
) -> None:
    body = await _error(
        core, access_token(), "search_transactions", {"account_id": ACCOUNT_ID, **args}
    )

    assert body["code"] == "invalid_argument"
    assert message in body["message"]
    assert core.requests == []


@pytest.mark.parametrize(
    "args",
    [
        {"initiated_from": "2026-11-01T00:00:00"},
        {"text": "ab"},
        {"limit": 0},
        {"limit": 101},
        {"min_amount_paise": 0},
        {"statuses": ["teleported"]},
    ],
)
async def test_malformed_search_criteria_are_invalid_arguments(
    core: FakeCoreApi, args: dict[str, Any]
) -> None:
    body = await _error(
        core, access_token(), "search_transactions", {"account_id": ACCOUNT_ID, **args}
    )

    assert body["code"] == "invalid_argument"
    assert core.requests == []


# --------------------------------------------------------------- get_transaction


@pytest.mark.parametrize("role", [Role.SUPPORT_AGENT, Role.DEMO_READONLY])
async def test_device_and_location_are_withheld_without_aml_read(
    core: FakeCoreApi, role: Role
) -> None:
    detail = await _ok(core, role, "get_transaction", {"txn_id": TXN_ID})

    assert [detail[k] for k in ("device_id", "ip_address", "geo_lat", "geo_lng")] == [None] * 4
    assert detail["geo_city"] == "Bengaluru", "the city is coarse enough to keep"
    assert detail["status_history"][0]["to_status"] == "success"


async def test_an_analyst_sees_device_location_and_the_counterparty(core: FakeCoreApi) -> None:
    detail = await _ok(core, Role.ANALYST, "get_transaction", {"txn_id": TXN_ID})

    assert (detail["device_id"], detail["ip_address"]) == ("device-7f3c", "203.0.113.7")
    assert (detail["geo_lat"], detail["geo_lng"]) == (12.9716, 77.5946)
    assert detail["counterparty_vpa"] == "ravi.kumar@okaxis"


# --------------------------------------------------------------- get_spending_insights


async def test_insights_are_aggregates_with_display_amounts(core: FakeCoreApi) -> None:
    insights = await _ok(
        core, Role.SUPPORT_AGENT, "get_spending_insights", {"account_id": ACCOUNT_ID, "months": 3}
    )

    [month] = insights["months"]
    assert (month["month"], month["debits_display"], month["credits_display"]) == (
        "2026-11",
        "₹250.00",
        "₹85,000.00",
    )
    assert month["categories"][0]["debits_display"] == "₹250.00"
    assert core.last.url.params["months"] == "3"


@pytest.mark.parametrize("months", [0, 13])
async def test_insights_cover_one_to_twelve_months(core: FakeCoreApi, months: int) -> None:
    body = await _error(
        core,
        access_token(),
        "get_spending_insights",
        {"account_id": ACCOUNT_ID, "months": months},
    )

    assert body["code"] == "invalid_argument"


# --------------------------------------------------------------- failure matrix, every tool

TOOLS = [
    ("get_account_summary", {"account_id": ACCOUNT_ID}, f"GET {ACCOUNT}"),
    ("search_transactions", {"account_id": ACCOUNT_ID}, f"GET {SEARCH}"),
    ("get_transaction", {"txn_id": TXN_ID}, f"GET {DETAIL_PATH}"),
    ("get_spending_insights", {"account_id": ACCOUNT_ID}, f"GET {INSIGHTS_PATH}"),
]


@pytest.mark.parametrize(("tool", "args", "route"), TOOLS)
async def test_transactions_read_is_required(
    core: FakeCoreApi, tool: str, args: dict[str, Any], route: str
) -> None:
    scopes = ROLE_SCOPES[Role.ANALYST] - {Scope.TRANSACTIONS_READ}

    body = await _error(core, access_token(Role.ANALYST, scopes=scopes), tool, args)

    assert (body["code"], body["message"]) == (
        "forbidden",
        "the transactions:read scope is required",
    )
    assert core.requests == []


@pytest.mark.parametrize(("tool", "args", "route"), TOOLS)
async def test_a_malformed_id_never_reaches_core_api(
    core: FakeCoreApi, tool: str, args: dict[str, Any], route: str
) -> None:
    [name] = args
    body = await _error(core, access_token(), tool, {name: new_id(IdPrefix.CUSTOMER)})

    assert body["code"] == "invalid_argument"
    assert core.requests == []


@pytest.mark.parametrize(("tool", "args", "route"), TOOLS)
async def test_what_core_api_cannot_find_is_not_found(
    core: FakeCoreApi, tool: str, args: dict[str, Any], route: str
) -> None:
    core.route(route, core_api_error(404, "not_found", "not on file"))

    body = await _error(core, access_token(), tool, args)

    assert (body["code"], body["message"]) == ("not_found", "not on file")


@pytest.mark.parametrize(("tool", "args", "route"), TOOLS)
async def test_core_api_being_unavailable_is_a_dependency_failure(
    core: FakeCoreApi, tool: str, args: dict[str, Any], route: str
) -> None:
    core.route(route, core_api_error(503, "unavailable"))

    body = await _error(core, access_token(), tool, args)

    assert (body["code"], body["dependency"], body["retry_after_s"]) == (
        "dependency_unavailable",
        "core-api",
        1.0,
    )
