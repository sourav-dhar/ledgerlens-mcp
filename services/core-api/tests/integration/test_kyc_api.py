"""A Customer's KYC is read as their current profile with its history, and document metadata."""

from datetime import UTC, datetime, timedelta

import db_rows as rows
import psycopg
import pytest
from httpx import AsyncClient

from kosha_domain.ids import IdPrefix, new_id

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

NOW = datetime.now(UTC).replace(microsecond=0)


async def test_kyc_status_is_the_newest_profile_with_its_history(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    customer_id = rows.customer(committed)
    rows.kyc_profile(
        committed, customer_id, kyc_status="expired", created_at=NOW - timedelta(days=900)
    )
    current = rows.kyc_profile(
        committed,
        customer_id,
        kyc_type="v_cip",
        kyc_status="re_kyc_due",
        risk_category="medium",
        pep_flag=True,
        next_review_due=(NOW + timedelta(days=30)).date(),
        created_at=NOW - timedelta(days=10),
    )
    for days, (src, dst) in enumerate([(None, "in_review"), ("in_review", "verified")]):
        rows.kyc_event(
            committed,
            current,
            from_status=src,
            to_status=dst,
            occurred_at=NOW - timedelta(days=10 - days),
        )

    response = await api.get(f"/v1/customers/{customer_id}/kyc")

    assert response.status_code == 200
    body = response.json()
    assert (body["kyc_id"], body["kyc_type"], body["kyc_status"]) == (
        current,
        "v_cip",
        "re_kyc_due",
    )
    assert (body["pan_last4"], body["aadhaar_last4"]) == ("234C", "4821")
    assert (body["risk_category"], body["pep_flag"]) == ("medium", True)
    assert [(e["from_status"], e["to_status"]) for e in body["events"]] == [
        (None, "in_review"),
        ("in_review", "verified"),
    ]


async def test_kyc_never_carries_pii_tokens(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    customer_id = rows.customer(committed)
    rows.kyc_profile(committed, customer_id)

    body = (await api.get(f"/v1/customers/{customer_id}/kyc")).json()

    assert not {"pan_token", "aadhaar_ref_token"} & body.keys()
    assert "kms:" not in str(body)
    assert "vault:" not in str(body)


async def test_a_customer_without_a_profile_has_no_kyc(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    customer_id = rows.customer(committed)

    response = await api.get(f"/v1/customers/{customer_id}/kyc")

    assert response.status_code == 404
    assert "no KYC profile" in response.json()["error"]["message"]


@pytest.mark.parametrize("suffix", ["kyc", "kyc/documents"])
async def test_an_unknown_customer_is_not_found(api: AsyncClient, suffix: str) -> None:
    response = await api.get(f"/v1/customers/{new_id(IdPrefix.CUSTOMER)}/{suffix}")

    assert response.status_code == 404
    assert "customer" in response.json()["error"]["message"]


async def test_documents_are_metadata_newest_first_across_profiles(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    customer_id = rows.customer(committed)
    old = rows.kyc_profile(committed, customer_id, kyc_status="expired")
    new = rows.kyc_profile(committed, customer_id)
    older_doc = rows.kyc_document(
        committed, (old, customer_id), status="expired", uploaded_at=NOW - timedelta(days=800)
    )
    newer_doc = rows.kyc_document(
        committed,
        (new, customer_id),
        doc_type="selfie",
        status="rejected",
        rejection_reason="Face not clearly visible",
        uploaded_at=NOW - timedelta(days=5),
    )

    response = await api.get(f"/v1/customers/{customer_id}/kyc/documents")

    assert response.status_code == 200
    documents = response.json()["documents"]
    assert [d["document_id"] for d in documents] == [newer_doc, older_doc]
    assert (documents[0]["doc_type"], documents[0]["rejection_reason"]) == (
        "selfie",
        "Face not clearly visible",
    )
    assert all("s3_key" not in d for d in documents)


async def test_a_customer_without_documents_has_an_empty_list(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    customer_id = rows.customer(committed)

    response = await api.get(f"/v1/customers/{customer_id}/kyc/documents")

    assert response.status_code == 200
    assert response.json() == {"documents": []}
