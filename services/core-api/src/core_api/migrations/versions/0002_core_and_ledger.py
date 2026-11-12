"""Core banking and the double-entry ledger.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
    CREATE TYPE core.gender AS ENUM ('female', 'male', 'transgender');
    CREATE TYPE core.persona AS ENUM (
        'salaried', 'student', 'gig_worker', 'sme_owner', 'nri', 'senior_citizen'
    );
    CREATE TYPE core.segment AS ENUM ('mass', 'affluent', 'premium');
    CREATE TYPE core.income_band AS ENUM (
        'up_to_3_lakh', '3_to_6_lakh', '6_to_12_lakh', '12_to_25_lakh', '25_to_50_lakh',
        'above_50_lakh'
    );
    CREATE TYPE core.residential_status AS ENUM ('resident', 'nri');
    CREATE TYPE core.onboarding_channel AS ENUM ('app', 'web', 'assisted', 'partner');
    CREATE TYPE core.customer_status AS ENUM (
        'prospect', 'active', 'on_hold', 'dormant', 'frozen', 'under_investigation',
        'deceased_claim_pending', 'closed'
    );
    CREATE TYPE core.address_type AS ENUM ('permanent', 'correspondence');
    CREATE TYPE core.product_code AS ENUM (
        'savings_regular', 'savings_salary', 'current', 'fixed_deposit',
        'recurring_deposit'
    );
    CREATE TYPE core.mode_of_operation AS ENUM ('single', 'joint');
    CREATE TYPE core.account_status AS ENUM (
        'pending_activation', 'active', 'kyc_pending', 'dormant', 'inoperative',
        'debit_freeze', 'credit_freeze', 'total_freeze', 'lien_marked', 'on_hold',
        'pending_closure', 'closed'
    );
    CREATE TYPE core.card_network AS ENUM ('rupay', 'visa', 'mastercard');
    CREATE TYPE core.card_type AS ENUM ('debit', 'credit', 'prepaid');
    CREATE TYPE core.card_status AS ENUM (
        'inactive', 'active', 'temp_blocked', 'pin_blocked', 'blocked', 'hotlisted',
        'expired', 'replaced'
    );
    CREATE TYPE core.vpa_status AS ENUM ('active', 'suspended', 'deregistered');
    CREATE TYPE core.beneficiary_status AS ENUM (
        'pending_cooling', 'active', 'disabled', 'deleted'
    );
    CREATE TYPE core.direction AS ENUM ('debit', 'credit');
    CREATE TYPE core.rail AS ENUM (
        'upi', 'imps', 'neft', 'rtgs', 'card_pos', 'card_ecom', 'atm', 'nach',
        'internal'
    );
    CREATE TYPE core.transaction_type AS ENUM (
        'p2p', 'p2m', 'salary', 'emi', 'bill_pay', 'refund', 'reversal',
        'cash_withdrawal', 'interest_credit', 'charges', 'fd_booking'
    );
    CREATE TYPE core.channel AS ENUM ('mobile_app', 'web', 'pos', 'atm', 'api');
    CREATE TYPE core.transaction_status AS ENUM (
        'initiated', 'authorised', 'processing', 'pending', 'success', 'credit_delayed',
        'deemed_success', 'on_hold', 'under_review', 'pending_settlement', 'settled',
        'failed', 'timed_out', 'declined', 'cancelled', 'expired', 'returned',
        'reversal_initiated', 'reversed', 'partially_reversed', 'refunded',
        'chargeback_initiated'
    );
    CREATE TYPE ledger.gl_account AS ENUM (
        'customer_deposits', 'upi_settlement', 'imps_settlement', 'neft_settlement',
        'rtgs_settlement', 'card_settlement', 'atm_settlement', 'nach_settlement',
        'fee_income', 'gst_payable', 'interest_expense', 'suspense'
    );

    CREATE TABLE core.customers (
        customer_id text PRIMARY KEY CHECK (kosha.is_id(customer_id, 'cus')),
        cif_number text NOT NULL UNIQUE CHECK (cif_number ~ '^[0-9]{10}$'),
        first_name text NOT NULL,
        middle_name text,
        last_name text NOT NULL,
        date_of_birth date NOT NULL,
        gender core.gender NOT NULL,
        email text,
        mobile text NOT NULL CHECK (mobile ~ '^[6-9][0-9]{9}$'),
        mobile_verified boolean NOT NULL DEFAULT false,
        persona core.persona NOT NULL,
        occupation text,
        employer_name text,
        annual_income_band core.income_band,
        segment core.segment NOT NULL,
        residential_status core.residential_status NOT NULL,
        preferred_language text NOT NULL DEFAULT 'en',
        onboarding_channel core.onboarding_channel NOT NULL,
        relationship_start_date date NOT NULL,
        status core.customer_status NOT NULL,
        risk_category kosha.risk_category NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX customers_name_trgm_idx
        ON core.customers USING gin ((first_name || ' ' || last_name) gin_trgm_ops);

    CREATE TABLE core.addresses (
        address_id text PRIMARY KEY CHECK (kosha.is_id(address_id, 'adr')),
        customer_id text NOT NULL REFERENCES core.customers,
        address_type core.address_type NOT NULL,
        line1 text NOT NULL,
        line2 text,
        city text NOT NULL,
        district text,
        state text NOT NULL,
        state_code text NOT NULL CHECK (state_code ~ '^[0-9]{2}$'),
        pincode text NOT NULL CHECK (pincode ~ '^[1-9][0-9]{5}$'),
        country text NOT NULL DEFAULT 'IN',
        is_verified boolean NOT NULL DEFAULT false,
        valid_from date NOT NULL,
        valid_to date CHECK (valid_to >= valid_from)
    );
    CREATE INDEX addresses_customer_idx ON core.addresses (customer_id);

    -- Balances are a cache of ledger.postings; available = ledger - holds (GLOSSARY).
    CREATE TABLE core.accounts (
        account_id text PRIMARY KEY CHECK (kosha.is_id(account_id, 'acc')),
        customer_id text NOT NULL REFERENCES core.customers,
        account_number text NOT NULL UNIQUE CHECK (account_number ~ '^[0-9]{9,18}$'),
        ifsc text NOT NULL CHECK (ifsc ~ '^[A-Z]{4}0[A-Z0-9]{6}$'),
        product_code core.product_code NOT NULL,
        status core.account_status NOT NULL,
        status_reason text,
        mode_of_operation core.mode_of_operation NOT NULL,
        opened_at timestamptz NOT NULL,
        closed_at timestamptz CHECK (closed_at >= opened_at),
        ledger_balance_paise bigint NOT NULL DEFAULT 0,
        hold_amount_paise bigint NOT NULL DEFAULT 0 CHECK (hold_amount_paise >= 0),
        available_balance_paise bigint NOT NULL
            GENERATED ALWAYS AS (ledger_balance_paise - hold_amount_paise) STORED,
        minimum_balance_paise bigint NOT NULL DEFAULT 0 CHECK (minimum_balance_paise >= 0),
        interest_rate_bps integer NOT NULL DEFAULT 0 CHECK (interest_rate_bps >= 0),
        overdraft_limit_paise bigint NOT NULL DEFAULT 0 CHECK (overdraft_limit_paise >= 0),
        nominee_registered boolean NOT NULL DEFAULT false,
        last_txn_at timestamptz,
        -- Target of composite keys that pin a row's customer to the account's owner.
        UNIQUE (account_id, customer_id)
    );
    CREATE INDEX accounts_customer_idx ON core.accounts (customer_id);

    CREATE TABLE core.cards (
        card_id text PRIMARY KEY CHECK (kosha.is_id(card_id, 'crd')),
        account_id text NOT NULL REFERENCES core.accounts,
        network core.card_network NOT NULL,
        card_type core.card_type NOT NULL,
        pan_last4 text NOT NULL CHECK (pan_last4 ~ '^[0-9]{4}$'),
        token_ref text NOT NULL,
        status core.card_status NOT NULL,
        expiry_month smallint NOT NULL CHECK (expiry_month BETWEEN 1 AND 12),
        expiry_year smallint NOT NULL CHECK (expiry_year >= 2000),
        atm_limit_paise bigint NOT NULL CHECK (atm_limit_paise >= 0),
        pos_limit_paise bigint NOT NULL CHECK (pos_limit_paise >= 0),
        ecom_limit_paise bigint NOT NULL CHECK (ecom_limit_paise >= 0),
        contactless_enabled boolean NOT NULL DEFAULT true,
        international_enabled boolean NOT NULL DEFAULT false,
        issued_at timestamptz NOT NULL
    );
    CREATE INDEX cards_account_idx ON core.cards (account_id);

    CREATE TABLE core.vpas (
        vpa_id text PRIMARY KEY CHECK (kosha.is_id(vpa_id, 'vpa')),
        customer_id text NOT NULL,
        account_id text NOT NULL,
        vpa text NOT NULL UNIQUE
            CHECK (vpa ~ '^[A-Za-z0-9][A-Za-z0-9._-]{1,255}@[A-Za-z][A-Za-z0-9]{1,63}$'),
        is_primary boolean NOT NULL DEFAULT false,
        status core.vpa_status NOT NULL,
        created_at timestamptz NOT NULL,
        FOREIGN KEY (account_id, customer_id) REFERENCES core.accounts (account_id, customer_id)
    );
    CREATE INDEX vpas_account_idx ON core.vpas (account_id, customer_id);
    CREATE UNIQUE INDEX vpas_one_primary_per_customer
        ON core.vpas (customer_id) WHERE is_primary AND status = 'active';

    CREATE TABLE core.beneficiaries (
        beneficiary_id text PRIMARY KEY CHECK (kosha.is_id(beneficiary_id, 'ben')),
        customer_id text NOT NULL REFERENCES core.customers,
        nickname text NOT NULL,
        account_number_masked text NOT NULL,
        ifsc text NOT NULL CHECK (ifsc ~ '^[A-Z]{4}0[A-Z0-9]{6}$'),
        bank_name text NOT NULL,
        added_at timestamptz NOT NULL,
        cooling_period_ends_at timestamptz NOT NULL CHECK (cooling_period_ends_at >= added_at),
        status core.beneficiary_status NOT NULL
    );
    CREATE INDEX beneficiaries_customer_idx ON core.beneficiaries (customer_id);

    CREATE TABLE core.merchants (
        merchant_id text PRIMARY KEY CHECK (kosha.is_id(merchant_id, 'mer')),
        display_name text NOT NULL,
        legal_name text NOT NULL,
        mcc smallint NOT NULL CHECK (mcc BETWEEN 0 AND 9999),
        category text NOT NULL,
        sub_category text,
        city text NOT NULL,
        state text NOT NULL,
        vpa text UNIQUE,
        gstin text CHECK (gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'),
        acquirer_bank text NOT NULL,
        risk_level kosha.risk_category NOT NULL
    );

    -- Partitioned by month on initiated_at; the key must include it (ADR 0011).
    CREATE TABLE core.transactions (
        txn_id text NOT NULL CHECK (kosha.is_id(txn_id, 'txn')),
        account_id text NOT NULL,
        customer_id text NOT NULL,
        direction core.direction NOT NULL,
        amount_paise bigint NOT NULL CHECK (amount_paise > 0),
        currency text NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
        rail core.rail NOT NULL,
        txn_type core.transaction_type NOT NULL,
        status core.transaction_status NOT NULL,
        status_reason_code text,
        failure_reason_code text,
        hold_reason text,
        expected_credit_by timestamptz,
        utr text,
        rrn text CHECK (rrn ~ '^[0-9]{12}$'),
        npci_txn_id text,
        counterparty_name text,
        counterparty_vpa text,
        counterparty_account_masked text,
        counterparty_ifsc text CHECK (counterparty_ifsc ~ '^[A-Z]{4}0[A-Z0-9]{6}$'),
        merchant_id text REFERENCES core.merchants,
        mcc smallint CHECK (mcc BETWEEN 0 AND 9999),
        channel core.channel NOT NULL,
        device_id text,
        ip_address inet,
        geo_city text,
        geo_lat numeric(8, 5) CHECK (geo_lat BETWEEN -90 AND 90),
        geo_lng numeric(8, 5) CHECK (geo_lng BETWEEN -180 AND 180),
        narration text NOT NULL,
        remarks text,
        initiated_at timestamptz NOT NULL,
        posted_at timestamptz,
        value_date date,
        balance_after_paise bigint,
        risk_score smallint CHECK (risk_score BETWEEN 0 AND 100),
        is_flagged boolean NOT NULL DEFAULT false,
        PRIMARY KEY (txn_id, initiated_at),
        FOREIGN KEY (account_id, customer_id) REFERENCES core.accounts (account_id, customer_id)
    ) PARTITION BY RANGE (initiated_at);

    CREATE INDEX transactions_account_timeline_idx
        ON core.transactions (account_id, initiated_at DESC, txn_id DESC);
    CREATE INDEX transactions_customer_timeline_idx
        ON core.transactions (customer_id, initiated_at DESC);
    CREATE INDEX transactions_merchant_idx
        ON core.transactions (merchant_id) WHERE merchant_id IS NOT NULL;
    -- Not unique: a unique index must include initiated_at, which would only forbid
    -- duplicates at the same instant, and both legs of an on-us transfer share a UTR.
    CREATE INDEX transactions_utr_idx ON core.transactions (utr) WHERE utr IS NOT NULL;
    CREATE INDEX transactions_narration_trgm_idx
        ON core.transactions USING gin (narration gin_trgm_ops);
    CREATE INDEX transactions_ops_queue_idx ON core.transactions (account_id)
        WHERE status IN ('on_hold', 'credit_delayed', 'under_review');

    -- Monthly UTC partitions; returns how many were created. Run ahead of time by a
    -- scheduled job: a month whose rows already sit in the default partition cannot be
    -- split out without moving them first.
    CREATE FUNCTION kosha.create_transaction_partitions(first_month date, last_month date)
        RETURNS integer LANGUAGE plpgsql AS $$
    DECLARE
        m date := date_trunc('month', first_month)::date;
        next_m date;
        partition text;
        created integer := 0;
    BEGIN
        WHILE m <= last_month LOOP
            next_m := (m + interval '1 month')::date;
            partition := 'transactions_' || to_char(m, 'YYYY_MM');
            IF to_regclass('core.' || partition) IS NULL THEN
                EXECUTE format(
                    'CREATE TABLE core.%I PARTITION OF core.transactions'
                    ' FOR VALUES FROM (%L) TO (%L)',
                    partition,
                    to_char(m, 'YYYY-MM-DD') || ' 00:00:00+00',
                    to_char(next_m, 'YYYY-MM-DD') || ' 00:00:00+00'
                );
                created := created + 1;
            END IF;
            m := next_m;
        END LOOP;
        RETURN created;
    END
    $$;
    REVOKE EXECUTE ON FUNCTION kosha.create_transaction_partitions(date, date) FROM PUBLIC;

    SELECT kosha.create_transaction_partitions(
        (date_trunc('month', now()) - interval '18 months')::date,
        (date_trunc('month', now()) + interval '3 months')::date
    );
    CREATE TABLE core.transactions_default PARTITION OF core.transactions DEFAULT;

    CREATE TABLE core.transaction_status_history (
        history_id text PRIMARY KEY CHECK (kosha.is_id(history_id, 'tsh')),
        txn_id text NOT NULL,
        txn_initiated_at timestamptz NOT NULL,
        from_status core.transaction_status,
        to_status core.transaction_status NOT NULL CHECK (to_status IS DISTINCT FROM from_status),
        reason_code text,
        actor kosha.actor NOT NULL,
        occurred_at timestamptz NOT NULL,
        FOREIGN KEY (txn_id, txn_initiated_at)
            REFERENCES core.transactions (txn_id, initiated_at)
    );
    CREATE INDEX transaction_status_history_txn_idx
        ON core.transaction_status_history (txn_id, txn_initiated_at, occurred_at);

    -- One balanced entry per money-moving Transaction; entries without a Transaction
    -- (settlement sweeps, GST remittance) leave both columns null.
    CREATE TABLE ledger.journal_entries (
        entry_id text PRIMARY KEY CHECK (kosha.is_id(entry_id, 'jrn')),
        txn_id text,
        txn_initiated_at timestamptz,
        posted_at timestamptz NOT NULL,
        description text NOT NULL,
        CHECK ((txn_id IS NULL) = (txn_initiated_at IS NULL)),
        UNIQUE (txn_id, txn_initiated_at),
        FOREIGN KEY (txn_id, txn_initiated_at)
            REFERENCES core.transactions (txn_id, initiated_at)
    );

    -- Signed amounts. Customer Accounts are sub-ledgers of customer_deposits, so exactly
    -- those postings name an Account.
    CREATE TABLE ledger.postings (
        posting_id text PRIMARY KEY CHECK (kosha.is_id(posting_id, 'pst')),
        entry_id text NOT NULL REFERENCES ledger.journal_entries,
        gl_account ledger.gl_account NOT NULL,
        account_id text REFERENCES core.accounts,
        amount_paise bigint NOT NULL CHECK (amount_paise <> 0),
        CHECK ((gl_account = 'customer_deposits') = (account_id IS NOT NULL))
    );
    CREATE INDEX postings_entry_idx ON ledger.postings (entry_id);
    CREATE INDEX postings_account_idx ON ledger.postings (account_id) INCLUDE (amount_paise)
        WHERE account_id IS NOT NULL;

    -- Business rows are never deleted, and history and the ledger are append-only.
    GRANT SELECT, INSERT, UPDATE ON
        core.customers, core.addresses, core.accounts, core.cards, core.vpas,
        core.beneficiaries, core.merchants, core.transactions
        TO kosha_app;
    GRANT SELECT, INSERT ON
        core.transaction_status_history, ledger.journal_entries, ledger.postings
        TO kosha_app;
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE ledger.postings, ledger.journal_entries, core.transaction_status_history,
        core.transactions, core.merchants, core.beneficiaries, core.vpas, core.cards,
        core.accounts, core.addresses, core.customers;
    DROP FUNCTION kosha.create_transaction_partitions(date, date);
    DROP TYPE ledger.gl_account, core.transaction_status, core.channel,
        core.transaction_type, core.rail, core.direction, core.beneficiary_status,
        core.vpa_status, core.card_status, core.card_type, core.card_network,
        core.account_status, core.mode_of_operation, core.product_code, core.address_type,
        core.customer_status, core.onboarding_channel, core.residential_status,
        core.income_band, core.segment, core.persona, core.gender;
    """)
