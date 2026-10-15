# rca ledger (review convergence audits)

| Date | HEAD | Verdict | Scope | Batches | Fix commits | Notes |
|---|---|---|---|---|---|---|
| 2026-10-14 | 1d284a9 | STILL FINDING REAL FAULTS | 7c673b6..1d284a9 (last 30, no prior ledger) | 22 (one pushed fix commit each) | 22 | 21/22 with assertion-level fail-before/pass-after (845ea1f: new module, error-only); oscillation: abstract word limit 73168f1->59d64c8, revise first-line rule 59d64c8->44937a4; last-3-batch lines 63% tests/docs |
