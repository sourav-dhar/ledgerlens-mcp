"""KYC input is validated before the database is touched."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from signed import TEST_KEY, SignedAs

from core_api.app import create_app
from core_api.settings import Settings
from kosha_domain.ids import IdPrefix, new_id

pytestmark = pytest.mark.anyio


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(internal_signing_keys=SecretStr(TEST_KEY)))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", auth=SignedAs("staff-0042")
    ) as c:
        yield c


@pytest.mark.parametrize("suffix", ["kyc", "kyc/documents"])
async def test_a_malformed_customer_id_is_an_invalid_argument(
    client: AsyncClient, suffix: str
) -> None:
    response = await client.get(f"/v1/customers/{new_id(IdPrefix.ACCOUNT)}/{suffix}")

    assert response.status_code == 400


@pytest.mark.parametrize("suffix", ["kyc", "kyc/documents"])
async def test_a_valid_request_without_a_database_is_unavailable(
    client: AsyncClient, suffix: str
) -> None:
    response = await client.get(f"/v1/customers/{new_id(IdPrefix.CUSTOMER)}/{suffix}")

    assert response.status_code == 503
