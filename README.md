# Multi-Processor Payment Reconciliation

> Reference architecture for reconciling Stripe, PayPal, Square and ACH transactions into a canonical ledger with matching, discrepancy handling and optional accounting sync.

**Status:** Reference Implementation / Portfolio System  
**Domain:** Payments · Finance Operations · Reconciliation  
**Stack:** n8n · PostgreSQL · SQL · API integrations

This repository demonstrates the architecture and workflow design for a multi-processor reconciliation system. It is intended to show how payment events can be ingested, normalized, matched, reviewed and synchronized without treating n8n itself as the entire engineering story.

It is **not presented as a verified client deployment**. Time-savings and error-reduction figures should be treated as modeled business outcomes unless separately evidenced.

---

## Problem

Finance teams operating across multiple processors often need to reconcile:

- processor transactions;
- payouts and settlement timing;
- refunds and reversals;
- processor fees;
- ACH/bank records;
- accounting journal entries.

The difficult part is not merely pulling APIs. The system needs a canonical transaction model, idempotent ingestion, deterministic matching, explicit exception handling and an audit trail.

---

## System flow

```text
Stripe ─────┐
PayPal ─────┤
Square ─────┼──→ ingestion workflows
ACH import ─┘           ↓
                    raw events
                         ↓
                 normalize + enrich
                         ↓
                  canonical ledger
                         ↓
                   matching engine
                  ↙              ↘
              matched          exceptions
                 ↓                 ↓
          accounting sync     review / alerts
                 ↓
          cash-position view
```

### Implemented workflow artifacts

The repository currently contains eight n8n workflows:

1. `01_ingest_stripe.json`
2. `02_ingest_paypal.json`
3. `03_ingest_square.json`
4. `04_ingest_ach_import.json`
5. `05_normalize_enrich.json`
6. `06_reconcile_match_engine.json`
7. `07_qb_sync.json`
8. `08_exception_notifications.json`

The previous README referred to workflow `09`, but no ninth workflow exists in the repository. This upgrade corrects the documentation to match the actual artifact set.

---

## Core capabilities represented in the design

### Ingestion

- processor-specific source workflows;
- raw-event preservation;
- normalization into a common representation;
- support for batch ACH import.

### Reconciliation

The design accounts for multiple matching passes, including:

- exact/reference matches;
- date-window tolerance;
- fee-aware comparisons;
- refund/reversal relationships;
- partial or split-payment handling;
- scored candidate selection;
- unmatched-item exception handling.

### Accounting and review

- optional QuickBooks journal-sync workflow;
- discrepancy / exception notifications;
- sync-state/idempotency concepts;
- consolidated cash-position modeling.

---

## Repository structure

```text
multi-processor-reconciliation/
├── .env.example
├── sql/
│   ├── schema.sql
│   └── seed/
├── n8n/
│   └── workflows/
│       ├── 01_ingest_stripe.json
│       ├── 02_ingest_paypal.json
│       ├── 03_ingest_square.json
│       ├── 04_ingest_ach_import.json
│       ├── 05_normalize_enrich.json
│       ├── 06_reconcile_match_engine.json
│       ├── 07_qb_sync.json
│       └── 08_exception_notifications.json
├── docs/
│   ├── architecture.md
│   └── screenshots/
├── README.md
└── LICENSE
```

---

## Database model

The SQL layer is designed around distinct lifecycle stages rather than a single mutable transaction table.

Typical entities include:

- processor definitions and accounts;
- append-oriented raw events;
- normalized transactions;
- unified ledger entries;
- match candidates;
- confirmed matches;
- discrepancies/exceptions;
- accounting journal records;
- synchronization state.

This separation matters because reconciliation needs both **current operational state** and **historical auditability**.

---

## Matching strategy

A production reconciliation engine should not rely on one equality check. The intended approach is a staged deterministic matcher:

### Pass 1 — high-confidence exact/reference matching

Compare stable external identifiers, processor account, currency and expected amount where those values are available.

### Pass 2 — tolerance-aware matching

Allow controlled settlement-date and fee differences while preserving explicit tolerances.

### Pass 3 — refund/reversal relationships

Link reversals and partial refunds back to the originating transaction.

### Pass 4 — split/partial settlement handling

Evaluate groups of records where multiple lines may reconcile to one expected amount.

### Pass 5 — exception queue

Anything below the acceptance threshold remains reviewable rather than being silently forced into a match.

For financial controls, **false reconciliation can be more damaging than an unresolved exception**. The system should therefore prefer explicit review over unjustified certainty.

---

## Quick start

### Requirements

- PostgreSQL 14+
- n8n
- optional processor/accounting credentials for live integrations

### 1. Create the database

The schema in this repository is under `sql/`:

```bash
psql "$DATABASE_URL" -f sql/schema.sql
```

### 2. Load sample data if required

Seed assets are under:

```text
sql/seed/
```

They are intended for demonstration and validation, not as production evidence.

### 3. Import workflows

Import the eight JSON files from `n8n/workflows/` in numeric order.

### 4. Configure credentials

Use n8n's credential manager and environment configuration. Do not commit live payment or accounting secrets.

---

## Evidence standard

| Claim type | Current status |
|---|---|
| Workflow artifacts exist | **Implemented** |
| SQL/data model exists | **Implemented** |
| Matching architecture is documented | **Implemented** |
| Sample/seed scenarios | **Synthetic / Demonstration** |
| Live multi-processor client deployment | **Not claimed here** |
| 40+ hours/month saved | **Modeled outcome, not verified client evidence here** |
| ~90% error reduction | **Modeled outcome, not verified client evidence here** |

See [`docs/evidence.md`](./docs/evidence.md).

---

## Reliability requirements for a production implementation

Before this pattern should be described as production-grade, the system should demonstrate:

- webhook/API authentication and signature verification;
- incremental cursors/checkpoints;
- idempotent raw ingestion;
- unique constraints against duplicate external events;
- rate-limit and retry handling;
- dead-letter or failed-event recovery;
- processor-specific reconciliation tolerances;
- transactional accounting-sync controls;
- replay-safe workflow behavior;
- structured logs and run metrics;
- automated tests around matching rules;
- explicit exception ownership and audit history.

See [`docs/reliability.md`](./docs/reliability.md).

---

## What should move out of n8n in a stronger implementation

n8n is useful for orchestration, scheduling, connectors and human-facing operational flows. The core reconciliation logic becomes stronger portfolio evidence when deterministic business logic is independently testable.

A target architecture should consider moving:

- canonical schemas;
- match scoring;
- tolerance rules;
- subset/split matching;
- idempotency helpers;
- validation;

into a small Python package/service with unit tests, while n8n remains the orchestration layer.

That is the primary engineering upgrade still required for this repository.

---

## Limitations

- Processor JSON workflows are reference artifacts and require credential/configuration review before live use.
- This repository does not independently prove the business-outcome numbers previously described in the README.
- Matching behavior needs executable automated tests rather than documentation alone.
- The optional QuickBooks flow requires validation against the target chart of accounts and accounting policy.
- Multi-currency and settlement behavior must be tested against real processor edge cases before production use.

---

## License

MIT. See [`LICENSE`](./LICENSE).

---

Built by **Ugo Chukwu / Etherlabs** as a financial-systems reference implementation.