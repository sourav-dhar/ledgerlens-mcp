"""Knowledge-base and audit input is validated before the database is touched."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from signed import TEST_KEY, SignedAs

from core_api.app import create_app
from core_api.repositories.kb import citation
from core_api.settings import Settings

pytestmark = pytest.mark.anyio

RECORD: dict[str, Any] = {
    "audit_id": "aud_01JZ8Q4V9X2M3N4P5Q6R7S8T9V",
    "client_id": "claude-desktop",
    "roles": ["support_agent"],
    "tool_name": "search_transactions",
    "args_hash": "0" * 64,
    "outcome": "success",
    "latency_ms": 41,
}


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(internal_signing_keys=SecretStr(TEST_KEY)))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        auth=SignedAs("support-7", "internal"),
    ) as c:
        yield c


@pytest.mark.parametrize("doc_code", ["CMP-SOP-4", "cmp-sop-004", "COMPLIANCE-SOP-004"])
async def test_a_malformed_document_code_is_an_invalid_argument(
    client: AsyncClient, doc_code: str
) -> None:
    response = await client.get(f"/v1/kb/documents/{doc_code}")

    assert response.status_code == 400


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/v1/kb/search", {}),
        ("/v1/kb/search", {"q": "a"}),
        ("/v1/kb/search", {"q": "x" * 201}),
        ("/v1/kb/search", {"q": "escalation", "limit": 21}),
        ("/v1/kb/search", {"q": "escalation", "department": ["finance"]}),
        ("/v1/kb/documents/CMP-SOP-004", {"version": "latest!"}),
    ],
)
async def test_malformed_parameters_are_rejected(
    client: AsyncClient, path: str, params: dict[str, Any]
) -> None:
    response = await client.get(path, params=params)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "change",
    [
        {"args_hash": "not-a-hash"},
        {"outcome": "maybe"},
        {"latency_ms": -1},
        {"roles": []},
        {"actor_sub": "someone-else"},
        {"audit_id": "aud_123"},
        {"audit_id": "cus_01JZ8Q4V9X2M3N4P5Q6R7S8T9V"},
    ],
    ids=["hash", "outcome", "latency", "no roles", "actor in body", "short id", "wrong prefix"],
)
async def test_a_malformed_audit_record_is_rejected(
    client: AsyncClient, change: dict[str, Any]
) -> None:
    response = await client.post("/v1/audit", json=RECORD | change)

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/v1/kb/search?q=escalation", None),
        ("GET", "/v1/kb/documents/CMP-SOP-004", None),
        ("POST", "/v1/audit", RECORD),
    ],
)
async def test_valid_requests_without_a_database_are_unavailable(
    client: AsyncClient, method: str, path: str, body: dict[str, Any] | None
) -> None:
    response = await client.request(method, path, json=body)

    assert response.status_code == 503


@pytest.mark.parametrize(
    ("section_path", "expected"),
    [
        ("4 › 4.2 Enhanced Due Diligence", "kb://compliance/CMP-SOP-004#4.2"),  # noqa: RUF001
        ("Appendix A", "kb://compliance/CMP-SOP-004"),
        (None, "kb://compliance/CMP-SOP-004"),
    ],
)
def test_a_citation_points_at_the_section_number_when_there_is_one(
    section_path: str | None, expected: str
) -> None:
    assert citation("compliance", "CMP-SOP-004", section_path) == expected
