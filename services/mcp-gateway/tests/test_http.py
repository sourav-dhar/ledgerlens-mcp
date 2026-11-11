"""HTTP surface: probes and the Streamable HTTP endpoint."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from mcp_gateway import __version__
from mcp_gateway.app import create_app
from mcp_gateway.settings import Settings

pytestmark = pytest.mark.anyio

ACCEPT_BOTH = {"Accept": "application/json, text/event-stream"}


@pytest.fixture
async def http() -> AsyncIterator[AsyncClient]:
    app = create_app(Settings())
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c,
    ):
        yield c


@pytest.mark.parametrize("path", ["/healthz", "/readyz"])
async def test_probes(http: AsyncClient, path: str) -> None:
    response = await http.get(path)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "mcp-gateway", "version": __version__}


async def test_initialize_over_streamable_http_returns_plain_json(http: AsyncClient) -> None:
    response = await http.post(
        "/mcp",
        headers=ACCEPT_BOTH,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0"},
            },
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["result"]["serverInfo"]["name"] == "LedgerLens"


async def test_malformed_json_rpc_is_rejected(http: AsyncClient) -> None:
    response = await http.post("/mcp", headers=ACCEPT_BOTH, content=b"{not json")

    assert response.status_code in {400, 422}
