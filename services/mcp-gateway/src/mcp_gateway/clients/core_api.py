"""The gateway's client for core-api (ADR 0001, ADR 0013, system design §8).

Every request is signed for the principal the gateway authenticated, over the final
percent-encoded target, so core-api can trust who it acts for. core-api's errors become the
gateway's taxonomy, and its payloads never reach the caller. A transient failure (connect
error, timeout, ``503``, ``504``) is retried; a write only ever with its original
idempotency key, so a response lost after core-api committed comes back as the stored
replay rather than as a second write.

Retry budgets, breakers and deadlines join in P4 (resilience LLD §3-§5).
"""

import asyncio
import logging
import random
import time
from collections.abc import Callable, Generator, Mapping, Sequence
from dataclasses import dataclass
from http import HTTPStatus

import httpx
from pydantic import BaseModel, ValidationError

from kosha_domain.signing import Principal, SignedRequest, sign
from mcp_gateway.errors import (
    ConflictError,
    DeadlineExceededError,
    DependencyUnavailableError,
    GatewayError,
    InternalError,
    InvalidArgumentError,
    NotFoundError,
)

logger = logging.getLogger(__name__)

CORE_API = "core-api"
IDEMPOTENCY_KEY = "Idempotency-Key"
REPLAYED = "Idempotent-Replayed"

type QueryValue = str | int | bool | Sequence[str]
type QueryParams = Mapping[str, QueryValue | None]

_TRANSIENT_STATUSES = frozenset({HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.GATEWAY_TIMEOUT})


class _SignedFor(httpx.Auth):
    """Signs each attempt afresh, so a retry carries a current timestamp."""

    requires_request_body = True

    def __init__(self, key: bytes, principal: Principal, clock: Callable[[], float]) -> None:
        self._key = key
        self._principal = principal
        self._clock = clock

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response]:
        ceiling = self._principal.kb_ceiling
        signed = SignedRequest(
            method=request.method,
            target=request.url.raw_path.decode("ascii"),
            actor=self._principal.actor,
            kb_ceiling=None if ceiling is None else ceiling.value,
            body=request.content,
        )
        request.headers.update(sign(self._key, signed, timestamp=int(self._clock())))
        yield request


@dataclass(frozen=True, slots=True)
class Written[M: BaseModel]:
    """The outcome of a write; ``replayed`` when core-api returned the stored response."""

    value: M
    replayed: bool


def _query(params: QueryParams | None) -> tuple[tuple[str, str], ...]:
    """Query pairs without the unset ones; a sequence repeats its parameter."""
    pairs: list[tuple[str, str]] = []
    for name, value in (params or {}).items():
        match value:
            case None:
                continue
            case bool():
                pairs.append((name, "true" if value else "false"))
            case str() | int():
                pairs.append((name, str(value)))
            case _:
                pairs.extend((name, item) for item in value)
    return tuple(pairs)


def _upstream_message(response: httpx.Response) -> str | None:
    """core-api's caller-facing message, if the body has the shape it promises (LLD §7)."""
    try:
        body = response.json()
    except ValueError:
        return None
    match body:
        case {"error": {"message": str() as message}}:
            return message
        case _:
            return None


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return max(0.0, float(response.headers["Retry-After"]))
    except (KeyError, ValueError):
        return None


_CALLER_ERRORS: dict[int, tuple[type[GatewayError], str]] = {
    400: (InvalidArgumentError, "core-api rejected the request"),
    # FastAPI's own parsing errors: never the shape core-api promises, so never its message.
    422: (InvalidArgumentError, "core-api rejected the request as malformed"),
    404: (NotFoundError, "not found"),
    409: (ConflictError, "the request conflicts with the current state"),
}


def _from_response(response: httpx.Response) -> GatewayError:
    status = response.status_code
    if status in _CALLER_ERRORS:
        error, fallback = _CALLER_ERRORS[status]
        return error(_upstream_message(response) or fallback)
    if status == HTTPStatus.SERVICE_UNAVAILABLE:
        return DependencyUnavailableError(
            "core-api is unavailable; retry shortly",
            dependency=CORE_API,
            retry_after_s=_retry_after(response),
        )
    if status == HTTPStatus.GATEWAY_TIMEOUT:
        return DeadlineExceededError("core-api did not answer within its deadline")
    if status >= HTTPStatus.INTERNAL_SERVER_ERROR:
        logger.warning("core-api answered %s to %s", status, response.request.url.path)
        return DependencyUnavailableError("core-api failed", dependency=CORE_API)
    # 401 means core-api could not verify our signature: a key mismatch, not the caller's
    # fault. Any other status is one this client never expects.
    logger.error("core-api answered %s to %s", status, response.request.url.path)
    return InternalError("core-api refused the gateway's request")


def _from_transport(exc: httpx.TransportError) -> GatewayError:
    match exc:
        case httpx.ConnectTimeout() | httpx.PoolTimeout():
            return DependencyUnavailableError("core-api could not be reached", dependency=CORE_API)
        case httpx.TimeoutException():
            return DeadlineExceededError("core-api did not answer in time")
        case _:
            return DependencyUnavailableError("core-api could not be reached", dependency=CORE_API)


def _is_transient(exc: httpx.TransportError) -> bool:
    return isinstance(exc, httpx.TimeoutException | httpx.NetworkError | httpx.RemoteProtocolError)


def _parse[M: BaseModel](response: httpx.Response, model: type[M]) -> M:
    try:
        return model.model_validate_json(response.content)
    except ValidationError:
        logger.exception("core-api's answer to %s broke the contract", response.request.url.path)
        raise InternalError("core-api answered in an unexpected shape") from None


class CoreApi:
    """Typed, signed access to core-api for one gateway instance."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        signing_key: bytes,
        attempts: int = 2,
        backoff_s: float = 0.1,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if attempts < 1:
            msg = "attempts must be at least 1"
            raise ValueError(msg)
        self._http = http
        self._key = signing_key
        self._attempts = attempts
        self._backoff_s = backoff_s
        self._clock = clock

    async def get[M: BaseModel](
        self, principal: Principal, path: str, model: type[M], *, params: QueryParams | None = None
    ) -> M:
        response = await self._send(principal, "GET", path, params=_query(params))
        return _parse(response, model)

    async def post[M: BaseModel](
        self,
        principal: Principal,
        path: str,
        body: BaseModel,
        model: type[M],
        *,
        idempotency_key: str | None = None,
    ) -> Written[M]:
        """A write to an idempotent route: keyed by ``idempotency_key`` or by its body.

        Retrying is safe only because core-api stores the first response under the key, so
        this client offers no way to post to a route that is not idempotent.
        """
        headers = {"Content-Type": "application/json"}
        if idempotency_key is not None:
            headers[IDEMPOTENCY_KEY] = idempotency_key
        response = await self._send(
            principal, "POST", path, content=body.model_dump_json().encode(), headers=headers
        )
        return Written(_parse(response, model), replayed=response.headers.get(REPLAYED) == "true")

    async def _send(
        self,
        principal: Principal,
        method: str,
        path: str,
        *,
        params: tuple[tuple[str, str], ...] = (),
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        auth = _SignedFor(self._key, principal, self._clock)
        for attempt in range(1, self._attempts + 1):
            final = attempt == self._attempts
            try:
                response = await self._http.request(
                    method, path, params=params, content=content, headers=headers, auth=auth
                )
            except httpx.TransportError as exc:
                if final or not _is_transient(exc):
                    raise _from_transport(exc) from exc
            else:
                if response.is_success:
                    return response
                if final or response.status_code not in _TRANSIENT_STATUSES:
                    raise _from_response(response)
            await asyncio.sleep(random.uniform(0, self._backoff_s))  # noqa: S311 (jitter)
        raise AssertionError("unreachable: the final attempt returns or raises")  # pragma: no cover
