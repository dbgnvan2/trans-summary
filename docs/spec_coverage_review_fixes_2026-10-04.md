# Spec coverage — review fixes 2026-10-04

Plan: `docs/plan_review_fixes_2026-10-04.md`. Review: `REVIEW-trans-summary-2026-10-04.md`.
Branch `validation-hardening`, commits `1c2cb73`..`ab8846e` (not pushed). Offline suite at
the end: 969 passed, 18 skipped, 3 xfailed.

| ID | Status | Evidence |
|---|---|---|
| R1 (G1) GUI BLOCK applies gate side effects | done | `tests/test_ts_gui_web_generation.py::test_r1a_gui_block_quarantines_stale_bundle`, `::test_r1b_gui_block_writes_marker_and_manifest`, `::test_r1c_gui_allow_does_not_quarantine` |
| R2 (G11) cleanup deletes only own `_vN` | done | `tests/test_cleanup_pipeline_r2.py` (4 tests) |
| R3 (B-05) resolved placeholders not re-sent | done | `tests/test_extraction_placeholder_r3.py` |
| R4 (D-09) CSS not escaped | done | `tests/test_html_css_r4.py::test_r4a_css_not_escaped` |
| R5 (F12/F14) client factory, one retry layer | done, one deviation | `tests/test_client_factory_r5.py` (11 tests). R5.c uses new `config.TIMEOUT_FALLBACK = 600` (the SDK default) instead of `TIMEOUT_DEFAULT = 300`, which could have timed out long non-streaming calls that used to get 600 s |
| R5 + B-11 max_tokens not retried | done | `tests/test_client_factory_r5.py::test_b11_max_tokens_not_retried_and_usage_logged` |
| R6 (F2) names in headings / labels / `---` | done | `tests/test_faithfulness_scaffolding_r6.py` (incl. R6.e real-artifact pins, Title-Case heading run test). R6.f docstring: human check |
| R7 (F3) theme judge sees evidence | done | `tests/test_theme_judge_input_r7.py`; gold ug12/ug13 |
| R8 zero claims → ERROR | done | `tests/test_faithfulness_judge.py::test_r8a_*`, `::test_r8b_*`, `::test_r8c_*`; `tests/test_release_gate.py::test_r8d_zero_claims_artifact_blocks` |
| R9 (F4) cache key covers extraction | done | `tests/test_judge_disk_cache_h2.py::test_r9a_*`, `::test_r9b_logic_version_bumped` |
| R10 live re-calibration | done (live) | 2026-10-04: faithfulness gold recall/precision 1.0/1.0 (33 cases); real abstracts roots_bowen PASS, where_roots + dave_g FAIL; theme judge 1.0/1.0 (20 real grounded, 13 ungrounded incl. ug12/ug13). Not offline-testable |
| R11 Gen Abstract fails when unfaithful | done | `tests/test_abstract_faithful_retry.py::test_r11a_*`, `::test_r11b_*` |
| R12 (G6) speaker item from presenter | done | `tests/test_coverage_speaker_r12.py` |
| R13 (F13) summary LLM rescue | done | `tests/test_validator_gating_r15.py::test_r13a_*`, `::test_r13b_*` |
| R14 (C-07) unverified ≠ missing | done | `tests/test_validator_gating_r15.py::test_r14b_*`, `tests/test_abstract_validation_llm_fallback.py::test_r14a_*` |
| R15 validators gate publication | partial | Emphasis, topics, summary coverage gate (`emphasis_grounding`, `topics_grounding`, `summary_coverage` in `config.GATE_BLOCKING_CHECKS`; tests `test_validator_gating_r15.py::test_r15c_*`, `::test_r15e_*`, `::test_r15b_*`, `::test_r15d_*`). **Key terms not gated**: decision 2a required all trusted samples to pass; `dave_g_test2` still fails 2 paraphrased labels (`::test_r15e_key_terms_stay_advisory`). R15.a design changed: the deterministic checks run live in the gate instead of stored verdicts |
| R16 docs | done | CHANGELOG 2026-10-05, TODO, README (`tests/test_docs_accuracy.py::test_r16_*`), ARCHITECTURE §4.3 |
| R17 learning-qa sweep | done | 9 findings, all fixed in `ab8846e` (`tests/test_validator_gating_r15.py::test_sweep*`, `test_api_exceptions.py::test_rate_limit_honours_retry_after_header`). Not re-swept after the fixes |
| R18 status report | done | this file |

Not run: the nightly mutation gate (`quality_gates.py mutation`, ~30 min).
`_emphasis_quote_found_ratio` — a gated target, floor 0.5 — gained a disfluency
step and an empty-quote guard; its new branches are covered by
`test_r15_emphasis_ignores_disfluencies` and `test_sweep_empty_or_filler_only_quote_grounds_nothing`.
