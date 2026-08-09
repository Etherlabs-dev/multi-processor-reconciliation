# Architecture

The repository uses a deliberately narrow service boundary: deterministic financial rules live in a Python 3.11 package, PostgreSQL is the durable audit/control layer, and n8n remains the integration orchestrator.

## Components

### Python reconciliation engine

`src/reconciliation` owns independently testable logic for:

- processor-specific normalization using `Decimal` and UTC timestamps;
- currency/type/date/amount candidate eligibility;
- explainable candidate scores and ambiguity controls;
- fee-aware, refund, partial-refund and bounded split classifications;
- deterministic input fingerprints;
- cursor/event replay behavior and accounting idempotency semantics.

FastAPI exposes `/normalize`, `/reconcile` and `/health` so workflows do not need to duplicate these rules. The reference in-memory idempotency objects define behavior; PostgreSQL constraints and compare-and-swap cursor updates provide durable enforcement.

### n8n orchestration

Eight committed workflows cover Stripe, PayPal, Square and ACH ingestion, normalization, reconciliation, accounting preparation and exception notifications. n8n owns schedules, API connectors, credential references, database calls and notifications. Workflows 01 through 06 delegate financial normalization or matching to the Python engine; their remaining Code nodes only parse transport formats or validate approved input.

Workflow 07 no longer derives monetary totals from a confidence score. It accepts only an explicitly approved journal payload with a stable idempotency key and equal debit/credit totals. Live QuickBooks posting remains an integration step that requires an organization-specific chart of accounts and accounting approval.

### PostgreSQL

The schema stores processor/account references, one checkpoint per account, raw-event hashes, canonical ledger transactions, payouts, reconciliation runs/matches/exceptions, accounting jobs and balanced posting evidence.

Important enforced controls include:

- unique raw events per account/type/external ID;
- unique ledger transactions and payouts per account/external ID;
- uppercase three-letter currencies and non-negative fees;
- immutable run fingerprints and replay-safe match/exception keys;
- one accounting job per idempotency key;
- balanced journal debit and credit totals;
- versioned checkpoints for compare-and-swap cursor advancement.

Credential values do not belong in PostgreSQL or workflow exports. `processor_accounts.credential_ref` stores only an external credential-manager reference.

## Data flow

```text
processor APIs / ACH
        │
        ▼
n8n source connectors
        │
        ▼
Python /normalize ──► ledger_transactions + payouts
        │
        ▼
Python /reconcile ──► recon_runs + matches + exceptions
        │                              │
        │                              └──► notifications / review
        ▼
approved balanced journal ──► replay-safe accounting job
```

The database and Python reference primitives implement raw-event hashes, duplicate suppression and checkpoint compare-and-swap behavior. Wiring each processor's real pagination response into durable `raw_events` and `sync_state` writes remains an explicit production integration gap; the workflow artifacts must not be presented as proving that live behavior.

## Safety choices

- Currency, record type, amount tolerance and date windows are hard eligibility controls.
- Close top candidates remain unresolved; the engine does not force the highest score.
- Split matching is bounded to groups of two through five (three by default).
- Duplicate inputs are reported and excluded from matching.
- Fingerprints are independent of input ordering.
- Cursor advancement rejects stale workers, and malformed batches do not mutate state.
- Reusing an accounting idempotency key with different content is a conflict.

## Known production gaps

This is a tested reference implementation, not a verified live deployment. Production adoption still requires processor webhook verification, API pagination/retry/dead-letter behavior, durable service adapters, monitoring, exception ownership, real statement calibration, and end-to-end accounting acceptance.
