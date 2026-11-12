"""Ledger reconciliation, and an opening-balances GL account for balances brought forward.

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
    -- Contra account for balances that predate the ledger: Accounts opened before Kosha's
    -- ledger went live start with one entry, Account +X and opening_balances -X.
    ALTER TYPE ledger.gl_account ADD VALUE 'opening_balances';

    -- Cached Account balances against the Postings they summarise (index-only scan of
    -- postings_account_idx). Any row with a non-zero difference is a ledger defect.
    CREATE VIEW ledger.account_reconciliation AS
    SELECT a.account_id,
           a.ledger_balance_paise AS cached_balance_paise,
           coalesce(p.posted_paise, 0) AS posted_balance_paise,
           a.ledger_balance_paise - coalesce(p.posted_paise, 0) AS difference_paise
    FROM core.accounts a
    LEFT JOIN (
        SELECT account_id, sum(amount_paise)::bigint AS posted_paise
        FROM ledger.postings
        WHERE account_id IS NOT NULL
        GROUP BY account_id
    ) p USING (account_id);

    GRANT SELECT ON ledger.account_reconciliation TO kosha_app;
    """)


def downgrade() -> None:
    # Postgres cannot drop an enum value, so the type is rebuilt without it; this fails, as
    # it should, while any Posting still uses opening_balances. The CHECK that compares
    # gl_account with a literal is typed by the old enum and is rebuilt around the swap.
    op.execute("""
    DROP VIEW ledger.account_reconciliation;
    ALTER TABLE ledger.postings DROP CONSTRAINT postings_check;
    ALTER TYPE ledger.gl_account RENAME TO gl_account_0007;
    CREATE TYPE ledger.gl_account AS ENUM (
        'customer_deposits', 'upi_settlement', 'imps_settlement', 'neft_settlement',
        'rtgs_settlement', 'card_settlement', 'atm_settlement', 'nach_settlement',
        'fee_income', 'gst_payable', 'interest_expense', 'suspense'
    );
    ALTER TABLE ledger.postings
        ALTER COLUMN gl_account TYPE ledger.gl_account USING gl_account::text::ledger.gl_account;
    ALTER TABLE ledger.postings ADD CONSTRAINT postings_check
        CHECK ((gl_account = 'customer_deposits') = (account_id IS NOT NULL));
    DROP TYPE ledger.gl_account_0007;
    """)
