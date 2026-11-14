"""Request dependencies shared by the routers."""

import time
from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader

from core_api.db import Caller, Database
from core_api.errors import UnauthenticatedError, UnavailableError
from core_api.settings import Settings
from kosha_domain.signing import ACTOR, KB_CEILING, SIGNATURE, TIMESTAMP, SignatureError, verify


def _database(request: Request) -> Database | None:
    database: Database | None = request.app.state.database
    return database


def require(database: Database | None) -> Database:
    """The configured database, checked inside the handler.

    A dependency that raised here would pre-empt validation: FastAPI runs dependencies
    before it reports invalid query parameters, so bad input would answer ``503``.
    """
    if database is None:
        raise UnavailableError("no database is configured")
    return database


# Declared for the OpenAPI document; ``_caller`` reads and verifies the headers itself.
_signed_by_gateway = APIKeyHeader(
    name=SIGNATURE,
    scheme_name="GatewaySignature",
    description=(
        f"`v1=` and a hex HMAC-SHA256 by the gateway over the method, target, body, "
        f"`{TIMESTAMP}`, `{ACTOR}` and `{KB_CEILING}` headers (ADR 0013)."
    ),
    auto_error=False,
)


def _target(request: Request) -> str:
    """The path and query as the client sent them, which is what the gateway signed."""
    raw_path: bytes = request.scope.get("raw_path") or request.url.path.encode()
    query: bytes = request.scope.get("query_string", b"")
    return (raw_path + b"?" + query if query else raw_path).decode("latin-1")


async def _caller(
    request: Request, _signature: Annotated[str | None, Security(_signed_by_gateway)]
) -> Caller:
    """The principal the gateway authenticated, proven by the request's signature."""
    settings: Settings = request.app.state.settings
    try:
        principal = verify(
            settings.signing_keys(),
            request.method,
            _target(request),
            await request.body(),
            request.headers,
            now=int(time.time()),
        )
    except SignatureError as exc:
        raise UnauthenticatedError(str(exc)) from None
    return Caller(actor=principal.actor, kb_ceiling=principal.kb_ceiling)


DatabaseDep = Annotated[Database | None, Depends(_database)]
CallerDep = Annotated[Caller, Depends(_caller)]
