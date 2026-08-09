# Evidence and Claim Policy

This repository is a **reference implementation** for multi-processor payment reconciliation. It should demonstrate architecture, control design, workflow artifacts and deterministic financial logic without presenting modeled outcomes as verified client results.

## Evidence classes

| Label | Meaning |
|---|---|
| **Implemented** | Present in repository artifacts |
| **Tested** | Covered by automated tests |
| **Synthetic / Demonstration** | Shown using seed or generated data |
| **Modeled Outcome** | Business impact estimated from assumptions |
| **Production** | Verified live deployment evidence |
| **Client Outcome** | Real customer result with evidence/permission |

## Current evidence position

### Implemented
- SQL schema and seed structure
- eight n8n workflow artifacts
- processor-specific ingestion flows
- normalization/enrichment workflow
- reconciliation/matching workflow
- accounting-sync workflow artifact
- exception notification workflow
- architecture documentation
- Python 3.11 reconciliation package and FastAPI boundary
- deterministic fingerprints and replay/idempotency primitives
- PostgreSQL uniqueness, balance, currency and cursor-version constraints

### Tested
- 38 automated tests with a real PostgreSQL 16 instance
- normalization, exact/date/fee/refund/partial/split/ambiguous/missing/duplicate/currency cases
- stale cursor, malformed batch, duplicate-event and accounting replay behavior
- schema creation, all seed imports and key database constraints
- successful import of all eight exports in n8n 2.33.7 plus an offline structural/secret scan

### Synthetic / demonstration
Seed data and the committed benchmark are synthetic. The independently executed synthetic benchmark contains six expected match groups: all six were correct, zero false matches were produced, and seven deliberately ambiguous/missing/currency-mismatched records remained unresolved. Runtime is machine-specific and is recorded as diagnostic evidence only.

### Not established by this repository alone
- 40+ hours/month actually saved for a real finance team
- ~90% reduction in reconciliation errors
- live production throughput at a stated transaction volume
- live QuickBooks accounting correctness
- production uptime/SLA

See `results/synthetic_benchmark.json` for configuration, environment, fingerprint and runtime provenance. It does not claim business savings, production throughput or client outcomes.
