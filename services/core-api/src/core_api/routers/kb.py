"""`/v1/kb`: search the knowledge base and read one document, within the caller's ceiling."""

import re
from typing import Annotated, Any

from fastapi import APIRouter, Query

from core_api.deps import CallerDep, DatabaseDep, require
from core_api.errors import InvalidArgumentError, NotFoundError
from core_api.repositories.kb import KbRepository
from core_api.schemas.kb import KbDocument, SearchResults
from kosha_domain.vocabulary import Department

router = APIRouter(prefix="/v1/kb", tags=["knowledge base"])

_DOC_CODE = re.compile(r"^[A-Z]{2,4}-[A-Z]{2,5}-[0-9]{3}$")

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"description": "Invalid argument"},
    503: {"description": "Database unavailable; retry shortly"},
    504: {"description": "Deadline exceeded"},
}


@router.get("/search", summary="Search the knowledge base", responses=_ERRORS)
async def search_knowledge_base(
    caller: CallerDep,
    database: DatabaseDep,
    q: Annotated[str, Query(min_length=2, max_length=200, description="Words or a quoted phrase.")],
    department: Annotated[list[Department] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> SearchResults:
    """Passages from effective documents, best first; nothing above the caller's ceiling."""
    async with require(database).unit_of_work(caller, read_only=True) as conn:
        hits = await KbRepository(conn).search(q, departments=department or (), limit=limit)
    return SearchResults(retrieval="full_text", results=hits)


@router.get(
    "/documents/{doc_code}",
    summary="Get a knowledge-base document",
    responses={**_ERRORS, 404: {"description": "No such document within the caller's ceiling"}},
)
async def get_document(
    doc_code: str,
    caller: CallerDep,
    database: DatabaseDep,
    version: Annotated[
        str | None,
        Query(pattern=r"^[0-9]+(\.[0-9]+)*$", description="Defaults to the effective version."),
    ] = None,
) -> KbDocument:
    """The document with its chunks in order. Above the ceiling it reads as missing."""
    if not _DOC_CODE.match(doc_code):
        msg = f"{doc_code!r} is not a document code such as CMP-SOP-004"
        raise InvalidArgumentError(msg)
    async with require(database).unit_of_work(caller, read_only=True) as conn:
        document = await KbRepository(conn).document(doc_code, version)
    if document is None:
        # The same answer whether the document is missing or above the ceiling, so a
        # caller cannot probe for documents they may not read.
        msg = f"document {doc_code} not found"
        raise NotFoundError(msg)
    return document
