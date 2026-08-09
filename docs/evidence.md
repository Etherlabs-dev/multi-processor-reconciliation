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

### Synthetic / demonstration
Seed data and example transactions can demonstrate matching behavior, but they are not proof of real-world business impact.

### Not established by this repository alone
- 40+ hours/month actually saved for a real finance team
- ~90% reduction in reconciliation errors
- live production throughput at a stated transaction volume
- live QuickBooks accounting correctness
- production uptime/SLA

Any future benchmark should state the dataset, number of transactions, discrepancy mix, expected matches, actual matches, false-match rate, unresolved rate and runtime.