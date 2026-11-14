"""API errors, the database failures they stand for, and the one body shape they share.

Every error answers ``{"error": {"code": ..., "message": ...}}``; ``code`` is the stable,
machine-readable part the gateway maps to its own errors (LLD core-api §7).
"""

from collections.abc import Mapping
from typing import ClassVar

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from psycopg import errors
from psycopg_pool import PoolTimeout

_RETRY_SOON = {"Retry-After": "1"}


class ApiError(Exception):
    status_code: ClassVar[int] = 500
    code: ClassVar[str] = "internal"
    headers: ClassVar[Mapping[str, str]] = {}

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidArgumentError(ApiError):
    status_code = 400
    code = "invalid_argument"


class UnauthenticatedError(ApiError):
    """The request was not provably signed by the gateway (ADR 0013)."""

    status_code = 401
    code = "unauthenticated"


class NotFoundError(ApiError):
    status_code = 404
    code = "not_found"


class ConflictError(ApiError):
    """An idempotency conflict, or a change the domain rules forbid."""

    status_code = 409
    code = "conflict"


class UnavailableError(ApiError):
    status_code = 503
    code = "unavailable"
    headers = _RETRY_SOON


class DeadlineExceededError(ApiError):
    status_code = 504
    code = "deadline_exceeded"


def from_database_error(exc: Exception) -> ApiError | None:
    """The API error a database failure stands for; ``None`` when it is a defect (500).

    The schema enforces lifecycles and append-only history itself (revisions 0003, 0005),
    so its refusals are the caller's conflict, not the server's bug.
    """
    match exc:
        case PoolTimeout():
            return UnavailableError("no database connection is free; retry shortly")
        case errors.QueryCanceled():
            return DeadlineExceededError("the database did not answer within the deadline")
        case errors.CheckViolation() if (exc.diag.constraint_name or "").endswith("_lifecycle"):
            return ConflictError(exc.diag.message_primary or "illegal status transition")
        case errors.RestrictViolation():
            return ConflictError(exc.diag.message_primary or "the record cannot be changed")
        case psycopg.OperationalError():
            return UnavailableError("the database is unavailable; retry shortly")
        case _:
            return None


def _respond(error: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"error": {"code": error.code, "message": error.message}},
        headers=dict(error.headers),
    )


async def _api_error(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ApiError):  # registered for ApiError only
        raise exc
    return _respond(exc)


async def _database_error(_: Request, exc: Exception) -> JSONResponse:
    mapped = from_database_error(exc)
    if mapped is None:
        raise exc
    return _respond(mapped)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(psycopg.Error, _database_error)
