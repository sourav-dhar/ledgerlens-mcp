"""Write tools: raise a dispute, flag a Transaction for review.

A write happens only once the user has agreed to it (LLD §3). A client that can ask its user
is asked through MCP elicitation, in either protocol era: on 2025-era connections the gateway
sends ``elicitation/create``; on 2026-07-28 connections the tool answers ``input_required`` and
the client calls again with the user's answer. Only a client that cannot ask its user may pass
``confirm: true`` instead. Every write carries the caller's ``idempotency_key``, so a retry
returns the original rather than writing twice.

Over the deployed transport (stateless HTTP) a 2025-era client's capabilities, sent once at
``initialize``, are unknown to later requests, so such a client confirms with ``confirm``.
"""

import json
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import httpx
import httpx2
import pytest
from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server.auth import AccessToken
from gateway_harness import SETTINGS, FakeCoreApi, access_token, core_api_error, gateway

from core_api.schemas.cases import Dispute, TransactionReview
from kosha_domain.ids import IdPrefix, new_id
from kosha_domain.lifecycles import DisputeStatus, TransactionReviewStatus
from kosha_domain.vocabulary import DisputeReason, ReviewPriority
from mcp_gateway.app import serve_http
from mcp_gateway.auth.scopes import Role

pytestmark = pytest.mark.anyio

TXN_ID = new_id(IdPrefix.TRANSACTION)
NOW = datetime(2026, 11, 20, 9, 30, tzinfo=UTC)
KEY = str(uuid4())

DISPUTE = Dispute(
    dispute_id=new_id(IdPrefix.DISPUTE),
    txn_id=TXN_ID,
    txn_initiated_at=NOW,
    customer_id=new_id(IdPrefix.CUSTOMER),
    reason_code=DisputeReason.FAILED_BUT_DEBITED,
    amount_paise=25_000,
    status=DisputeStatus.RAISED,
    tat_due_at=NOW + timedelta(days=1),
    compensation_paise=10_000,
    created_by="staff-0042",
    created_at=NOW,
)
REVIEW = TransactionReview(
    review_id=new_id(IdPrefix.TRANSACTION_REVIEW),
    txn_id=TXN_ID,
    txn_initiated_at=NOW,
    reason="Five round-amount credits from new payees in an hour",
    priority=ReviewPriority.HIGH,
    status=TransactionReviewStatus.QUEUED,
    created_by="staff-0042",
    created_at=NOW,
)

DISPUTES = "POST /v1/disputes"
REVIEWS = "POST /v1/reviews"
RAISE = {"txn_id": TXN_ID, "reason_code": "failed_but_debited", "idempotency_key": KEY}
FLAG = {
    "txn_id": TXN_ID,
    "reason": "Five round-amount credits from new payees in an hour",
    "priority": "high",
    "idempotency_key": KEY,
}
LEGACY, MODERN = "legacy", "2026-07-28"
ERAS = [LEGACY, MODERN]

type Answer = Literal["yes", "no", "decline", "cancel"]


class User:
    """The person behind an MCP client: answers its confirmation prompts and remembers them."""

    def __init__(self, answer: Answer = "yes") -> None:
        self.answer: Answer = answer
        self.prompts: list[str] = []

    async def __call__(self, message: str, *_: Any) -> ElicitResult[dict[str, bool]]:
        self.prompts.append(message)
        match self.answer:
            case "yes" | "no":
                return ElicitResult(action="accept", content={"value": self.answer == "yes"})
            case "decline" | "cancel":
                return ElicitResult(action=self.answer)


@pytest.fixture
def core() -> FakeCoreApi:
    return FakeCoreApi(
        {
            DISPUTES: httpx.Response(201, content=DISPUTE.model_dump_json().encode()),
            REVIEWS: httpx.Response(201, content=REVIEW.model_dump_json().encode()),
        }
    )


async def _call(
    core: FakeCoreApi,
    tool: str,
    args: dict[str, Any],
    *,
    token: AccessToken | Role = Role.COMPLIANCE_OFFICER,
    user: User | None = None,
    era: str = MODERN,
) -> Any:
    caller = access_token(token) if isinstance(token, Role) else token
    async with Client(gateway(core, caller), elicitation_handler=user, mode=era) as client:
        return await client.call_tool(tool, args, raise_on_error=False)


async def _ok(core: FakeCoreApi, tool: str, args: dict[str, Any], **how: Any) -> dict[str, Any]:
    result = await _call(core, tool, args, **how)
    assert not result.is_error, result.content
    content: dict[str, Any] = result.structured_content
    return content


async def _error(core: FakeCoreApi, tool: str, args: dict[str, Any], **how: Any) -> dict[str, Any]:
    result = await _call(core, tool, args, **how)
    assert result.is_error
    body: dict[str, Any] = result.structured_content["error"]
    return body


def _writes(core: FakeCoreApi) -> Sequence[httpx.Request]:
    return [r for r in core.requests if r.method == "POST"]


# --------------------------------------------------------------- the user agrees


@pytest.mark.parametrize("era", ERAS)
async def test_a_dispute_is_raised_once_the_user_agrees(core: FakeCoreApi, era: str) -> None:
    user = User("yes")

    dispute = await _ok(
        core, "raise_dispute", {**RAISE, "amount_paise": 25_000}, user=user, era=era
    )

    [prompt] = user.prompts
    assert TXN_ID in prompt
    assert "₹250.00" in prompt
    [write] = _writes(core)
    assert write.headers["Idempotency-Key"] == KEY
    assert (dispute["dispute_id"], dispute["status"], dispute["replayed"]) == (
        DISPUTE.dispute_id,
        "raised",
        False,
    )
    assert (dispute["amount_display"], dispute["compensation_display"]) == ("₹250.00", "₹100.00")


@pytest.mark.parametrize("era", ERAS)
async def test_a_transaction_is_flagged_once_the_user_agrees(core: FakeCoreApi, era: str) -> None:
    user = User("yes")

    review = await _ok(
        core, "flag_transaction_for_review", FLAG, token=Role.ANALYST, user=user, era=era
    )

    [prompt] = user.prompts
    assert TXN_ID in prompt
    assert "high" in prompt
    [write] = _writes(core)
    assert write.headers["Idempotency-Key"] == KEY
    assert (review["review_id"], review["status"], review["replayed"]) == (
        REVIEW.review_id,
        "queued",
        False,
    )


async def test_the_body_core_api_receives_is_the_request(core: FakeCoreApi) -> None:
    await _ok(core, "raise_dispute", RAISE, user=User("yes"))
    await _ok(core, "flag_transaction_for_review", FLAG, user=User("yes"))

    dispute, review = (json.loads(r.content) for r in _writes(core))
    assert dispute == {"txn_id": TXN_ID, "reason_code": "failed_but_debited", "amount_paise": None}
    assert review == {"txn_id": TXN_ID, "reason": FLAG["reason"], "priority": "high"}


# --------------------------------------------------------------- the user does not agree


@pytest.mark.parametrize("era", ERAS)
@pytest.mark.parametrize("answer", ["no", "decline", "cancel"])
@pytest.mark.parametrize(
    ("tool", "args"), [("raise_dispute", RAISE), ("flag_transaction_for_review", FLAG)]
)
async def test_nothing_is_written_unless_the_user_agrees(
    core: FakeCoreApi, era: str, answer: Answer, tool: str, args: dict[str, Any]
) -> None:
    user = User(answer)

    body = await _error(core, tool, args, user=user, era=era)

    assert body["code"] == "declined"
    assert "nothing was written" in body["message"]
    assert len(user.prompts) == 1
    assert _writes(core) == []


@pytest.mark.parametrize("era", ERAS)
async def test_confirm_does_not_skip_a_clients_own_prompt(core: FakeCoreApi, era: str) -> None:
    """A model sets ``confirm``; only the client's prompt reaches the person."""
    user = User("decline")

    body = await _error(core, "raise_dispute", {**RAISE, "confirm": True}, user=user, era=era)

    assert body["code"] == "declined"
    assert len(user.prompts) == 1
    assert _writes(core) == []


# --------------------------------------------------------------- clients that cannot ask


@pytest.mark.parametrize("era", ERAS)
async def test_a_client_that_cannot_ask_must_pass_confirm(core: FakeCoreApi, era: str) -> None:
    body = await _error(core, "raise_dispute", RAISE, era=era)

    assert body["code"] == "invalid_argument"
    assert "confirm: true" in body["message"]
    assert _writes(core) == []


@pytest.mark.parametrize("era", ERAS)
async def test_confirm_true_writes_for_a_client_that_cannot_ask(
    core: FakeCoreApi, era: str
) -> None:
    dispute = await _ok(core, "raise_dispute", {**RAISE, "confirm": True}, era=era)

    assert dispute["dispute_id"] == DISPUTE.dispute_id
    assert len(_writes(core)) == 1


# --------------------------------------------------------------- idempotency


async def test_a_retried_write_returns_the_original_marked_replayed(core: FakeCoreApi) -> None:
    core.route(
        DISPUTES,
        httpx.Response(
            200,
            content=DISPUTE.model_dump_json().encode(),
            headers={"Idempotent-Replayed": "true"},
        ),
    )

    dispute = await _ok(core, "raise_dispute", RAISE, user=User("yes"))

    assert (dispute["dispute_id"], dispute["replayed"]) == (DISPUTE.dispute_id, True)


async def test_a_key_reused_for_another_write_is_a_conflict(core: FakeCoreApi) -> None:
    core.route(DISPUTES, core_api_error(409, "conflict", "the key was used for another request"))

    body = await _error(core, "raise_dispute", RAISE, user=User("yes"))

    assert (body["code"], body["message"]) == ("conflict", "the key was used for another request")


async def test_a_transaction_core_api_cannot_find_is_not_found(core: FakeCoreApi) -> None:
    core.route(REVIEWS, core_api_error(404, "not_found", f"transaction {TXN_ID} not found"))

    body = await _error(core, "flag_transaction_for_review", FLAG, user=User("yes"))

    assert body["code"] == "not_found"


async def test_core_api_being_unavailable_is_a_dependency_failure(core: FakeCoreApi) -> None:
    core.route(DISPUTES, core_api_error(503, "unavailable"))

    body = await _error(core, "raise_dispute", RAISE, user=User("yes"))

    assert (body["code"], body["dependency"]) == ("dependency_unavailable", "core-api")
    assert {r.headers["Idempotency-Key"] for r in _writes(core)} == {KEY}, "retried, same key"


# --------------------------------------------------------------- refused before anyone is asked


@pytest.mark.parametrize(
    ("tool", "args", "role", "scope"),
    [
        ("raise_dispute", RAISE, Role.ANALYST, "disputes:write"),
        ("raise_dispute", RAISE, Role.DEMO_READONLY, "disputes:write"),
        ("flag_transaction_for_review", FLAG, Role.SUPPORT_AGENT, "reviews:write"),
        ("flag_transaction_for_review", FLAG, Role.DEMO_READONLY, "reviews:write"),
    ],
)
async def test_roles_without_the_write_scope_are_refused_before_anyone_is_asked(
    core: FakeCoreApi, tool: str, args: dict[str, Any], role: Role, scope: str
) -> None:
    user = User("yes")

    body = await _error(core, tool, args, token=role, user=user)

    assert (body["code"], body["message"]) == ("forbidden", f"the {scope} scope is required")
    assert (user.prompts, core.requests) == ([], [])


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("raise_dispute", {**RAISE, "idempotency_key": "retry-1"}),
        ("raise_dispute", {k: v for k, v in RAISE.items() if k != "idempotency_key"}),
        ("raise_dispute", {**RAISE, "amount_paise": 0}),
        ("raise_dispute", {**RAISE, "reason_code": "changed_my_mind"}),
        ("raise_dispute", {**RAISE, "txn_id": new_id(IdPrefix.ACCOUNT)}),
        ("flag_transaction_for_review", {**FLAG, "reason": "no"}),
        ("flag_transaction_for_review", {**FLAG, "priority": "whenever"}),
    ],
)
async def test_malformed_writes_are_refused_before_anyone_is_asked(
    core: FakeCoreApi, tool: str, args: dict[str, Any]
) -> None:
    user = User("yes")

    body = await _error(core, tool, args, user=user)

    assert body["code"] == "invalid_argument"
    assert (user.prompts, core.requests) == ([], [])


# --------------------------------------------------------------- over the deployed transport

type Deployed = Callable[[User | None, str], Client[StreamableHttpTransport]]


@pytest.fixture
async def deployed(core: FakeCoreApi) -> AsyncIterator[Deployed]:
    """Clients of the gateway as deployed: stateless Streamable HTTP with JSON responses."""
    app = serve_http(gateway(core, access_token(Role.COMPLIANCE_OFFICER)), SETTINGS)

    def in_memory(
        headers: dict[str, str] | None = None,
        timeout: httpx2.Timeout | None = None,
        auth: httpx2.Auth | None = None,
        *,
        follow_redirects: bool = False,
    ) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            headers=headers,
            timeout=timeout,
            auth=auth,
            follow_redirects=follow_redirects,
        )

    def client(user: User | None, era: str) -> Client[StreamableHttpTransport]:
        url = f"http://gateway{SETTINGS.mcp_path}"
        transport = StreamableHttpTransport(url, httpx_client_factory=in_memory)
        return Client(transport, elicitation_handler=user, mode=era)

    async with app.router.lifespan_context(app):
        yield client


async def test_a_2026_client_is_asked_over_the_deployed_transport(
    core: FakeCoreApi, deployed: Deployed
) -> None:
    user = User("yes")

    async with deployed(user, MODERN) as client:
        result = await client.call_tool("raise_dispute", RAISE, raise_on_error=False)

    assert not result.is_error, result.content
    assert len(user.prompts) == 1
    assert len(_writes(core)) == 1


async def test_a_2025_client_confirms_with_confirm_over_the_deployed_transport(
    core: FakeCoreApi, deployed: Deployed
) -> None:
    user = User("yes")

    async with deployed(user, LEGACY) as client:
        unconfirmed = await client.call_tool("raise_dispute", RAISE, raise_on_error=False)
        confirmed = await client.call_tool(
            "raise_dispute", {**RAISE, "confirm": True}, raise_on_error=False
        )

    assert unconfirmed.is_error
    assert unconfirmed.structured_content is not None
    assert unconfirmed.structured_content["error"]["code"] == "invalid_argument"
    assert not confirmed.is_error, confirmed.content
    assert user.prompts == [], "nothing is sent that the stateless transport cannot deliver"
    assert len(_writes(core)) == 1
