# Multi-Processor Payment Reconciliation (n8n + Postgres)

Automate daily payment reconciliation across **Stripe**, **PayPal**, **Square**, and **Bank ACH** into a unified ledger, with intelligent matching (fees/refunds/splits/currency), discrepancy flagging, and optional **QuickBooks Online** journal sync.

> Built as **Solution #7** in my *30-Day Financial Automation Build Challenge*: production-grade financial ops automations built in **n8n + Postgres + Python** (inside n8n code nodes).

---

## Why this exists

Teams running multiple processors typically spend **10–20 hours/week** manually matching transactions to accounting.
That manual work creates:

* missed transactions
* duplicate postings
* fee mismatch confusion
* delayed cash visibility

This project gives you a repeatable, open-source reconciliation pipeline you can run daily.

---

## What it does

### Core capabilities

* **Daily auto-pull** from Stripe, PayPal, Square, and ACH sources
* **Unified transaction ledger** (normalized schema across processors)
* **Intelligent matching engine**

  * refunds
  * partial / split payments
  * fee variations
  * settlement vs auth timing
  * currency conversion (via FX table)
* **Discrepancy detection**

  * missing transactions
  * duplicates
  * fee mismatches
  * unmatched items (ledger vs books)
* **Exception queue** for finance review
* **(Optional) QuickBooks Online sync**

  * auto-create journal entries
  * track sync state + idempotency
* **Real-time cash position**

  * per processor account
  * consolidated view

### Intended outcomes

* Save **40+ hours/month**
* Reduce reconciliation errors by **~90%**
* Get reliable cash visibility across processors

---

## High-level architecture

```
┌──────────────┐     ┌──────────────┐
│ Stripe API    │     │ PayPal API    │
└──────┬────────┘     └──────┬────────┘
       │                     │
       │                     │
┌──────▼────────┐     ┌──────▼────────┐
│ Square API     │     │ Bank / ACH     │
└──────┬────────┘     └──────┬────────┘
       │                     │
       └──────────┬──────────┘
                  │
          ┌───────▼────────┐
          │ n8n Ingestion    │  (pagination, rate limits, retries)
          └───────┬────────┘
                  │
          ┌───────▼────────┐
          │ Postgres         │
          │ - raw_events      │
          │ - normalized txns │
          │ - unified_ledger  │
          │ - matches/errors  │
          └───────┬────────┘
                  │
          ┌───────▼────────┐
          │ n8n Matching     │ (Python code nodes)
          └───────┬────────┘
                  │
          ┌───────▼────────┐
          │ Exceptions Queue │ → Slack/Email + dashboard
          └───────┬────────┘
                  │
          ┌───────▼────────┐
          │ QBO Sync (opt.)  │ → journals + sync_state
          └──────────────────┘
```

---

## Repo structure

```
.
├─ sql/
│  ├─ schema.sql
│  ├─ seed/
│  │  ├─ processors.csv
│  │  ├─ processor_accounts.csv
│  │  ├─ fx_rates.csv
│  │  ├─ raw_events.csv
│  │  ├─ normalized_transactions.csv
│  │  ├─ unified_ledger.csv
│  │  ├─ match_candidates.csv
│  │  ├─ matches.csv
│  │  ├─ discrepancies.csv
│  │  └─ qbo_journal_entries.csv
│  └─ README.md
│
├─ n8n/
│  ├─ workflows/
│  │  ├─ 01_ingest_stripe.json
│  │  ├─ 02_ingest_paypal.json
│  │  ├─ 03_ingest_square.json
│  │  ├─ 04_ingest_ach_import.json
│  │  ├─ 05_build_unified_ledger.json
│  │  ├─ 06_match_transactions.json
│  │  ├─ 07_discrepancy_queue.json
│  │  ├─ 08_qbo_sync_journals.json
│  │  └─ 09_cash_position_snapshot.json
│  └─ README.md
│
├── docs/
│   ├── architecture.md
│   └─ screenshots/
│
└── .env.example                  # Template for environment variables (API keys, DB connection, etc.)
├─ LICENSE
└─ README.md
```

---

## Quick start

### 1) Requirements

* **Postgres 14+** (local, Supabase, Railway, RDS—anything Postgres)
* **n8n** (self-hosted or n8n cloud)
* Optional integrations:

  * Stripe API credentials
  * PayPal API credentials
  * Square API credentials
  * QuickBooks Online (OAuth app)

### 2) Create the database

Run the schema:

```bash
psql "$DATABASE_URL" -f db/schema.sql
```

### 3) Load seed/test data (optional)

If you want a demo quickly, import the CSVs under `db/seed/` into their matching tables.

> Tip: If you’re using **n8n Tables**, you can upload the CSVs directly there as well.

### 4) Configure environment variables

Copy `.env.example` → `.env` and set values.

Key variables:

* `DATABASE_URL`
* `N8N_BASE_URL` (optional)

Processor API creds (optional for live pulls):

* `STRIPE_SECRET_KEY`
* `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`
* `SQUARE_ACCESS_TOKEN`

QuickBooks Online (optional):

* `QBO_CLIENT_ID`, `QBO_CLIENT_SECRET`, `QBO_REALM_ID`
* `QBO_REFRESH_TOKEN` (or use n8n OAuth2 credential)

### 5) Import n8n workflows

In n8n:

* Go to **Workflows → Import from File**
* Import workflows from `n8n/workflows/` in order (01 → 09)

### 6) Run the demo flow

1. Run **01–04** to ingest (or just load seed data)
2. Run **05** to build the unified ledger
3. Run **06** to generate match candidates + matches
4. Run **07** to create discrepancy queue
5. (Optional) Run **08** to sync journals to QBO
6. Run **09** to compute cash position snapshot

---

## How matching works (summary)

This project uses a multi-pass reconciliation strategy:

1. **Exact match pass**

   * same processor account
   * same currency
   * amount within tolerance (configurable)
   * date window (e.g., ±2 days)
   * same external reference (when available)

2. **Fee-aware pass**

   * gross vs net normalization
   * fee computed and compared to expected range

3. **Refund & reversal pass**

   * links refunds to original charge
   * handles partial refunds

4. **Split / partial payment pass**

   * groups multiple ledger lines that sum to expected amount

5. **Scoring + best-candidate selection**

   * each candidate match gets a score
   * highest score wins (if above threshold)
   * everything else becomes an exception

Full details: `docs/matching-logic.md`

---

## Database model (overview)

The schema is designed for:

* **raw ingestion** (append-only)
* **normalization** (one row per canonical transaction)
* **ledger** (unified view for matching)
* **matching + discrepancies** (auditable reconciliation)
* **sync tracking** (idempotent journal creation)

Key tables:

* `processors`, `processor_accounts`
* `raw_events`
* `normalized_transactions`
* `unified_ledger`
* `match_candidates`, `matches`
* `discrepancies`
* `qbo_journal_entries`, `sync_state`

See: `db/schema.sql`

---

## n8n workflows

Each workflow is modular and can be run independently.

### Ingestion

* **01_ingest_stripe**: pulls charges, refunds, payouts/fees; stores raw + normalized
* **02_ingest_paypal**: pulls balances + transactions; stores raw + normalized
* **03_ingest_square**: pulls payments/refunds; stores raw + normalized
* **04_ingest_ach_import**: imports ACH batches (CSV/Bank export)

### Ledger + Matching

* **05_build_unified_ledger**: normalizes into a single ledger table
* **06_match_transactions**: generates candidates, scores, writes matches
* **07_discrepancy_queue**: flags mismatches + creates review queue

### Accounting Sync (optional)

* **08_qbo_sync_journals**: creates journal entries in QBO; tracks sync state

### Cash Visibility

* **09_cash_position_snapshot**: computes per-processor + total cash position

---

## Demo strategy (for video)

A simple, compelling 3–6 minute demo format:

1. **Problem (20s)**: “4 processors. Manual rec takes 10–20 hrs/week.”
2. **Architecture (30s)**: show n8n → Postgres → matching → exception queue → (optional) QBO.
3. **Live run (2–3m)**:

   * trigger ingestion or show populated ledger
   * run matching
   * open exceptions (duplicates, fee mismatch, missing settlement)
4. **QBO sync (30s)**: show journal entry created + idempotency
5. **Cash position (20s)**: show consolidated cash position snapshot

Script: `docs/demo-script.md`

---

## Production notes

* Use **per-processor cursors** and store them in `sync_state` for incremental pulls.
* Enforce **idempotency** using unique constraints on `(processor, external_id, event_type)` at the raw level and `(processor_account_id, external_transaction_id)` at the normalized level.
* Always preserve raw payloads for auditability.
* Consider adding:

  * dead-letter queue for failed ingestions
  * reconciliation tolerances per processor
  * alerting thresholds (e.g., any discrepancy over $500 triggers immediate Slack)

---

## Roadmap

* [ ] Add Xero journal sync
* [ ] Add NetSuite CSV export
* [ ] Add UI dashboard (simple web app or Metabase preset)
* [ ] Improve split-payment matching with subset-sum optimization
* [ ] Add automated FX pulls (ECB/OpenExchangeRates)

---

## Contributing

Contributions are welcome.

* Open an issue describing the bug/feature
* Include sample data (sanitized) if possible
* For workflow changes, export the updated n8n JSON and keep node names stable

---

## License

MIT (see `LICENSE`).

---

## Disclaimer

This is an automation template and reference implementation. Always validate outputs with your accounting team and tailor the journal logic to your chart of accounts and reporting requirements.

---

## Author

Built by **Ugo Chukwu** — Financial Automation Engineer.

If you’re dealing with reconciliation, revenue leakage, payment recovery, or finance ops automation at scale, feel free to reach out.
