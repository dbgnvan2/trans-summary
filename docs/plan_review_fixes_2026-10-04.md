# Plan — fixes from the 2026-10-04 full-repo review

Source: `REVIEW-trans-summary-2026-10-04.md` (repo root). Finding IDs (G1, F2, …) refer to that report and
are used verbatim below. Author decisions (2026-10-04): transcripts are trusted; keys.json fallback is
app-wide; emphasis/topics/key-terms/summary-coverage validators should gate; keep G7 as is; a non-empty
prose artifact with zero claims → ERROR; Gen Abstract fails when every attempt fails faithfulness; no
token report on halted runs.

Status: **PLAN — awaiting approval. No code changed.**

---

## Decisions needed before Phase 5 (everything else can start)

**D1 — what "gating" means for the four validators.** Two options:

| | (a) Halt the stage | (b) Block at publish (recommended) |
|---|---|---|
| Mechanism | Core / Structured Summary return False on a validator FAIL; Run Selected stops | Each validator writes a machine-readable verdict; a new `validator_verdicts` check in `GATE_BLOCKING_CHECKS` reads them |
| Run continues? | No — Bowen/Emphasis, blog, webpdf are skipped | Yes — all artifacts are produced; publish is blocked with the reason in the manifest and PUBLISH-BLOCKED marker |
| Precedent | — | Same reason Val Abstract was made advisory on 2026-07-16 (`fix(pipeline): make Val Abstract advisory so it can't halt Bowen/Emphasis`); the release gate is already the one place that decides publish |
| Stale-verdict risk | none | must key verdicts to the artifact hash (P6) so a regenerated artifact doesn't inherit an old verdict |

The plan below is written for (b). Under (a), R15 becomes a ~20-line change in `extraction_pipeline.py` and
`ts_gui.py` and R15.c/R15.d drop out.

**D2 — real-artifact fixtures for summary / overview / blog.** `tests/fixtures/` has none (G17). R6 and R8
change what the faithfulness judge sees for exactly those artifacts, and LEARNINGS.md records that idealized
calibration passed while real artifacts false-BLOCKed (M2). I need 2–3 real, user-reviewed
`- summary-generated.md`, `- overview.md`, `- blog.md` sets (e.g. from the KCFC projects folder the existing
fixtures came from). Please point me at them or approve copying from
`/Volumes/CrucialX9/1 MY DISK/KCFC ALL/projects/`.

**D3 — live re-calibration (costs API spend).** R6, R7 and R8 change the judges' input, so both gold-set
calibrations must be re-run against the live model (`RUN_FAITHFULNESS_CALIBRATION=1 …`, per project memory).
Needs `ANTHROPIC_API_KEY` exported. Approve running it, or run it yourself.

---

## Scope

In scope: the blocker (G1), every verified major except G7 (kept by decision), the author decisions (Q3, Q5,
Q6), and two confirmed one-line minors (B-05, D-09).

Out of scope (stay in the report; candidates for a later batch): all other minors, including F5 (mutation
harness), F11 (model provenance), G2/G13 (other ignored return values), G8/G9 (advisory-validator leniency —
see note under R14), STRUCT-* refactors.

---

## Acceptance criteria → tests

Test file names are new unless marked *(extend)*. Every test name carries the criterion ID.

### Phase 1 — independent, low-risk

**R1 (G1) — GUI publish BLOCK performs the gate side effects.**
- R1.a A BLOCK in the GUI webpdf stage quarantines a pre-existing `- webpage.html` / `- simple.html` / PDF to
  `*.blocked-stale`. → `tests/test_ts_gui_web_generation.py::test_r1a_gui_block_quarantines_stale_bundle` *(extend)*
- R1.b It writes the PUBLISH-BLOCKED marker and a manifest with decision BLOCK. →
  `…::test_r1b_gui_block_writes_marker_and_manifest`
- R1.c An ALLOW still generates and does not leave a marker. → `…::test_r1c_gui_allow_clears_marker`
- Implementation: on BLOCK call `release_gate.publish_allowed(base_name, logger)` (it re-runs the gate; the
  judge disk cache makes the second run cheap) — or add `release_gate.record_block(decision, base_name)` that
  performs marker + quarantine + manifest from an existing decision. Prefer the helper (no second gate run).

**R2 (G11) — cleanup deletes only this transcript's `_vN` files.**
- R2.a Cleaning `T - P - 2025-01-01` leaves `T - P - 2025-01-01 Part 2_v3.txt` in place. →
  `tests/test_cleanup_pipeline_r2.py::test_r2a_prefix_sibling_survives`
- R2.b `T - P - 2025-01-01_v1.txt` … `_v3.txt` are still removed. → `…::test_r2b_own_versions_removed`
- R2.c Timestamped variant `T - P - 2025-01-01_20250101_101010_v2.txt` — pin the intended behaviour (I'll
  read `parse_filename_metadata` and match it; if ambiguous I'll ask). → `…::test_r2c_timestamped_variant`
- Implementation: `re.fullmatch(re.escape(base_name) + r"_v\d+\.txt", f.name)` at `cleanup_pipeline.py:70-74`.

**R3 (B-05) — resolved placeholders are not re-appended.**
- R3.a A template containing `{{structural_themes}}` produces a prompt with no `## Provided Context` block
  for that key. → `tests/test_extraction_placeholder_r3.py::test_r3a_resolved_placeholder_not_reappended`
- R3.b A template without the placeholder still gets the context block (existing behaviour). →
  `…::test_r3b_unresolved_placeholder_appended`
- Implementation: `re.compile(r"\{\{\s*" + re.escape(key) + r"\s*\}\}", re.IGNORECASE)` at
  `extraction_pipeline.py:242`. Note: this changes the prompt sent for lens/theme generation (removes the
  duplicate). No calibration impact (generation, not the judges).

**R4 (D-09) — CSS is not HTML-escaped inside `<style>`.**
- R4.a Rendered webpage, simple page and PDF HTML contain `'Georgia'` and no `&#39;`. →
  `tests/test_html_css_r4.py::test_r4a_css_not_escaped` (parametrized over the three templates)
- Implementation: `{{ common_css|safe }}`, `{{ webpage_css|safe }}`, `{{ pdf_css|safe }}` in the three
  templates. CSS is repo-owned, not user input.

### Phase 2 — shared Anthropic client (Q2: app-wide keys.json)

**R5 (F14 + F12) — one client factory used everywhere.**
- R5.a `transcript_utils.get_anthropic_client()` resolves the key via `resolve_anthropic_key()` (env, then
  keys.json) and raises a clear error if neither exists. →
  `tests/test_client_factory_r5.py::test_r5a_factory_uses_keys_json_when_env_unset`
- R5.b The client is built with `max_retries=0` (the wrapper is the only retry layer). →
  `…::test_r5b_sdk_retries_disabled`
- R5.c `call_claude_with_retry` uses `config.TIMEOUT_DEFAULT` when no timeout is passed; the 900.0 fallback
  and 1.5 escalation factor move to `config.py`. → `…::test_r5c_default_timeout_applied`,
  `…::test_r5c_timeout_constants_in_config`
- R5.d No production module constructs `anthropic.Anthropic(` or reads `os.getenv("ANTHROPIC_API_KEY")`
  outside the factory and `resolve_anthropic_key`. → `tests/test_code_health.py::test_r5d_single_client_construction_site`
  *(extend; AST/grep over top-level `*.py`, excluding peripheral scripts listed in the test)*
- R5.e The conftest offline guard patches the factory, so no unit test can make a live call even with the env
  key exported. → `…::test_r5e_conftest_blocks_factory`
- R5.f The two silent `client=None` paths (`validation_pipeline.py:756, 846`) log a warning when no client is
  available (they will rarely be hit after R5.a). → `…::test_r5f_no_client_logs_warning`
- Sites to convert (~15): formatting_pipeline.py:107-111; extraction_pipeline.py:81, 1023, 1157, 1413;
  abstract_pipeline.py:259-264; validation_pipeline.py:84-87, 755, 845; ts_gui.py:1390, 1508, 1606, 2607;
  transcript_initial_validation*.py; release_gate.py:501, 597; transcript_validate_headers.py; plus any found
  by the R5.d test.
- Adjacent issue found, not fixed: B-11 (deterministic `max_tokens` truncation is retried 3×) sits in the same
  function. One-line fix (re-raise on `max_tokens` instead of `continue`). **Include?** — default: yes, with
  `…::test_b11_max_tokens_not_retried`, since I'm editing that function anyway.

### Phase 3 — what the gate judges (F2, F3, Q5, F4)

Prerequisite: D2 (real fixtures). Order inside the phase matters: R6 → R7 → R8 → R9 → R10.

**R6 (F2) — headings, bold-only lines, dash-separated bold labels and `---` regions are judged.**
- R6.a `extract_claims` returns a claim containing the name for each shape: `## Luciano Malorni's 1975
  Study`, a bold-only line `**Luciano Malorni pioneered…**`, `- **Luciano Malorni** — pioneered…`,
  `**Luciano Malorni.** …`. → `tests/test_faithfulness_scaffolding_r6.py::test_r6a_<shape>` (4 tests)
- R6.b `entity_grounding` (`find_ungrounded_names`) flags the same fabricated name in each shape, so both
  blockers agree. → `…::test_r6b_entity_grounding_<shape>`
- R6.c A `---` block is stripped only when every line is `key: value` / list YAML; prose between two `---`
  rules is judged. → `…::test_r6c_hr_delimited_prose_is_judged`, `…::test_r6c_real_front_matter_still_stripped`
- R6.d Generic scaffolding headings (`## Key Takeaways`, `## TL;DR`, Bowen concept labels from
  `config.BOWEN_CONCEPT_LABELS`) do **not** become claims. → `…::test_r6d_scaffolding_headings_not_claims`
- R6.e No new false BLOCK on the trusted real artifacts (D2 fixtures + existing `roots_bowen_test`):
  `find_ungrounded_names(...) == []` and `extract_claims` count recorded. →
  `tests/test_golden_transcript_regression.py::test_r6e_real_prose_artifacts_no_new_ungrounded` *(extend)*
- R6.f The docstring at `abstract_validation.py:55-59` matches the new behaviour. → covered by review; flag as
  human-check (docstring, not code).
- Implementation: re-emit Title-Case multi-word spans from removed headings / bold-only lines / labels with any
  separator (extend `_name_shaped_bold_labels` at `faithfulness_judge.py:214`); tighten the `---` strip in
  `abstract_validation.py:792-795`. Apply in `_strip_scaffolding` only if R6.e stays green — otherwise in
  `extract_claims` only (judge side), and record why.

**R7 (F3) — the theme judge sees the whole theme block.**
- R7.a The text sent to `judge_themes` for a theme includes its `**Key evidence:**` content (and other fields)
  except meta labels (Coverage/role, Lens fuel — list in config). →
  `tests/test_theme_judge_input_r7.py::test_r7a_key_evidence_included`
- R7.b Meta labels are excluded. → `…::test_r7b_meta_labels_excluded`
- R7.c Theme gold set gains ≥2 cases with a fabricated name only in Key evidence (labelled ungrounded). →
  `tests/fixtures/theme_gold/gold.json` + `tests/test_theme_parsing_contract.py::test_r7c_gold_has_key_evidence_cases` *(extend)*
- R7.d The `kcfc` / `monika_h3_themes` / `societal_emotional` / `dave_g_test2` / `roots_bowen_test` theme
  fixtures parse to the same theme count as before. → `…::test_r7d_theme_counts_unchanged`
- Implementation: add a `full_block` (or `judged_text`) field to the theme codec output
  (`transcript_utils.py:1320-1332`, `artifact_contracts.py:194-208`); `faithfulness_judge.py:660-662` uses it.

**R8 (Q5 / A-08) — non-empty prose with zero claims is ERROR.**
- R8.a An artifact whose body (after removing YAML front matter) has ≥1 non-blank line but yields no claims →
  `FaithfulnessResult(ERROR, "0 claims extracted from N-word artifact")`. →
  `tests/test_faithfulness_judge.py::test_r8a_nonempty_zero_claims_is_error` *(extend)*
- R8.b An empty or front-matter-only artifact stays PASS. → `…::test_r8b_empty_artifact_pass`
- R8.c ERROR verdicts are not written to the disk cache (existing rule) — pin it for this path. →
  `…::test_r8c_zero_claims_error_not_cached`
- R8.d On the release gate, R8.a produces BLOCK with that message. → `tests/test_release_gate.py::test_r8d_zero_claims_blocks` *(extend)*

**R9 (F4) — the judge cache key covers extraction code; version bumped.**
- R9.a Editing (monkeypatching the source of) each of `extract_claims`, `_is_claim`, `_name_shaped_bold_labels`,
  `abstract_validation._strip_scaffolding`, the theme codec parser, or `config.BOWEN_CONCEPT_LABELS` changes
  the faithfulness/theme cache key. → `tests/test_judge_disk_cache_h2.py::test_r9a_<component>_changes_key` *(extend)*
- R9.b `config.JUDGE_LOGIC_VERSION` is bumped to `2026-10-04` so caches from before R6–R8 are invalid. →
  `…::test_r9b_logic_version_bumped` (asserts the value is not the previous `2026-08-22`)

**R10 — re-calibration (D3).**
- R10.a Faithfulness gold set: recall ≥ 0.9, precision ≥ 0.7 (current bars). →
  `tests/test_faithfulness_calibration.py` (live, `RUN_FAITHFULNESS_CALIBRATION=1`)
- R10.b Theme gold set incl. R7.c cases: same bars. → `…::test_theme_judge_meets_gold_thresholds` (live)
- R10.c Real-artifact path: roots_bowen PASS; where_roots and dave_g FAIL naming the known fabrications. →
  existing live real-artifact test.
- **Not offline-testable** — live LLM. Proposal: I run it once with your approval (D3) and paste the numbers
  into CHANGELOG; update the project memory note.

### Phase 4 — Gen Abstract fails when unfaithful (Q6)

**R11 (Q6) — `generate_structured_abstract` returns False after all attempts fail faithfulness.**
- R11.a All attempts `status == "fail"` → returns False; best draft is still written; error log unchanged. →
  `tests/test_abstract_faithful_retry.py::test_r11a_all_attempts_fail_returns_false` *(extend)*
- R11.b `status == "unavailable"` (judge off / no key) still returns True (gate verifies at publish). →
  `…::test_r11b_unavailable_still_true`
- R11.c Any existing test that asserts True on all-fail is updated, and the change is noted in CHANGELOG. →
  same file.
- Effect: in Run Selected, the run halts at Gen Abstract (later stages skipped). That follows from Q6.
- Implementation: `extraction_pipeline.py:1199-1206` `return True` → `return False`.

### Phase 5 — validators gate (Q3), written for D1 option (b)

Prerequisites — fix the validators' known wrong verdicts first, or gating turns them into wrong blocks:

**R12 (G6) — "Speaker identified" item is created from real metadata.**
- R12.a Coverage items built from `parse_filename_metadata("Title - Presenter - 2025-01-01")` include a
  required speaker item. → `tests/test_coverage_speaker_r12.py::test_r12a_abstract_speaker_item_from_presenter`,
  `…::test_r12a_summary_speaker_item_from_presenter`
- Implementation: `metadata.get("speaker") or metadata.get("presenter")` at `abstract_validation.py:273`,
  `summary_validation.py:170`.

**R13 (F13) — summary LLM rescue works.**
- R13.a A "YES\nNO" reply is accepted (`min_length=2`). →
  `tests/test_summary_validation_r13.py::test_r13a_short_yes_no_reply_accepted`
- R13.b An API exception marks items unverified instead of raising. → `…::test_r13b_api_error_marks_unverified`
- Implementation: extract one shared `verify_with_llm` (abstract version, with its guards) used by both
  modules. Only this function — the wider STRUCT-04 merge stays out of scope.

**R14 (C-07 / P1) — "could not verify" is distinct from "not covered".**
- R14.a On an LLM failure, items get `confidence="llm_unavailable"` and the report says
  "LLM verification unavailable — retry". → `…::test_r14a_llm_failure_reported_distinctly`
- R14.b The gating verdict for that case is ERROR (retryable), not FAIL. → `…::test_r14b_unavailable_is_error`

Note: G8/G9 (key-term substring match, whole-transcript topic grading) make validators *more lenient*, so
gating them causes no false blocks; they stay out of scope.

**R15 — the four validators gate publication.**
- R15.a Each of `validate_emphasis_items`, `validate_topics_lightweight`, `validate_key_terms_fidelity`,
  `validate_summary_coverage` writes a verdict record `{status: PASS|FAIL|ERROR, artifact_sha256, reason}`
  (emphasis currently writes no report — it gets one). →
  `tests/test_validator_verdicts_r15.py::test_r15a_<validator>_writes_verdict` (4 tests)
- R15.b The GUI Structured Summary stage runs `validate_summary_coverage` after generation (today it never
  runs in the GUI — `ts_gui.py:2268-2272` calls only `generate_structured_summary`; it runs only inside
  `summarize_transcript(generate_structured=True)`, which the GUI never sets). →
  `tests/test_ts_gui_run_all.py::test_r15b_structured_summary_stage_validates` *(extend)*
- R15.c New release-gate check `validator_verdicts` in `DEFAULT_CHECKS` and `GATE_BLOCKING_CHECKS`: FAIL or
  ERROR on any verdict → BLOCK naming the validator; a verdict whose `artifact_sha256` doesn't match the
  current artifact → ERROR "stale validation — re-run" (P6); a missing verdict for an artifact that exists →
  ERROR. → `tests/test_release_gate.py::test_r15c_fail_blocks`, `…::test_r15c_stale_verdict_errors`,
  `…::test_r15c_missing_verdict_errors`, `…::test_r15c_all_pass_allows`
- R15.d `config.GATE_BLOCKING_CHECKS` pin: a source-level test asserts the set contains
  `validator_verdicts`, `faithfulness`, `theme_grounding` and that the judge flags ship True (also closes G14).
  → `tests/test_code_health.py::test_r15d_blocking_checks_and_judges_armed` *(extend)*
- R15.e **Real-data dry run before arming**: run all four validators on `dave_g_test2`, `roots_bowen_test` and
  the D2 fixtures. Project memory records that dave_g's key-terms FAILs are validator strictness, not
  hallucinations — so key-terms gating will block that trusted sample unless something changes. →
  `tests/test_golden_transcript_regression.py::test_r15e_validators_on_trusted_fixtures` *(extend; asserts the
  observed verdicts)*. **Decision point:** if any trusted sample FAILs, I stop and report which validator and
  why, and you choose: fix the validator, or leave that one advisory. I will not loosen a threshold to make a
  fixture pass without your call.

### Phase 6 — docs and review

- R16 CHANGELOG entry per phase; TODO.md updated (review section with fixed/deferred); README key-setup
  section updated for keys.json (part of G19 — the install-line fix is one line, included);
  ARCHITECTURE_DESIGN.md §4.3 lists `consistency` and `validator_verdicts` as blocking (part of STRUCT-10).
  → human review of the diff; `tests/test_code_health.py` already checks README model IDs.
- R17 `learning-qa` over the full diff before push (house process); findings fixed in the same session.
- R18 Status report against R1–R17 with done/partial/not done and file paths; `docs/spec_coverage.md` updated.

---

## Order and dependencies

```
Phase 1: R1, R2, R3, R4          independent — one commit each
Phase 2: R5 (+B-11)              before R14 (validators need a working client)
Phase 3: R6 → R7 → R8 → R9 → R10 needs D2 before R6; D3 before R10
Phase 4: R11                     independent; can go any time
Phase 5: R12, R13, R14 → R15     needs D1; R15.e is a stop-and-ask point
Phase 6: R16, R17, R18
```

Phases 1, 2 and 4 can start as soon as this plan is approved. Phase 3 waits on D2/D3, Phase 5 on D1.
Each phase is committed separately on `validation-hardening` with the full suite green; nothing is pushed
until R17 passes.

## Criteria that are not code-testable

- R6.f (docstring accuracy) — human read of the diff.
- R10.a–c (live calibration) — live LLM run, numbers recorded in CHANGELOG.
- R15.e outcome on trusted fixtures — the test pins the observed verdicts, but whether a FAIL there is a real
  defect or validator strictness is your judgement.
- R16 (docs) — human review.

## Risks

- R6 adds claims to every prose artifact → more judge tokens per publish and a chance of new false BLOCKs on
  real content; R6.e and R10 are the guards.
- R11 and R15 both make runs stop or block more often by design. Expect the first runs after merge to surface
  existing artifacts that now block; the manifest/marker will name the reason.
- The working tree has uncommitted edits to `quality_gates.py` / tests (`FIX_MUTATION_GATE_PROMPT.md` task).
  I will leave them untouched and stage only my own files per commit.
