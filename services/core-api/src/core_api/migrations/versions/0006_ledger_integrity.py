"""Ledger integrity: balanced journal entries, and an append-only ledger and history.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None

# Evidence of what happened: rows are appended, never rewritten, by anyone.
_APPEND_ONLY = (
    "ledger.journal_entries",
    "ledger.postings",
    "core.transaction_status_history",
    "kyc.kyc_events",
)


def _name(table: str) -> str:
    return table.split(".")[1]


def upgrade() -> None:
    op.execute("""
    -- Deferred to commit, so an entry and its postings can be written in any order within
    -- a transaction. Fired from both tables: postings catch an imbalance, and the entry
    -- itself catches an entry that never received postings at all.
    CREATE FUNCTION ledger.check_entry_balanced() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        total numeric;
        legs integer;
    BEGIN
        SELECT coalesce(sum(p.amount_paise), 0), count(*) INTO total, legs
        FROM ledger.postings p
        WHERE p.entry_id = NEW.entry_id;
        IF legs < 2 OR total <> 0 THEN
            RAISE EXCEPTION 'journal entry % is unbalanced: % postings summing to % paise',
                    NEW.entry_id, legs, total
                USING ERRCODE = 'check_violation', CONSTRAINT = TG_NAME,
                    SCHEMA = TG_TABLE_SCHEMA, TABLE = TG_TABLE_NAME;
        END IF;
        RETURN NULL;
    END
    $$;

    CREATE CONSTRAINT TRIGGER journal_entries_balanced
        AFTER INSERT ON ledger.journal_entries
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION ledger.check_entry_balanced();
    CREATE CONSTRAINT TRIGGER postings_balanced
        AFTER INSERT ON ledger.postings
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION ledger.check_entry_balanced();
    """)
    for table in _APPEND_ONLY:
        op.execute(f"""
        CREATE TRIGGER {_name(table)}_append_only BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION kosha.forbid_change();
        CREATE TRIGGER {_name(table)}_no_truncate BEFORE TRUNCATE ON {table}
            FOR EACH STATEMENT EXECUTE FUNCTION kosha.forbid_change();
        """)


def downgrade() -> None:
    for table in _APPEND_ONLY:
        op.execute(f"""
        DROP TRIGGER {_name(table)}_no_truncate ON {table};
        DROP TRIGGER {_name(table)}_append_only ON {table};
        """)
    op.execute("""
    DROP TRIGGER postings_balanced ON ledger.postings;
    DROP TRIGGER journal_entries_balanced ON ledger.journal_entries;
    DROP FUNCTION ledger.check_entry_balanced();
    """)
