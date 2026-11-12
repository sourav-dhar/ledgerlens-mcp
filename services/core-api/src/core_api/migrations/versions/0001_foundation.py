"""Foundation: extensions, schemas, the application role and shared types.

Revision ID: 0001
Revises:
"""

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE EXTENSION IF NOT EXISTS pg_trgm;

    CREATE SCHEMA kosha;   -- cross-cutting types, lifecycle tables and helpers
    CREATE SCHEMA core;    -- customers, accounts, payments
    CREATE SCHEMA ledger;  -- double-entry journal
    CREATE SCHEMA kyc;
    CREATE SCHEMA risk;
    CREATE SCHEMA ops;     -- disputes, reviews, outbox, audit, idempotency
    CREATE SCHEMA kb;      -- knowledge base

    -- The role the services run as. Login roles are granted it at deploy time; it owns
    -- nothing, so row-level security and revoked privileges always apply to it.
    -- Roles are cluster-wide, hence the guard and why downgrade leaves it in place.
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'kosha_app') THEN
            CREATE ROLE kosha_app NOLOGIN;
        END IF;
    END
    $$;
    GRANT USAGE ON SCHEMA kosha, core, ledger, kyc, risk, ops, kb TO kosha_app;

    -- Prefixed ULID, as minted by kosha_domain.ids: 26 Crockford base32 characters whose
    -- first character is at most 7, because a ULID is 128 bits.
    CREATE FUNCTION kosha.is_id(value text, prefix text) RETURNS boolean
        LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
        RETURN value ~ ('^' || prefix || '_[0-7][0-9A-HJKMNP-TV-Z]{25}$');

    CREATE TYPE kosha.actor AS ENUM ('system', 'customer', 'staff', 'npci', 'risk_engine');
    CREATE TYPE kosha.risk_category AS ENUM ('low', 'medium', 'high');
    """)


def downgrade() -> None:
    op.execute("""
    DROP SCHEMA kb, ops, risk, kyc, ledger, core, kosha CASCADE;
    DROP EXTENSION IF EXISTS pg_trgm;
    DROP EXTENSION IF EXISTS vector;
    """)
