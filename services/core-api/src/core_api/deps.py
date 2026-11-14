"""Request dependencies shared by the routers."""

from typing import Annotated

from fastapi import Depends, Header, Request

from core_api.db import Caller, Database
from core_api.errors import UnavailableError
from kosha_domain.vocabulary import Classification


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


def _caller(
    x_kosha_actor: Annotated[
        str,
        Header(
            min_length=1,
            max_length=128,
            description="The principal the gateway verified (its `sub`).",
        ),
    ],
    x_kosha_kb_ceiling: Annotated[
        Classification | None,
        Header(description="Highest knowledge-base classification the principal may read."),
    ] = None,
) -> Caller:
    """The principal the gateway forwards with each request.

    The gateway is the only client and reaches ``core-api`` over the private network
    (LLD security §3); authenticating these headers with the service token is a separate
    step, to land before the first deployment.
    """
    return Caller(actor=x_kosha_actor, kb_ceiling=x_kosha_kb_ceiling)


DatabaseDep = Annotated[Database | None, Depends(_database)]
CallerDep = Annotated[Caller, Depends(_caller)]
