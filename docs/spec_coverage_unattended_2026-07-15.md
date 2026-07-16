# Unattended-Robustness — exit-criteria sign-off (U1–U7)

Spec: [`spec_unattended_robustness_2026-07-15.md`](spec_unattended_robustness_2026-07-15.md).
Phase 5 (measure U1–U7; close). Status **2026-07-15: all seven exit criteria met.**
Per-module coverage detail: [`spec_coverage_m2`](spec_coverage_m2_2026-07-15.md),
[`spec_coverage_m3`](spec_coverage_m3_2026-07-15.md); the rest are recorded in
`CHANGELOG.md`.

Suite at sign-off: **564 passed / 17 skipped / 5 xfailed / 0 failed** (live faithfulness
calibration opt-in). The judge is armed (`config.FAITHFULNESS_JUDGE_ENABLED = True`).

| ID | Exit criterion | Status | Delivered by | Evidence |
|----|----------------|--------|--------------|----------|
| **U1** | No run publishes an artifact that failed a hard gate. | ✅ met | M1 gate guards the publish path (`release_gate.publish_allowed`; `html_generator`/`packaging_pipeline` refuse to write on BLOCK, quarantine stale bundles) + M5 | `test_release_gate.py::test_m1b2_blocked_run_writes_no_bundle`, `::test_m1b2_publish_allowed_reflects_gate`, `test_m5_fault_injection.py::test_m5d1_fault_in_blocking_check_blocks` |
| **U2** | Every quote, timestamp, section-citation, and named entity in a published artifact is machine-verified against the source, or the artifact is blocked — **including fluent prose hallucinations**. | ✅ met (was partial until M2 armed) | M4 (entity grounding, verbatim quotes, timestamp citations) + **M2 faithfulness judge (ARMED)** | `test_release_gate.py::test_m1_real_run_with_fabricated_name_blocks`, `::test_m4a_*`, `::test_m4b_*`; `test_faithfulness_calibration.py::test_m2b1_real_abstract_artifacts_judged_correctly` (FAILs the real `Luciano Malorni`) |
| **U3** | A transient/tooling failure never equals a genuine pass or "absent"; it yields a distinct, retryable ERROR that blocks publish (P1). | ✅ met | M1.C + M5.D | `test_release_gate.py::test_m1c1_error_on_blocking_check_blocks_advisory_error_does_not`, `::test_m1c1_missing_source_is_error_not_pass`; `test_m5_fault_injection.py::test_m5d1_fault_in_blocking_check_blocks` |
| **U4** | Every producer→consumer boundary is schema-validated; format drift is a hard error, not a silent zero (P19). | ✅ met | M3 (`artifact_contracts.py` + `schemas/`; gate `check_artifact_contracts`, hard blocker) | `test_artifact_contracts.py::test_m3c2_*`, `::test_m3d1_legacy_markdown_migrates`; `test_release_gate.py::test_m3c2_drifted_bowen_artifact_blocks`, `::test_m3c2_drifted_boundary_blocks` |
| **U5** | Every run emits one machine-readable manifest carrying an authoritative publish decision + provenance. | ✅ met | M7 (`build_manifest`/`write_manifest`; run-manifest JSON + PUBLISH-BLOCKED marker) | `test_release_gate.py::test_m7a1_manifest_matches_gate`, `::test_m7b1_exit_code_reflects_decision` |
| **U6** | Mutation score on core modules ≥ threshold in CI; zero assertion-free tests; parser/validator tests run against real formats. | ✅ met | M6 (`quality_gates.py` vacuity checker + mutation-gate config + CI job) | `test_quality_gates.py::test_m6a1_mutation_gate_config_is_valid`, `::test_m6b1_vacuity_checker_flags_assertionless_test`, `::test_m6b1_no_new_vacuous_tests`, `::test_m6c1_real_format_fixtures_exist` |
| **U7** | The full edge-case/fault matrix (empty / short / long / malformed / API-fail / dirty re-run / partial artifacts) each fails closed or degrades with a distinct signal. | ✅ met | M5 (`test_m5_fault_injection.py`) | `::test_m5a1_input_edge_matrix_never_crashes_decision_definite`, `::test_m5b1_missing_source_blocks`, `::test_m5c1_gate_is_idempotent_same_state`, `::test_m5d1_*` |

## Design principles held

1. **Fail closed** — absence of proof of correctness blocks publication (ERROR blocks by default; the publish path writes no bundle on BLOCK).
2. **Verify against the artifact, now** (P6) — checks resolve the exact on-disk artifact; the judge model is pinned to its calibrated version so a model bump can't silently un-calibrate it.
3. **Transient ≠ terminal** (P1) — a check that couldn't run is ERROR, not PASS/FAIL, and is retryable (the faithfulness memo never caches ERROR).
4. **Contracts are code** (P19) — every boundary format is a schema enforced on both sides.
5. **Every drop is surfaced** (P2) — zero-from-non-empty is a loud error; "nothing judged" is not "all faithful".
6. **The judge is judged** — M2 ships only after clearing precision/recall on a gold set **built from the real extraction path** (the P10 lesson: an isolated-example gold set gave a falsely-perfect calibration).

## Residual risk (documented, not eliminated)

Per the spec's own note, "no hallucination ever ships" is not provable in the
absolute; it is *reduced to* U2's machine-checkable subset (verbatim + entailment
over the gold set). Faithfulness covers **prose** artifacts; **themes** are excluded
(interpretive by design) pending a description-only path. Escaped hallucinations
should each become a new gold-set case (living artifact). Follow-ups tracked in
`TODO.md`.
