"""Write requests are validated before the database is touched."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from signed import TEST_KEY, SignedAs

from core_api.app import create_app
from core_api.services.idempotency import request_hash
from core_api.settings import Settings
from kosha_domain.ids import IdPrefix, new_id

pytestmark = pytest.mark.anyio

TXN = new_id(IdPrefix.TRANSACTION)
DISPUTE = {"txn_id": TXN, "reason_code": "duplicate"}
REVIEW = {"txn_id": TXN, "reason": "Velocity spike on a new device"}
KEY = {"Idempotency-Key": "test-write-0001"}


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(internal_signing_keys=SecretStr(TEST_KEY)))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", auth=SignedAs("staff-0042")
    ) as c:
        yield c


@pytest.mark.parametrize(("path", "body"), [("/v1/disputes", DISPUTE), ("/v1/reviews", REVIEW)])
async def test_a_valid_write_without_a_database_is_unavailable(
    client: AsyncClient, path: str, body: dict[str, Any]
) -> None:
    response = await client.post(path, json=body, headers=KEY)

    assert response.status_code == 503


@pytest.mark.parametrize(("path", "body"), [("/v1/disputes", DISPUTE), ("/v1/reviews", REVIEW)])
@pytest.mark.parametrize("key", [None, "", "has space", "x" * 256])
async def test_a_write_needs_a_well_formed_idempotency_key(
    client: AsyncClient, path: str, body: dict[str, Any], key: str | None
) -> None:
    headers = {} if key is None else {"Idempotency-Key": key}

    response = await client.post(path, json=body, headers=headers)

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/v1/disputes", DISPUTE | {"reason_code": "changed_my_mind"}),
        ("/v1/disputes", DISPUTE | {"amount_paise": 0}),
        ("/v1/disputes", DISPUTE | {"note": "unexpected field"}),
        ("/v1/reviews", REVIEW | {"reason": "no"}),
        ("/v1/reviews", REVIEW | {"priority": "asap"}),
        ("/v1/reviews", {"txn_id": TXN}),
    ],
)
async def test_a_malformed_body_is_rejected(
    client: AsyncClient, path: str, body: dict[str, Any]
) -> None:
    response = await client.post(path, json=body, headers=KEY)

    assert response.status_code == 422


@pytest.mark.parametrize(("path", "body"), [("/v1/disputes", DISPUTE), ("/v1/reviews", REVIEW)])
async def test_a_malformed_transaction_id_is_an_invalid_argument(
    client: AsyncClient, path: str, body: dict[str, Any]
) -> None:
    response = await client.post(path, json=body | {"txn_id": "txn_123"}, headers=KEY)

    assert response.status_code == 400


def test_the_request_hash_covers_the_caller_and_ignores_key_order() -> None:
    same = request_hash("staff-0042", {"a": 1, "b": [2, 3]})

    assert same == request_hash("staff-0042", {"b": [2, 3], "a": 1})
    assert same != request_hash("support-7", {"a": 1, "b": [2, 3]})
    assert same != request_hash("staff-0042", {"a": 1, "b": [3, 2]})
    assert len(same) == 64
