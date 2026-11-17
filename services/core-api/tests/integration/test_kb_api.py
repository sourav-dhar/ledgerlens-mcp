"""Knowledge-base search and reads see only effective documents within the caller's ceiling."""

from typing import Any

import db_rows as rows
import psycopg
import pytest
from httpx import AsyncClient
from signed import SignedAs

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

SUPPORT = SignedAs("support-7", "internal")
COMPLIANCE = SignedAs("compliance-1", "restricted")


def _doc(
    db: psycopg.Connection, word: str, classification: str = "internal", **overrides: Any
) -> str:
    """A document with one chunk that mentions ``word``, a token unique to the test."""
    doc_id = rows.document(db, classification=classification, **overrides)
    rows.chunk(
        db,
        doc_id,
        classification,
        chunk_index=0,
        section_path="4 › 4.2 Enhanced Due Diligence",  # noqa: RUF001 — plan v0.2's separator
        content=f"Escalate {word} alerts to the MLRO within one business day.",
    )
    return doc_id


async def _search(api: AsyncClient, auth: SignedAs, **params: Any) -> dict[str, Any]:
    response = await api.get("/v1/kb/search", params=params, auth=auth)
    assert response.status_code == 200, response.text
    return response.json()


async def test_search_finds_effective_chunks_with_citations(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    _doc(committed, "zephyrine", doc_code="CMP-SOP-901", title="Alert Handling SOP")

    body = await _search(api, SUPPORT, q="zephyrine alerts")

    assert body["retrieval"] == "full_text"
    [hit] = body["results"]
    assert (hit["doc_code"], hit["title"], hit["department"]) == (
        "CMP-SOP-901",
        "Alert Handling SOP",
        "compliance",
    )
    assert hit["citation"] == "kb://compliance/CMP-SOP-901#4.2"
    assert "zephyrine" in hit["content"]
    assert hit["score"] > 0


async def test_superseded_versions_are_not_searched(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    _doc(committed, "quillwort", doc_code="CMP-SOP-902", version="1.0", status="superseded")
    _doc(committed, "quillwort", doc_code="CMP-SOP-902", version="2.0")

    body = await _search(api, SUPPORT, q="quillwort")

    assert [(r["doc_code"], r["version"]) for r in body["results"]] == [("CMP-SOP-902", "2.0")]


@pytest.mark.parametrize(
    ("auth", "visible"),
    [
        (SignedAs("demo-1"), ["public"]),
        (SUPPORT, ["internal", "public"]),
        (COMPLIANCE, ["confidential", "internal", "public", "restricted"]),
    ],
    ids=["no ceiling", "internal", "restricted"],
)
async def test_search_sees_only_what_the_ceiling_allows(
    api: AsyncClient, committed: psycopg.Connection, auth: SignedAs, visible: list[str]
) -> None:
    for level in ("public", "internal", "confidential", "restricted"):
        _doc(committed, "marrowfat", classification=level)

    body = await _search(api, auth, q="marrowfat", limit=10)

    assert sorted(r["classification"] for r in body["results"]) == visible


async def test_search_filters_by_department_and_honours_the_limit(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    for _ in range(3):
        _doc(committed, "tamarisk")
    _doc(committed, "tamarisk", department="risk", doc_code="RSK-SOP-903")

    risk = await _search(api, SUPPORT, q="tamarisk", department=["risk"])
    limited = await _search(api, SUPPORT, q="tamarisk", limit=2)

    assert [r["doc_code"] for r in risk["results"]] == ["RSK-SOP-903"]
    assert len(limited["results"]) == 2


async def test_a_document_reads_as_its_effective_version_in_chunk_order(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    rows.document(committed, doc_code="CMP-POL-904", version="1.0", status="superseded")
    doc_id = rows.document(committed, doc_code="CMP-POL-904", version="1.1")
    for index in (1, 0):
        rows.chunk(committed, doc_id, "internal", chunk_index=index, content=f"Part {index}.")

    response = await api.get("/v1/kb/documents/CMP-POL-904", auth=SUPPORT)

    assert response.status_code == 200
    body = response.json()
    assert (body["doc_code"], body["version"], body["status"]) == (
        "CMP-POL-904",
        "1.1",
        "effective",
    )
    assert [c["content"] for c in body["chunks"]] == ["Part 0.", "Part 1."]


async def test_a_specific_version_can_still_be_read(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    rows.document(committed, doc_code="CMP-POL-905", version="1.0", status="superseded")
    rows.document(committed, doc_code="CMP-POL-905", version="2.0")

    response = await api.get(
        "/v1/kb/documents/CMP-POL-905", params={"version": "1.0"}, auth=SUPPORT
    )

    assert (response.json()["version"], response.json()["status"]) == ("1.0", "superseded")


async def test_a_document_above_the_ceiling_is_indistinguishable_from_a_missing_one(
    api: AsyncClient, committed: psycopg.Connection
) -> None:
    rows.document(committed, doc_code="LGL-POL-906", classification="restricted")

    hidden = await api.get("/v1/kb/documents/LGL-POL-906", auth=SUPPORT)
    missing = await api.get("/v1/kb/documents/LGL-POL-999", auth=SUPPORT)
    allowed = await api.get("/v1/kb/documents/LGL-POL-906", auth=COMPLIANCE)

    assert (hidden.status_code, missing.status_code, allowed.status_code) == (404, 404, 200)
    assert (
        hidden.json()["error"]["message"].replace("906", "999")
        == missing.json()["error"]["message"]
    )
