-- Processors (e.g. Stripe, PayPal, Square, ACH)
CREATE TABLE processors (
    id           SERIAL PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE
);

-- One row per connected account for each processor
CREATE TABLE processor_accounts (
    id              SERIAL PRIMARY KEY,
    processor_id    INTEGER NOT NULL REFERENCES processors(id) ON DELETE CASCADE,
    account_name    TEXT NOT NULL,
    credentials_json JSONB NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Cursor tracking to support incremental syncs
CREATE TABLE sync_state (
    id                 SERIAL PRIMARY KEY,
    processor_account_id INTEGER NOT NULL REFERENCES processor_accounts(id) ON DELETE CASCADE,
    last_cursor        TEXT,
    last_synced_at     TIMESTAMP
);

-- Raw events pulled from each processor; stored verbatim for auditability
CREATE TABLE raw_events (
    id           SERIAL PRIMARY KEY,
    processor    TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    external_id  TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_raw_events_external_id ON raw_events (processor, external_id);

-- Canonical ledger transactions (charges/payments/refunds)
CREATE TABLE ledger_transactions (
    id                  UUID PRIMARY KEY,
    processor           TEXT NOT NULL,
    processor_account_id INTEGER NOT NULL REFERENCES processor_accounts(id) ON DELETE CASCADE,
    external_id         TEXT NOT NULL,
    type                TEXT,
    gross_amount        NUMERIC(18,2),
    fee_amount          NUMERIC(18,2),
    net_amount          NUMERIC(18,2),
    currency            TEXT,
    occurred_at         TIMESTAMP,
    customer_ref        TEXT,
    description         TEXT,
    status              TEXT
);
CREATE INDEX idx_ledger_transactions_external_id ON ledger_transactions (processor, external_id);

-- Relationships between transactions (e.g. refund → original charge)
CREATE TABLE ledger_links (
    id                    SERIAL PRIMARY KEY,
    transaction_id        UUID NOT NULL REFERENCES ledger_transactions(id) ON DELETE CASCADE,
    related_transaction_id UUID NOT NULL REFERENCES ledger_transactions(id) ON DELETE CASCADE,
    relation_type         TEXT NOT NULL
);

-- Payouts/settlements from each processor
CREATE TABLE payouts (
    id                  SERIAL PRIMARY KEY,
    processor           TEXT NOT NULL,
    processor_account_id INTEGER NOT NULL REFERENCES processor_accounts(id) ON DELETE CASCADE,
    external_id         TEXT NOT NULL,
    payout_amount       NUMERIC(18,2),
    currency            TEXT,
    payout_date         DATE,
    status              TEXT
);
CREATE INDEX idx_payouts_external_id ON payouts (processor, external_id);

-- Reconciliation runs (one record per reconciliation execution)
CREATE TABLE recon_runs (
    id                  SERIAL PRIMARY KEY,
    time_window_start   TIMESTAMP,
    time_window_end     TIMESTAMP,
    processors_included TEXT[],
    stats               JSONB
);

-- Matches between entities during reconciliation (e.g. transaction ↔ payout)
CREATE TABLE recon_matches (
    id               SERIAL PRIMARY KEY,
    run_id           INTEGER NOT NULL REFERENCES recon_runs(id) ON DELETE CASCADE,
    left_entity_type TEXT NOT NULL,   -- e.g. 'transaction', 'payout'
    left_entity_id   TEXT NOT NULL,
    right_entity_type TEXT,
    right_entity_id  TEXT,
    confidence       NUMERIC,
    reason           TEXT
);

-- Exceptions detected during reconciliation
CREATE TABLE recon_exceptions (
    id             SERIAL PRIMARY KEY,
    run_id         INTEGER NOT NULL REFERENCES recon_runs(id) ON DELETE CASCADE,
    exception_type TEXT NOT NULL,    -- e.g. 'unmatched_transaction'
    severity       TEXT,
    entity_ref     TEXT,
    details_json   JSONB
);

-- QuickBooks sync jobs (one per reconciliation run)
CREATE TABLE qb_sync_jobs (
    id              SERIAL PRIMARY KEY,
    run_id          INTEGER REFERENCES recon_runs(id) ON DELETE SET NULL,
    status          TEXT,
    qb_payload_json JSONB,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Journal postings to QuickBooks clearing accounts
CREATE TABLE qb_postings (
    id              SERIAL PRIMARY KEY,
    clearing_account TEXT,
    journal_entry_id TEXT,
    totals          NUMERIC(18,2),
    posted_at       TIMESTAMP
);
