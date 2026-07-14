# TODO — open bugs & tech debt

Tracked so we don't lose them. Items surfaced during the **2026-07-13 run-log
review** sessions unless marked *pre-existing* (not introduced by that work).
Fixed items live in CHANGELOG.md; recurring lessons in LEARNINGS.md.

---

## Bugs (unfixed)

### `unknown_script` rows in the cost log on real runs
Some pipeline API calls log token usage with a nameless logger, so
`logs/token_usage.csv` and the token-usage report show `unknown_script` rows in
**real (non-test) runs** (5 such calls in the KCFC run). The *test*-side
pollution is already fixed (autouse `LOGS_DIR` redirect in `conftest.py`); this
is the real-run case. **Fix:** give those pipeline steps a named logger
(`setup_logging("<step>")`). Ref: `transcript_utils.py` ~`getattr(logger,'name','unknown_script')`.

### Emphasis saver doesn't sanitize `"` inside quote/concept text *(pre-existing)*
Unlike `_format_bowen_refs` (which maps `"`→`'`), the emphasis save block writes
quotes raw, so a nested `"` inside a quote would truncate on re-parse (a P19
round-trip hazard). Ref: `extraction_pipeline.py` `extract_scored_emphasis` save block.

### `_load_runtime_settings` AttributeError on valid non-dict JSON *(pre-existing)*
Corrupt JSON resets to `{}`, but a *valid* non-dict top-level (hand-edited `[]`
or a string) would `AttributeError` on the first `.get`. Ref: `config.py` `_load_runtime_settings`.

---

## Pre-existing test failures (9 — red before the run-log work, still red)
Worth a dedicated pass; none related to the validator/estimator/Bowen fixes.

- `test_config_validation.py::test_runtime_settings_persistence` — config singleton doesn't reload across instances (SOURCE_DIR).
- `test_html_generation.py::test_highlighting_logic` — highlight tuple unpack (`expected 3, got 2`).
- `tests/test_html_generator.py::` `test_generate_simple_html_page_structure`, `test_highlight_html_content_basic`, `test_highlight_html_content_exact_word_match` — HTML highlighting.
- `tests/test_header_validation_token_limits.py::` `test_validate_batch_caps_tokens_for_haiku`, `test_cap_max_tokens_defaults_to_32000_when_model_limit_unknown` — token-cap logic.
- `tests/test_bowen_references_integration.py::` `test_bowen_references_generation_and_extraction`, `test_bowen_references_fallback_to_primary_when_filter_invalid` — Bowen integration (may now behave differently after the Bowen fixes — recheck when investigating).

---

## Improvements / tech debt

### Bowen extraction still concept-labels on some transcripts
Enriched prompt + fixed attribution filter + counter now capture genuine
attributions (e.g. "Bowen's basic ideas") and the drop-diagnostic makes 0-results
inspectable — but the *primary extraction* still surfaces concept applications and
can miss real attributions (e.g. "Bowen did at MCV" on the KCFC file). **Next:**
iterate the extraction prompt using `… - bowen-references-debug.md` as evidence.

### Cost estimator still ~20% low
Improved 3.6× → ~1.3× low. Remaining gap: Ranked Lenses output under-modeled
(~2171 est vs ~4850 actual) and the Theme/Lens validation loop can run up to 3×
(modeled as 1 pass). Calibrate against more real runs if tighter estimates matter.
Ref: `transcript_cost_estimator.py`.

### Topics validation `section_mismatch`
Topics cite section ranges that don't line up with actual sections
(`section_mismatch` 6–7 on real runs). Cosmetic; the topics themselves validate.
Ref: `validation_pipeline.py` `validate_topics_lightweight`.

### `_validated` filename gate broader than needed
`do_run_selected` blocks any selection whose source lacks `_validated`, including
late-only stages (package/webpdf/bowen_emphasis) that don't read the raw source.
Matches prior `do_all` behaviour (spec SS.10) — not a regression. Revisit if it
causes spurious "run Init Val first" blocks. Ref: `ts_gui.py` `do_run_selected`.

### Redundant Emphasis+Bowen double-run
Selecting **Core** (with Include Emphasis/Bowen) *and* the standalone
**Bowen + Emphasis** stage runs both twice (wasted cost + overwrite). A workflow
choice, not a bug — a heads-up warning when both are selected would help.
Ref: `ts_gui.py` `_run_selected_stages`.

---

## Next: Step 3 — multi-agent contract audit (P19)
One agent per LLM pipeline step builds a 4-way contract table
(**prompt → generation → save format → parser/validator**), verified against the
**real KCFC artifacts** already on disk (no new API spend), with an adversarial
verification pass to avoid false positives. Token-heavy — **best started in a
fresh conversation**; context to hand off: this file, LEARNINGS.md (P19 +
checklist), and the KCFC project dir
`/Volumes/CrucialX9/1 MY DISK/KCFC ALL/projects/2021 Webcast Feb - KCFC - 2021-02-xx/`.
