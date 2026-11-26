"""Knowledge tools end to end: the Role's ceiling enforced by real row-level security.

Unit tests prove the gateway sends each Role's ceiling; these prove what that ceiling does on
real rows (a Document above it is neither found nor readable) and that a real Document is
read in windows, in chunk order, to its last chunk.
"""

import secrets
import string
from typing import Any

import db_rows as rows
import httpx
import psycopg
import pytest
from fastapi import FastAPI
from fastmcp import Client
from gateway_harness import access_token, gateway

from mcp_gateway.auth.scopes import Role

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
def word() -> str:
    """A search word no other test uses: committed rows are shared by the whole session."""
    return "".join(secrets.choice(string.ascii_lowercase) for _ in range(10))


def _document(db: psycopg.Connection, classification: str, *contents: str) -> str:
    """A Document's code, its chunks in order."""
    doc_id = rows.document(db, classification=classification)
    for index, content in enumerate(contents):
        rows.chunk(db, doc_id, classification, chunk_index=index, content=content)
    [(doc_code,)] = db.execute(
        "SELECT doc_code FROM kb.documents WHERE doc_id = %s", [doc_id]
    ).fetchall()
    return str(doc_code)


async def _call(app: FastAPI, role: Role, tool: str, args: dict[str, Any]) -> Any:
    async with Client(gateway(httpx.ASGITransport(app=app), access_token(role))) as client:
        return await client.call_tool(tool, args, raise_on_error=False)


async def _ok(app: FastAPI, role: Role, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    result = await _call(app, role, tool, args)
    assert not result.is_error, result.content
    assert result.structured_content is not None
    return result.structured_content


async def test_a_document_above_the_ceiling_is_neither_found_nor_read(
    core_api_app: FastAPI, committed: psycopg.Connection, word: str
) -> None:
    doc_code = _document(committed, "confidential", f"Escalate {word} alerts to the MLRO.")

    analyst = await _ok(core_api_app, Role.ANALYST, "search_knowledge_base", {"query": word})
    support = await _ok(core_api_app, Role.SUPPORT_AGENT, "search_knowledge_base", {"query": word})
    hidden = await _call(core_api_app, Role.SUPPORT_AGENT, "get_document", {"doc_code": doc_code})

    assert [p["doc_code"] for p in analyst["passages"]] == [doc_code]
    assert analyst["passages"][0]["citation"].startswith(f"kb://compliance/{doc_code}#")
    assert support["passages"] == []
    assert hidden.is_error
    assert hidden.structured_content["error"]["code"] == "not_found"


async def test_a_long_document_is_read_in_windows_to_its_last_chunk(
    core_api_app: FastAPI, committed: psycopg.Connection, word: str
) -> None:
    contents = [f"{i}. Escalate {word} alerts. " + "Record the reason. " * 150 for i in range(6)]
    doc_code = _document(committed, "internal", *contents)

    read: list[str] = []
    windows = 0
    args: dict[str, Any] = {"doc_code": doc_code}
    while True:
        window = await _ok(core_api_app, Role.SUPPORT_AGENT, "get_document", args)
        windows += 1
        read += [chunk["content"] for chunk in window["chunks"]]
        if window["next_chunk"] is None:
            break
        args = {
            "doc_code": doc_code,
            "version": window["version"],
            "from_chunk": window["next_chunk"],
        }

    assert read == contents
    assert windows > 1, "about 17 KB of text cannot come back in one 12 KB result"
