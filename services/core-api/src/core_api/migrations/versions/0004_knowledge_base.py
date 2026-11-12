"""Knowledge base: documents and chunks behind classification-ceiling row-level security.

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
    CREATE TYPE kb.department AS ENUM (
        'compliance', 'onboarding', 'legal', 'risk', 'customer_support', 'sales',
        'marketing', 'engineering', 'company'
    );
    CREATE TYPE kb.document_type AS ENUM (
        'policy', 'sop', 'runbook', 'playbook', 'api_reference', 'guideline', 'faq',
        'template'
    );
    CREATE TYPE kb.document_status AS ENUM ('draft', 'effective', 'superseded');
    -- Declaration order is the sensitivity order that row-level security compares.
    CREATE TYPE kb.classification AS ENUM ('public', 'internal', 'confidential', 'restricted');
    CREATE TYPE kb.source_format AS ENUM ('md', 'pdf', 'docx', 'html', 'openapi');

    CREATE TABLE kb.documents (
        doc_id text PRIMARY KEY CHECK (kosha.is_id(doc_id, 'doc')),
        doc_code text NOT NULL CHECK (doc_code ~ '^[A-Z]{2,4}-[A-Z]{2,5}-[0-9]{3}$'),
        department kb.department NOT NULL,
        title text NOT NULL,
        doc_type kb.document_type NOT NULL,
        version text NOT NULL,
        status kb.document_status NOT NULL,
        effective_date date NOT NULL,
        review_due date,
        owner_role text,
        approver text,
        classification kb.classification NOT NULL,
        source_format kb.source_format NOT NULL,
        s3_uri text,
        sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
        supersedes_doc_id text REFERENCES kb.documents,
        regulatory_refs text[] NOT NULL DEFAULT '{}',
        tags text[] NOT NULL DEFAULT '{}',
        UNIQUE (doc_code, version),
        -- Target of the chunks' composite key that keeps their classification in step.
        UNIQUE (doc_id, classification)
    );
    -- Retrieval must prefer the effective version; there is exactly one to prefer.
    CREATE UNIQUE INDEX documents_one_effective_version
        ON kb.documents (doc_code) WHERE status = 'effective';

    -- classification is denormalised from the document so RLS filters chunks directly.
    CREATE TABLE kb.chunks (
        chunk_id text PRIMARY KEY CHECK (kosha.is_id(chunk_id, 'chk')),
        doc_id text NOT NULL,
        classification kb.classification NOT NULL,
        chunk_index integer NOT NULL CHECK (chunk_index >= 0),
        section_path text,
        content text NOT NULL,
        token_count integer NOT NULL CHECK (token_count >= 0),
        -- text-embedding-3-large reduced to 1024 dimensions (ADR 0009); null until
        -- embedded, and full-text search still finds the chunk meanwhile.
        embedding vector(1024),
        tsv tsvector NOT NULL GENERATED ALWAYS AS (
            to_tsvector('english', coalesce(section_path, '') || ' ' || content)
        ) STORED,
        metadata jsonb NOT NULL DEFAULT '{}',
        UNIQUE (doc_id, chunk_index),
        FOREIGN KEY (doc_id, classification)
            REFERENCES kb.documents (doc_id, classification) ON UPDATE CASCADE
    );
    CREATE INDEX chunks_embedding_hnsw_idx ON kb.chunks
        USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
    CREATE INDEX chunks_tsv_idx ON kb.chunks USING gin (tsv);
    CREATE INDEX chunks_doc_classification_idx ON kb.chunks (doc_id, classification);

    -- The caller's ceiling, set per transaction with set_config('kosha.kb_ceiling', ..., true)
    -- so a pooled connection cannot carry it into the next request. Unset means public; an
    -- unknown value fails the cast and with it the query.
    CREATE FUNCTION kb.caller_ceiling() RETURNS kb.classification
        LANGUAGE sql STABLE PARALLEL SAFE
        RETURN coalesce(
            nullif(current_setting('kosha.kb_ceiling', true), '')::kb.classification,
            'public'::kb.classification
        );

    -- FORCE binds the table owner too. Only superusers and BYPASSRLS roles are exempt.
    ALTER TABLE kb.documents ENABLE ROW LEVEL SECURITY;
    ALTER TABLE kb.documents FORCE ROW LEVEL SECURITY;
    CREATE POLICY documents_within_ceiling ON kb.documents FOR SELECT TO kosha_app
        USING (classification <= kb.caller_ceiling());

    ALTER TABLE kb.chunks ENABLE ROW LEVEL SECURITY;
    ALTER TABLE kb.chunks FORCE ROW LEVEL SECURITY;
    CREATE POLICY chunks_within_ceiling ON kb.chunks FOR SELECT TO kosha_app
        USING (classification <= kb.caller_ceiling());

    GRANT SELECT ON kb.documents, kb.chunks TO kosha_app;
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE kb.chunks, kb.documents;
    DROP FUNCTION kb.caller_ceiling();
    DROP TYPE kb.source_format, kb.classification, kb.document_status, kb.document_type,
        kb.department;
    """)
