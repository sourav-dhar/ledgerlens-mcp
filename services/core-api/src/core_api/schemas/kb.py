"""Knowledge-base results and documents as the API returns them."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from kosha_domain.vocabulary import Classification, Department, DocumentStatus, DocumentType


class SearchHit(BaseModel):
    doc_code: str
    title: str
    version: str
    effective_date: date
    department: Department
    classification: Classification
    section_path: str | None
    content: str
    score: float
    citation: str
    """``kb://{department}/{doc_code}#{section}``, the form the gateway's resources use."""


class SearchResults(BaseModel):
    retrieval: Literal["full_text"]
    """Full-text only until ingestion embeds the corpus (P5); then ``hybrid``."""
    results: list[SearchHit]
    """Best first. Only effective versions, and only up to the caller's ceiling."""


class DocumentChunk(BaseModel):
    chunk_index: int
    section_path: str | None
    content: str


class KbDocument(BaseModel):
    doc_code: str
    title: str
    department: Department
    doc_type: DocumentType
    version: str
    status: DocumentStatus
    effective_date: date
    review_due: date | None
    owner_role: str | None
    classification: Classification
    regulatory_refs: list[str]
    tags: list[str]
    chunks: list[DocumentChunk]
    """In document order."""
