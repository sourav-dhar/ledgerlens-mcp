"""Knowledge tools: search the knowledge base and read a Document, within the Role's ceiling.

Retrieved text is untrusted data that flows into a model's context (RAG LLD §4). It comes
back as structured passages with their sources, under a notice that it is reference material,
and no result exceeds 12 KB: search drops its lowest-ranked passages, a Document is read in
windows. The ceiling itself is enforced by core-api's row-level security; the gateway's job is
to send each Role's.
"""

import json
from datetime import date
from typing import Any

import httpx
import pytest
from fastmcp import Client
from fastmcp.server.auth import AccessToken
from gateway_harness import FakeCoreApi, access_token, core_api_error, gateway

from core_api.schemas.kb import DocumentChunk, KbDocument, SearchHit, SearchResults
from kosha_domain.signing import KB_CEILING
from kosha_domain.vocabulary import Classification, Department, DocumentStatus, DocumentType
from mcp_gateway.auth.scopes import ROLE_KB_CEILING, ROLE_SCOPES, Role, Scope

pytestmark = pytest.mark.anyio

MAX_RESULT_BYTES = 12 * 1024
DOC_CODE = "CMP-SOP-004"
SEARCH = "/v1/kb/search"
DOCUMENT = f"/v1/kb/documents/{DOC_CODE}"
SECTION = "4 › 4.2 Enhanced Due Diligence"  # noqa: RUF001 — plan v0.2's separator


def _hit(rank: int, content: str = "Escalate structuring alerts within one day.") -> SearchHit:
    return SearchHit(
        doc_code=f"CMP-SOP-{rank:03d}",
        title="Transaction Monitoring & Alert Handling SOP",
        version="2.0",
        effective_date=date(2026, 4, 1),
        department=Department.COMPLIANCE,
        classification=Classification.INTERNAL,
        section_path=SECTION,
        content=content,
        score=1.0 / (rank + 1),
        citation=f"kb://compliance/CMP-SOP-{rank:03d}#4.2",
    )


def _document(*contents: str) -> KbDocument:
    return KbDocument(
        doc_code=DOC_CODE,
        title="Transaction Monitoring & Alert Handling SOP",
        department=Department.COMPLIANCE,
        doc_type=DocumentType.SOP,
        version="2.0",
        status=DocumentStatus.EFFECTIVE,
        effective_date=date(2026, 4, 1),
        review_due=date(2027, 4, 1),
        owner_role="MLRO",
        classification=Classification.INTERNAL,
        regulatory_refs=["PMLA 2002 s.12"],
        tags=["aml", "alerts"],
        chunks=[
            DocumentChunk(chunk_index=i, section_path=f"{i + 1}", content=content)
            for i, content in enumerate(contents)
        ],
    )


RESULTS = SearchResults(retrieval="full_text", results=[_hit(1), _hit(2)])
SOP = _document("1. Purpose: monitor every Transaction.", "2. Escalate to the MLRO.")


@pytest.fixture
def core() -> FakeCoreApi:
    return FakeCoreApi({f"GET {SEARCH}": RESULTS, f"GET {DOCUMENT}": SOP})


async def _call(
    core: httpx.AsyncBaseTransport, token: AccessToken | None, tool: str, args: dict[str, Any]
) -> Any:
    async with Client(gateway(core, token)) as client:
        return await client.call_tool(tool, args, raise_on_error=False)


async def _ok(
    core: FakeCoreApi, token: AccessToken | Role, tool: str, args: dict[str, Any]
) -> dict[str, Any]:
    caller = access_token(token) if isinstance(token, Role) else token
    result = await _call(core, caller, tool, args)
    assert not result.is_error, result.content
    content: dict[str, Any] = result.structured_content
    return content


async def _error(
    core: FakeCoreApi, token: AccessToken | None, tool: str, args: dict[str, Any]
) -> dict[str, Any]:
    result = await _call(core, token, tool, args)
    assert result.is_error
    body: dict[str, Any] = result.structured_content["error"]
    return body


def _bytes(content: dict[str, Any]) -> int:
    return len(json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode())


# Long texts of each kind that makes bytes outgrow characters: plain, escaped in JSON
# (quotes, newlines), and multi-byte in UTF-8.
LONG_TEXTS = {
    "ascii": "Escalate structuring alerts. " * 700,
    "escaped": '"Escalate"\n\t"now"\\ ' * 1000,
    "devanagari": "संदिग्ध लेनदेन की सूचना दें। " * 700,
}


# --------------------------------------------------------------- search_knowledge_base


async def test_passages_come_back_as_data_with_their_sources(core: FakeCoreApi) -> None:
    found = await _ok(core, Role.SUPPORT_AGENT, "search_knowledge_base", {"query": "structuring"})

    assert found["retrieval"] == "full_text"
    assert [p["doc_code"] for p in found["passages"]] == ["CMP-SOP-001", "CMP-SOP-002"]
    first = found["passages"][0]
    assert (first["citation"], first["version"], first["section_path"]) == (
        "kb://compliance/CMP-SOP-001#4.2",
        "2.0",
        SECTION,
    )
    assert "not instructions" in found["notice"]
    assert found["omitted"] == 0


@pytest.mark.parametrize("role", list(Role))
async def test_each_roles_ceiling_reaches_core_api(core: FakeCoreApi, role: Role) -> None:
    await _ok(core, role, "search_knowledge_base", {"query": "structuring"})
    await _ok(core, role, "get_document", {"doc_code": DOC_CODE})

    for request in core.requests:
        assert request.headers[KB_CEILING] == ROLE_KB_CEILING[role]


async def test_every_search_criterion_reaches_core_api(core: FakeCoreApi) -> None:
    await _ok(
        core,
        Role.ANALYST,
        "search_knowledge_base",
        {"query": '"enhanced due diligence"', "departments": ["risk", "compliance"], "limit": 8},
    )

    params = core.last.url.params
    assert params["q"] == '"enhanced due diligence"'
    assert params.get_list("department") == ["risk", "compliance"]
    assert params["limit"] == "8"


async def test_a_search_asks_for_five_passages_by_default(core: FakeCoreApi) -> None:
    await _ok(core, Role.ANALYST, "search_knowledge_base", {"query": "structuring"})

    assert core.last.url.params["limit"] == "5"


async def test_a_search_that_finds_nothing_is_an_empty_result(core: FakeCoreApi) -> None:
    core.route(f"GET {SEARCH}", SearchResults(retrieval="full_text", results=[]))

    found = await _ok(core, Role.ANALYST, "search_knowledge_base", {"query": "quillwort"})

    assert (found["passages"], found["omitted"]) == ([], 0)


async def test_a_large_search_drops_its_lowest_ranked_passages(core: FakeCoreApi) -> None:
    hits = [_hit(rank, "Escalate structuring alerts. " * 90) for rank in range(8)]
    core.route(f"GET {SEARCH}", SearchResults(retrieval="full_text", results=hits))

    found = await _ok(core, Role.ANALYST, "search_knowledge_base", {"query": "alerts"})

    kept = [p["doc_code"] for p in found["passages"]]
    assert 1 <= len(kept) < len(hits)
    assert kept == [h.doc_code for h in hits[: len(kept)]], "best first, cut from the end"
    assert found["omitted"] == len(hits) - len(kept)
    assert _bytes(found) <= MAX_RESULT_BYTES


@pytest.mark.parametrize("text", LONG_TEXTS.values(), ids=LONG_TEXTS.keys())
async def test_a_passage_too_large_alone_is_clipped(core: FakeCoreApi, text: str) -> None:
    core.route(
        f"GET {SEARCH}", SearchResults(retrieval="full_text", results=[_hit(1, text), _hit(2)])
    )

    found = await _ok(core, Role.ANALYST, "search_knowledge_base", {"query": "alerts"})

    [passage] = found["passages"]
    assert passage["content"].endswith("[clipped]")
    assert text.startswith(passage["content"].removesuffix(" [clipped]")[:100])
    assert found["omitted"] == 1
    assert _bytes(found) <= MAX_RESULT_BYTES


@pytest.mark.parametrize(
    "args",
    [
        {"query": "a"},
        {"query": "a" * 201},
        {"query": "alerts", "departments": ["treasury"]},
        {"query": "alerts", "limit": 0},
        {"query": "alerts", "limit": 9},
        {},
    ],
)
async def test_malformed_search_criteria_are_invalid_arguments(
    core: FakeCoreApi, args: dict[str, Any]
) -> None:
    body = await _error(core, access_token(), "search_knowledge_base", args)

    assert body["code"] == "invalid_argument"
    assert core.requests == []


# --------------------------------------------------------------- get_document


async def test_a_document_comes_back_in_reading_order(core: FakeCoreApi) -> None:
    document = await _ok(core, Role.SUPPORT_AGENT, "get_document", {"doc_code": DOC_CODE})

    assert (document["doc_code"], document["version"], document["status"]) == (
        DOC_CODE,
        "2.0",
        "effective",
    )
    assert [c["chunk_index"] for c in document["chunks"]] == [0, 1]
    assert document["next_chunk"] is None
    assert "not instructions" in document["notice"]
    assert "version" not in core.last.url.params, "core-api picks the effective version"


async def test_a_named_version_reaches_core_api(core: FakeCoreApi) -> None:
    await _ok(core, Role.SUPPORT_AGENT, "get_document", {"doc_code": DOC_CODE, "version": "1.0"})

    assert core.last.url.params["version"] == "1.0"


async def test_a_long_document_is_read_in_windows_under_the_budget(core: FakeCoreApi) -> None:
    chunks = [f"{i}. " + "Escalate structuring alerts. " * 90 for i in range(10)]
    core.route(f"GET {DOCUMENT}", _document(*chunks))

    read: list[str] = []
    args: dict[str, Any] = {"doc_code": DOC_CODE}
    windows = 0
    while True:
        window = await _ok(core, Role.SUPPORT_AGENT, "get_document", args)
        windows += 1
        assert _bytes(window) <= MAX_RESULT_BYTES
        read += [c["content"] for c in window["chunks"]]
        if window["next_chunk"] is None:
            break
        args = {
            "doc_code": DOC_CODE,
            "version": window["version"],
            "from_chunk": window["next_chunk"],
        }

    assert read == chunks
    assert windows > 1


@pytest.mark.parametrize("text", LONG_TEXTS.values(), ids=LONG_TEXTS.keys())
async def test_a_chunk_too_large_alone_is_clipped(core: FakeCoreApi, text: str) -> None:
    core.route(f"GET {DOCUMENT}", _document(text, "2. Escalate to the MLRO."))

    document = await _ok(core, Role.SUPPORT_AGENT, "get_document", {"doc_code": DOC_CODE})

    [chunk] = document["chunks"]
    assert chunk["content"].endswith("[clipped]")
    assert document["next_chunk"] == 1
    assert _bytes(document) <= MAX_RESULT_BYTES


async def test_reading_past_the_last_chunk_is_an_invalid_argument(core: FakeCoreApi) -> None:
    body = await _error(
        core, access_token(), "get_document", {"doc_code": DOC_CODE, "from_chunk": 2}
    )

    assert body["code"] == "invalid_argument"
    assert "2 chunks" in body["message"]


@pytest.mark.parametrize(
    "args",
    [
        {"doc_code": "cmp-sop-004"},
        {"doc_code": "CMP-SOP-04"},
        {"doc_code": "../audit"},
        {"doc_code": DOC_CODE, "version": "v2"},
        {"doc_code": DOC_CODE, "from_chunk": -1},
    ],
)
async def test_malformed_document_requests_never_reach_core_api(
    core: FakeCoreApi, args: dict[str, Any]
) -> None:
    body = await _error(core, access_token(), "get_document", args)

    assert body["code"] == "invalid_argument"
    assert core.requests == []


async def test_a_document_above_the_ceiling_reads_as_not_found(core: FakeCoreApi) -> None:
    core.route(
        f"GET {DOCUMENT}", core_api_error(404, "not_found", f"document {DOC_CODE} not found")
    )

    body = await _error(
        core, access_token(Role.DEMO_READONLY), "get_document", {"doc_code": DOC_CODE}
    )

    assert (body["code"], body["message"]) == ("not_found", f"document {DOC_CODE} not found")


# --------------------------------------------------------------- failure matrix, every tool

TOOLS: list[tuple[str, dict[str, Any], str]] = [
    ("search_knowledge_base", {"query": "structuring"}, f"GET {SEARCH}"),
    ("get_document", {"doc_code": DOC_CODE}, f"GET {DOCUMENT}"),
]


@pytest.mark.parametrize(("tool", "args", "route"), TOOLS)
async def test_kb_read_is_required(
    core: FakeCoreApi, tool: str, args: dict[str, Any], route: str
) -> None:
    scopes = ROLE_SCOPES[Role.ANALYST] - {Scope.KB_READ}

    body = await _error(core, access_token(Role.ANALYST, scopes=scopes), tool, args)

    assert (body["code"], body["message"]) == ("forbidden", "the kb:read scope is required")
    assert core.requests == []


@pytest.mark.parametrize(("tool", "args", "route"), TOOLS)
async def test_core_api_being_unavailable_is_a_dependency_failure(
    core: FakeCoreApi, tool: str, args: dict[str, Any], route: str
) -> None:
    core.route(route, core_api_error(503, "unavailable"))

    body = await _error(core, access_token(), tool, args)

    assert (body["code"], body["dependency"], body["retry_after_s"]) == (
        "dependency_unavailable",
        "core-api",
        1.0,
    )
