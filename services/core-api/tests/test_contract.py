"""The HTTP contract is a reviewed snapshot: any change to it shows up as a diff."""

import pytest
from httpx import ASGITransport, AsyncClient
from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.json import JSONSnapshotExtension

from core_api.app import create_app
from core_api.settings import Settings


@pytest.mark.anyio
async def test_the_openapi_contract_is_unchanged(snapshot: SnapshotAssertion) -> None:
    app = create_app(Settings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        document = (await client.get("/openapi.json")).json()
    del document["info"]["version"]  # bumped by every release, not a contract change

    assert document == snapshot(extension_class=JSONSnapshotExtension)
