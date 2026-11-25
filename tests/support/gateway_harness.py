"""Run the MCP gateway in-process against a core-api of the test's choosing.

Tools are tested through FastMCP's in-memory client. The access token a real deployment
gets from JWT verification is injected instead, so a test states exactly who calls. The
JWT path itself is tested over HTTP.

`FakeCoreApi` answers from a table of routes, but only to requests it can verify were
signed by the gateway (ADR 0013), and its answers are built from core-api's own response
models, so a canned payload cannot drift from the real contract.
"""

import time
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken
from pydantic import BaseModel, SecretStr
from signed import TEST_KEY

from kosha_domain.signing import SignatureError, verify
from mcp_gateway.auth.scopes import ROLE_SCOPES, Role, Scope
from mcp_gateway.server import create_server
from mcp_gateway.settings import Settings

CURSOR_KEY = "cursor-key-for-gateway-tests-" + "c" * 8
SETTINGS = Settings(
    internal_signing_key=SecretStr(TEST_KEY),
    cursor_keys=SecretStr(CURSOR_KEY),
    core_api_backoff_s=0,
)


def access_token(
    role: Role | None = Role.ANALYST,
    *,
    scopes: frozenset[Scope] | None = None,
    sub: str = "staff-0042",
    client_id: str = "console",
) -> AccessToken:
    """A verified token for a Staff member in ``role``, with that Role's scopes by default."""
    granted = scopes if scopes is not None else ROLE_SCOPES[role] if role else frozenset(Scope)
    claims: dict[str, Any] = {"sub": sub, "client_id": client_id}
    if role is not None:
        claims["cognito:groups"] = [role.value]
    return AccessToken(
        token="injected-test-token",  # noqa: S106 — never verified; claims are given directly
        client_id=client_id,
        scopes=sorted(granted),
        claims=claims,
    )


def gateway(
    transport: httpx.AsyncBaseTransport,
    token: AccessToken | None,
    *,
    settings: Settings = SETTINGS,
) -> FastMCP:
    return create_server(settings, core_api_transport=transport, token_source=lambda: token)


type Answer = BaseModel | httpx.Response


class FakeCoreApi(httpx.AsyncBaseTransport):
    """core-api as a route table: ``"GET /v1/customers"`` -> model or response."""

    def __init__(self, routes: dict[str, Answer] | None = None) -> None:
        self.routes: dict[str, Answer] = dict(routes or {})
        self.requests: list[httpx.Request] = []

    def route(self, method_and_path: str, answer: Answer) -> None:
        self.routes[method_and_path] = answer

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        self.requests.append(request)
        try:
            verify(
                [TEST_KEY.encode()],
                request.method,
                request.url.raw_path.decode("ascii"),
                body,
                request.headers,
                now=int(time.time()),
            )
        except SignatureError as exc:
            return core_api_error(401, "unauthenticated", str(exc))
        answer = self.routes.get(f"{request.method} {request.url.path}")
        match answer:
            case None:
                return core_api_error(404, "not_found", f"no route for {request.url.path}")
            case httpx.Response():
                return answer
            case BaseModel():
                return httpx.Response(200, content=answer.model_dump_json().encode())

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]


def core_api_error(status: int, code: str, message: str = "said core-api") -> httpx.Response:
    headers = {"Retry-After": "1"} if status == 503 else {}
    return httpx.Response(
        status, json={"error": {"code": code, "message": message}}, headers=headers
    )
