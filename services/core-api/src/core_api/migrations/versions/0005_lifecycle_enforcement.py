"""Status lifecycles enforced in the database.

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None

# (table, status column, lifecycle) for every status column that has a lifecycle.
_GUARDED = (
    ("core.transactions", "status", "Transaction"),
    ("core.accounts", "status", "Account"),
    ("kyc.kyc_profiles", "kyc_status", "KYC profile"),
    ("core.cards", "status", "Card"),
    ("ops.disputes", "status", "Dispute"),
    ("risk.aml_alerts", "status", "AML alert"),
    ("ops.transaction_reviews", "status", "Transaction review"),
    ("core.beneficiaries", "status", "Beneficiary"),
)


def _trigger_name(table: str, column: str) -> str:
    return f"{table.split('.')[1]}_{column}_lifecycle"


def upgrade() -> None:
    op.execute("""
    -- kosha_domain.lifecycles, frozen at this revision. The test suite compares the two
    -- edge for edge; a lifecycle change ships as a new revision that edits these rows.
    CREATE TABLE kosha.allowed_transitions (
        lifecycle text NOT NULL,
        from_status text NOT NULL,
        to_status text NOT NULL,
        PRIMARY KEY (lifecycle, from_status, to_status)
    );
    INSERT INTO kosha.allowed_transitions (lifecycle, from_status, to_status) VALUES
        ('Transaction', 'initiated', 'authorised'),
        ('Transaction', 'initiated', 'declined'),
        ('Transaction', 'initiated', 'cancelled'),
        ('Transaction', 'initiated', 'expired'),
        ('Transaction', 'authorised', 'processing'),
        ('Transaction', 'processing', 'pending'),
        ('Transaction', 'processing', 'success'),
        ('Transaction', 'processing', 'on_hold'),
        ('Transaction', 'processing', 'failed'),
        ('Transaction', 'processing', 'timed_out'),
        ('Transaction', 'pending', 'success'),
        ('Transaction', 'pending', 'credit_delayed'),
        ('Transaction', 'pending', 'deemed_success'),
        ('Transaction', 'pending', 'failed'),
        ('Transaction', 'pending', 'returned'),
        ('Transaction', 'success', 'pending_settlement'),
        ('Transaction', 'success', 'reversal_initiated'),
        ('Transaction', 'credit_delayed', 'success'),
        ('Transaction', 'credit_delayed', 'reversal_initiated'),
        ('Transaction', 'deemed_success', 'success'),
        ('Transaction', 'deemed_success', 'reversal_initiated'),
        ('Transaction', 'on_hold', 'under_review'),
        ('Transaction', 'under_review', 'processing'),
        ('Transaction', 'under_review', 'declined'),
        ('Transaction', 'pending_settlement', 'settled'),
        ('Transaction', 'settled', 'refunded'),
        ('Transaction', 'settled', 'chargeback_initiated'),
        ('Transaction', 'timed_out', 'reversal_initiated'),
        ('Transaction', 'returned', 'reversed'),
        ('Transaction', 'reversal_initiated', 'reversed'),
        ('Transaction', 'reversal_initiated', 'partially_reversed'),
        ('Account', 'pending_activation', 'active'),
        ('Account', 'pending_activation', 'kyc_pending'),
        ('Account', 'active', 'dormant'),
        ('Account', 'active', 'debit_freeze'),
        ('Account', 'active', 'credit_freeze'),
        ('Account', 'active', 'total_freeze'),
        ('Account', 'active', 'lien_marked'),
        ('Account', 'active', 'on_hold'),
        ('Account', 'active', 'pending_closure'),
        ('Account', 'kyc_pending', 'active'),
        ('Account', 'dormant', 'active'),
        ('Account', 'dormant', 'inoperative'),
        ('Account', 'inoperative', 'active'),
        ('Account', 'debit_freeze', 'active'),
        ('Account', 'credit_freeze', 'active'),
        ('Account', 'total_freeze', 'active'),
        ('Account', 'lien_marked', 'active'),
        ('Account', 'on_hold', 'active'),
        ('Account', 'pending_closure', 'closed'),
        ('KYC profile', 'not_started', 'pending_documents'),
        ('KYC profile', 'pending_documents', 'pending_vcip'),
        ('KYC profile', 'pending_documents', 'in_review'),
        ('KYC profile', 'pending_vcip', 'in_review'),
        ('KYC profile', 'in_review', 'on_hold'),
        ('KYC profile', 'in_review', 'escalated'),
        ('KYC profile', 'in_review', 'verified'),
        ('KYC profile', 'in_review', 'rejected'),
        ('KYC profile', 'on_hold', 'in_review'),
        ('KYC profile', 'escalated', 'verified'),
        ('KYC profile', 'escalated', 'rejected'),
        ('KYC profile', 'verified', 're_kyc_due'),
        ('KYC profile', 're_kyc_due', 'in_review'),
        ('KYC profile', 're_kyc_due', 're_kyc_overdue'),
        ('KYC profile', 're_kyc_overdue', 'in_review'),
        ('KYC profile', 're_kyc_overdue', 'expired'),
        ('Card', 'inactive', 'active'),
        ('Card', 'inactive', 'expired'),
        ('Card', 'active', 'temp_blocked'),
        ('Card', 'active', 'pin_blocked'),
        ('Card', 'active', 'blocked'),
        ('Card', 'active', 'hotlisted'),
        ('Card', 'active', 'expired'),
        ('Card', 'temp_blocked', 'active'),
        ('Card', 'temp_blocked', 'hotlisted'),
        ('Card', 'pin_blocked', 'active'),
        ('Card', 'pin_blocked', 'hotlisted'),
        ('Card', 'blocked', 'replaced'),
        ('Card', 'hotlisted', 'replaced'),
        ('Card', 'expired', 'replaced'),
        ('Dispute', 'raised', 'acknowledged'),
        ('Dispute', 'raised', 'auto_reversed'),
        ('Dispute', 'raised', 'withdrawn'),
        ('Dispute', 'acknowledged', 'under_investigation'),
        ('Dispute', 'acknowledged', 'withdrawn'),
        ('Dispute', 'awaiting_customer_info', 'under_investigation'),
        ('Dispute', 'under_investigation', 'awaiting_customer_info'),
        ('Dispute', 'under_investigation', 'on_hold'),
        ('Dispute', 'under_investigation', 'chargeback_raised'),
        ('Dispute', 'under_investigation', 'resolved_customer_favour'),
        ('Dispute', 'under_investigation', 'resolved_merchant_favour'),
        ('Dispute', 'on_hold', 'under_investigation'),
        ('Dispute', 'chargeback_raised', 'pre_arbitration'),
        ('Dispute', 'chargeback_raised', 'resolved_customer_favour'),
        ('Dispute', 'chargeback_raised', 'resolved_merchant_favour'),
        ('Dispute', 'pre_arbitration', 'arbitration'),
        ('Dispute', 'pre_arbitration', 'resolved_customer_favour'),
        ('Dispute', 'pre_arbitration', 'resolved_merchant_favour'),
        ('Dispute', 'arbitration', 'resolved_customer_favour'),
        ('Dispute', 'arbitration', 'resolved_merchant_favour'),
        ('Dispute', 'resolved_customer_favour', 'closed'),
        ('Dispute', 'resolved_merchant_favour', 'closed'),
        ('Dispute', 'auto_reversed', 'closed'),
        ('Dispute', 'withdrawn', 'closed'),
        ('AML alert', 'open', 'assigned'),
        ('AML alert', 'assigned', 'in_review'),
        ('AML alert', 'in_review', 'pending_info'),
        ('AML alert', 'in_review', 'on_hold'),
        ('AML alert', 'in_review', 'escalated'),
        ('AML alert', 'in_review', 'closed_false_positive'),
        ('AML alert', 'in_review', 'closed_no_action'),
        ('AML alert', 'pending_info', 'in_review'),
        ('AML alert', 'on_hold', 'in_review'),
        ('AML alert', 'escalated', 'closed_no_action'),
        ('AML alert', 'escalated', 'closed_str_filed'),
        ('Transaction review', 'queued', 'in_review'),
        ('Transaction review', 'in_review', 'on_hold'),
        ('Transaction review', 'in_review', 'cleared'),
        ('Transaction review', 'in_review', 'escalated_to_aml'),
        ('Transaction review', 'in_review', 'blocked'),
        ('Transaction review', 'on_hold', 'in_review'),
        ('Beneficiary', 'pending_cooling', 'active'),
        ('Beneficiary', 'pending_cooling', 'deleted'),
        ('Beneficiary', 'active', 'disabled'),
        ('Beneficiary', 'active', 'deleted'),
        ('Beneficiary', 'disabled', 'active'),
        ('Beneficiary', 'disabled', 'deleted');

    GRANT SELECT ON kosha.allowed_transitions TO kosha_app;

    -- Raised as check_violation with the trigger's name (*_lifecycle) as the constraint, so
    -- core-api maps it to 409 conflict; the message is worded as the domain words it.
    -- Inserts are not checked: historical rows arrive in their final status, with history.
    CREATE FUNCTION kosha.enforce_transition() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        lifecycle_name text := TG_ARGV[0];
        status_column text := TG_ARGV[1];
        src text := to_jsonb(OLD) ->> status_column;
        dst text := to_jsonb(NEW) ->> status_column;
    BEGIN
        IF NOT EXISTS (
            SELECT FROM kosha.allowed_transitions t
            WHERE t.lifecycle = lifecycle_name AND t.from_status = src AND t.to_status = dst
        ) THEN
            RAISE EXCEPTION '% cannot move from % to %',
                    lifecycle_name, quote_literal(src), quote_literal(dst)
                USING ERRCODE = 'check_violation', CONSTRAINT = TG_NAME,
                    SCHEMA = TG_TABLE_SCHEMA, TABLE = TG_TABLE_NAME, COLUMN = status_column;
        END IF;
        RETURN NEW;
    END
    $$;
    """)
    for table, column, lifecycle in _GUARDED:
        op.execute(f"""
        CREATE TRIGGER {_trigger_name(table, column)}
            BEFORE UPDATE OF {column} ON {table}
            FOR EACH ROW WHEN (OLD.{column} IS DISTINCT FROM NEW.{column})
            EXECUTE FUNCTION kosha.enforce_transition('{lifecycle}', '{column}');
        """)


def downgrade() -> None:
    for table, column, _ in _GUARDED:
        op.execute(f"DROP TRIGGER {_trigger_name(table, column)} ON {table}")
    op.execute("""
    DROP FUNCTION kosha.enforce_transition();
    DROP TABLE kosha.allowed_transitions;
    """)
