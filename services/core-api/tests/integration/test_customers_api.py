"""Customers are found by name, CIF or mobile, and read as a profile with their Addresses."""

import db_rows as rows
import psycopg
import pytest
from httpx import AsyncClient

from core_api import __version__
from core_api.migrations import head
from kosha_domain.ids import IdPrefix, new_id

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def test_a_profile_carries_the_customer_and_their_addresses(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    customer_id = rows.customer(
        committed, first_name="Ananya", last_name="Iyer", email="ananya.iyer@example.com"
    )
    rows.address(
        committed,
        customer_id,
        city="Chennai",
        state="Tamil Nadu",
        state_code="33",
        pincode="600020",
    )

    response = await api.get(f"/v1/customers/{customer_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["customer_id"] == customer_id
    assert (body["first_name"], body["last_name"]) == ("Ananya", "Iyer")
    assert body["email"] == "ananya.iyer@example.com"
    assert (body["status"], body["segment"], body["date_of_birth"]) == (
        "active",
        "mass",
        "1990-04-12",
    )
    assert [(a["address_type"], a["city"], a["pincode"]) for a in body["addresses"]] == [
        ("permanent", "Chennai", "600020")
    ]


async def test_an_unknown_customer_is_not_found(api: AsyncClient) -> None:
    response = await api.get(f"/v1/customers/{new_id(IdPrefix.CUSTOMER)}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_customers_are_found_by_part_of_their_name_ignoring_case(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    wanted = rows.customer(committed, first_name="Zoravar", last_name="Sandhu")
    rows.customer(committed, first_name="Zoya", last_name="Qureshi")

    response = await api.get("/v1/customers", params={"name": "ravar sand"})

    assert response.status_code == 200
    assert [c["customer_id"] for c in response.json()["customers"]] == [wanted]


async def test_a_name_search_treats_wildcards_literally(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    rows.customer(committed, first_name="Percy", last_name="Wadia")

    response = await api.get("/v1/customers", params={"name": "%_"})

    assert response.json()["customers"] == []


async def test_customers_are_found_by_cif_number(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    customer_id = rows.customer(committed)
    cif = committed.execute(
        "SELECT cif_number FROM core.customers WHERE customer_id = %s", [customer_id]
    ).fetchone()
    assert cif is not None

    response = await api.get("/v1/customers", params={"cif_number": cif[0]})

    assert [c["customer_id"] for c in response.json()["customers"]] == [customer_id]


async def test_customers_are_found_by_the_last_four_digits_of_their_mobile(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    customer_id = rows.customer(committed, mobile="9123407316", last_name="Mobilefour")

    response = await api.get("/v1/customers", params={"mobile_last4": "7316", "name": "mobilefour"})

    found = response.json()["customers"]
    assert [c["customer_id"] for c in found] == [customer_id]
    assert found[0]["mobile"] == "9123407316"


async def test_a_search_returns_at_most_the_limit_in_name_order(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    for first in ("Chitra", "Anil", "Bhavna"):
        rows.customer(committed, first_name=first, last_name="Limitorder")

    response = await api.get("/v1/customers", params={"name": "limitorder", "limit": 2})

    assert [c["full_name"] for c in response.json()["customers"]] == [
        "Anil Limitorder",
        "Bhavna Limitorder",
    ]


async def test_readiness_reports_the_schema_revision(api: AsyncClient) -> None:
    response = await api.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "core-api",
        "version": __version__,
        "schema_revision": head(),
    }
