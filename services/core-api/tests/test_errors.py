"""Database failures become typed API errors with one response shape."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from psycopg import OperationalError, errors
from psycopg_pool import PoolTimeout

from core_api.errors import (
    ApiError,
    DeadlineExceededError,
    NotFoundError,
    UnavailableError,
    from_database_error,
    install_error_handlers,
)


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (PoolTimeout("couldn't get a connection after 2.00 sec"), UnavailableError),
        (OperationalError("connection refused"), UnavailableError),
        (
            errors.QueryCanceled("canceling statement due to statement timeout"),
            DeadlineExceededError,
        ),
    ],
)
def test_infrastructure_failures_map_to_retryable_errors(
    raised: Exception, expected: type[ApiError]
) -> None:
    assert isinstance(from_database_error(raised), expected)


def test_an_unlisted_database_error_is_not_mapped() -> None:
    assert from_database_error(errors.UndefinedTable("no such table")) is None


def test_a_check_violation_outside_a_lifecycle_is_not_mapped() -> None:
    assert from_database_error(errors.CheckViolation("amount_paise > 0")) is None


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/missing")
    async def missing() -> None:  # pyright: ignore[reportUnusedFunction]
        raise NotFoundError("customer cus_X not found")

    @app.get("/slow")
    async def slow() -> None:  # pyright: ignore[reportUnusedFunction]
        raise errors.QueryCanceled("canceling statement due to statement timeout")

    @app.get("/busy")
    async def busy() -> None:  # pyright: ignore[reportUnusedFunction]
        raise PoolTimeout("couldn't get a connection after 2.00 sec")

    return app


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/missing", 404, "not_found"),
        ("/slow", 504, "deadline_exceeded"),
        ("/busy", 503, "unavailable"),
    ],
)
async def test_errors_share_one_body_shape(app: FastAPI, path: str, status: int, code: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["message"]


@pytest.mark.anyio
async def test_an_unavailable_dependency_asks_the_caller_to_retry(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/busy")

    assert response.headers["Retry-After"] == "1"
