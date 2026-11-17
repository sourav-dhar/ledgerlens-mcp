"""Unmasking a PAN opens its token and leaves an audit record in the same transaction."""

import db_rows as rows
import psycopg
import pytest
from httpx import AsyncClient
from signed import SignedAs

from kosha_domain.ids import IdPrefix, new_id
from kosha_domain.vault import LOCAL_PASSPHRASE, LocalKeyring, PanVault, VaultError

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

VAULT = PanVault(LocalKeyring(LOCAL_PASSPHRASE))
COMPLIANCE = SignedAs("compliance-1", "restricted")


def _with_pan(db: psycopg.Connection, pan: str = "ABCPS1234D") -> str:
    customer_id = rows.customer(db)
    rows.kyc_profile(
        db,
        customer_id,
        pan_token=VAULT.encrypt(pan, customer_id=customer_id),
        pan_last4=pan[-4:],
    )
    return customer_id


def _unmaskings(db: psycopg.Connection, customer_id: str) -> list[tuple[object, ...]]:
    return db.execute(
        "SELECT actor_sub, tool_name, pii_unmasked, outcome::text FROM ops.audit_log"
        " WHERE %s = ANY(resource_ids)",
        [customer_id],
    ).fetchall()


async def test_the_full_pan_is_returned_and_the_unmasking_is_audited(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    customer_id = _with_pan(committed)

    response = await api.get(f"/v1/customers/{customer_id}/kyc/pan", auth=COMPLIANCE)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["customer_id"], body["pan"], body["pan_last4"]) == (
        customer_id,
        "ABCPS1234D",
        "234D",
    )
    assert _unmaskings(committed, customer_id) == [("compliance-1", "unmask_pan", True, "success")]


async def test_a_customer_without_a_pan_on_file_is_not_found(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    customer_id = rows.customer(committed)
    rows.kyc_profile(committed, customer_id, pan_token=None, pan_last4=None)

    response = await api.get(f"/v1/customers/{customer_id}/kyc/pan", auth=COMPLIANCE)

    assert response.status_code == 404
    assert "no PAN on file" in response.json()["error"]["message"]
    assert _unmaskings(committed, customer_id) == []


async def test_an_unknown_customer_is_not_found(api: AsyncClient) -> None:
    response = await api.get(f"/v1/customers/{new_id(IdPrefix.CUSTOMER)}/kyc/pan", auth=COMPLIANCE)

    assert response.status_code == 404


async def test_a_token_copied_from_another_customer_is_refused_and_not_audited(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    victim = _with_pan(committed)
    token = committed.execute(
        "SELECT pan_token FROM kyc.kyc_profiles WHERE customer_id = %s", [victim]
    ).fetchone()
    assert token is not None
    thief = rows.customer(committed)
    rows.kyc_profile(committed, thief, pan_token=token[0], pan_last4="234D")

    with pytest.raises(VaultError):
        await api.get(f"/v1/customers/{thief}/kyc/pan", auth=COMPLIANCE)

    assert _unmaskings(committed, thief) == []
