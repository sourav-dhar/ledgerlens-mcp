"""Guards every data route must have, checked against the published contract.

Routes are read from the OpenAPI document, so a new route is covered the moment it is
registered: forgetting authentication or the database check fails the build rather than
waiting for someone to notice.
"""

import re
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from signed import TEST_KEY, SignedAs

from core_api.app import create_app
from core_api.settings import Settings
from kosha_domain.ids import IdPrefix, new_id

pytestmark = pytest.mark.anyio

APP = create_app(Settings(internal_signing_keys=SecretStr(TEST_KEY)))

# A well-formed value for every path parameter a route may declare.
_PATH_VALUES = {
    "customer_id": new_id(IdPrefix.CUSTOMER),
    "account_id": new_id(IdPrefix.ACCOUNT),
    "txn_id": new_id(IdPrefix.TRANSACTION),
    "alert_id": new_id(IdPrefix.AML_ALERT),
    "doc_code": "CMP-SOP-004",
}

# The smallest valid request for routes that need more than their path.
_QUERY: dict[str, dict[str, str]] = {
    "/v1/customers": {"name": "Ravi"},
    "/v1/kb/search": {"q": "escalation"},
}
_BODY: dict[str, dict[str, Any]] = {
    "/v1/disputes": {"txn_id": _PATH_VALUES["txn_id"], "reason_code": "duplicate"},
    "/v1/reviews": {"txn_id": _PATH_VALUES["txn_id"], "reason": "Velocity spike"},
    "/v1/audit": {
        "audit_id": new_id(IdPrefix.AUDIT_RECORD),
        "client_id": "claude-desktop",
        "roles": ["analyst"],
        "tool_name": "search_transactions",
        "args_hash": "0" * 64,
        "outcome": "success",
        "latency_ms": 12,
    },
}
_HEADERS = {"/v1/disputes": {"Idempotency-Key": "guard-1"}, "/v1/reviews": {"Idempotency-Key": "g"}}

DATA_ROUTES = [
    (method.upper(), path)
    for path, operations in APP.openapi()["paths"].items()
    if path.startswith("/v1/")
    for method in sorted(operations)
]


def _url(path: str) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: _PATH_VALUES[m.group(1)], path)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=APP), base_url="http://test") as c:
        yield c


def test_the_guards_see_every_data_route() -> None:
    assert len(DATA_ROUTES) == 16
    assert all(m in {"GET", "POST"} for m, _ in DATA_ROUTES)


@pytest.mark.parametrize(("method", "path"), DATA_ROUTES)
async def test_every_data_route_refuses_an_unsigned_request(
    client: AsyncClient, method: str, path: str
) -> None:
    response = await client.request(
        method,
        _url(path),
        params=_QUERY.get(path),
        json=_BODY.get(path),
        headers=_HEADERS.get(path),
    )

    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize(("method", "path"), DATA_ROUTES)
async def test_every_data_route_answers_unavailable_without_a_database(
    client: AsyncClient, method: str, path: str
) -> None:
    response = await client.request(
        method,
        _url(path),
        params=_QUERY.get(path),
        json=_BODY.get(path),
        headers=_HEADERS.get(path),
        auth=SignedAs("analyst-7", "confidential"),
    )

    assert response.status_code == 503, response.text
    assert response.headers["Retry-After"] == "1"
