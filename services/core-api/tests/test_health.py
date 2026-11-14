from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from core_api import __version__
from core_api.app import create_app
from core_api.settings import Settings

pytestmark = pytest.mark.anyio


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(Settings())
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c,
    ):
        yield c


async def test_liveness_reports_ok_with_identity(client: AsyncClient) -> None:
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "core-api", "version": __version__}


async def test_without_a_database_the_service_is_not_ready(client: AsyncClient) -> None:
    response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert response.json() == {
        "status": "unavailable",
        "service": "core-api",
        "version": __version__,
        "schema_revision": None,
    }


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
    monkeypatch.setenv("DATABASE_URL", "postgresql://kosha@db/kosha")

    settings = Settings()

    assert (settings.host, settings.port) == ("0.0.0.0", 8080)
    assert settings.database_url is not None
    assert settings.database_url.get_secret_value() == "postgresql://kosha@db/kosha"


def test_the_database_url_never_appears_in_settings_output() -> None:
    settings = Settings(database_url=SecretStr("postgresql://kosha:s3cret@db/kosha"))

    assert "s3cret" not in repr(settings)
