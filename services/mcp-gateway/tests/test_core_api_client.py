"""The gateway's client for core-api: signed requests, mapped errors, same-key retries.

Signing is proven against the real core-api app (ADR 0013): without a database it answers
a correctly signed request with `503`, and anything it cannot verify with `401`. Failures
the app cannot produce without a database are scripted with `httpx.MockTransport`.
"""

import json
from collections.abc import AsyncIterator, Callable
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel, SecretStr
from signed import TEST_KEY

from core_api.app import create_app
from core_api.settings import Settings as CoreApiSettings
from kosha_domain.ids import IdPrefix, new_id
from kosha_domain.signing import ACTOR, KB_CEILING, SIGNATURE, Principal
from kosha_domain.vocabulary import Classification
from mcp_gateway.clients.core_api import CORE_API, CoreApi
from mcp_gateway.errors import (
    ConflictError,
    DeadlineExceededError,
    DependencyUnavailableError,
    GatewayError,
    InternalError,
    InvalidArgumentError,
    NotFoundError,
)

pytestmark = pytest.mark.anyio

STAFF = Principal(actor="staff-0042", kb_ceiling=Classification.INTERNAL)
KEY = TEST_KEY.encode()


class Thing(BaseModel):
    thing_id: str


class NewThing(BaseModel):
    name: str


type Handler = Callable[[httpx.Request], httpx.Response]


def _api(handler: Handler, *, key: bytes = KEY, attempts: int = 2) -> CoreApi:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://core-api")
    return CoreApi(http, signing_key=key, attempts=attempts, backoff_s=0)


def _error(status: int, code: str, message: str = "said core-api") -> httpx.Response:
    headers = {"Retry-After": "1"} if status == 503 else {}
    return httpx.Response(
        status, json={"error": {"code": code, "message": message}}, headers=headers
    )


class Script:
    """A transport that answers from a list, one response per request, and keeps them."""

    def __init__(self, *outcomes: httpx.Response | Exception) -> None:
        self._outcomes = list(outcomes)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        outcome = self._outcomes.pop(0) if len(self._outcomes) > 1 else self._outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


# --------------------------------------------------------------- against the real core-api


@pytest.fixture
async def core_app() -> AsyncIterator[FastAPI]:
    """core-api without a database: a request it can verify reaches the handler, then 503."""
    app = create_app(CoreApiSettings(internal_signing_keys=SecretStr(TEST_KEY)))
    async with app.router.lifespan_context(app):
        yield app


def _real(app: FastAPI, *, key: bytes = KEY) -> CoreApi:
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://core-api")
    return CoreApi(http, signing_key=key, backoff_s=0)


async def test_core_api_verifies_the_signature(core_app: FastAPI) -> None:
    api = _real(core_app)

    with pytest.raises(DependencyUnavailableError) as raised:
        await api.get(STAFF, f"/v1/customers/{new_id(IdPrefix.CUSTOMER)}", Thing)

    assert (raised.value.dependency, raised.value.retry_after_s) == (CORE_API, 1.0)


async def test_the_final_encoded_query_is_what_gets_signed(core_app: FastAPI) -> None:
    api = _real(core_app)

    with pytest.raises(DependencyUnavailableError):
        await api.get(STAFF, "/v1/customers", Thing, params={"name": "Zoë D'Souza & co"})


async def test_a_signature_core_api_rejects_is_internal_not_the_callers_fault(
    core_app: FastAPI,
) -> None:
    api = _real(core_app, key=b"another-key-that-core-api-never-saw!")

    with pytest.raises(InternalError):
        await api.get(STAFF, f"/v1/customers/{new_id(IdPrefix.CUSTOMER)}", Thing)


async def test_core_apis_own_validation_message_reaches_the_caller(core_app: FastAPI) -> None:
    api = _real(core_app)

    with pytest.raises(InvalidArgumentError) as raised:
        await api.get(STAFF, "/v1/customers/cus_123", Thing)

    assert "cus_<ULID>" in raised.value.message


# --------------------------------------------------------------- the request on the wire


async def test_the_principal_and_its_ceiling_are_signed_into_the_request() -> None:
    script = Script(httpx.Response(200, json={"thing_id": "t1"}))

    thing = await _api(script).get(STAFF, "/v1/things/t1", Thing)

    assert thing == Thing(thing_id="t1")
    [request] = script.requests
    assert (request.headers[ACTOR], request.headers[KB_CEILING]) == ("staff-0042", "internal")
    assert request.headers[SIGNATURE].startswith("v1=")


async def test_a_write_sends_its_body_and_idempotency_key() -> None:
    script = Script(httpx.Response(201, json={"thing_id": "t1"}))
    key = str(uuid4())

    written = await _api(script).post(
        STAFF, "/v1/things", NewThing(name="lamp"), Thing, idempotency_key=key
    )

    assert (written.value, written.replayed) == (Thing(thing_id="t1"), False)
    [request] = script.requests
    assert request.headers["Idempotency-Key"] == key
    assert json.loads(request.content) == {"name": "lamp"}


async def test_a_replayed_write_says_so() -> None:
    replay = httpx.Response(200, json={"thing_id": "t1"}, headers={"Idempotent-Replayed": "true"})

    written = await _api(Script(replay)).post(
        STAFF, "/v1/things", NewThing(name="lamp"), Thing, idempotency_key="k"
    )

    assert written.replayed


# --------------------------------------------------------------- error mapping


@pytest.mark.parametrize(
    ("response", "raised"),
    [
        (_error(400, "invalid_argument"), InvalidArgumentError),
        (httpx.Response(422, json={"detail": [{"loc": ["query", "limit"]}]}), InvalidArgumentError),
        (_error(404, "not_found"), NotFoundError),
        (_error(409, "conflict"), ConflictError),
        (_error(401, "unauthenticated"), InternalError),
        (_error(503, "unavailable"), DependencyUnavailableError),
        (_error(504, "deadline_exceeded"), DeadlineExceededError),
        (httpx.Response(500, text="Internal Server Error"), DependencyUnavailableError),
        (httpx.Response(502, text="<html>bad gateway</html>"), DependencyUnavailableError),
    ],
)
async def test_core_api_failures_map_to_the_gateway_taxonomy(
    response: httpx.Response, raised: type[GatewayError]
) -> None:
    with pytest.raises(raised):
        await _api(Script(response)).get(STAFF, "/v1/things/t1", Thing)


@pytest.mark.parametrize(
    ("status", "code", "raised"),
    [(400, "invalid_argument", InvalidArgumentError), (404, "not_found", NotFoundError)],
)
async def test_caller_errors_keep_core_apis_message(
    status: int, code: str, raised: type[GatewayError]
) -> None:
    with pytest.raises(raised) as caught:
        await _api(Script(_error(status, code, "thing t1 not found"))).get(
            STAFF, "/v1/things/t1", Thing
        )

    assert caught.value.message == "thing t1 not found"


async def test_upstream_bodies_never_reach_the_caller() -> None:
    script = Script(httpx.Response(500, text="psycopg.errors.UndefinedColumn: pan_token"))

    with pytest.raises(DependencyUnavailableError) as raised:
        await _api(script).get(STAFF, "/v1/things/t1", Thing)

    assert "pan_token" not in raised.value.message


@pytest.mark.parametrize(
    ("exc", "raised"),
    [
        (httpx.ConnectError("refused"), DependencyUnavailableError),
        (httpx.ConnectTimeout("slow to connect"), DependencyUnavailableError),
        (httpx.ReadTimeout("slow to answer"), DeadlineExceededError),
        (httpx.RemoteProtocolError("dropped"), DependencyUnavailableError),
    ],
)
async def test_transport_failures_map_to_the_gateway_taxonomy(
    exc: Exception, raised: type[GatewayError]
) -> None:
    with pytest.raises(raised):
        await _api(Script(exc)).get(STAFF, "/v1/things/t1", Thing)


async def test_a_response_that_breaks_the_contract_is_internal() -> None:
    script = Script(httpx.Response(200, json={"unexpected": True}))

    with pytest.raises(InternalError):
        await _api(script).get(STAFF, "/v1/things/t1", Thing)


# --------------------------------------------------------------- retries


@pytest.mark.parametrize(
    "first",
    [_error(503, "unavailable"), _error(504, "deadline_exceeded"), httpx.ConnectError("refused")],
)
async def test_a_read_is_retried_once_after_a_transient_failure(
    first: httpx.Response | Exception,
) -> None:
    script = Script(first, httpx.Response(200, json={"thing_id": "t1"}))

    thing = await _api(script).get(STAFF, "/v1/things/t1", Thing)

    assert thing == Thing(thing_id="t1")
    assert len(script.requests) == 2


async def test_a_lost_write_response_is_retried_with_the_same_key_and_replays() -> None:
    script = Script(
        httpx.ReadTimeout("committed, but the answer was lost"),
        httpx.Response(200, json={"thing_id": "t1"}, headers={"Idempotent-Replayed": "true"}),
    )

    written = await _api(script).post(
        STAFF, "/v1/things", NewThing(name="lamp"), Thing, idempotency_key="key-1"
    )

    assert written.replayed
    first, second = script.requests
    assert first.headers["Idempotency-Key"] == second.headers["Idempotency-Key"] == "key-1"
    assert first.content == second.content


async def test_attempts_are_capped() -> None:
    script = Script(_error(503, "unavailable"))

    with pytest.raises(DependencyUnavailableError):
        await _api(script, attempts=2).get(STAFF, "/v1/things/t1", Thing)

    assert len(script.requests) == 2


@pytest.mark.parametrize(
    "response",
    [
        _error(400, "invalid_argument"),
        _error(404, "not_found"),
        _error(409, "conflict"),
        _error(401, "unauthenticated"),
        httpx.Response(500, text="boom"),
    ],
)
async def test_answers_that_would_not_change_are_not_retried(response: httpx.Response) -> None:
    script = Script(response)

    with pytest.raises(GatewayError):
        await _api(script).get(STAFF, "/v1/things/t1", Thing)

    assert len(script.requests) == 1


# --------------------------------------------------------------- request details


async def test_query_parameters_drop_unset_values_and_repeat_lists() -> None:
    script = Script(httpx.Response(200, json={"thing_id": "t1"}))

    await _api(script).get(
        STAFF,
        "/v1/things",
        Thing,
        params={"status": ["posted", "held"], "flagged": True, "limit": 5, "text": None},
    )

    [request] = script.requests
    assert request.url.query == b"status=posted&status=held&flagged=true&limit=5"


async def test_a_post_keyed_by_its_body_sends_no_idempotency_header() -> None:
    script = Script(httpx.Response(201, json={"thing_id": "t1"}))

    await _api(script).post(STAFF, "/v1/audit", NewThing(name="call"), Thing)

    [request] = script.requests
    assert "Idempotency-Key" not in request.headers


@pytest.mark.parametrize("retry_after", [None, "soon"])
async def test_an_unusable_retry_after_is_left_out(retry_after: str | None) -> None:
    headers = {} if retry_after is None else {"Retry-After": retry_after}
    unavailable = httpx.Response(503, json={"error": {"code": "unavailable"}}, headers=headers)

    with pytest.raises(DependencyUnavailableError) as raised:
        await _api(Script(unavailable), attempts=1).get(STAFF, "/v1/things/t1", Thing)

    assert raised.value.retry_after_s is None


def test_at_least_one_attempt_is_required() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        _api(Script(httpx.Response(200)), attempts=0)
