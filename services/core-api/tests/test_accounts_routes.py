"""Account and Transaction input is validated before the database is touched."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from signed import TEST_KEY, SignedAs

from core_api.app import create_app
from core_api.settings import Settings
from kosha_domain.ids import IdPrefix, new_id

pytestmark = pytest.mark.anyio

ACCOUNT = new_id(IdPrefix.ACCOUNT)
SEARCH = f"/v1/accounts/{ACCOUNT}/transactions"
NOW = datetime.now(UTC)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """No database: valid input then answers 503, invalid input 400 or 422."""
    app = create_app(Settings(internal_signing_keys=SecretStr(TEST_KEY)))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", auth=SignedAs("staff-0042")
    ) as c:
        yield c


@pytest.mark.parametrize(
    "path",
    [
        "/v1/accounts/acc_123",
        f"/v1/accounts/{new_id(IdPrefix.CUSTOMER)}",
        "/v1/accounts/acc_123/transactions",
        "/v1/transactions/txn_123",
        f"/v1/transactions/{ACCOUNT}",
    ],
)
async def test_a_malformed_id_is_an_invalid_argument(client: AsyncClient, path: str) -> None:
    response = await client.get(path)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_argument"


@pytest.mark.parametrize(
    "params",
    [
        {"initiated_from": NOW.isoformat(), "initiated_before": NOW.isoformat()},
        {"initiated_from": (NOW - timedelta(days=400)).isoformat()},
        {
            "initiated_from": (NOW - timedelta(days=800)).isoformat(),
            "initiated_before": (NOW - timedelta(days=400)).isoformat(),
        },
        {"min_amount_paise": 5_000, "max_amount_paise": 1_000},
        {"after_txn_id": new_id(IdPrefix.TRANSACTION)},
        {"after_initiated_at": NOW.isoformat()},
        {"after_initiated_at": NOW.isoformat(), "after_txn_id": "txn_123"},
    ],
    ids=[
        "empty window",
        "window from over 366 days ago",
        "window over 366 days long",
        "min above max",
        "keyset without its instant",
        "keyset without its id",
        "keyset with a malformed id",
    ],
)
async def test_inconsistent_search_criteria_are_invalid_arguments(
    client: AsyncClient, params: dict[str, Any]
) -> None:
    response = await client.get(SEARCH, params=params)

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "invalid_argument"


@pytest.mark.parametrize(
    "params",
    [
        {"initiated_from": "2026-11-01T00:00:00"},
        {"direction": "sideways"},
        {"status": ["paid"]},
        {"rail": ["swift"]},
        {"min_amount_paise": 0},
        {"text": "ab"},
        {"limit": 0},
        {"limit": 101},
    ],
    ids=["naive time", "direction", "status", "rail", "zero amount", "short text", "0", "101"],
)
async def test_malformed_search_parameters_are_rejected(
    client: AsyncClient, params: dict[str, Any]
) -> None:
    response = await client.get(SEARCH, params=params)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "path",
    [f"/v1/accounts/{ACCOUNT}", SEARCH, f"/v1/transactions/{new_id(IdPrefix.TRANSACTION)}"],
)
async def test_valid_requests_without_a_database_are_unavailable(
    client: AsyncClient, path: str
) -> None:
    response = await client.get(path)

    assert response.status_code == 503
