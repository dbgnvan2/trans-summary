# M2 spec coverage — semantic faithfulness judge

Spec: [`spec_unattended_robustness_2026-07-15.md`](spec_unattended_robustness_2026-07-15.md) §M2.
Scope (confirmed 2026-07-15): all narrative artifacts (abstract, summary, overview,
blog, themes); Sonnet judge; full build incl. live calibration.

**Status:** code + gold set + gate wiring + offline tests complete; the judge is
**disabled by default** (`config.FAITHFULNESS_JUDGE_ENABLED = False`) and ships
only once the live M2.B.1 calibration clears the precision/recall bars. Live
calibration is **blocked pending an `ANTHROPIC_API_KEY`** in the run environment.

## Acceptance criteria → tests

| AC | Requirement | Status | Verified by |
|----|-------------|--------|-------------|
| **M2.A** | Claim-level entailment for narrative artifacts; unentailed → FAIL naming the sentence | ✅ done | `faithfulness_judge.judge_artifact`; `test_faithfulness_judge.py::test_m2a1_fabricated_claim_flagged` |
| **M2.A.1** | On a fixture with a known fabrication, returns FAIL naming that sentence | ✅ done | `::test_m2a1_fabricated_claim_flagged` (Luciano-Malorni-shaped injected claim) |
| **M2.A.2** | On the clean real artifact, returns PASS (no false FAIL) | ✅ done | `::test_m2a2_clean_artifact_passes` |
| **M2.B** | Curated gold set pins the judge's threshold | ✅ built | `tests/fixtures/faithfulness_gold/gold.json` (21 real-source cases); `::test_gold_set_is_balanced_and_sources_exist` |
| **M2.B.1** | Judge precision/recall on the gold set ≥ threshold (recall ≥0.9 on contradicted+unsupported) | ⏳ blocked | `test_faithfulness_calibration.py::test_m2b1_judge_meets_gold_thresholds` — **needs `ANTHROPIC_API_KEY`** + `RUN_FAITHFULNESS_CALIBRATION=1` |
| **M2.C** | Judge fails closed — its own error → ERROR (blocks), never PASS | ✅ done | `::test_m2c1_judge_error_is_error_not_pass`, `::test_m2c_unparseable_judge_response_is_error`; gate: `test_release_gate.py::test_m2c_faithfulness_no_apikey_is_error_blocks` |
| **M2.C.1** | Judge exception → ERROR verdict | ✅ done | `::test_m2c1_judge_error_is_error_not_pass` |

## Gate wiring (U2)

`release_gate.check_faithfulness` judges `config.FAITHFULNESS_ARTIFACT_SUFFIXES`;
FAIL/ERROR → BLOCK (`faithfulness` in `config.GATE_BLOCKING_CHECKS`). A PASS no-op
while disabled, so the deterministic gate is unaffected until enabled
(`test_release_gate.py::test_m2_faithfulness_disabled_is_noop_pass`,
`::test_m2_faithfulness_fail_blocks`).

## The judge is judged (M2.B)

`binary_faithfulness_metrics` computes precision/recall on the dangerous class
(contradicted+unsupported collapsed vs entailed); recall is load-bearing (a FN is a
hallucination waved through). Bars in config: recall ≥ 0.90, precision ≥ 0.70.
Offline-tested (`::test_binary_metrics_*`). The gold set uses **real** sources
(`dave_g_test2`, `where_roots`) with labels verified against the source text (P6);
it includes the real shipped `Luciano Malorni` fabrication as an `unsupported` case.

## Calibration procedure (the live, spend step)

```
RUN_FAITHFULNESS_CALIBRATION=1 ANTHROPIC_API_KEY=... \
  PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_faithfulness_calibration.py -q -s
```
Prints a per-case truth-vs-prediction table + metrics. If it clears the bars, flip
`config.FAITHFULNESS_JUDGE_ENABLED = True` to arm the gate. If it misses, tune the
judge prompt / thresholds and re-run (the gold set is the living calibration
artifact — add every escaped hallucination found in production).

## Not code-testable (flagged per planning rules)

The judge's *semantic* quality is bounded by the gold set, not a unit test (spec
§M2 flags this). Proposal on record: living gold set + human sign-off on any
threshold change. AC M2.B.1 makes the *threshold* testable; the judgment quality is
a curated-eval concern.
