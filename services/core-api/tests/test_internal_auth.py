"""Only requests the gateway signed reach a data route (ADR 0013)."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr, ValidationError
from signed import TEST_KEY, SignedAs

from core_api.app import create_app
from core_api.settings import Settings
from kosha_domain.ids import IdPrefix, new_id

pytestmark = pytest.mark.anyio

CUSTOMER = f"/v1/customers/{new_id(IdPrefix.CUSTOMER)}"
OTHER_KEY = "previous-signing-key-" + "y" * 16


async def _client(settings: Settings) -> AsyncClient:
    app = create_app(settings)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """No database: a request that passes authentication is then unavailable (503)."""
    settings = Settings(internal_signing_keys=SecretStr(f"{TEST_KEY},{OTHER_KEY}"))
    async with await _client(settings) as c:
        yield c


async def test_a_signed_request_passes_authentication(client: AsyncClient) -> None:
    response = await client.get(CUSTOMER, auth=SignedAs("staff-0042"))

    assert response.status_code == 503


async def test_the_previous_key_is_accepted_during_rotation(client: AsyncClient) -> None:
    response = await client.get(CUSTOMER, auth=SignedAs("staff-0042", key=OTHER_KEY))

    assert response.status_code == 503


async def test_a_signed_query_string_passes_authentication(client: AsyncClient) -> None:
    response = await client.get(
        "/v1/customers", params={"name": "Ravi Kumar%"}, auth=SignedAs("staff-0042")
    )

    assert response.status_code == 503


async def test_an_unsigned_request_is_unauthenticated(client: AsyncClient) -> None:
    response = await client.get(CUSTOMER, headers={"X-Kosha-Actor": "staff-0042"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize(
    "auth",
    [
        SignedAs("staff-0042", key="unknown-signing-key-" + "z" * 16),
        SignedAs("staff-0042", skew_s=-300),
    ],
    ids=["unknown key", "stale"],
)
async def test_a_badly_signed_request_is_unauthenticated(
    client: AsyncClient, auth: SignedAs
) -> None:
    response = await client.get(CUSTOMER, auth=auth)

    assert response.status_code == 401


async def test_a_forged_principal_is_unauthenticated(client: AsyncClient) -> None:
    signed = client.build_request("GET", CUSTOMER)
    headers = dict(next(SignedAs("support-7").auth_flow(signed)).headers)

    response = await client.get(CUSTOMER, headers=headers | {"X-Kosha-Kb-Ceiling": "restricted"})

    assert response.status_code == 401


async def test_without_keys_every_data_route_is_refused() -> None:
    async with await _client(Settings()) as client:
        response = await client.get(CUSTOMER, auth=SignedAs("staff-0042"))

    assert response.status_code == 401
    assert "not configured" in response.json()["error"]["message"]


@pytest.mark.parametrize("path", ["/healthz", "/openapi.json"])
async def test_probes_and_the_contract_need_no_signature(path: str) -> None:
    async with await _client(Settings()) as client:
        response = await client.get(path)

    assert response.status_code == 200


def test_signing_keys_are_read_current_first() -> None:
    settings = Settings(internal_signing_keys=SecretStr(f" {TEST_KEY} , {OTHER_KEY} "))

    assert settings.signing_keys() == (TEST_KEY.encode(), OTHER_KEY.encode())


def test_a_short_signing_key_is_refused_at_startup() -> None:
    with pytest.raises(ValidationError, match="32 bytes"):
        Settings(internal_signing_keys=SecretStr("too-short"))
