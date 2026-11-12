"""Knowledge base: classification ceilings enforced by row-level security, and search columns."""

import db_rows as rows
import psycopg
import pytest
from psycopg import errors, sql

from kosha_domain.vocabulary import Classification

pytestmark = pytest.mark.integration

LEVELS = [c.value for c in Classification]


@pytest.fixture
def corpus(db: psycopg.Connection) -> dict[str, str]:
    """One document with one chunk per classification; returns chunk_id → classification."""
    chunks: dict[str, str] = {}
    for level in LEVELS:
        doc_id = rows.document(db, classification=level)
        chunks[rows.chunk(db, doc_id, level)] = level
    return chunks


def _visible(db: psycopg.Connection, table: str, ceiling: str | None) -> set[str]:
    """Classifications kosha_app can read with ``ceiling`` set for the transaction."""
    with db.transaction():
        db.execute("SET LOCAL ROLE kosha_app")
        if ceiling is not None:
            db.execute("SELECT set_config('kosha.kb_ceiling', %s, true)", [ceiling])
        query = sql.SQL("SELECT DISTINCT classification::text FROM {}").format(
            sql.Identifier("kb", table)
        )
        return {level for (level,) in db.execute(query).fetchall()}


@pytest.mark.parametrize("table", ["chunks", "documents"])
@pytest.mark.parametrize(
    ("ceiling", "expected"),
    [
        (None, {"public"}),
        ("", {"public"}),
        ("public", {"public"}),
        ("internal", {"public", "internal"}),
        ("confidential", {"public", "internal", "confidential"}),
        ("restricted", set(LEVELS)),
    ],
)
def test_the_application_sees_only_what_its_ceiling_allows(
    db: psycopg.Connection,
    corpus: dict[str, str],
    table: str,
    ceiling: str | None,
    expected: set[str],
) -> None:
    assert _visible(db, table, ceiling) == expected


def test_an_unknown_ceiling_fails_closed(db: psycopg.Connection, corpus: dict[str, str]) -> None:
    with pytest.raises(errors.InvalidTextRepresentation):
        _visible(db, "chunks", "top_secret")


def test_a_ceiling_ends_with_its_transaction(db: psycopg.Connection) -> None:
    db.execute("SELECT set_config('kosha.kb_ceiling', 'restricted', true)")
    db.rollback()

    row = db.execute("SELECT current_setting('kosha.kb_ceiling', true)").fetchone()

    assert row in {("",), (None,)}


def test_row_level_security_binds_the_table_owner_too(db: psycopg.Connection) -> None:
    rows_ = db.execute(
        "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class"
        " WHERE oid IN ('kb.chunks'::regclass, 'kb.documents'::regclass)"
    ).fetchall()

    assert sorted(rows_) == [("chunks", True, True), ("documents", True, True)]


def test_a_chunk_carries_its_documents_classification(db: psycopg.Connection) -> None:
    doc_id = rows.document(db, classification="internal")

    with pytest.raises(errors.ForeignKeyViolation), db.transaction():
        rows.chunk(db, doc_id, "public")


def test_reclassifying_a_document_reclassifies_its_chunks(db: psycopg.Connection) -> None:
    doc_id = rows.document(db, classification="internal")
    chunk_id = rows.chunk(db, doc_id, "internal")

    db.execute("UPDATE kb.documents SET classification = 'restricted' WHERE doc_id = %s", [doc_id])

    row = db.execute(
        "SELECT classification::text FROM kb.chunks WHERE chunk_id = %s", [chunk_id]
    ).fetchone()
    assert row == ("restricted",)


def test_only_one_version_of_a_document_is_effective(db: psycopg.Connection) -> None:
    rows.document(db, doc_code="CMP-SOP-004", version="1.0", status="superseded")
    rows.document(db, doc_code="CMP-SOP-004", version="2.0", status="effective")

    with pytest.raises(errors.UniqueViolation), db.transaction():
        rows.document(db, doc_code="CMP-SOP-004", version="2.1", status="effective")


def test_full_text_vector_is_generated_from_section_and_content(db: psycopg.Connection) -> None:
    chunk_id = rows.chunk(db, rows.document(db), "internal")

    row = db.execute(
        "SELECT tsv @@ to_tsquery('english', 'enhanced & structuring')"
        " FROM kb.chunks WHERE chunk_id = %s",
        [chunk_id],
    ).fetchone()

    assert row == (True,)


def test_embeddings_have_the_configured_dimensions(db: psycopg.Connection) -> None:
    doc_id = rows.document(db)
    rows.chunk(db, doc_id, "internal", embedding=str([0.01] * 1024))

    with pytest.raises(errors.DataException), db.transaction():
        rows.chunk(db, doc_id, "internal", embedding=str([0.01] * 1536))


def test_search_indexes_from_the_design_exist(db: psycopg.Connection) -> None:
    rows_ = db.execute(
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'kb'"
    ).fetchall()
    indexes = dict(rows_)

    assert "hnsw" in indexes["chunks_embedding_hnsw_idx"]
    assert "m='16'" in indexes["chunks_embedding_hnsw_idx"].replace(" ", "")
    assert "gin" in indexes["chunks_tsv_idx"]
