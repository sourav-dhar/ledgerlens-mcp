"""Knowledge-base retrieval. Row-level security does the ceiling: no query here filters by it.

Every statement runs as ``kosha_app`` with ``kosha.kb_ceiling`` set for the transaction, and
the ``kb.documents`` and ``kb.chunks`` policies hide rows above it. A query bug therefore
cannot leak a restricted document; it can only fail to find one.
"""

import re
from collections.abc import Sequence

from core_api.db import Connection
from core_api.schemas.kb import DocumentChunk, KbDocument, SearchHit
from kosha_domain.vocabulary import Department

# The full-text half of the hybrid query in LLD rag-pipeline §2; vector hits and RRF join
# it once ingestion has embedded the corpus.
_SEARCH = """
    WITH params AS (SELECT websearch_to_tsquery('english', %(q)s) AS tsq)
    SELECT d.doc_code, d.title, d.version, d.effective_date, d.department,
           c.classification, c.section_path, c.content,
           ts_rank_cd(c.tsv, p.tsq)::float8 AS score
    FROM kb.chunks c
    JOIN kb.documents d USING (doc_id)
    CROSS JOIN params p
    WHERE c.tsv @@ p.tsq
      AND d.status = 'effective'
      AND (%(departments)s::text[] IS NULL OR d.department::text = ANY(%(departments)s))
    ORDER BY score DESC, d.doc_code, c.chunk_index
    LIMIT %(limit)s
"""

_DOCUMENT = """
    SELECT doc_id, doc_code, title, department, doc_type, version, status, effective_date,
           review_due, owner_role, classification, regulatory_refs, tags
    FROM kb.documents
    WHERE doc_code = %(doc_code)s
      AND (version = %(version)s OR (%(version)s::text IS NULL AND status = 'effective'))
"""

_CHUNKS = """
    SELECT chunk_index, section_path, content
    FROM kb.chunks
    WHERE doc_id = %s
    ORDER BY chunk_index
"""

_SECTION_NUMBER = re.compile(r"^\s*(\d+(?:\.\d+)*)\b")


def citation(department: str, doc_code: str, section_path: str | None) -> str:
    """``kb://{department}/{doc_code}``, with ``#{n.n}`` when the innermost section is numbered."""
    base = f"kb://{department}/{doc_code}"
    if section_path is None:
        return base
    innermost = section_path.split("›")[-1]  # noqa: RUF001 — plan v0.2's separator
    match = _SECTION_NUMBER.match(innermost)
    return f"{base}#{match.group(1)}" if match else base


class KbRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    async def search(
        self, q: str, *, departments: Sequence[Department], limit: int
    ) -> list[SearchHit]:
        params = {"q": q, "departments": [d.value for d in departments] or None, "limit": limit}
        found = await (await self._conn.execute(_SEARCH, params)).fetchall()
        return [
            SearchHit.model_validate(
                r | {"citation": citation(r["department"], r["doc_code"], r["section_path"])}
            )
            for r in found
        ]

    async def document(self, doc_code: str, version: str | None) -> KbDocument | None:
        params = {"doc_code": doc_code, "version": version}
        row = await (await self._conn.execute(_DOCUMENT, params)).fetchone()
        if row is None:
            return None
        chunks = await (await self._conn.execute(_CHUNKS, [row["doc_id"]])).fetchall()
        return KbDocument.model_validate(
            row | {"chunks": [DocumentChunk.model_validate(c) for c in chunks]}
        )
