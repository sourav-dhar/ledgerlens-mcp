"""AML and insights input is validated before the database is touched."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from signed import TEST_KEY, SignedAs

from core_api.app import create_app
from core_api.repositories.insights import KOLKATA, month_starts
from core_api.settings import Settings
from kosha_domain.ids import IdPrefix, new_id

pytestmark = pytest.mark.anyio

NOW = datetime.now(UTC).isoformat()
INSIGHTS = f"/v1/accounts/{new_id(IdPrefix.ACCOUNT)}/insights"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(internal_signing_keys=SecretStr(TEST_KEY)))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", auth=SignedAs("analyst-7")
    ) as c:
        yield c


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/v1/aml/alerts/alr_123", {}),
        (f"/v1/aml/alerts/{new_id(IdPrefix.CUSTOMER)}", {}),
        ("/v1/aml/alerts", {"customer_id": "cus_123"}),
        ("/v1/aml/alerts", {"after_sla_due_at": NOW}),
        ("/v1/aml/alerts", {"after_alert_id": new_id(IdPrefix.AML_ALERT)}),
        ("/v1/aml/alerts", {"after_sla_due_at": NOW, "after_alert_id": "alr_1"}),
        ("/v1/accounts/acc_123/insights", {}),
    ],
)
async def test_malformed_ids_and_half_positions_are_invalid_arguments(
    client: AsyncClient, path: str, params: dict[str, Any]
) -> None:
    response = await client.get(path, params=params)

    assert response.status_code == 400, response.text


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/v1/aml/alerts", {"status": ["resolved"]}),
        ("/v1/aml/alerts", {"typology": ["phishing"]}),
        ("/v1/aml/alerts", {"limit": 101}),
        ("/v1/aml/alerts", {"after_sla_due_at": "2026-11-01T00:00:00"}),
        (INSIGHTS, {"months": 0}),
        (INSIGHTS, {"months": 13}),
    ],
)
async def test_malformed_parameters_are_rejected(
    client: AsyncClient, path: str, params: dict[str, Any]
) -> None:
    response = await client.get(path, params=params)

    assert response.status_code == 422


def test_months_are_kolkata_calendar_months_across_a_year_end() -> None:
    # 20:00 UTC on 31 Jan is 01:30 IST on 1 Feb.
    starts = month_starts(datetime(2027, 1, 31, 20, tzinfo=UTC), 3)

    assert [s.strftime("%Y-%m") for s in starts] == ["2026-12", "2027-01", "2027-02"]
    assert starts[-1] == datetime(2027, 2, 1, tzinfo=KOLKATA)
    assert starts[-1].astimezone(UTC) == datetime(2027, 1, 31, 18, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    "path", ["/v1/aml/alerts", f"/v1/aml/alerts/{new_id(IdPrefix.AML_ALERT)}", INSIGHTS]
)
async def test_valid_requests_without_a_database_are_unavailable(
    client: AsyncClient, path: str
) -> None:
    response = await client.get(path)

    assert response.status_code == 503
