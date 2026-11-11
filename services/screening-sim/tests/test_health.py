from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from screening_sim import __version__
from screening_sim.app import create_app
from screening_sim.settings import Settings

pytestmark = pytest.mark.anyio


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(Settings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.parametrize("path", ["/healthz", "/readyz"])
async def test_probe_reports_ok_with_identity(client: AsyncClient, path: str) -> None:
    response = await client.get(path)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "screening-sim", "version": __version__}


async def test_unknown_route_is_404(client: AsyncClient) -> None:
    response = await client.get("/does-not-exist")

    assert response.status_code == 404


async def test_probes_are_documented_in_openapi(client: AsyncClient) -> None:
    paths = (await client.get("/openapi.json")).json()["paths"]

    assert {"/healthz", "/readyz"} <= paths.keys()


def test_settings_default_to_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOST", raising=False)

    assert Settings().host == "127.0.0.1"


def test_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "8080")

    settings = Settings()

    assert (settings.host, settings.port) == ("0.0.0.0", 8080)
