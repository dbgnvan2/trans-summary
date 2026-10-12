# TODO triage and plan — 2026-10-11

Status: **proposed, awaiting approval.** No code changed yet.

Source: every open entry in `TODO.md` as of `4ffd3c9`, checked against the code on main.
Groups: **S** stale (close in TODO), **U** urgent, **Q** quick fixes with tests,
**D** needs your decision, **C** calibration runs (API spend, public sources only),
**L** larger work (defer, keep in TODO).

---

## S — Already fixed or no longer true (close in TODO.md, no code)

| TODO entry | Evidence on main |
|---|---|
| `_load_runtime_settings` crashes on valid non-dict JSON | `config.py:79` `isinstance(data, dict)` reset (review C1) |
| Dead duplicate `_generate_simple_html_page` | one definition, `html_generator.py:621` |
| Themes parser misses `### N. Title` (M3 shim) | `transcript_utils.parse_bold_numbered_theme_blocks` docstring: handles both formats (AC M3.D.1) |
| Phase 0 "6 vacuous tests on the allowlist" | `KNOWN_VACUOUS` no longer exists; Test-debt section already says fixed |
| Test debt "add a mutation-score gate to CI" | `.github/workflows/*.yml` nightly `mutation-gate` job runs `quality_gates.py mutation` |
| 2026-07-17 "re-calibrate after metadata-in-source" | re-calibrated 2026-07-19, 2026-10-04, 2026-10-09, 2026-10-10, 2026-10-11 |
| Pre-existing failures: Bowen integration (2) | un-xfailed 2026-07-15; removed from `KNOWN_REDS` |
| "`topic_term_faithfulness` … are blocking" (2026-09-23) | not in `GATE_BLOCKING_CHECKS` (`config.py:578`); it is advisory. Reword the entry. |
| "the theme and key-terms judges have no confirmation" | your decision CD2 (faithfulness only). Move to "accepted". |
| H12 "judge model is a floating alias" | judges moved to `claude-sonnet-5-5`; keep the note but update the model name |
| `--prose-real` output lacks prompt sha | `judge_recalibration.run_metadata()` (CF) records it; the metadata half stays open (Q5) |

---

## U — Urgent: Haiku 4.5 retirement (no sooner than 2026-10-15, 4 days)

`FORMATTING_MODEL`, `VALIDATION_MODEL` and `AUX_MODEL` all default to
`claude-haiku-4-5-20251001` (`config.py:47-49`). Haiku 4.5 is also referenced in
`model_specs.py`, `test_anthropic_models.py`, `skills/.../review_outputs.py` and 3 tests.

**Adjacent problem found:** `MODEL_OUTPUT_TOKEN_LIMITS` (`config.py:925`) has no entry for
`claude-haiku-5-5` or `claude-sonnet-5-5`, and `cap_max_tokens_for_model` falls back to
`MAX_TOKENS_SUMMARY` = 4096 for unknown models. Switching a model without adding its limit
could cap output at 4096 tokens (P9). U1 checks whether formatting goes through this cap.

| ID | Step | Verified by |
|---|---|---|
| U1 | Find every call path that uses the three Haiku defaults and whether each goes through `cap_max_tokens_for_model`. | list in the plan's results section |
| U2 | Add `claude-haiku-5-5` (and `claude-sonnet-5-5`) output limits from Anthropic's models page. | `tests/test_v5_models.py::test_u2_output_limits_known` |
| U3 | Run formatting on 3 public transcripts (roots_bowen, where_roots, Kerr 2026-09-13) with Haiku 4.5 and the candidate. Compare: mismatch count, contiguous-run max, heading errors, corrections, cost, time. | `docs/calibration_formatting_model_2026-10-11.md` + JSON in `docs/calibration/` |
| U4 | If the candidate is equal or better: switch the three defaults, update `model_specs.py`, README, ARCHITECTURE_DESIGN, CHANGELOG. | `tests/test_v5_models.py::test_u4_no_retiring_model_defaults` (no default ends in a retiring model id) |
| U5 | Run Initial Validation (V2) on the same 3 with the new `VALIDATION_MODEL`; findings count must not drop to zero (fail-open check). | same report |

Cost: about 6 formatting runs + 3 validation runs; I will report the estimate before
running. Not code-testable: formatting quality beyond the counts — you review one
formatted transcript side by side (human review).

**Decision U-a:** candidate model. My recommendation: `claude-haiku-5-5` for all three
(same tier, same price class). Alternative: `claude-sonnet-5-5` for formatting only if
Haiku 5.5 makes more heading errors.

---

## Q — Quick fixes (code + test, one batch)

| ID | Fix | Test (written first) |
|---|---|---|
| Q1 | `transcript_validate_webpage.missing_names`: match on word boundaries, so "Self" is not found inside "Differentiation of Self". (Hermes LOW, P7) | `tests/test_simple_web_validation.py::test_q1_substring_of_other_item_is_missing` (adversarial) + existing extra-text case still passes |
| Q2 | Emphasis saver writes `"` inside quote/concept raw (`extraction_pipeline.py:682`); map to `'` like `_format_bowen_refs`. | `tests/test_emphasis_roundtrip.py::test_q2_nested_quote_round_trips` (save → `parse_scored_emphasis_output` returns the full quote) |
| Q3 | Emphasis: when items parse but none validate for a reason other than verbatim, the raw response is saved (`extraction_pipeline.py:701`). Return False and save nothing, as the verbatim branch already does. | `tests/test_emphasis_roundtrip.py::test_q3_all_items_rejected_saves_nothing` |
| Q4 | `abstract_pipeline.parse_topics_from_extraction`: skip a topic whose name strips to `""`. | `tests/test_abstract_pipeline.py::test_q4_blank_topic_name_skipped` |
| Q5 | `judge_recalibration --prose-real` builds the source without the filename metadata the gate adds, so date/year claims are over-reported. Use the same metadata block as `release_gate._source_with_metadata`. | `tests/test_judge_recalibration.py::test_q5_prose_real_source_has_metadata` |
| Q6 | Replace the prompt example "attributes recovery to medication" (paraphrases gold us6) with one not in the gold set. This changes the judge prompt, so it needs a calibration run (C1). | `tests/test_faithfulness_judge.py::test_q6_prompt_examples_not_in_gold` (no example shares ≥5 content words with any gold claim) |

Q1–Q5 do not change the judge; Q6 does. I propose Q6 rides with C1, not this batch.

---

## D — Needs your decision

| ID | Question | My recommendation |
|---|---|---|
| D1 | Published Themes section shows the themes file's title, `---` lines and "Structural Themes (3 total)" (`html_generator._extract_webpage_metadata` falls back to the whole file). Render themes from the parsed items instead? Changes the published page. | Yes. Tests: page has no `---`/file title inside Themes; every parsed theme name present (both layouts). |
| D2 | Sticky cached FAIL: a FAIL verdict is saved to disk and replayed on re-runs. Stop persisting FAIL/ERROR verdicts (PASS only)? Cost: a failing artifact is re-judged on each gate run. | Yes, PASS only. Test: dirty-state (P8) — cached FAIL file present, gate re-judges. |
| D3 | Delete the stale worktree `.claude/worktrees/hungry-wilbur`? Its branch has no commits missing from main, but it has an uncommitted change to `ts_gui.py` (from 2026-02) that would be lost. | Show you the diff first, then remove. Also delete the 5 fully merged branches (`claude/nostalgic-tu`, `claude/review-top5-fixes`, `refactor_v1`, `validation-hardening`, `chore/untrack-ds-store`). Keep `judge-framing` (archive). |
| D4 | Partial miss of topics/themes/terms on the web page is a warning, not a block (RF.P.3). | Keep as is. |
| D5 | `cap_max_tokens_for_model` floors every model to 4096 (2 xfail tests). Make the cap the model limit when known? | Yes, together with U2 — otherwise the model switch can truncate output. |
| D6 | Emphasis quote threshold 0.80 lets "rational unit" pass for "emotional unit". | Measure first: score all real-fixture quotes, report the distribution; decide the threshold after. |
| D7 | Config settings don't reload across `ProjectSettings` instances (xfail). | Leave open; low impact. |

---

## C — Calibration runs (API spend, public sources only)

| ID | Run | Output |
|---|---|---|
| C1 | Q6 prompt change: gold set ×3 + 10 fresh Kerr checks (the CF method). Ships only if gold recall ≥ current and Kerr false fails stay 0/10. | `docs/calibration_q6_prompt_2026-10-xx.md` |
| C2 | `topic_term_faithfulness` on 3–5 public projects; keep advisory unless it is clean. | same style report |

C1 and C2 can wait until after U.

---

## L — Larger work: keep in TODO, not in this plan

H9 / M7 refactors, L13 GUI dispatch, M1 settings lock, L17 mutation timeout semantics,
chunked formatting, JSON sidecar consumer, Google Doc export, PDF text check, packaging
of main webpage/PDF against manifest hashes (simple page already checks mtime), F5
single orchestrator gate call, cross-artifact name consistency, emphasis timestamp drift,
Bowen extraction prompt, cost estimator, conclusion-phrase recall, entity surname rule,
Terms File vs pattern sets, gross-limit calibration, macOS review window, `_validated`
gate, k4/k5/k6 first-pass misses, google deps, stated-purpose extraction, topics gate
leniency (G9), key-terms gate (decided advisory).

---

## Order

1. S — TODO.md cleanup (docs only).
2. U1–U2 + D5 (token limits) → U3 runs → U4/U5 switch. Needs U-a.
3. Q1–Q5.
4. D1, D2, D3 per your answers.
5. learning-qa sweep on the diff, then commit to main.
6. C1 (with Q6), C2 later.

## Decisions needed now

U-a (candidate model), D1, D2, D3, D5. D4/D6/D7 default to my recommendation unless you say otherwise.
