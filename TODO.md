# TODO — open bugs & tech debt

Tracked so we don't lose them. Items surfaced during the **2026-07-13 run-log
review** sessions unless marked *pre-existing* (not introduced by that work).
Fixed items live in CHANGELOG.md; recurring lessons in LEARNINGS.md.

---

## M3 schema contracts — staging follow-ups (2026-07-15)

Codec layer (`artifact_contracts.py`) + bowen boundary landed (M3a, M3b-bowen).
Remaining boundaries stage one at a time behind the migration shim.

- **⚠️ Themes migration shim must handle TWO real formats.** A P6 sweep of the
  codec over every real artifact on the drive found `parse_bold_numbered_theme_blocks`
  (consumer) returns **zero** on a real structural-themes file that uses
  `### N. Title` (H3-numbered) instead of the `**N. Title**` (bold-numbered) format
  the parser expects (`Monika Baege and Michael Kerr interview - 2010-09-23`,
  processed with the 2025-02 prompt). This is genuine pre-existing producer/consumer
  drift (P19). **Before wiring themes to the gate** (`_CONTRACT_ARTIFACTS`), the
  themes codec / `parse_bold_numbered_theme_blocks` must parse BOTH formats, or the
  first unattended re-publish of that (and any same-era) run will false-BLOCK
  (AC M3.D.1 requires legacy real artifacts to migrate). bowen/key-terms/topics/
  emphasis/interpretive-themes are all clean across the 6 real projects checked.
- **JSON sidecar is write-only so far.** `write_json_sidecar` emits `<base> -
  <artifact>.json` but no consumer reads it yet (gate + renderers still re-parse
  the `.md`). Durable provenance today; make a consumer prefer the validated
  `.json` (with an md↔json reconcile) in a later step to fully realize the
  structured-intermediate benefit.
- **Remaining boundaries to wire:** emphasis, key-terms, themes (see above),
  topics, abstract-input (JSON validate hook at `AbstractInput` assembly — no
  markdown wire format, so no round-trip; pinned by the producer/gate path).

---

## Test-validity audit (2026-07-15) — Step 1 done, follow-ups open

Mutation testing + fixture-provenance + vacuity scan of the whole suite. Full
report: `TEST_VALIDITY_REPORT.md`. Harness: `mut_harness.py`.

### ✅ FIXED 2026-07-15 (Step 1)
- Two broken tests in `test_validation_warnings.py`: `test_summary_proportionality_warning`
  (crashed — `unittest.mock` unimported; stale mock) and `test_summary_evaluative_warning`
  (mis-indented into the prior method, never collected). Both now run and pass.
- Added `tests/test_validator_logic_hardening.py` (15 tests) pinning validator decision
  logic. Mutation score: `summary_validation` 9%→28%, `abstract_validation` 36%→50%,
  `validation_pipeline` 24%→27%.

### Open follow-ups (test debt)
- ~~**`validate_key_terms_fidelity` tier thresholds still unpinned.**~~ ✅ FIXED
  2026-07-15 (Step 2). The `0.50 / 0.90 / 0.80 / 0.35` cutoffs are promoted to
  `config.KEY_TERMS_*` and pinned by a real-artifact disk-fixture test
  (`test_f1_keyterms_real_run_tiers_pinned`: EXACT==8 / FAIL==2 on the real run).
  A new LOCAL def-grounding floor (`KEY_TERMS_DEF_LOCAL_MIN`) closes the
  swapped-definition false-pass and is pinned by `test_f1_keyterms_swapped_definition_not_exact`.
- **Remaining low mutation scores.** Even after Step 1, `summary_validation` (28%) and
  `validation_pipeline` (27%) leave the medium-tier coverage branch (`match_count>=1 or
  ratio>=0.2`), word-allocation math, and `check_proportionality` internals untested.
- **False-green synthetic format tests.** Several theme/bowen/key-terms tests assert
  abandoned formats as correct (e.g. `test_summary_pipeline_parsing.py::test_parse_themes_header_format`
  certifies the A1 `### header`-as-theme bug). Repoint at `tests/fixtures/` real artifacts
  or delete; they pass only via legacy fallback paths and mask a re-drift.
- **Vacuous assertion-free tests.** `test_validation_headless.py` (×2) and
  `test_exception_fix.py` (×4) `print`/`return` instead of asserting; give them real
  assertions or mark clearly as manual harnesses.
- **Institutionalize:** add a mutation-score gate on the seven core modules to CI so
  this cannot silently rot again (coverage % does not detect it).

---

## P19 contract-audit findings (2026-07-14, step 3)

Multi-agent producer→consumer (prompt → generation → save → parser/validator)
contract audit against the **real KCFC artifacts**. 12 confirmed, each verified
against real on-disk bytes + an adversarial refutation pass (8 candidate findings
were refuted). Ordered by corrected severity. IDs `A1`–`A12`.

### 🔴 HIGH — ✅ FIXED 2026-07-14 (A1–A3 + sibling)
Shared bold-numbered-first parser (`transcript_utils.parse_bold_numbered_theme_blocks`
+ `is_scaffolding_theme_name`), both consumers reordered, loud zero-from-non-empty
warning, round-trip tests on the real artifacts (`tests/test_theme_parsing_contract.py`).
Verified on real KCFC files: structural 1→3, interpretive 2→7. `learning-qa` review
also fixed a P19 sibling — `extraction_pipeline._is_valid_section_content` validated
all-scaffolding structural files as usable content (now routes through the parser) —
and hardened `is_scaffolding_theme_name` against false-positives (labels →
`config.THEME_SCAFFOLDING_LABELS`, rule #9). 284 tests pass, 7 pre-existing failures
unrelated. See CHANGELOG.md.

### ✅ FIXED 2026-07-14 — validator pass-on-empty cluster (A5, A9, A10, A11)
"Validators reporting success without verifying." A5: `count_header_verdicts`
(drift-tolerant) wired into both header producers — loud warning on FAIL>0 /
zero-from-non-empty + report `## Verdict Summary` (real KCFC: 1 FAIL/5 WARN/44 PASS,
was silent pass); advisory by design. A9: empty required-items → fail-closed in
`summary_validation` + `abstract_validation` (P5 siblings). A10: distinct
`config.PURPOSE_EXTRACTION_FAILED` sentinel — transient failure keeps the purpose
check required + hard-uncovered (P1), not silently demoted. A11: empty-keyword item →
`(False,'low')` (LLM-rescue-eligible, not auto-'high', not hard-failed). `learning-qa`
2nd pass caught + fixed an LLM-rescue-bypass regression (F1/F2). 295 tests pass. See
CHANGELOG.md + `tests/test_validator_pass_on_empty_contract.py`.

- **A1 — Theme parser returns 1 bogus theme instead of 3 (abstract path).**
  `parse_themes_from_extraction` gates on `"###" in text`, so Strategy 1 captures
  the section header `### Structural Themes (3 total)` as the theme *name* and
  mashes the 3 real `**N. …**` themes into one description blob. The bold-numbered
  Strategy 2 that would parse them is dead-gated behind `if not themes:`. Live run
  on real `structural-themes.md` → **1 theme, the 3 real ones lost**, fed to the
  abstract with no error. Ref: `abstract_pipeline.py:149` (`_is_real_theme_name`
  `:134`, gate `:165`, bold regex `:167`).
- **A2 — Theme parser collapses 7 interpretive themes into 2 junk entries (summary path).**
  Same root cause, different consumer. Real 7-theme `interpretive-themes.md` parses
  to `['## Interpretive / Process Themes (7 total)' (12 002-char blob), 'Summary Paragraph']`;
  zero real themes reach `prepare_summary_input`. Ref: `summary_pipeline.py:300`
  (early `return themes` `:338`), consumed `:607`.
- **A3 — `summary_pipeline.parse_themes` has NO path that reads the real format.**
  Even with A2's `###` hijack fixed, both fallback regexes anchor on a bare
  `\d+.` line, but real headers start with `**`. The working bold-numbered handler
  exists only in `abstract_pipeline` (`:166`), never ported. Zero-from-non-empty is
  silent. Ref: `summary_pipeline.py:346-363`.

### 🟠 MEDIUM — ✅ FIXED 2026-07-14 (A4, A6, A7, A8) + 🟡 A12
A4: non-capturing alternation so the closing body is searched (patterns →
`config.ABSTRACT_CONCLUSION_PATTERNS`, rule #9; narrow-phrase recall gap tracked
below). A6: `parse_section_range` expands every comma segment (`re.search`/`findall`,
survives "Sections N" prefixes), deduped — real cause of the topics `section_mismatch`.
A7: `verify_highlights_bs4.load_source_quotes` reads all 3 real quote formats +
non-zero exit on drift (bowen 0→1, emphasis 0→22). A8: `_top_lens_is_grounded`
(content-token overlap) gates the loop and **fails closed after retries** (no ungrounded
lens ships). A12: `_strip_leading_scaffolding` excludes a leading `# Abstract` header
from word count + keyword matching. `learning-qa` 2nd pass caught + fixed 2 HIGH
regressions (A8 exhaustion fall-through, A6 anchored-match drop). 311 tests pass. See
CHANGELOG.md + `tests/test_audit_medians_contract.py`.

- **A4 — `extract_closing_conclusion` single-group `re.findall` drops the body.**
  `r"## Section (N|…)[^#]+"` has one capturing group, so `findall` returns section
  *numbers* (`"45 46 …50"`) and discards the closing text. Conclusion search always
  fails → returns `"No explicit conclusion stated"` → the abstract validator
  **silently skips the required conclusion-coverage check on 100 % of transcripts**.
  Ref: `abstract_pipeline.py:305-317`; gate `abstract_validation.py:253-256`.
- **A5 — Header-validation verdicts are never counted; a real FAIL passes.**
  `validate_headers` returns `True` on `len≥100` with zero parsing. Model format-drifts
  (`**STATUS:** FAIL` in some batches vs plain elsewhere); a declared-format counter
  sees 0 FAILs / 2 of 5 WARNs. Section 15 genuinely FAILs yet the step reports success.
  Ref: `validation_pipeline.py:594`; no STATUS counter in any consumer.
- **A6 — `parse_section_range` truncates multi-segment citations to the first range.**
  Anchored `re.match(r"(\d+)\s*-\s*(\d+)")` fires on the leading range and never
  reaches the `else` findall: `"7-8, 15, 33-35"` → `[7,8]`. Deflates section-grounding
  scores. **This is the real cause of the `section_mismatch: 7` mislabelled "cosmetic"
  below.** Ref: `summary_pipeline.py:274-288`; consumed `validation_pipeline.py:429-430`,
  `summary_pipeline.py:249`.
- **A7 — `verify_highlights_bs4.load_source_quotes` uses the abandoned bowen format.**
  Regex expects `> **Label:** "quote"`; real artifact is `### Concept\n> "quote"` →
  returns `[]` → "Loaded 0 bowen references" → highlight verifier reports a clean pass
  having **verified nothing** (a mis-highlighted/hallucinated bowen quote rides through).
  Ref: `verify_highlights_bs4.py:56`; reuse `transcript_utils.load_bowen_references`.
- **A8 — `top_lens` accepted on a truthy-dict gate, never reconciled to the ranked lenses.**
  `if structural_valid and interpretive_valid and top_lens: break` — nothing compares
  `top_lens.title` to the 12 lenses actually written, so a paraphrased/invented top lens
  is "✓ validated" and piped to the blog. Ref: `extraction_pipeline.py:1323,1344,1484-1490`.
- **A9 — `validate_summary_coverage` reports PASS on an empty checklist (`all([]) == True`).**
  When topics are missing/drifted the required-items list is empty → "Required coverage:
  0/0" → **any non-empty (even off-topic) summary validates**. Also `check_keyword_coverage`
  auto-returns `(True,'high')` when `total_keywords == 0`. Ref: `summary_validation.py:469,316-317`.
- **A10 — Abstract coverage denominator regenerated from a live LLM call at validation time.**
  `is_required = "manually insert" not in opening_purpose`, and `extract_opening_purpose`
  hits the API at read time. No key / a timeout demotes the purpose check required→optional
  — **a transient outage flips FAIL into reported PASS** (P1). Re-run now yields `3/3` vs the
  saved `4/4`. Ref: `abstract_validation.py:240`; `abstract_pipeline.py:259`; `validation_pipeline.py:650`.

### 🟡 LOW

- **A11 — Empty-keyword coverage item auto-marked covered `'high'`.** `if total_keywords
  == 0: return True, "high"` — latent on this artifact (all topic names >4 keywords), bites
  on all-stopword/short topic names. Ref: `summary_validation.py:316`.
- **A12 — Abstract word count includes the forbidden `# Abstract` header (+2 tokens).**
  Prompt says "no headers"; model emits one; `len(abstract.split())` counts it (331 vs 329),
  can tip a boundary-length abstract's min/max check. Ref: `abstract_validation.py:620`;
  save `extraction_pipeline.py:1102`.

### Refuted but real fragility (not strict P19 — keep on radar)
Emphasis raw-quote no-escaping (non-greedy regex tolerates it; = pre-existing item below);
`verify_with_llm` positional YES/NO zip (both abstract & summary — real fragility, no
format-drift trigger); `extract_section("Lenses (Ranked)")` regex miss (sibling path handles it).

---

## Real-run audit (2026-07-15) — Step 2: validator gate hardening ✅

Audited a full real run (`Where Roots Bowen Theory Reside in the Brain - Michael
Kerr - 2022-02-18`) against its source; re-ran the deterministic validators on the
real artifacts in both directions. See CHANGELOG.md (Step 2) + LEARNINGS.md.

**Fixed:** emphasis 15-word blindspot → head+tail match + real return bool (also
fixed a pre-existing false-negative); key-terms definition proxy → added local
grounding (`_best_local_grounding`) + downgrade-with-warning + thresholds promoted
to `config.*` and pinned; abstract fabricated-name detector (`find_ungrounded_names`,
advisory); Bowen within-file dedup; `html_generator` 2-vs-3 tuple crash (+ sibling
`format_ref_list`); `unknown_script` named loggers (5 sites). Tests:
`tests/test_validator_gate_hardening.py`, fixtures `tests/fixtures/where_roots/`.

**Adjacent issues (flagged by learning-qa review, not fixed — rule 10):**
- **Dead duplicate `_generate_simple_html_page`.** `html_generator.py` defines it
  twice (~line 266 dead-shadowed, ~line 642 live); the first is unreachable. Pre-existing.
- **`_best_local_grounding` re-normalizes the whole transcript per key term.**
  N terms × full-transcript `normalize_text` — fine at current scale (sub-second on
  ~11k words × 10 terms) but hoist `norm_tokens` out of the per-term path if it ever bites.

**Still open (generation-side, lower priority):**
- **Emphasis timestamps drift from the quote's real location.** Several items carry
  a timestamp for the wrong block (e.g. the mass-energy quote tagged `00:18:06`,
  actually ~`00:20:04`; a Rediger-book quote tagged `00:48:10`, actually ~`01:24`).
  Quotes are verbatim; the citation is wrong. This is in emphasis *generation*, not
  the validator. Consider deriving/validating the timestamp from the matched span.
- **Cross-artifact name inconsistency.** The same unnamed person is "Bertoloso"
  (topics, faithful to source ASR), "Bertolaso" (structural themes, corrected), and
  the now-flagged fabricated "Luciano Malorni" (abstract). F4's detector catches the
  fabrication; consistency across artifacts is not enforced.

## Phase 1 (unattended-robustness spec) — known limitations of the release gate

The fail-closed release gate (M1/M4/M7) is in. `learning-qa` reviewed the diff;
its findings were fixed except these two, kept as honest limitations:

- **F2 — the entity blocker only catches MULTI-WORD Latin names.** A single-word
  fabricated surname ("Malorni" alone), an ALL-CAPS acronym/org, initials
  ("J. Ewing"), or a non-Latin-script name slip through `find_ungrounded_names`
  (`abstract_validation.py`) and publish silently. It caught the actual shipped
  "Luciano Malorni" (multi-word). Broadening to single-word/acronym would flag
  every capitalized word — the real fix is the semantic judge (M2, deferred). U2
  is therefore only met for the multi-word subset (already stated in the spec).
- **F5 — manifest/publish-decision precision (largely addressed).** `publish_allowed`
  now writes the run manifest tied to THE decision that gated (fixed: a normal
  publish always leaves a manifest, no separate second gate run). Residual: each
  publish entry point (webpage/pdf/package) still runs the gate independently
  (deterministic, so the decision is identical) and the manifest is a gate-time
  snapshot — bundle files written *after* the guard aren't all captured. A single
  orchestrator-level `gate_and_report` call (once, after all artifacts exist,
  before publish) would make it exact + run the gate once; do it when the
  pipeline orchestration layer is next touched.

## Phase 0 (unattended-robustness spec) — product decisions surfaced

Raised while resolving the pre-existing red tests (M8.B). Each is xfail-annotated
with a reason; these need a product call, not a test edit.

- **Universal `MAX_TOKENS_SUMMARY=4096` output ceiling.** `cap_max_tokens_for_model`
  floors *every* model to `config.MAX_TOKENS_SUMMARY` (4096), so the haiku 8192
  entry in `MODEL_OUTPUT_TOKEN_LIMITS` and any higher per-model limit are always
  dominated. Header-validation batches and long summaries may be truncated (P9).
  **Decide:** is 4096 the intended global ceiling, or should the cap be the *model*
  limit (raising header-validation / summary headroom)? xfail:
  `test_header_validation_token_limits.py` (2 tests).
- **Config settings don't reload across `ProjectSettings` instances.** A new
  instance does not pick up a persisted `default_source_dir`. Real gap; fixing it
  is a config-wide change. xfail: `test_config_validation.py::test_runtime_settings_persistence`.
- **Bowen integration tests certify the abandoned `> **Label:**` format.** Repoint
  them at a real-format fixture or delete (the live format is covered by
  `test_theme_parsing_contract` + `tests/fixtures/where_roots/`). Tracked under M6.C.
  xfail: `test_bowen_references_integration.py` (2 tests).
- **6 vacuous (assertion-free) tests still on the allowlist.** `test_exception_fix.py`
  (×4) and `test_validation_headless.py` (×2) verify nothing (TEST_VALIDITY_REPORT §3).
  The M6.B gate (`quality_gates.find_vacuous_tests`) now blocks *new* ones and
  allowlists these; give them real assertions and drop them from `KNOWN_VACUOUS`
  in `tests/test_quality_gates.py`.

## Bugs (unfixed)

### ~~`unknown_script` rows in the cost log on real runs~~ ✅ FIXED 2026-07-15 (Step 2)
Five API calls logged token usage with a nameless logger → `unknown_script` rows in
**real runs**. Fixed: `abstract_pipeline` (×2), `summary_pipeline`,
`transcript_extract_terms`, `transcript_audit_voice` now pass a named logger.
Tests: `test_validator_gate_hardening.py::test_extract_terms_passes_named_logger`,
`::test_audit_voice_passes_named_logger`. (Abstract/summary sites pass the module
logger directly.)

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
- ~~`test_html_generation.py::test_highlighting_logic` — highlight tuple unpack (`expected 3, got 2`).~~ ✅ FIXED 2026-07-15 (Step 2).
- ~~`tests/test_html_generator.py::` `test_generate_simple_html_page_structure`, `test_highlight_html_content_basic`, `test_highlight_html_content_exact_word_match` — HTML highlighting.~~ ✅ FIXED 2026-07-15 (Step 2): both `_highlight_html_content` and `format_ref_list` now tolerate 2-/3-tuples.
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

### Topics validation `section_mismatch` — ✅ parser bug FIXED (A6)
Topics cite section ranges that don't line up with actual sections
(`section_mismatch` 6–7 on real runs). ~~Cosmetic; the topics themselves validate.~~
**2026-07-14:** the P19 audit (**A6**) traced most of this to `parse_section_range`
truncating multi-segment citations to the first range — **fixed** (see the MEDIUM
banner above). Re-run a real transcript to confirm the residual mismatch count drops;
any remainder is genuine topic/section drift, not the parser.
Ref: `validation_pipeline.py` `validate_topics_lightweight`, `summary_pipeline.py` `parse_section_range`.

### Abstract conclusion detection has narrow phrase recall *(from A4 fix)*
`extract_closing_conclusion` now searches the closing body correctly, but
`config.ABSTRACT_CONCLUSION_PATTERNS` is a short hardcoded phrase list — a real
closing using none of them (e.g. the KCFC "witching hour…" sign-off) still returns
"No explicit conclusion stated", dropping the conclusion-coverage check. Broaden the
phrase set (editorial) or add a fallback (e.g. last 1–2 sentences of the final
section). Ref: `abstract_pipeline.py` `extract_closing_conclusion`, `config.ABSTRACT_CONCLUSION_PATTERNS`.

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

## ~~Step 3 — multi-agent contract audit (P19)~~ ✅ DONE 2026-07-14
Ran: 11 finders (one per LLM pipeline step) + 20 adversarial verifiers, all checked
against the real KCFC artifacts. 12 findings confirmed (see **P19 contract-audit
findings** at the top of this file, A1–A12), 8 refuted. No new API spend.
Next actionable work: the **theme-parsing cluster A1–A3** (highest impact — silently
corrupts both the abstract and summary inputs on every real transcript).
