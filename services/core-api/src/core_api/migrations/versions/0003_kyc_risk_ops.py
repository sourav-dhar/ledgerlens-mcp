"""KYC, financial-crime risk, and operations (disputes, reviews, outbox, audit, idempotency).

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
    CREATE TYPE kyc.kyc_type AS ENUM ('min_kyc', 'full_kyc', 'v_cip', 'ckyc_download');
    CREATE TYPE kyc.kyc_status AS ENUM (
        'not_started', 'pending_documents', 'pending_vcip', 'in_review', 'on_hold',
        'escalated', 'verified', 'rejected', 're_kyc_due', 're_kyc_overdue', 'expired'
    );
    CREATE TYPE kyc.pan_status AS ENUM ('valid', 'invalid', 'not_aadhaar_linked');
    CREATE TYPE kyc.ovd_type AS ENUM ('passport', 'voter_id', 'driving_licence', 'aadhaar');
    CREATE TYPE kyc.document_type AS ENUM (
        'pan_card', 'aadhaar_masked', 'passport', 'selfie', 'address_proof', 'signature'
    );
    CREATE TYPE kyc.document_status AS ENUM ('accepted', 'rejected', 'expired');
    CREATE TYPE risk.typology AS ENUM (
        'structuring', 'rapid_movement', 'mule_account', 'round_tripping',
        'dormant_reactivation', 'high_risk_geo', 'velocity'
    );
    CREATE TYPE risk.severity AS ENUM ('low', 'medium', 'high', 'critical');
    CREATE TYPE risk.list_source AS ENUM ('un_sc', 'ofac_sdn', 'mha_uapa', 'internal_pep');
    CREATE TYPE risk.screening_decision AS ENUM ('clear', 'potential_match', 'true_match');
    CREATE TYPE risk.aml_alert_status AS ENUM (
        'open', 'assigned', 'in_review', 'pending_info', 'on_hold', 'escalated',
        'closed_false_positive', 'closed_no_action', 'closed_str_filed'
    );
    CREATE TYPE ops.dispute_reason AS ENUM (
        'unauthorised', 'goods_not_received', 'duplicate', 'amount_mismatch',
        'failed_but_debited', 'credit_not_received'
    );
    CREATE TYPE ops.dispute_status AS ENUM (
        'raised', 'acknowledged', 'awaiting_customer_info', 'under_investigation',
        'on_hold', 'chargeback_raised', 'pre_arbitration', 'arbitration',
        'resolved_customer_favour', 'resolved_merchant_favour', 'auto_reversed',
        'withdrawn', 'closed'
    );
    CREATE TYPE ops.review_priority AS ENUM ('low', 'normal', 'high', 'urgent');
    CREATE TYPE ops.transaction_review_status AS ENUM (
        'queued', 'in_review', 'on_hold', 'cleared', 'escalated_to_aml', 'blocked'
    );
    CREATE TYPE ops.idempotency_status AS ENUM ('in_progress', 'completed');
    CREATE TYPE ops.audit_outcome AS ENUM ('success', 'denied', 'error');

    -- Append-only guard for tables whose rows are evidence. Revoked privileges stop the
    -- application role; this stops everyone else, the owner and migrations included.
    CREATE FUNCTION kosha.forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION '%.% is append-only: % is not allowed',
                TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
            USING ERRCODE = 'restrict_violation', SCHEMA = TG_TABLE_SCHEMA,
                TABLE = TG_TABLE_NAME;
    END
    $$;

    -- Full Aadhaar is never stored (vault token + last 4) and PAN only as a KMS token
    -- + last 4; the negated pattern checks trip on a raw value written by mistake.
    CREATE TABLE kyc.kyc_profiles (
        kyc_id text PRIMARY KEY CHECK (kosha.is_id(kyc_id, 'kyc')),
        customer_id text NOT NULL REFERENCES core.customers,
        kyc_type kyc.kyc_type NOT NULL,
        kyc_status kyc.kyc_status NOT NULL,
        ckyc_number text CHECK (ckyc_number ~ '^[0-9]{14}$'),
        pan_token text CHECK (pan_token !~ '^[A-Z]{5}[0-9]{4}[A-Z]$'),
        pan_last4 text CHECK (pan_last4 ~ '^[0-9]{3}[A-Z]$'),
        pan_status kyc.pan_status,
        pan_name_match_score numeric(5, 2) CHECK (pan_name_match_score BETWEEN 0 AND 100),
        aadhaar_ref_token text CHECK (aadhaar_ref_token !~ '^[0-9]{12}$'),
        aadhaar_last4 text CHECK (aadhaar_last4 ~ '^[0-9]{4}$'),
        ovd_type kyc.ovd_type,
        vcip_session_id text,
        vcip_agent_id text,
        liveness_score numeric(5, 2) CHECK (liveness_score BETWEEN 0 AND 100),
        face_match_score numeric(5, 2) CHECK (face_match_score BETWEEN 0 AND 100),
        vcip_geo_lat numeric(8, 5) CHECK (vcip_geo_lat BETWEEN -90 AND 90),
        vcip_geo_lng numeric(8, 5) CHECK (vcip_geo_lng BETWEEN -180 AND 180),
        pep_flag boolean NOT NULL DEFAULT false,
        sanctions_flag boolean NOT NULL DEFAULT false,
        fatca_crs_declared boolean NOT NULL DEFAULT false,
        risk_category kosha.risk_category NOT NULL,
        risk_rationale text,
        verified_at timestamptz,
        verified_by text,
        next_review_due date,
        created_at timestamptz NOT NULL DEFAULT now(),
        CHECK ((pan_token IS NULL) = (pan_last4 IS NULL)),
        CHECK ((aadhaar_ref_token IS NULL) = (aadhaar_last4 IS NULL)),
        UNIQUE (kyc_id, customer_id)
    );
    CREATE INDEX kyc_profiles_customer_idx ON kyc.kyc_profiles (customer_id);
    CREATE INDEX kyc_profiles_review_due_idx ON kyc.kyc_profiles (next_review_due)
        WHERE kyc_status = 'verified';

    -- Images are never generated: an S3 key and a digest stand in for them.
    CREATE TABLE kyc.kyc_documents (
        document_id text PRIMARY KEY CHECK (kosha.is_id(document_id, 'kdc')),
        kyc_id text NOT NULL,
        customer_id text NOT NULL,
        doc_type kyc.document_type NOT NULL,
        s3_key text NOT NULL,
        sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
        status kyc.document_status NOT NULL,
        rejection_reason text,
        uploaded_at timestamptz NOT NULL,
        expires_on date,
        FOREIGN KEY (kyc_id, customer_id) REFERENCES kyc.kyc_profiles (kyc_id, customer_id)
    );
    CREATE INDEX kyc_documents_profile_idx ON kyc.kyc_documents (kyc_id, customer_id);

    CREATE TABLE kyc.kyc_events (
        event_id text PRIMARY KEY CHECK (kosha.is_id(event_id, 'kev')),
        kyc_id text NOT NULL REFERENCES kyc.kyc_profiles,
        from_status kyc.kyc_status,
        to_status kyc.kyc_status NOT NULL CHECK (to_status IS DISTINCT FROM from_status),
        actor kosha.actor NOT NULL,
        reason text,
        occurred_at timestamptz NOT NULL
    );
    CREATE INDEX kyc_events_profile_idx ON kyc.kyc_events (kyc_id, occurred_at);

    CREATE TABLE risk.aml_rules (
        rule_id text PRIMARY KEY CHECK (kosha.is_id(rule_id, 'rul')),
        name text NOT NULL UNIQUE,
        typology risk.typology NOT NULL,
        params jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(params) = 'object'),
        severity risk.severity NOT NULL,
        enabled boolean NOT NULL DEFAULT true,
        UNIQUE (rule_id, typology)
    );

    -- An alert copies its rule's typology for filtering; the composite key keeps them equal.
    CREATE TABLE risk.aml_alerts (
        alert_id text PRIMARY KEY CHECK (kosha.is_id(alert_id, 'alr')),
        customer_id text NOT NULL REFERENCES core.customers,
        rule_id text NOT NULL,
        typology risk.typology NOT NULL,
        score numeric(5, 2) NOT NULL CHECK (score BETWEEN 0 AND 100),
        status risk.aml_alert_status NOT NULL,
        assigned_to text,
        sla_due_at timestamptz NOT NULL,
        triggering_txn_ids text[] NOT NULL DEFAULT '{}',
        narrative text,
        disposition text,
        str_reference text,
        created_at timestamptz NOT NULL DEFAULT now(),
        closed_at timestamptz,
        CHECK (status <> 'closed_str_filed' OR str_reference IS NOT NULL),
        FOREIGN KEY (rule_id, typology) REFERENCES risk.aml_rules (rule_id, typology)
    );
    CREATE INDEX aml_alerts_queue_idx ON risk.aml_alerts (status, sla_due_at);
    CREATE INDEX aml_alerts_customer_idx ON risk.aml_alerts (customer_id);
    CREATE INDEX aml_alerts_rule_idx ON risk.aml_alerts (rule_id, typology);

    CREATE TABLE risk.screening_results (
        screening_id text PRIMARY KEY CHECK (kosha.is_id(screening_id, 'scr')),
        customer_id text NOT NULL REFERENCES core.customers,
        screened_name text NOT NULL,
        list_source risk.list_source NOT NULL,
        match_score numeric(5, 2) NOT NULL CHECK (match_score BETWEEN 0 AND 100),
        decision risk.screening_decision NOT NULL,
        vendor_ref text,
        screened_at timestamptz NOT NULL
    );
    CREATE INDEX screening_results_customer_idx
        ON risk.screening_results (customer_id, screened_at DESC);

    CREATE TABLE ops.disputes (
        dispute_id text PRIMARY KEY CHECK (kosha.is_id(dispute_id, 'dsp')),
        txn_id text NOT NULL,
        txn_initiated_at timestamptz NOT NULL,
        customer_id text NOT NULL REFERENCES core.customers,
        reason_code ops.dispute_reason NOT NULL,
        amount_paise bigint NOT NULL CHECK (amount_paise > 0),
        status ops.dispute_status NOT NULL,
        tat_due_at timestamptz NOT NULL,
        compensation_paise bigint NOT NULL DEFAULT 0 CHECK (compensation_paise >= 0),
        resolution text,
        chargeback_ref text,
        idempotency_key text UNIQUE,
        created_by text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        FOREIGN KEY (txn_id, txn_initiated_at)
            REFERENCES core.transactions (txn_id, initiated_at)
    );
    CREATE INDEX disputes_txn_idx ON ops.disputes (txn_id, txn_initiated_at);
    CREATE INDEX disputes_customer_idx ON ops.disputes (customer_id);
    CREATE INDEX disputes_queue_idx ON ops.disputes (status, tat_due_at);

    CREATE TABLE ops.transaction_reviews (
        review_id text PRIMARY KEY CHECK (kosha.is_id(review_id, 'rev')),
        txn_id text NOT NULL,
        txn_initiated_at timestamptz NOT NULL,
        reason text NOT NULL,
        priority ops.review_priority NOT NULL,
        status ops.transaction_review_status NOT NULL,
        idempotency_key text UNIQUE,
        created_by text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        FOREIGN KEY (txn_id, txn_initiated_at)
            REFERENCES core.transactions (txn_id, initiated_at)
    );
    CREATE INDEX transaction_reviews_txn_idx
        ON ops.transaction_reviews (txn_id, txn_initiated_at);
    CREATE INDEX transaction_reviews_queue_idx ON ops.transaction_reviews (status, priority);

    -- Transactional outbox (ADR 0008): written with the business change, relayed to SQS.
    CREATE TABLE ops.outbox (
        event_id text PRIMARY KEY CHECK (kosha.is_id(event_id, 'evt')),
        aggregate_type text NOT NULL,
        aggregate_id text NOT NULL,
        event_type text NOT NULL,
        payload jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        published_at timestamptz
    );
    CREATE INDEX outbox_unpublished_idx ON ops.outbox (created_at) WHERE published_at IS NULL;

    -- One row per tool call; evidence, so append-only for everyone.
    CREATE TABLE ops.audit_log (
        audit_id text PRIMARY KEY CHECK (kosha.is_id(audit_id, 'aud')),
        actor_sub text NOT NULL,
        client_id text NOT NULL,
        roles text[] NOT NULL,
        tool_name text NOT NULL,
        args_hash text NOT NULL CHECK (args_hash ~ '^[0-9a-f]{64}$'),
        resource_ids text[] NOT NULL DEFAULT '{}',
        pii_unmasked boolean NOT NULL DEFAULT false,
        outcome ops.audit_outcome NOT NULL,
        error_code text,
        latency_ms integer NOT NULL CHECK (latency_ms >= 0),
        trace_id text,
        occurred_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX audit_log_occurred_idx ON ops.audit_log (occurred_at);
    CREATE INDEX audit_log_actor_idx ON ops.audit_log (actor_sub, occurred_at);
    CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON ops.audit_log
        FOR EACH ROW EXECUTE FUNCTION kosha.forbid_change();
    CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON ops.audit_log
        FOR EACH STATEMENT EXECUTE FUNCTION kosha.forbid_change();

    -- Written in the same transaction as the business change (ADR 0007).
    CREATE TABLE ops.idempotency_keys (
        scope text NOT NULL,
        key text NOT NULL,
        request_hash text NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
        status ops.idempotency_status NOT NULL,
        response jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        expires_at timestamptz NOT NULL,
        PRIMARY KEY (scope, key),
        CHECK (status = 'in_progress' OR response IS NOT NULL)
    );
    CREATE INDEX idempotency_keys_expiry_idx ON ops.idempotency_keys (expires_at);

    GRANT SELECT, INSERT, UPDATE ON
        kyc.kyc_profiles, kyc.kyc_documents, risk.aml_rules, risk.aml_alerts,
        ops.disputes, ops.transaction_reviews
        TO kosha_app;
    GRANT SELECT, INSERT ON
        kyc.kyc_events, risk.screening_results, ops.audit_log
        TO kosha_app;
    -- Not business rows: the relay prunes published events, a job prunes expired keys.
    GRANT SELECT, INSERT, UPDATE, DELETE ON ops.outbox, ops.idempotency_keys TO kosha_app;
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE ops.idempotency_keys, ops.audit_log, ops.outbox, ops.transaction_reviews,
        ops.disputes, risk.screening_results, risk.aml_alerts, risk.aml_rules,
        kyc.kyc_events, kyc.kyc_documents, kyc.kyc_profiles;
    DROP FUNCTION kosha.forbid_change();
    DROP TYPE ops.audit_outcome, ops.idempotency_status, ops.transaction_review_status,
        ops.review_priority, ops.dispute_status, ops.dispute_reason, risk.aml_alert_status,
        risk.screening_decision, risk.list_source, risk.severity, risk.typology,
        kyc.document_status, kyc.document_type, kyc.ovd_type, kyc.pan_status,
        kyc.kyc_status, kyc.kyc_type;
    """)
