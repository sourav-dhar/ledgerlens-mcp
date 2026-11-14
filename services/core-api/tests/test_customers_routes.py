"""Input is validated before the database is touched; the contract is a reviewed snapshot."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from signed import TEST_KEY, SignedAs
from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.json import JSONSnapshotExtension

from core_api.app import create_app
from core_api.settings import Settings
from kosha_domain.ids import IdPrefix, new_id

pytestmark = pytest.mark.anyio


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """The app without a database: anything that reaches the database is unavailable."""
    app = create_app(Settings(internal_signing_keys=SecretStr(TEST_KEY)))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", auth=SignedAs("staff-0042")
        ) as c,
    ):
        yield c


@pytest.mark.parametrize("customer_id", ["cus_123", "acc_01JZ8Q4V9X2M3N4P5Q6R7S8T9V", "x" * 40])
async def test_a_malformed_customer_id_is_an_invalid_argument(
    client: AsyncClient, customer_id: str
) -> None:
    response = await client.get(f"/v1/customers/{customer_id}")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_argument"


async def test_a_search_needs_at_least_one_criterion(client: AsyncClient) -> None:
    response = await client.get("/v1/customers")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_argument"


@pytest.mark.parametrize(
    "params",
    [
        {"cif_number": "12345"},
        {"mobile_last4": "12a4"},
        {"name": "a"},
        {"name": "Ravi", "limit": 0},
        {"name": "Ravi", "limit": 101},
    ],
)
async def test_malformed_search_criteria_are_rejected(
    client: AsyncClient, params: dict[str, str | int]
) -> None:
    response = await client.get("/v1/customers", params=params)

    assert response.status_code == 422


async def test_a_valid_request_without_a_database_is_unavailable(client: AsyncClient) -> None:
    response = await client.get(f"/v1/customers/{new_id(IdPrefix.CUSTOMER)}")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert response.json()["error"]["code"] == "unavailable"


async def test_the_openapi_contract_is_unchanged(
    client: AsyncClient, snapshot: SnapshotAssertion
) -> None:
    document = (await client.get("/openapi.json")).json()
    del document["info"]["version"]  # bumped by every release, not a contract change

    assert document == snapshot(extension_class=JSONSnapshotExtension)
