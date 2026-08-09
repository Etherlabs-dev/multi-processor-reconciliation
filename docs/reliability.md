# Reliability and Failure Modes

Financial reconciliation fails differently from ordinary workflow automation: a silent false match can be worse than an explicit unresolved item. The design should therefore prioritize auditability, deterministic controls, and safe failure.

## 1. Duplicate ingestion

**Risk:** retries or webhook redelivery create duplicate ledger records.

**Controls:**
- stable external-event identifiers;
- unique constraints;
- idempotent upserts;
- raw-event retention;
- replay tests.

## 2. Partial ingestion / pagination gaps

**Risk:** a processor API page, payout window, or cursor is skipped.

**Controls:**
- persist per-source cursors/checkpoints;
- reconcile ingestion counts;
- alert on stale cursors;
- support bounded replay windows.

## 3. Rate limits and transient API failures

**Controls:** exponential backoff, bounded retries, jitter, failed-event capture, and retry visibility.

## 4. Settlement timing differences

Authorizations, captures, payouts and bank settlements can occur on different dates.

**Control:** matching windows must be explicit and processor-specific rather than hidden inside workflow branches.

## 5. Fee mismatch

Gross and net amounts should never be compared without a documented fee model.

**Control:** normalize gross, fee, refund, FX and net values separately where the processor exposes them.

## 6. Refunds and reversals

Refunds must remain linked to their originating transaction. Partial refunds require amount-aware relationship logic.

## 7. Split payments / grouped settlement

Multiple records may legitimately reconcile to one target amount.

**Control:** grouping logic should be deterministic, bounded and covered by unit tests. Avoid unbounded subset searches on large candidate sets.

## 8. False-positive reconciliation

**Risk:** the matcher selects the wrong candidate merely because one candidate scores highest.

**Control:** require a minimum confidence/score and preserve ambiguity as an exception. Do not force a match when confidence is low.

## 9. Accounting-sync duplication

**Risk:** retrying a QuickBooks workflow posts duplicate journals.

**Controls:** idempotency keys, sync-state records, external journal identifiers and reconciliation of sync results.

## 10. Human exception handling

Every unresolved item should expose:
- why it failed to match;
- candidate evidence;
- amount/currency/source;
- age;
- reviewer/owner;
- resolution history.

## 11. Credential and webhook security

- store secrets in credential managers/environment variables;
- verify webhook signatures where supported;
- use least-privilege API scopes;
- never place live credentials in workflow JSON committed to Git.

## 12. Observability

A production system should expose:
- ingestion success/failure count by source;
- records normalized;
- match rate;
- exception rate;
- exception value by currency;
- oldest unresolved item;
- retry/dead-letter count;
- accounting-sync success/failure;
- workflow duration and error rate.

## Executed acceptance tests

The automated suite now includes fixtures for:
- exact match;
- date-tolerance match;
- fee-aware match;
- duplicate input;
- missing source transaction;
- partial refund;
- full reversal;
- split payment;
- currency mismatch;
- ambiguous candidate set;
- retry/replay idempotency;
- accounting-sync replay.

The suite also validates malformed monetary/currency/identifier inputs, deterministic ordering/fingerprints, stale cursor rejection, atomic failed batches, database uniqueness and balanced accounting entries. These tests establish repository behavior; they do not establish live processor or QuickBooks reliability.
