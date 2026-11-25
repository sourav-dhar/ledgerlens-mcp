"""KYC tools end to end: masking on real rows, and a PAN reveal that core-api audits.

A reveal is the most sensitive path through the gateway: core-api opens a sealed PAN with
the keyring (ADR 0014) and records the unmasking in the same transaction. These tests prove
the reveal happens only when asked for, and that each one leaves exactly one record.
"""

from collections.abc import AsyncIterator
from typing import Any

import db_rows as rows
import httpx
import psycopg
import pytest
from fastapi import FastAPI
from fastmcp import Client
from gateway_harness import access_token, gateway

from core_api.app import create_app
from core_api.settings import Settings as CoreApiSettings
from kosha_domain.vault import LOCAL_PASSPHRASE, LocalKeyring, PanVault
from mcp_gateway.auth.scopes import Role

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

VAULT = PanVault(LocalKeyring(LOCAL_PASSPHRASE))
PAN = "ABCPS1234D"


@pytest.fixture
async def core_api_app(api_settings: CoreApiSettings) -> AsyncIterator[FastAPI]:
    app = create_app(api_settings)
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
def customer_id(committed: psycopg.Connection) -> str:
    """A Customer whose KYC profile holds a sealed PAN and an Aadhaar's last four."""
    customer_id = rows.customer(committed)
    rows.kyc_profile(
        committed,
        customer_id,
        pan_token=VAULT.encrypt(PAN, customer_id=customer_id),
        pan_last4=PAN[-4:],
        aadhaar_last4="4821",
    )
    return customer_id


async def _status(app: FastAPI, role: Role, args: dict[str, Any]) -> dict[str, Any]:
    async with Client(gateway(httpx.ASGITransport(app=app), access_token(role))) as client:
        result = await client.call_tool("get_kyc_status", args, raise_on_error=False)
    assert not result.is_error, result.content
    assert result.structured_content is not None
    return result.structured_content


def _unmaskings(db: psycopg.Connection, customer_id: str) -> list[tuple[object, ...]]:
    return db.execute(
        "SELECT actor_sub, tool_name, pii_unmasked FROM ops.audit_log WHERE %s = ANY(resource_ids)",
        [customer_id],
    ).fetchall()


async def test_a_status_check_keeps_the_pan_masked_and_unmasks_nothing(
    core_api_app: FastAPI, committed: psycopg.Connection, customer_id: str
) -> None:
    status = await _status(core_api_app, Role.COMPLIANCE_OFFICER, {"customer_id": customer_id})

    assert (status["pan"], status["aadhaar"]) == ("******234D", "XXXX XXXX 4821")
    assert status["kyc_status"] == "verified"
    assert _unmaskings(committed, customer_id) == []


async def test_a_reveal_returns_the_full_pan_and_leaves_one_audit_record(
    core_api_app: FastAPI, committed: psycopg.Connection, customer_id: str
) -> None:
    status = await _status(
        core_api_app, Role.COMPLIANCE_OFFICER, {"customer_id": customer_id, "reveal_pan": True}
    )

    assert status["pan"] == PAN
    assert status["aadhaar"] == "XXXX XXXX 4821"
    assert _unmaskings(committed, customer_id) == [("staff-0042", "unmask_pan", True)]
