# Architecture

This document explains the architecture for **Multi‑Processor Payment Reconciliation** built with **n8n + PostgreSQL** (portable to Supabase or any Postgres provider) and **Python** inside n8n Code nodes.

---

## Goal

Provide a repeatable daily reconciliation pipeline that:

* Pulls transactions + payouts from **Stripe**, **PayPal**, **Square**, and **ACH/bank** sources
* Normalizes everything into a **canonical ledger**
* Runs an **auditable matching engine**
* Produces a **discrepancy / exception queue** for finance review
* (Optional) Pushes **QuickBooks Online** journal entries using **clearing accounts**
* Computes **cash position** across all processors

---

## Components

### 1) Orchestration layer: n8n

n8n is the workflow engine that:

* schedules daily runs (Cron)
* calls APIs (HTTP Request)
* performs transformations (Python Code nodes)
* writes results to Postgres (Postgres / Supabase nodes)
* sends alerts (Slack/Email)

**Design principle:** modular workflows, each with a single responsibility.

### 2) Data layer: PostgreSQL

Postgres is the source of truth:

* raw payload storage for audit (`raw_events`)
* normalized canonical transactions (`normalized_transactions`)
* unified ledger view (`unified_ledger`)
* reconciliation objects (`match_candidates`, `matches`, `discrepancies`)
* sync tracking for idempotency (`sync_state`, `qbo_journal_entries`)

**Design principle:** keep reconciliation *reproducible* (same inputs → same outputs).

### 3) Matching logic layer: Python inside n8n

Python nodes implement deterministic matching:

* exact matches (external refs / ids)
* net vs gross reconciliation (fee-aware)
* refund linking (refund → original)
* split payment grouping (sum of parts ≈ expected)
* candidate scoring & thresholding

**Design principle:** explainable rules before ML.

### 4) Accounting sync (optional): QuickBooks Online

If enabled:

* journals are generated from settlement/payout events
* processor clearing accounts are used to avoid double counting
* sync is idempotent (don’t post the same journal twice)

---

## Data flow

### A) Ingestion phase

Each processor has its own workflow.

**Inputs**

* Stripe API
* PayPal API
* Square API
* ACH feed (CSV import or bank feed)

**Outputs**

* raw events saved to `raw_events`
* normalized transactions saved to `normalized_transactions`
* payouts/settlements saved to `payouts` (or equivalent)
* cursors updated in `sync_state`

**Key guarantees**

* incremental sync (cursor-based)
* idempotent writes (unique constraints)
* raw payload persistence

### B) Normalization → unified ledger

A ledger builder workflow standardizes all transactions into one consistent structure.

**Output table:** `unified_ledger`

Common fields include:

* processor / account
* transaction type (charge, refund, payout, fee)
* gross, fee, net
* currency + base currency conversion
* occurred_at / settled_at

### C) Matching engine

Runs multi-pass matching and produces:

* `match_candidates` (possible links + score)
* `matches` (accepted matches)
* `discrepancies` (exceptions requiring review)

### D) Exception queue + notifications

Discrepancies are triaged into a review queue.

Examples:

* unmatched payout
* unmatched transaction
* fee mismatch
* duplicate suspected
* currency inconsistency

Notifications:

* daily digest (Slack/email)
* severity thresholds

### E) Accounting sync (optional)

If QuickBooks is enabled:

* generate journal entries per settlement window
* post to QBO
* record journal id + sync metadata

---

## Clearing account model (QuickBooks)

To avoid double counting:

* **Do not** book each processor charge directly to your bank account.
* Book activity into a **processor clearing account** (e.g., "Stripe Clearing").
* When payout hits the bank, move balance from clearing → bank and book fees.

Typical journal per payout:

* **Debit** Bank (net payout)
* **Debit** Merchant Fees (fees)
* **Credit** Processor Clearing (gross)

---

## Idempotency & constraints

Recommended constraints:

* `raw_events`: `(processor, event_type, external_id)` unique
* normalized txns: `(processor_account_id, external_id)` unique
* payouts: `(processor_account_id, external_id)` unique
* matches: `(run_id, left_id, right_id)` unique (or hash)
* qbo journals: `(processor_account_id, payout_external_id)` unique

---

## Operational guidance

### Scheduling

Typical daily schedule:

1. Ingest Stripe
2. Ingest PayPal
3. Ingest Square
4. Import ACH
5. Build Unified Ledger
6. Run Matching
7. Generate Exceptions
8. Sync QBO (optional)
9. Snapshot Cash Position

### Observability

At minimum track:

* ingestion counts per processor
* number of matches vs discrepancies
* sum(net) vs sum(payouts) deltas
* QBO sync success/failure

### Tuning knobs

* date window tolerance (± days)
* amount tolerance (± cents)
* scoring weights
* match threshold

---
