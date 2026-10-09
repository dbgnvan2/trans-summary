# Review: trans-summary (full repo) — 2026-10-04

Method: `/reviewer` REPO mode. 8 independent read-only workers (4 areas × G-CORRECT, 2 merged
G-SEC slices, G-STRUCT and G-TEST across the whole repo), then 2 challenge workers that
re-verified every blocker/major against the code (one more challenge worker than the skill
default, because there were ~35 blocker/major candidates after dedup). Two minor findings were
spot-checked by running them. Branch `validation-hardening` at `3a298ac`, including the
uncommitted edits to `quality_gates.py` and its tests. Previous full review:
`docs/CODE_REVIEW_2026-07-18.md`.

## Verdict

The July fixes held: the XSS escaping is complete on every HTML/PDF path, the config loader
survives dirty state, and the release gate's core block logic is sound. The main problem now
is in two places around the gate:
- **What the gate does not get to see.** Claim extraction strips headings, bold-only lines,
  dash-separated bold labels and `---`-delimited regions before either hard blocker runs, and
  the theme judge sees only the Description field. A fabricated name in those places publishes
  unchecked, even though the code's own docstrings say the judge is the backstop for them.
- **What happens when the gate says BLOCK from the GUI.** The webpdf stage returns early and
  skips the quarantine, marker and manifest step, so the previous run's webpage and PDF stay on
  disk looking current.

Across the codebase, validators compute a verdict that nothing reads: four validator results in
`extraction_pipeline` and the webpage check in the GUI are discarded. That is why several
wrong-verdict bugs in those validators have gone unnoticed. Fix first: G1 (the GUI BLOCK path),
then F2/F3 (feed the stripped regions to the judges), then G11 (cleanup deleting other
transcripts' files).

## Coverage

| Area | G-CORRECT | G-SEC | G-STRUCT | G-TEST |
|---|---|---|---|---|
| A — publish gate & judges (release_gate, faithfulness_judge, key_terms_semantic_judge, judge_drift_monitor, artifact_contracts, bowen_attribution, quality_gates, mut_harness, schemas) | covered | covered | covered | partial |
| B — extraction & LLM core (extraction_pipeline, transcript_utils, config, model_specs, summary/abstract/formatting pipelines, pipeline, emphasis_detector, cost estimator) | covered | partial | covered (config.py 1025–1503 skipped, deferred M7) | partial |
| C — validators (validation_pipeline, abstract/summary_validation, initial_validation v1/v2, validation_learning, transcript_validate_* ×11) | covered | partial | partial | partial |
| D — output, GUI, CLI (ts_gui, html_generator, bundle_export, packaging/cleanup, transcript_to_*, transcript_* CLI wrappers, templates) | covered | partial | partial (ts_gui ~600/2712 lines) | partial |
| Peripheral scripts (debug_*, GoogleDocSummary, ListModels, legacy_*, run_tests, root test_*.py) | not reviewed | not reviewed | covered (dead-code lens only) | partial |

What the partial cells mean:
- **G-SEC partial** means the worker grep-swept the file for eval/exec, yaml.load, subprocess,
  rmtree/unlink, `|safe`, path joins and key handling, but did not read it line by line.
  - B: extraction_pipeline, summary/abstract/formatting pipelines.
  - C: 9 of the 11 transcript_validate_* files.
  - D: most of ts_gui.
- **G-TEST partial** means about 60 of the 86 `tests/*.py` files were grepped only. Those
  include test_ts_gui_*, test_extraction_*, test_abstract_*, test_summary_*,
  test_initial_validation_* and test_artifact_contracts*. `pytest --co` was not run.

Read: about 29.4k LOC of non-test Python and about 13.9k LOC of tests, at the depth shown
above. Nothing was executed except two small regex/Jinja checks (B-05, D-09).

Not reviewed: `skills/` (output-critic helper), `scripts/gen_bundle_reference_docx.py`, prompt
contents (only spot-checked for placeholder and threshold drift), `.claude/worktrees/*` copies.

Excluded: `uv.lock`, `source/` transcripts, `tests/fixtures/` data, `templates/styles/*.docx`,
historical `*_FIXES*.md` / `CODE_REVIEW*.md` docs.

Live paths that are mocked everywhere and therefore untested offline: the faithfulness/theme
judge API calls, pandoc rendering, WeasyPrint rendering.

## Findings

Each finding has a tag, location, description, fix, confidence and verification status. A
second worker re-checked each blocker and major ("Verified"). "Corroborated" means two or more
lenses found it independently.

### Blockers

**G1 · CORRECT · `ts_gui.py:1898-1911`. A GUI publish BLOCK leaves the stale bundle in place.**
The webpdf stage calls `release_gate.run_gate` and returns on BLOCK before
`generate_webpage`/`generate_pdf`.
- **Side effects skipped:** `run_gate` has none. The stale-bundle quarantine, the
  PUBLISH-BLOCKED marker and the manifest only happen in `publish_allowed`
  (release_gate.py:878-886).
- **Why later steps don't fix it:** Run Selected stops at the first failure
  (ts_gui.py:2214-2217), so package/bundle never run to clean up.
- **Effect:** after an earlier ALLOW, a BLOCKED re-run leaves the old webpage/PDF on disk as
  current output, with no marker and no BLOCK record. This breaks the documented
  F4/M1.B.2 contract.
- **Test gap:** `tests/test_ts_gui_web_generation.py:34-57` asserts the early return but not the
  quarantine.
- **Fix:** on BLOCK, call `release_gate.publish_allowed(base_name, logger)` (or a helper that
  returns the decision and performs marker + quarantine + manifest). Extend the test to assert
  that a pre-existing webpage is renamed `*.blocked-stale`.
- Confidence high · **Verified**.

### Major

**F2 · CORRECT/SEC · `abstract_validation.py:791-819` → `faithfulness_judge.py:132-133, 214`. Fabrications in headings, bold lines and `---` regions bypass both hard blockers.**
`_strip_scaffolding`, which both `entity_grounding` and `extract_claims` use, drops all of the
following:
- every `#` heading
- every bold-only line
- the label of `**X** — …` / `**X.**`
- the leading fenced block
- everything between a leading `---` and the next `\n---`, with no check that the block is YAML

`_name_shaped_bold_labels` re-adds only the colon-form labels.

The docstring at abstract_validation.py:55-59 says the faithfulness judge is "the semantic
backstop for those shapes". It is not, because it uses the same strip. So
`## Luciano Malorni's 1975 Study`, `- **Luciano Malorni** — pioneered…`, or a paragraph between
two `---` rules ships unchecked.

The overview's FAQ answers are also repeated as prose, which is judged, so for the overview
only the question headings are lost.

Fix:
- In `extract_claims`, re-add the Title-Case spans from removed headings, bold-only lines and
  labels with any separator as claims.
- Strip a `---` block only if every line in it is `key: value`.
- Add one adversarial test per shape.

Confidence high · **Verified** · Corroborated (A-01 correctness, AC-02 security).

**F3 · DATA · `transcript_utils.py:1324-1328`, `faithfulness_judge.py:660-662`. The theme judge never sees "Key evidence".**
- **What the judge gets:** the Description regex stops at the next `**Label:**`, so the theme
  judge receives only the name and the description.
- **What is published unjudged:** "Key evidence" holds names, quotes, figures and Q&A
  attributions. It is in `FAITHFULNESS_SKIP_LINE_LABELS` (config.py:649), themes are not in the
  entity or faithfulness suffix lists, and html_generator.py:74-99 publishes the full block.
- **Calibration blind spot:** the theme gold set goes through the same codec, so calibration
  cannot detect this.
- **Fix:** send the full theme block (minus meta labels such as Coverage/Lens fuel) to the theme
  judge. Add a gold case with a fabricated name only in Key evidence, then re-calibrate (P20).
- Confidence high · **Verified**. It is minor if Key evidence in practice only cites sections.

**F1 · CORRECT · `formatting_pipeline.py:427-438, 643`. A formatter that stops early can pass format validation.**
- **The defect:** when the formatted text runs out, `_compare_transcripts` adds one mismatch and
  breaks, so the ratio is computed only over the words actually checked.
- **What already narrows it:** `max_tokens` already raises (transcript_utils.py:225-229), and
  `min_words` = 50% of raw is enforced. The worker originally rated this a blocker; the
  challenge pass downgraded it for this reason.
- **The remaining gap:** an `end_turn` response that keeps 50–99% of the lecture passes, and
  every later artifact is built from the shortened transcript.
- The skip_b path (468-494) also doesn't count inserted words.
- **Fix:** fail when `stopped_reason == "B_exhausted"` and more than a small tolerance of A
  remains unchecked (or count the remainder as mismatches). Add a test with a 60%-length
  formatted text.
- Confidence high · **Verified (partial)**.

**G11 · DATA · `cleanup_pipeline.py:69-74, 90-98`. Cleanup deletes other transcripts' working files.**
- **The defect:** `f.name.startswith(base_name)` plus `_v\d+\.txt$` matches files that belong to
  other transcripts.
- **Effect:** cleaning `T - P - 2025-01-01` unlinks `T - P - 2025-01-01 Part 2_v3.txt`, which
  cannot be undone. The confirmation dialog names only the current base.
- **Test gap:** `test_cleanup_pipeline.py` (root level) uses only an unrelated name with no
  shared prefix.
- **Already done correctly elsewhere:** the GUI's `_find_existing_validation_versions`
  (ts_gui.py:392) uses an anchored regex.
- **Fix:** `re.fullmatch(re.escape(base_name) + r"_v\d+\.txt", f.name)`, plus an adversarial
  sibling test.
- Confidence high · **Verified** · Corroborated (BD-03 security, D-06 correctness, gtest-08
  tests).

**G3 · SEC/CORRECT · `ts_gui.py:2652-2662`, `transcript_initial_validation_v2.py:341-389`, `validation_learning.py:153-160`. Auto Init Val applies every LLM finding regardless of confidence.**
- **The defect:** the GUI auto path applies all findings. Only `run_iterative` filters by
  `VALIDATION_AUTO_APPLY_CONFIDENCE`. `validate_correction` (error-type allowlist, context-length
  bounds) has no production caller; only tests call it (C-12).
- **Why it matters:** a low-confidence wrong correction is written into the `_validated` source,
  which every later grounding check treats as ground truth.
- **Narrower parts:**
  - The `alias` global-rewrite path is only reachable from off-schema LLM output (no prompt asks
    for `alias`). It still bypasses the proper_noun approved-terms gate.
  - `pattern.subn(correct, …)` treats the LLM text as a regex template. A backslash raises, and
    the GUI's broad `except` catches it.
- **Fix:** filter by confidence and call `validate_correction` inside `apply_corrections_safe`,
  so no caller can skip them. Drop `alias` from the LLM-allowed types, or gate it like
  proper_noun. Use `lambda m: correct`.
- Confidence high · **Verified (partial: the alias part is minor)** · Corroborated (AC-03, C-12,
  C-13).

**G6 · CORRECT · `abstract_validation.py:273`, `summary_validation.py:170`. The required "Speaker identified" item is never created.**
- **The defect:** both modules read `metadata.get("speaker")`. Production metadata comes from
  `parse_filename_metadata`, which provides `presenter`/`author` and never `speaker`
  (transcript_utils.py:1079-1087).
- **Effect:** an abstract or summary that never names the speaker passes coverage.
- **Why tests miss it:** every test passes `{"speaker": …}` directly.
- **Fix:** read `speaker or presenter`, and add a test that builds metadata through
  `parse_filename_metadata`.
- Confidence high · **Verified**.

**G7 · CORRECT · `abstract_validation.py:408, 421-426`, `summary_validation.py:312, 325-330`. One substring keyword hit counts a required topic as covered.**
- **The defect:** `kw in text_lower` with no word boundary, and one hit gives "medium".
  "medium" items are never sent to the LLM rescue pass, which only takes "low".
- **Effect:** "family" or "process" covers a required major topic.
- **Note:** `tests/test_validator_logic_hardening.py:131-137` pins one-of-many → covered on
  purpose, so a fix means changing that test and its intent (see Questions).
- **Fix:** match on word boundaries, require ≥2 hits or ≥0.5 ratio for "covered", and send
  required single-hit items to the LLM pass.
- Confidence high · **Verified** (deliberate behaviour, but the result is wrong).

**F8 · CORRECT · `extraction_pipeline.py:1628-1645`. The default GUI blog path skips the A8 lens-grounding guard.**
- **The defect:** when `skip_extracts_summary=True`, which is always the case from the GUI
  (ts_gui.py:2313-2323), `top_lens` comes straight from `_validate_themes_and_lenses`. The checks
  `_top_lens_is_grounded` and structural/interpretive validity, enforced on the other path
  (1473-1511), are skipped.
- **Backstop:** the blog body is still judged at publish. An ungrounded lens frame is not.
- **Fix:** apply the same three checks in the else-branch, and leave `top_lens = {}` when they
  fail.
- Confidence high · **Verified** · Corroborated (B-03, STRUCT note).

**F12 · PERF/ERROR · `transcript_utils.py:612-786` + every `anthropic.Anthropic()` construction. Nested retries and missing timeouts.**
- **The defect:** no client sets `max_retries` or `timeout`. The SDK's 2 retries (600 s default)
  nest inside the wrapper's 3 attempts, which also raise the timeout to 1.5× or a 900 s literal.
- **Call sites with no timeout:** about 9, including summary_validation.py:562,
  abstract_validation.py:563, abstract_pipeline.py:266, transcript_validate_headers.py:184,
  validation_pipeline.py:96 and transcript_extract_terms.py:89.
- **Worst case:** about 2.4 h of GUI worker blocking for one logical call, or about 4.75 h on
  the formatting path, given repeated stalls.
- **Fix:** one client factory with `max_retries=0`, and a `timeout=config.TIMEOUT_DEFAULT`
  default in the wrapper. Move the 900.0 and 1.5 values into config.
- Confidence high · **Verified** · Corroborated (STRUCT-03).

**F14 · ARCH/ERROR · ~15 sites, e.g. `formatting_pipeline.py:107`, `extraction_pipeline.py:81/1023/1157/1413`, `abstract_pipeline.py:259`, `validation_pipeline.py:84/755/845`, `ts_gui.py:1390/1508/1606/2607`. The API key is resolved two ways.**
- **The split:** the gate, judges and drift check use `resolve_anthropic_key` (env, then
  `~/.config/llm/keys.json`). Generation and validation use `os.getenv` only.
- **Effect with the key only in keys.json:** the gate works, every generation stage fails
  (loudly), and `validation_pipeline.py:756/846` silently drops to keyword-only coverage
  (`client=None`).
- **Test gap:** the conftest offline guard patches only `resolve_anthropic_key`.
- **Fix:** add `transcript_utils.get_anthropic_client()`, used everywhere, and point conftest at
  it. This also fixes F12.
- Confidence high · **Verified (partial: "silently" holds only for the two validation sites)** ·
  Corroborated (B-10, STRUCT-02, D notes).

### Minor

Verified by a challenge worker (several downgraded from major):

| ID | Tag · Where | What | Fix |
|---|---|---|---|
| F4 | ARCH · release_gate.py:395-432, 567 | Judge disk-cache key hashes routing code but not `extract_claims`/`_is_claim`/`_name_shaped_bold_labels`/`_strip_scaffolding`/`BOWEN_CONCEPT_LABELS`/theme parser. Stale PASS only after a future unbumped edit; not stale today. **Fixing F2/F3 triggers this**: bump `JUDGE_LOGIC_VERSION` when you do. | Hash those sources too. Corroborated (A-05, STRUCT-01). |
| F5 | TEST · mut_harness.py:149-160, 27-38 | No baseline-green check: a red or >120 s suite scores every mutant "killed". DESELECT (10) has drifted from KNOWN_REDS (3). (Refuted part: a missing `python` *crashes*, not scores 1.0; DESELECT drift fails safe.) | Run the suite once unmutated and abort if not green; `sys.executable`; timeout bucket. Corroborated (A-03, AC-08, gtest-01/02, STRUCT-15). |
| F6 | CORRECT · judge_drift_monitor.py:84, 90 | `--model` override not passed to `judge_themes`; report names the wrong model. | Pass `model=model`. |
| F7 | ERROR · extraction_pipeline.py:1422-1436 | Core ignores emphasis/Bowen return values; the exception path leaves a stale artifact that no required-artifact check flags. | Propagate the failure. |
| F9 | DATA · extraction_pipeline.py:678-686 | All items fail `validate_emphasis_item` → raw response saved, returns True. Schema catches bad types only; length/score/pronoun rejects ship. | Write nothing and return False when 0 of N pass. |
| F10 | DATA · summary_pipeline.py:172-202 | Summary proceeds with 0 topics when all topics are under 5%; the codec doesn't catch it. | Fail when parsed topics are empty. |
| F11 | ARCH · config.py:271-297, 331-335 | GUI model change updates `settings` only; `config.DEFAULT_MODEL` etc. stay at import value → run manifest provenance and cost estimate are wrong (outputs use the right model). Manifest also omits judge models. | Remove module-level mirrors; add judge models to provenance. Corroborated (B-09, STRUCT-06, D-11). |
| F13 | CORRECT · summary_validation.py:562-569 | Summary `verify_with_llm` lacks the abstract copy's `min_length=2`/try-except, so a "YES\nNO" reply (<50 chars) always fails after 3 paid calls and no report is written. | Share one implementation (see systemic #4). |
| G2 | ERROR · ts_gui.py:1923-1931 | webpdf ignores `validate_webpage`'s bool; status goes green and Run Selected continues. | `success = success and ok`. |
| G4 | SEC · transcript_initial_validation.py:116-125 | v1 unfenced-JSON path returns before `filter_validation_findings` (non-default v1 only). | Fall through to the filter. Corroborated (AC-04, C-01). |
| G5 | ERROR · transcript_initial_validation.py:132-150 | v1: no `[` / truncated array → `[]` → file copied as `_validated` (non-default v1 only). | Raise, as v2 does. |
| G8 | CORRECT · validation_pipeline.py:286-306 | Key-term grounding matches inside words ("fusion" in "confusion"); `None` local grounding treated as OK. Advisory report only. | Token-boundary match; None → at most PARTIAL. |
| G9 | CORRECT · validation_pipeline.py:467-535 | Topic grade uses whole-transcript overlap; `section_ratio` ignored (documented choice). Advisory only. | Use section_ratio as a cap; move thresholds to config. |
| G10 | SEC · bundle_export.py:151-163 | pandoc `-f markdown` keeps raw_attribute on and has no `--sandbox`: ```` ```{=openxml} ````, live links and image fetches pass into the shared DOCX. Needs hostile text in your own transcript or LLM output. | Add `--sandbox`; disable raw_attribute and use a Lua filter for page breaks. |
| G12 | CORRECT · transcript_process.py:120-132 | CLI base name doesn't strip `_validated`, so it targets the wrong project dir (fails loudly after a wasted format call). | `clean_project_name`. Corroborated (D-03, STRUCT-11). |
| G13 | ERROR · transcript_process.py:321-377 | CLI prints "PROCESSING COMPLETE" and exits 0 after a failed or blocked publish. | Non-zero exit on step failure. |
| G14 | TEST · conftest.py:56-57 (root) | Nothing pins that `FAITHFULNESS_JUDGE_ENABLED`/`THEME_JUDGE_ENABLED` ship True; flipping either disarms a hard blocker with a green suite. | AST read of config.py asserting True; same for `GATE_BLOCKING_CHECKS`. |
| G15 | TEST · release_gate.py:654-688 | `check_consistency` runs via `run_gate` in tests, but its ERROR branches (missing/empty transcript) are unpinned. | 3 direct adapter tests. |
| G16 | TEST · html_generator.py:217-714 | `escape()` calls outside `markdown_to_html` have only benign-input tests. | Feed `<script>`/`"><img onerror>` through each. |
| G17 | TEST · tests/fixtures | No real summary/overview/blog artifacts; stripping is tested on modelled inline text. | Add real fixtures to the golden regression. |
| G18 | TEST · config.py:87-101 | Directory-override + `exists()` guard has only an xfail test. | Dirty-state test with live and dead paths. |
| G19 | MAINT · README.md:45-59 | Install line omits jinja2/jsonschema; README says `.env` but no production code calls `load_dotenv`; keys.json not documented. | `pip install -r requirements.txt`; document key sources. |
| G20 | ARCH · abstract_pipeline.py:97-151 et al. | Topics parsed 3+ ways, key terms 4+; abstract fallback invents coverage % (`max(5,100-idx*10)`). Gate's `artifact_contracts` blocks drift at publish. | Route consumers through `artifact_contracts.codec()`. Corroborated (STRUCT-05, B-07). |
| G21 | SEC · faithfulness_judge.py:447-457, 659-664 | Judge prompts put untrusted transcript + artifact in the user turn with `===` delimiters, no system prompt, no data-only rule. Minor while transcripts are your own. | `system=` instructions, tag-wrap, data-only rule, injection gold case. |

Spot-checked by running them (confirmed):

| ID | Where | What | Fix |
|---|---|---|---|
| B-05 | extraction_pipeline.py:242 | Placeholder detection regex `{{\s*key\\s*}}` requires a literal backslash and never matches, so every replacement (themes, topics, key terms, lenses) is appended a second time under "## Provided Context". Ran it: `search('{{structural_themes}}') → False`. Doubles those tokens. | `r"\{\{\s*" + re.escape(key) + r"\s*\}\}"` + test. |
| D-09 | html_generator.py:38-43, templates/*.html:4-6 | Autoescape HTML-escapes CSS inside `<style>`: `'Georgia'` renders as `&#39;Georgia&#39;` (ran it), so the font-family declaration is dropped in webpage, simple page and PDF. | `{{ common_css\|safe }}` etc. + test. |

Single-worker findings, not challenge-verified. These are lower confidence, but each has a
specific location that can be checked:

| ID | Where | What |
|---|---|---|
| A-06 | release_gate.py:841-887 | Each publish entry point re-gates; a transient ERROR in one step and ALLOW in the next leaves a partial bundle with the marker cleared. |
| A-07 | release_gate.py:593 | Theme judge gets the bare transcript, faithfulness gets transcript + filename metadata, so a theme naming the presenter can false-BLOCK. |
| A-08 | faithfulness_judge.py:547-549 | Non-empty prose that yields 0 claims → PASS (and cached); the theme judge treats the same case as ERROR. |
| B-08 | extraction_pipeline.py:647-652, 807-813 | Timestamp derived from a normalised-space offset on the fuzzy path, so it can come from an earlier section. |
| B-11 | transcript_utils.py:225-229, 663-673 | `max_tokens` raises RuntimeError inside the retry `try`, so a deterministic truncation is retried 3× (confirmed by reading); failed attempts are not logged to token_usage.csv. |
| B-12 | config.py:87-97 vs 157-160 | Saved directory overrides applied inconsistently; a missing saved dir is skipped silently. |
| BD-02 | bundle_export.py:189-216 | `export_bundle` is the only publish entry without `base_name_is_safe`. |
| C-07 | abstract_validation.py:572-578 | An LLM failure marks items `llm_verified=False`, which looks identical to a real coverage miss. |
| C-09 | validation_pipeline.py:799-802, 866-868 | On exception the old validation report stays on disk; the GUI points the user to it. |
| C-10 | transcript_validate_bowen.py:50, _emphasis.py:96, _html_highlights.py:76 | CLIs unpack 2-tuples from loaders that return 3-tuples; they crash on any non-empty artifact. |
| C-11 | transcript_validate_webpage.py:223-233, _completeness.py:171 | Key-terms counted only under `## Key Terms` / `- **Term**`; real `### Term` files read as 0, so the check is skipped. |
| D-08 | ts_gui.py:917-967 | Switching source dir doesn't clear the selection; Run Selected runs the previous file against new dirs. |
| D-10 | ts_gui.py:1976-1992 | Log archive zips all of `logs/`, including earlier archives (grows each time) and runtime_settings/judge cache. |
| D-12 | ts_gui.py:2466-2498 | Malformed `stage_selections` in runtime_settings.json crashes GUI startup. |
| D-13 | ts_gui.py:1338-1356 | `progress.stop()` and selection state mutated off the Tk main thread. |
| D-14 | transcript_extract_terms.py:105-112 | `- yaml.md` input writes to a new `"X - yaml"` project dir and reports success. |
| AC-05 | abstract/summary_validation.py ~581-594 | YES/NO parsed by substring and position; a preamble line shifts every verdict. |
| AC-06 / BD-04 | requirements.txt, pyproject.toml | `pdfminer.six`, `tiktoken`, `markdown-it-py` declared but never imported (pdfminer pin possibly below an advisory fix, from memory, not checked). |
| AC-07 | requirements.txt | Jinja2==3.1.4 below 3.1.6; no lock hashes; no `pip-audit` in CI. |
| STRUCT-07 | transcript_validate_consistency.py | Blocking `consistency` check hard-codes suffixes and its own Bowen regex, and falls back to the largest raw `.txt`. |
| STRUCT-08 | artifact_contracts.py:116-177 | The contract layer imports private helpers from the pipelines (cycle hidden by in-function imports). |
| STRUCT-10 | ARCHITECTURE_DESIGN.md | Omits `consistency` from the blocking checks; describes `pipeline.py` as the orchestrator (it is a re-export facade). |
| STRUCT-12/13 | various | Editorial lists (emphasis score table, conclusion patterns, WEAK_DICTIONARY_PAIRS, 6 stopword sets) and pass/fail thresholds still inline; V1 Init Val fuzzy auto-apply 0.90 vs V2 0.95. |
| STRUCT-14 / gtest-11 | main.py, debug_*.py, run_tests.py, test_debug.py, test_regex.py, test_timestamp_regex.py | Dead scripts. `test_debug.py` is collected by pytest and overwrites `sys.argv` for the whole session. `run_tests.py` lists 3 files that no longer exist. Two regex tests assert on inline copies, not production code. |
| STRUCT-16 | validation_pipeline.py:287, 467-591 et al. | The M11 normalise-once fix was applied only to Bowen; the other per-item loops re-normalise the transcript for each item, ×5–7 gate runs per publish. |
| STRUCT-17 | bowen_attribution.py:177-203 | O(L²) newline bridging inside the blocking consistency check on unpunctuated text. |
| gtest-09 | tests/test_bundle_export.py:335 | Page-break assertion also matches the escaped text. |
| gtest-10 | quality_gates.py:24-42 | Vacuity checker counts `assert True`, `pytest.skip()` and bare `approx` as assertions. |
| gtest-12 | tests/test_bowen_references_integration.py:19-38, test_config_validation.py | "Restores" config via a setter that drops runtime overrides; runtime_settings mutated and not restored. |

## Systemic patterns

1. **Verdicts computed and then discarded.** extraction_pipeline.py:1733-1748 ignores
   the return values of `validate_emphasis_items`, `validate_topics_lightweight`,
   `validate_key_terms_fidelity` and `validate_summary_coverage`. The same thing happens in
   ts_gui webpdf (G2), Config Check (D-11), `cleanup_transcript_files` (always True, D-07), the
   CLI exit code (G13) and Core's sub-extractions (F7). Because nothing consumes these results,
   the wrong-verdict bugs in those validators (G7, G8, G9, F13, C-03/G6) cause no visible
   failure and have not been noticed. Decide per validator whether it is advisory or gating:
   wire the gating ones, label the advisory ones as advisory in the GUI and reports, and stop
   paying for checks nobody reads.
2. **The gate does not see everything that is published.** F2, F3 and (if confirmed) A-08: the
   scaffolding stripper and the theme codec were built to remove noise for the deterministic
   entity check, and the semantic judge reuses them, so it inherits the same blind spots.
   Docstrings claim the opposite. Any fix here also needs F4 (cache key) handled, or old PASS
   verdicts stay in force.
3. **No shared Anthropic client factory.** F12, F14 and the conftest offline-guard gap come from
   more than 20 places constructing `anthropic.Anthropic(...)` themselves. One `get_anthropic_client()`
   fixes key resolution, the retry layering, timeouts and the test guard together (P5).
4. **Sibling copies drift apart.**
   - summary_validation vs abstract_validation: F13, different coverage ratios and stopword
     lists.
   - GUI vs CLI orchestration: G12, D-05 (no `_validated` gate on CLI), STRUCT-11 (CLI has no
     abstract or overview stages).
   - The full vs skip-extracts blog path (F8).
   - `run_gate` vs `publish_allowed` (G1).
   - 3–5 topics/key-terms parsers (G20).
   - Two Init Val versions with different fail-open behaviour (G4/G5).

   This is the same P5 pattern the July review found, now in different places.
5. **Guards and fields that exist only in tests.** `validate_correction` (C-12), the `speaker`
   metadata key (G6), `test_regex.py` and `test_timestamp_regex.py` asserting on inline regex
   copies, and judges-armed flags (G14) that tests always override. Each test passes while the
   production path differs. Prefer tests that build their input through the real producer
   (`parse_filename_metadata`, real fixtures).

## Refuted in challenge pass

No finding was refuted outright. These parts of findings were refuted or narrowed:
- **F5:** "a missing `python` binary scores every mutant killed" is wrong. `FileNotFoundError` is
  not caught, so the gate crashes (mut_harness.py:156-160). DESELECT drift removes possible
  killers, which lowers the score, so it fails safe rather than open.
- **G15:** "check_consistency is never called by any test" is wrong. It runs through `run_gate`
  in tests/test_release_gate.py:85-146, 704-720, test_m5_fault_injection.py:57-76 and
  test_golden_transcript_regression.py:166. Only the adapter's own ERROR branches are unpinned.
- **F1:** downgraded from blocker. `max_tokens` already raises (transcript_utils.py:225-229) and
  `min_words` = 50% of raw is enforced (formatting_pipeline.py:147-157), so only early stops
  that keep 50–99% get through.
- **F14:** "silently" holds only for validation_pipeline.py:756/846. Generation sites raise
  loudly, and the opening-purpose sentinel is treated as not-PASS
  (tests/test_validator_pass_on_empty_contract.py:215-221).
- **G3:** the alias global rewrite needs off-schema LLM output (no prompt mentions `alias`, and
  dictionary aliases are suppressed, not injected). The regex-template crash is caught by the
  GUI's except at ts_gui.py:2673.
- **G12:** fails loudly (transcript_add_yaml pre-flight returns 1) and does not write to the
  wrong directory.
- **G20:** the drift is caught by the `artifact_contracts` blocking check at publish
  (config.py:538), so it does not ship silently.
- **G14:** the overriding conftest is the root `conftest.py`, not `tests/conftest.py`.

## Questions only the author can answer

**Answers (author, 2026-10-04):** 1 — all transcripts are the author's own, so G21/G10 stay minor.
2 — keys.json fallback should be app-wide (F14 → one shared client factory). 3 — all four
discarded validators (emphasis, topics, key-terms, summary coverage) should gate. 4 — keep
one-keyword-covered as is (G7 not a defect by design; keep the pinning test). 5 — open (see
reply in session: zero claims from a non-empty prose artifact recommended as ERROR). 6 — Gen
Abstract should FAIL when every attempt fails faithfulness. 7 — skip (no change).

1. **Are transcripts ever from third parties?** If yes, G21 (judge prompt injection) and G10
   (pandoc raw OpenXML) become major. If they are always your own lectures, they stay minor.
2. **Is the keys.json key fallback meant to be app-wide, or gate-only?** If app-wide, F14's
   factory is the fix. If gate-only, the README must say every generation stage needs the env
   var.
3. **Which validators are meant to gate?** emphasis, topics, key-terms and summary-coverage
   results are discarded today. See systemic #1.
4. **Is one keyword hit = covered (G7) intended?** It is pinned by
   `test_summary_keyword_one_of_many_is_medium`, so the current behaviour looks deliberate, but
   it lets a required topic pass on a generic word.
5. **Should a non-empty prose artifact with zero extracted claims be PASS or ERROR on an armed
   hard blocker (A-08)?** The theme judge chose ERROR.
6. **Should `generate_structured_abstract` show green in the GUI when every attempt failed
   faithfulness** (extraction_pipeline.py:1199-1206)? It relies on the gate to block later.
7. **Should a halted Run Selected still print the token-usage report?** Today the spend on
   failed runs is not shown (ts_gui.py:2214-2220).
