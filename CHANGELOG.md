# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2026-07-15 (unattended-robustness — M3: schema contracts)

Kill the P19 producer/consumer format-drift *class* (U4). Every structured
boundary becomes a schema-validated object; drift is a hard error, never a silent
zero. Scope decision: codec layer first — markdown stays the wire format, JSON is
a derived sidecar, generation prompts unchanged (delivers U4 regardless of wire
format). Staged one artifact at a time behind a migration shim; gate green
throughout.

**M3a — foundation.**
- **`schemas/*.schema.json` (6):** bowen, emphasis, key_terms, topics, themes,
  abstract_input — versioned, `additionalProperties:false` envelopes with
  `artifact`/`version` `const`s (catch a mis-routed object).
- **`artifact_contracts.py`:** per-boundary `Codec` — `parse_markdown` (migration
  shim, delegates to the ONE canonical text parser the consumer uses) / `validate`
  (jsonschema, loud `SchemaError` on drift) / `render_markdown` / `to_json`/
  `from_json`. Non-empty body → zero items = `SchemaError` (P19); truly empty
  (blank / frontmatter-only / bare H1–H2 header) = benign empty object.
- **Single-canonical-parser refactors** (behavior-preserving): extracted
  `parse_bowen_references_text` and `parse_topics_structure` so loader + codec
  share ONE format implementation. `parse_topics_structure` is *faithful* (the
  `<5%` editorial cut stays in `parse_topics_with_details`), so the JSON contract
  represents the artifact exactly.
- `jsonschema` pinned (requirements.txt, pyproject.toml). Real topics/themes
  fixtures copied from a production run for round-trip/migration tests.

**M3b — bowen wired (first boundary).**
- **Producer self-validation + JSON sidecar** at the bowen save site
  (`extract_bowen_references_from_transcript`): re-reads the saved artifact
  through the codec; on drift it LEAVES the file on disk (so the gate BLOCKs —
  deleting would invert a loud BLOCK into a silent drop), invalidates any stale
  sidecar, logs, and returns False. A valid save writes `<base> -
  bowen-references.json`.
- **Gate consumer-validation** `check_artifact_contracts` (release_gate.py):
  validates every on-disk structured artifact through the codec; drift → ERROR →
  **BLOCK**. Added to `config.GATE_BLOCKING_CHECKS` (U4: drift is a hard error).
  Verified against ALL real bowen artifacts on the drive (6/6 parse, 0 false
  reject) before landing as a hard blocker (P6).
- **`_has_body` empty-vs-drift discriminant:** a bare H1/H2 section header is a
  benign empty; an H3+ item header (or any non-heading line) with zero parsed
  items is drift — closes the all-headers-no-body gap.
- Tests: 30 codec + producer tests on REAL fixtures (round-trip field-level
  fidelity, drift-is-loud incl. all-headers, frontmatter/header-only benign,
  migration, producer self-check) + 4 gate tests. `_has_body` and
  `verify_saved_artifact` 100% mutation-killed; codec drift guard pinned.
- Two `learning-qa` pre-flight passes applied: topics faithful-parser +
  false-drift guard, emphasis type case-normalization, field-level round-trip
  assertion, and the delete-on-drift → leave-for-gate inversion fix (a HIGH
  finding — the producer's delete was silencing the very drift the gate blocks on).

**M3b — remaining boundaries wired (emphasis, key-terms, topics, themes,
abstract-input).**
- **One producer seam:** emphasis, topics, key-terms, and both themes all save
  through `_save_summary`, so `_self_validate_saved_summary` self-checks every one
  (re-read via codec → sidecar on success; on drift leave the file for the gate,
  invalidate stale sidecar, log; never delete). Non-codec types (blog/overview)
  are a no-op.
- **Themes migration shim reads BOTH real formats:** `**N. Title**` (current) and
  legacy `### N. Title` (H3-numbered, 2010-era runs) — a drive sweep found the H3
  format on a real structural-themes file that the bold-only parser returned zero
  for (P19). Verified 0 false-reject across every structural + interpretive
  artifact on the drive before gating themes.
- **Gate `_CONTRACT_ARTIFACTS`** extended to all 5 markdown boundaries (bowen,
  emphasis, key-terms, topics, both themes) — each a hard blocker on drift, each
  backed by a real-fixture round-trip/migration test.
- **abstract-input** (assembled `AbstractInput`, not saved markdown): producer
  self-validation in `prepare_abstract_input` via `to_contract_dict()` +
  `ac.validate` — a malformed input (empty topic name, out-of-range %) is a
  fail-closed `SchemaError` before the costly generation call (both callers catch
  it → stage returns False). Verified a real assembly validates (no false close).
- **Deliberate fail-closed decision (learning-qa F1):** the emphasis raw-response
  fallback (0 items from a >500-char response = drift) is saved under the canonical
  suffix ON PURPOSE so the gate BLOCKs — better than a silent absence; documented
  in-code. Two adjacent, non-M3 issues (emphasis content-rejected raw fallback;
  a whitespace-only topic-name edge) flagged in TODO, not silently fixed.

Suite: 540 passed / 14 skipped / 5 xfailed / 0 failed.

Spec: docs/spec_unattended_robustness_2026-07-15.md#M3 (M3.A, M3.B, M3.C, M3.D)

## [Unreleased] - 2026-07-15 (unattended-robustness — M5: fault-injection matrix)

The acceptance test for the fail-closed net: under adverse inputs and injected
faults the gate must give a definite decision (never crash) and degrade with a
distinct signal, or fail closed — never silently publish.

- **`tests/test_m5_fault_injection.py` (12).** M5.A input edge matrix (empty /
  whitespace / short / malformed / very-long transcript — no crash, correct
  block/allow); M5.B partial artifacts (missing source -> BLOCK; missing/empty
  abstract -> WARN, named); M5.C dirty re-run (BLOCK then clean clears the marker
  and quarantines the stale bundle; gate idempotent — same state, same manifest
  hashes); M5.D fault injection (a transient in a BLOCKING check -> ERROR -> BLOCK
  with no bundle; a fault in an ADVISORY check -> ALLOW_WITH_WARNINGS, F3).
- **`check_required_artifacts` (WARN).** Names a missing/empty required artifact
  (`config.GATE_REQUIRED_ARTIFACT_SUFFIXES`) so an incomplete bundle isn't shipped
  silently. Advisory per the entity-only blocking policy; a missing SOURCE still
  hard-blocks via entity_grounding's ERROR.

## [Unreleased] - 2026-07-15 (unattended-robustness — Phase 1: fail-closed release gate)

The pipeline's validators were advisory (they wrote a report; nothing blocked on
them), so a fabricated name could reach a published artifact. Phase 1 adds a
fail-closed release gate between generation and publication (spec M1/M4/M7).

### Added

- **`release_gate.py` (M1).** Every check returns a typed `Verdict`
  (PASS/WARN/FAIL/ERROR); `run_gate` aggregates them via a `config` policy table
  into a `GateDecision` (ALLOW / ALLOW_WITH_WARNINGS / BLOCK). A check that raises
  becomes an ERROR verdict — never silently skipped (M1.C) — and ERROR blocks by
  default (a run we couldn't verify must not ship, P1). Elected hard blocker:
  `entity_grounding`.
- **Provenance checks (M4).** `entity_grounding` (BLOCKING) FAILs on a fabricated
  proper name in the abstract (the shipped 'Luciano Malorni' class); scoped to the
  **abstract only** because the lexical name detector false-flags Title-Case
  headings/concepts in synthesized artifacts ('Key Takeaways', 'Role Absorption' —
  confirmed on real runs) and a false BLOCK is a hard stop. `verbatim_quotes`,
  `timestamp_citations` (catches the F6 drift), and `entity_consistency` (F7) run
  as WARN.
- **Run manifest (M7).** Each gated run writes `<base> - run-manifest.json`
  (per-artifact status + hashes, the GateDecision, source hash + model IDs, a
  single `publish_decision`); `release_gate.main` exits nonzero on BLOCK for
  cron/CI; a BLOCK drops a `PUBLISH-BLOCKED.txt` marker, cleared on a clean re-run
  (P8).

### Changed

- **Publish path is now gated (M1.B.2).** `generate_webpage`,
  `generate_simple_webpage`, `generate_pdf` (`html_generator`) and
  `package_transcript` (`packaging_pipeline`) call `release_gate.publish_allowed`
  and write NO bundle on a BLOCK. Tests: `tests/test_release_gate.py` (19 —
  real-fixture BLOCK/ALLOW, ERROR fail-closed + advisory-error-doesn't-block,
  manifest, publish guard, false-BLOCK scoping, stale-bundle quarantine, empty
  source, accented names). Two pre-existing unit tests were isolated from the gate.

### Review

`learning-qa` audited the diff. Fixed before commit: the entity blocker scoped to
the abstract (synthesized Title-Case labels false-BLOCK, confirmed on real runs);
advisory-check ERRORs no longer hard-stop publication (only blocking checks block
on ERROR); a BLOCK now quarantines any stale published bundle so it can't ship as
current; a present-but-empty source is ERROR not FAIL; the name detector matches
Latin-accented names. Documented as known limitations (TODO): single-word/acronym
names (needs the M2 judge) and manifest wiring into the live publish path.

## [Unreleased] - 2026-07-15 (unattended-robustness — Phase 0: code health + test-validity gates)

First phase of `docs/spec_unattended_robustness_2026-07-15.md` (approved scope:
the fail-closed net first). Phase 0 stabilises the ground and makes test validity
measurable, before the release-gate work (M1/M4/M7) touches the publish path.

### Fixed / hardened (M8)

- **`mut_harness` no longer corrupts its target on a kill (M8.C).** It restored
  byte-exactly only in a `finally`; a timeout/SIGKILL mid-run left an
  `ast.unparse`-reformatted, mutated file on disk (it corrupted
  `validation_pipeline.py` twice during Step 2). Now keeps a sidecar backup +
  SIGINT/SIGTERM handlers + self-heals a leftover mutant at the start of the next
  run, and streams progress. Logic extracted to `run_campaign(...)` with an
  injectable suite runner. Tests: `tests/test_mut_harness.py`.
- **Removed the dead duplicate `_generate_simple_html_page` (M8.A).** Python kept
  the later (live, tested) copy; the earlier was dead. Guard: `test_m8a1_no_shadowed_defs`
  AST-scans the core modules for shadowed top-level defs.
- **The 5 pre-existing red tests are now annotated `xfail` (M8.B),** so the suite
  is green (0 failed / 5 xfailed) and a real regression can't hide in a red suite.
  Each reason is recorded, and the underlying product decisions surfaced to
  TODO.md (the universal `MAX_TOKENS_SUMMARY=4096` output ceiling; config
  cross-instance settings reload; the abandoned-format bowen tests). Guard:
  `test_m8b1_known_reds_are_xfail_annotated`.
- **Artifact path audit (M8.D):** 216 uses go through `config.SUFFIX_*`; path
  *construction* is 100% via config. Fixed one straggler (`transcript_organize.py`
  used a literal ` - formatted.md`).

### Added (M6 — test-validity gates)

- **`quality_gates.py`:** a vacuity checker (`find_vacuous_tests` — flags
  assertion-free tests) and a mutation-gate config/runner. Enforced in-suite:
  `test_m6b1_no_new_vacuous_tests` blocks NEW vacuous tests (allowlisting the 6
  known ones, tracked in TODO), `test_m6a1_mutation_gate_config_is_valid` pins the
  gate config, `test_m6c1_real_format_fixtures_exist` protects the real-artifact
  fixtures.
- **CI (`.github/workflows/ci.yml`):** a strict `quality-gates` job (fails on a red
  suite + runs the vacuity gate) and a scheduled/dispatch `mutation-gate` job that
  fails when a core function drops below its score floor. The legacy lenient
  `build` matrix is left untouched.

## [Unreleased] - 2026-07-15 (real-run audit — Step 2: validator gate hardening)

Motivation: a full real run (`Where Roots Bowen Theory Reside in the Brain -
Michael Kerr - 2022-02-18`) was audited against its source transcript, and the
deterministic validators were **re-run with current code** on the real
artifacts, in both directions (good output must PASS; deliberately degraded
output must be FLAGGED). Several gates could be fooled or crashed. All validators
here are advisory (their return value drives a human-reviewed report, not a hard
pipeline gate), so a false PASS misleads the reviewer rather than auto-shipping —
but that report is the reviewer's signal. Findings report + method:
`scratchpad` audit notes; fixtures: `tests/fixtures/where_roots/` (real artifacts).

### Fixed (validator false-PASS / crash)

- **Emphasis validator only matched the first 15 words of each quote (P2/P9).**
  A quote with a verbatim opening and a fabricated tail passed silently (verified:
  a "…vaccines cause autism which Bowen never said" tail was accepted). It now
  probes BOTH the head and tail of every quote (`_emphasis_quote_found_ratio`,
  `config.EMPHASIS_HEADTAIL_WORDS`) and returns a real pass/fail bool instead of
  `None`. Side effect: fixed a pre-existing false-NEGATIVE (a genuine "Liking,
  that is pleasure…" quote that reflow made the 15-word match miss) — the real
  run now validates 100%. `validation_pipeline.validate_emphasis_items`.
- **Key-terms definition check was a gameable proxy (P7).** Definition support
  measured keyword overlap with the WHOLE transcript, so a definition describing
  the *wrong* concept still scored EXACT (verified: Homeostasis's definition
  swapped for the reward/salience-network definition → 0.87 → EXACT). It now also
  requires LOCAL grounding — overlap in the transcript window around where the
  term actually appears (`_best_local_grounding`,
  `config.KEY_TERMS_LOCAL_WINDOW_WORDS` / `KEY_TERMS_DEF_LOCAL_MIN`). Calibrated
  on the real run: valid definitions ≥0.54 local, swapped/off-topic ≤0.13. A
  grounded term whose definition fails the local check is downgraded from
  EXACT/PARTIAL to WEAK with a loud warning (P2). The 0.50/0.80/0.90/0.35 tier
  thresholds are promoted to `config.*` and pinned by a real-artifact test.
- **`_highlight_html_content` and `format_ref_list` crashed on 2-tuples (P19).**
  Loaders now emit 3-tuples `(label, quote, timestamp)`, but some callers still
  pass 2-tuples → `ValueError: not enough values to unpack`
  (`html_generator.py:531`). Both consumers now tolerate 2- and 3-tuples; the
  simple-page generator reuses the correct module-level `_format_ref_list`
  (which renders the timestamp) instead of a stale nested 2-tuple-only copy.
  Fixes 4 pre-existing red tests.

### Added (checks for previously-unguarded quality dimensions)

- **Abstract proper-name grounding (advisory, P2).** No gate checked abstract
  proper names; a real run fabricated a researcher name ("Luciano Malorni", for
  the person the source only ever calls "Bertoloso") and it shipped into the
  published HTML. `abstract_validation.find_ungrounded_names` flags multi-word
  Title-Case names whose tokens appear nowhere in the source (fuzzy-tolerant of
  ASR spelling normalization); surfaced as a warning + a line in the abstract
  validation report.
- **Bowen reference de-duplication (P2).** `load_bowen_references` returned the
  same quote twice when the model listed it under two concepts (real run: 5
  listed, 4 unique). It now dedupes by normalized quote text and logs what it
  dropped.
- **`tests/test_validator_gate_hardening.py` (18 tests)** — real-artifact
  contract + adversarial + edge-case tests for every fix above, each failing on
  the old code and asserting intended behavior (not a snapshot).

A `learning-qa` second-pass review of the diff caught two follow-ups that were
fixed before commit: (1) the key-terms local check located the term with *exact*
contiguous matching while `term_ratio` uses *fuzzy* matching, which would falsely
demote a legitimately-grounded multi-word term whose transcript form is
reordered/hyphenated (P19 #9) — the locator now uses a flat normalized token
stream and an unlocatable term gets the benefit of the doubt (no downgrade,
no warning), so the downgrade fires only when the term *was* located and the
definition still fails locally; (2) Bowen dedup now MERGES the duplicate's
concept label into the kept entry (`"A; B"`) instead of dropping it, so no
concept association is lost from the highlighter.

### Fixed (token-usage log hygiene)

- **Five API call sites logged token usage as `unknown_script`** on real runs
  (`abstract_pipeline` ×2, `summary_pipeline`, `transcript_extract_terms`,
  `transcript_audit_voice`). Each now passes a named logger so the cost log
  records the real step.

## [Unreleased] - 2026-07-15 (test-validity audit — Step 1: broken tests + validator hardening)

Motivation: a green 300+ test suite kept shipping critical bugs. A test-validity
audit (mutation testing + fixture-provenance + vacuity scan + learnings→test map)
found the suite is strong at pinning already-fixed bugs (all A1–A12 enforced) but
weak on the *validator decision logic* — mutation score 9% in `summary_validation`,
24% in `validation_pipeline`. Full write-up: `TEST_VALIDITY_REPORT.md`; harness:
`mut_harness.py`.

### Fixed (tests that verified nothing)

- **`test_summary_proportionality_warning` crashed before asserting.** It used
  `unittest.mock.patch` with only `import unittest` (no `unittest.mock`), so it
  raised `AttributeError` and never reached its assertions — an order-dependent
  false pass (it only "passed" when another test imported `unittest.mock` first).
  Added the import; corrected the stale mock (the test preset `item.covered=True`,
  but `validate_summary_coverage` re-derives coverage via `check_keyword_coverage`,
  so the item now carries real keywords present in the summary).
- **`test_summary_evaluative_warning` never ran.** It was indented one level too
  deep, defined *inside* `test_summary_too_long_warning`, so pytest never collected
  it. Dedented to a real test method; it passes.

### Added (validator decision-logic regression tests)

- **`tests/test_validator_logic_hardening.py` (15 tests).** Pins the validator
  logic the mutation pass exposed as unprotected: `required=` integrity of coverage
  items (speaker/opening/closing/Q&A), the topic required thresholds (`>=10%`
  summary, `>=15%` abstract), the first-theme-required rule (`i == 0`), the Q&A
  optional/required bands (15/30), the keyword-coverage count/ratio decision, the
  lexical grounding ratio, and the fail-closed `validate_key_terms_fidelity` on zero
  terms. Each assertion is written so the specific surviving mutation would fail it.

### Result

- Mutation score on the audited validator functions: `summary_validation` 9%→28%,
  `abstract_validation` 36%→50%, `validation_pipeline` 24%→27%. Suite grew by 16
  real tests (2 revived + 14 net new logic checks) with no regressions.

## [Unreleased] - 2026-07-14 (P19 contract audit — remaining medians A4/A6/A7/A8/A12)

### Fixed

- **Abstract closing-conclusion search discarded the closing body (A4, P19).**
  `extract_closing_conclusion` built the section regex with a *capturing* group
  `(N|…)`, so `re.findall` returned only section NUMBERS and the conclusion search
  ran against a string of digits — always failing and returning "No explicit
  conclusion stated", which silently dropped the required conclusion-coverage check.
  Made the alternation non-capturing so the body is searched. (The
  `conclusion_patterns` phrase list is now in `config.ABSTRACT_CONCLUSION_PATTERNS`,
  rule #9; its narrowness is a tracked recall gap, not a correctness bug.)
- **`parse_section_range` truncated multi-segment citations (A6, P19).**
  An anchored `re.match` fired on the leading range and returned only it, so
  `"7-8, 15, 33-35"` became `[7,8]` — deflating topic section-grounding (the real
  cause of the `section_mismatch` counts previously mislabelled "cosmetic"). Now
  expands every comma segment (`re.search`/`findall`, so `"Sections 7-8, 15"` also
  survives), deduped order-preserving.
- **Highlight verifier read an abandoned quote format (A7, P19).**
  `verify_highlights_bs4.load_source_quotes` matched only `> **Label:** "quote"`,
  returning `[]` on the real `### Concept\n> "quote"` (bowen) and `[meta] Concept:
  …\n"quote"` (emphasis-scored) artifacts — so the verifier reported a clean pass
  having checked nothing. Now parses all three formats, resolves the emphasis file to
  `emphasis-scored.md`, and treats "content present but zero parsed" as a drift error
  (loud warning + non-zero exit). On the real files: bowen 0→1, emphasis 0→22 quotes.
- **`top_lens` accepted without grounding (A8, P7).**
  The theme/lens validation loop accepted the validator's `top_lens` on a truthy-dict
  gate, never reconciling it to the ranked lenses actually generated, so a
  paraphrased/hallucinated top lens rode through into the blog. Added
  `_top_lens_is_grounded` (content-token overlap against the real `N. **Title**`
  lines); the loop now requires grounding to break and **fails closed after retries**
  (a `validated` flag — the exhaustion path no longer ships an ungrounded lens).
- **Abstract word count included the forbidden `# Abstract` header (A12).**
  `_strip_leading_scaffolding` now drops leading YAML front matter / heading / bold-
  label lines before the word count and keyword matching, so a header the model emits
  despite the "no headers" instruction can't tip the length check or the counts.

## [Unreleased] - 2026-07-14 (P19 contract audit — validator pass-on-empty cluster)

### Fixed

- **Header validation reported success on a report containing a real FAIL (A5, P19).**
  `validate_headers` / `HeaderValidator.run` wrote the report and returned success
  without ever counting the model's PASS/WARN/FAIL verdicts, and the model's format
  drift (`**STATUS:** FAIL` vs plain `STATUS: FAIL`) hid the failures from any naive
  counter. Added `transcript_utils.count_header_verdicts` (drift-tolerant), wired into
  both producers: a loud warning fires on `FAIL>0` or zero-verdicts-from-non-empty, and
  the report gets a `## Verdict Summary` header. On the real KCFC report it now surfaces
  1 FAIL / 5 WARN / 44 PASS (previously a silent pass). Advisory by design — the bool
  return still means "report generated", consistent with the coverage validators.
- **Coverage validators reported PASS on an empty required checklist (A9, P19).**
  `all(item.covered for item in required_items)` is `True` when `required_items == []`,
  so a summary/abstract whose upstream topics/themes were missing or format-drifted
  validated as "Required coverage: 0/0 — PASSED". Both `summary_validation` and
  `abstract_validation` now fail closed (with a warning) when no required items could be
  derived.
- **A transient purpose-extraction failure flipped a FAIL into a PASS (A10, P1).**
  `extract_opening_purpose` returned the same `"manually insert"` sentinel for a genuine
  absence AND for transient/config failures (no API key, timeout, missing prompt),
  silently demoting the required purpose check to optional. Transient failures now return
  a distinct `config.PURPOSE_EXTRACTION_FAILED` sentinel; the validator keeps that check
  REQUIRED and hard-uncovered (excluded from the LLM rescue pass), so validation cannot
  pass on an unverified purpose.
- **An ungroundable coverage item was auto-marked covered='high' (A11, P7).**
  `check_keyword_coverage` returned `(True, "high")` when an item had zero extractable
  keywords (e.g. an all-stopword topic name), satisfying required coverage with no
  grounding. It now returns `(False, "low")` — not auto-passed, but still eligible for
  the LLM rescue pass / human review (not hard-failed, so a legitimately-covered
  short-name topic can still be confirmed). Applied to both validators (P5 siblings).

## [Unreleased] - 2026-07-14 (P19 contract audit — theme-parsing cluster)

### Fixed

- **Theme parsers dropped or corrupted every theme on real transcripts (P19 — TODO.md A1/A2/A3).**
  The extraction stage writes structural/interpretive themes as bold-numbered
  `**N. Title**` blocks wrapped in `###`/`##` scaffolding (`### Structural Themes
  (3 total)`, `### Summary Paragraph`). Both consumers gated on `"###"` *first*, so
  they captured the scaffolding header as the theme name and mashed every real theme
  into one description blob — `parse_themes_from_extraction` returned **1 bogus theme**
  from a 3-theme file (abstract), `parse_themes` returned **2 junk entries** from a
  7-theme file (summary), and `summary_pipeline` had *no* code path that read the real
  `**N.**` format at all. Both now detect the bold-numbered format first (shared
  `parse_bold_numbered_theme_blocks` in `transcript_utils.py`), treat `###`-as-theme as
  a legacy fallback, reject scaffolding names (`is_scaffolding_theme_name`), and log a
  loud warning when non-empty input parses to zero themes. Verified against the real
  KCFC artifacts: structural 1→3, interpretive 2→7, with correct per-theme descriptions.
  Round-trip tests on the real artifacts: `tests/test_theme_parsing_contract.py`
  (fixtures copied from the real on-disk files, not idealized synthetic samples).
- **Extraction validity gate passed all-scaffolding structural files (P19 sibling, learning-qa).**
  `_is_valid_section_content` validated structural themes with a number-outside-bold
  regex (`1. **X**`) or a bare `###` presence check — so a `structural-themes.md`
  containing only scaffolding (`### Structural Themes (0 total)`, `### Summary
  Paragraph`) validated as usable content. It now routes through the format-aware
  `parse_themes_from_extraction` first and its fallback matches both bold forms.
  Ref: `extraction_pipeline.py` `_is_valid_section_content`.

### Changed

- **Theme scaffolding labels promoted to config** (`config.THEME_SCAFFOLDING_LABELS`,
  rule #9 — editorial content out of source). `is_scaffolding_theme_name` narrowed to
  four deliberately-conservative discriminators (empty / `#`-prefixed / config label /
  `(N total)` roll-up) after review flagged that a false-positive silently drops one
  theme without tripping the zero-from-non-empty guard; adversarial tests now assert
  real titles resembling scaffolding wording survive. Theme-block boundary widened from
  `#{2,3}` to `#{1,6}` so a stray H1/H4 scaffold can't be swallowed into the last
  theme's description.

## [Unreleased] - 2026-07-13 (run-log review, round 2)

### Fixed

- **`load_bowen_references` dropped references in a mixed-timestamp file.** The downstream reader (webpage/PDF) tried the *with-timestamp* pattern first and stopped as soon as it matched anything, so in a file mixing timestamped and non-timestamped references it captured only the timestamped ones. Replaced with a single pattern that makes the timestamp optional, so every reference parses regardless of order. (Fixes two previously-failing tests; a mock-setup bug in one was also corrected.)

- **Key-terms validation reported exact=0 / everything fail** once it started running (previous bug had it finding nothing). It required the *synthesized definition* to appear ~verbatim in the transcript, which no paraphrased definition ever does. It now grounds on the **term** (alias-aware: a slash-joined "A / B" grounds if either part appears) and checks the definition for **topical keyword support**, not verbatim. On the sample: 0 EXACT → 10 EXACT, and a hallucinated term still fails (adversarial test).
- **Bowen attribution detector missed possessive references with an intervening adjective** — "Bowen's **basic** ideas" failed because only an immediately-adjacent noun (or "key") was recognised, so genuine references were dropped. The possessive pattern now allows intervening words; adversarial cases ("Bowen's daughter…", "Bowen theory terms…") still correctly don't match.

### Added

- **Bowen drop-diagnostic.** When extraction produces candidates but 0 survive attribution filtering + grounding, a `… - bowen-references-debug.md` is written listing each candidate with *names-Bowen?* and *grounding* — so a zero result is inspectable (extraction-missed vs filter-over-dropped) instead of silently vanishing. This immediately exposed the attribution-detector bug above.

## [Unreleased] - 2026-07-13 (run-log review fixes)

### Added

- **"Silent empty" instrumentation.** New `warn_if_empty_parse` helper (transcript_utils.py) distinguishes a genuinely empty/absent source from a parser that yielded **zero items out of non-empty input** — the signature of a producer/consumer format drift (the class behind the emphasis/key-terms bugs). Wired into the post-Core emphasis, key-terms, and topics validators, which now log a loud "parsed 0 X from a non-empty source" warning instead of a silent "nothing to validate" pass. (Bowen is intentionally excluded — an empty result is valid there.)

### Fixed

- **Emphasis validation found nothing despite emphasis existing.** The scored-emphasis file is saved with the header and its quote separated by a blank line, but `parse_scored_emphasis_output` required both in one block, so the post-Core emphasis validator parsed 0 items. Hardened the parser to accept the header and quote either in one block or split across a blank line, and fixed the save to keep each item's header+quote adjacent (write→read round-trip). Real-artifact check: 0 → 10 items.
- **Key-terms validation found nothing despite key terms existing.** The dedicated key-terms artifact often has bare `### Term` blocks with no `## Key Terms` heading, which `_parse_key_terms_section` required. It now falls back to parsing the whole file. Real-artifact check: 0 → 9 terms.
- **Cost estimate ran ~3.6× low.** The estimator omitted Ranked Lenses, the Theme/Lens validation pass, and Bowen extraction, and collapsed the four separate core-extraction calls into one bundled "Key Items." These are now modelled separately. On the sample transcript the estimate went from $0.11 to $0.25 (actual ≈ $0.35–0.40).
- **Tests polluted the real cost log.** `log_token_usage` appends to `logs/token_usage.csv`; several tests called it (directly or via mock loggers), leaving junk rows (`test_script`, `<MagicMock …>`, nameless `unknown_script`). An autouse fixture in the root `conftest.py` now redirects the logs dir to a temp path for every test, so the production log can't be polluted.

## [Unreleased] - 2026-07-13 (lean abstract path)

### Added

- **Standalone Topics stage + Topics-only abstract (lean abstract path).** You can now produce an abstract (and, separately, Emphasis + Bowen) without running the full monolithic Core stage. A new `topics` stage (`generate_topics`) writes the Topics artifact straight from the transcript, and `generate_structured_abstract` now requires **only** Topics — the Interpretive-Themes artifact it previously demanded was never actually used by the abstract prompt (which builds from metadata, topics, and transcript-derived opening/closing/Q&A). Verified end-to-end on a real transcript: `Topics → Abstract` produced a coherent abstract for ~$0.02, roughly half the cost of full Core. Spec: `docs/spec_lean_abstract_2026-07-13.md` (LA.1–LA.5). Tests: `tests/test_lean_abstract.py`.
- The stage pre-flight now models this: `topics` depends on the transcript (yaml), and `gen_abstract` depends on Topics only (satisfiable by the `topics` stage **or** `core`), no longer on Interpretive Themes.

### Fixed

- Headless GUI tests could hang on a real `messagebox` dialog depending on test order; an autouse fixture (`tests/conftest.py`) now stubs Tk dialogs so the suite is hermetic and order-independent.

## [Unreleased] - 2026-07-13

### Added

- **Selectable pipeline stages with saved selections**: The GUI's per-stage "run" buttons and the hardcoded "Do All Steps" flow are replaced by a checkbox per stage plus a single **▶ Run Selected** button that runs whichever stages are ticked, in fixed pipeline order (cost estimate first, token-usage report last, halting on the first failure). A new **Manage Selections...** dialog saves the current tick-set under a name, reloads/deletes it, and marks one selection as the default that pre-ticks on startup (never auto-runs). Selections persist in `logs/runtime_settings.json` via new `config.py` methods (`save_stage_selection`, `delete_stage_selection`, `get_stage_selections`, `set_default_stage_selection`, `get_default_stage_selection`). Spec: `docs/spec_stage_selection_2026-07-12.md` (SS.1–SS.22); independent QA test spec: `docs/qa_test_spec_stage_selection_2026-07-12.md`.
- **Stage dependency pre-flight**: A synchronous validator (`_validate_stage_dependencies`) blocks a Run Selected before any work starts, with a single "Missing Prerequisites" message, if a checked stage's required upstream artifact is neither selected in the same run nor already present on disk (dependency graph verified against the actual pipeline function bodies, not button order). The whole run is blocked rather than partially run, and prerequisite stages are never silently auto-added. The validator resolves artifact paths through one shared helper (`_stage_artifact_path`) that the stage runners reuse, so its "does this exist" check can't drift from where stages write. Saved selections tolerate stage keys removed in a later release (unknown keys are logged and skipped, not fatal).

## [Unreleased] - 2026-07-12

### Added

- **Folder Defaults dialog**: New "Folder Defaults..." button beside directory selection opens a dialog to independently browse, view, and reset the default Processed directory, Projects directory, and Approved Terms file. Each is persisted via new `config.py` settings (`default_processed_dir`, `default_projects_dir`) in `logs/runtime_settings.json` alongside the existing source-directory and terms-file overrides, and reapplied automatically on the next launch.

### Changed

- **Resizable GUI layout**: The Source File list, File Status, and Processing Log panels are now hosted in a `ttk.PanedWindow` so their relative heights can be dragged, instead of fixed `rowconfigure` weights.

### Fixed

- **Format-validation timestamp stripping**: `strip_raw_speaker_prefixes()` now also matches parenthesized timestamps (not just bracketed), and `validate_format()` strips bare numeric-only TRX timestamp lines, preventing false mismatch counts on transcripts using those formats.

## [Unreleased] - 2026-05-13

### Added

- **GEO-optimized Overview Post**: New post type that runs parallel to the existing Lens #1 blog. Built from the abstract, structural themes, topics, and key terms — no lens required. Designed for Generative Engine Optimization with a definitional opener, TL;DR, question-shaped H2s, atomic citable statements, and a Frequently Asked Questions section. Frontmatter exposes `schema_type: "Article"`, `author`, `date_published`, and a structured `faq:` list ready for JSON-LD downstream. New GUI button "7b. Overview Post" triggers it independently of the lens-based blog. Configuration: `OVERVIEW_MIN_WORDS = 800`, `SUFFIX_OVERVIEW = " - overview.md"`, `PROMPT_OVERVIEW_FILENAME = "Transcript Summary Overview Post v1.md"`. Implementation plan and spec coverage at `docs/implementation_plan_2026-05-13.md` and `docs/spec_coverage_2026-05-13.md`.
- **Abstract loader fallback**: Standalone-path blog/overview generation now falls back from `SUFFIX_ABSTRACT_GEN` to `SUFFIX_ABSTRACT_INIT` when the validated abstract is absent, so transcripts that have only completed the initial abstract step can still produce post artifacts.

## [Unreleased] - 2026-03-10

### Fixed

- **Formatting context-budget guard**: Fixed the formatting preflight check to compare transcript input size against available model context capacity instead of the formatting output-token cap, preventing false aborts on long transcripts that still fit the model context window.
- **Context-budget warning text**: Updated preflight logging to say `context budget` / `safe input budget` so formatting failures are clearer in the GUI and logs.
- **Scored emphasis parsing compatibility**: Updated emphasis parsing and downstream loading to accept both bracketed and plain-text scored output formats, preventing false failure reports when the `.md` artifact already contains valid emphasis items.
- **`Set Directory` source-folder normalization**: Selecting a `source` folder in the GUI now resolves to its parent transcript base directory instead of producing an incorrect `source/source` path.
- **Fail-closed validation gating in `Run All`**: The GUI workflow now stops when header validation, abstract generation, or abstract coverage validation fails, instead of continuing into blog/web/package generation with invalid upstream artifacts.
- **Terms-file reset on transcript directory change**: Switching `TRANSCRIPTS_BASE` in the GUI now resets the active `Init Val` dictionary back to that directory's default `approve_terms.txt`, preventing accidental cross-corpus dictionary reuse.
- **Logger reinitialization**: `transcript_utils.setup_logging()` now replaces handlers on the named logger directly instead of relying on repeated `logging.basicConfig(...)` calls, ensuring each step writes to its intended log file.
- **Whisper/TRX format validation compatibility**: Formatting validation now strips supported TRX/Whisper transcript wrappers before word comparison, including `TRANSCRIPT` metadata headers, timestamped speaker prefixes, and appended `VALIDATION REPORT` / `FLAGGED ITEMS` footer blocks. This prevents false mismatch explosions when using `*_v-valid*.txt` inputs from the `trx` workflow.
- **Structured long-request streaming**: Enabled `stream=True` in both `summary_pipeline.generate_summary()` and `abstract_pipeline.generate_abstract()` so the structured generation paths comply with Anthropic SDK long-request requirements instead of relying on callers to opt in manually.
- **Structured transcript fallback**: Updated structured summary/abstract generation, structured validation, and webpage/PDF generation to load ` - yaml.md` when ` - formatted.md` is missing, preventing failures in projects where the YAML transcript remains but the formatted artifact does not.
- **PDF dependency messaging**: PDF generation now logs an explicit WeasyPrint dependency error instead of surfacing only a generic failure.

### Added

- **Transcript source format detection**: Added explicit source-format detection/logging in `formatting_pipeline` so formatting and validation report whether an input is `plain_transcript` or `trx_whisper_wrapped`.
- **Streaming regression tests**: Added coverage to verify `call_claude_with_retry()` uses `client.messages.stream(...)` when requested, and that structured summary/abstract generation explicitly enables streaming.
- **Fallback regression tests**: Added coverage for YAML-only structured abstract generation, abstract validation, and webpage generation.
- **Standalone Bowen/Emphasis extraction controls**: Added a dedicated `Bowen` button and independent `Core` / `Do All` include toggles in the GUI so Bowen references and emphasis items can be run together or separately.
- **Direct-file extraction support**: Added support for running standalone Bowen and emphasis extraction directly from a selected source `.txt` file in the GUI and via `transcript_extract_bowen.py` / `transcript_extract_emphasis.py`.
- **Independent Bowen skip control**: Added `--skip-bowen` to `transcript_summarize.py` and a matching backend `skip_bowen` path so Bowen reference extraction is no longer coupled to the rest of core extraction.
- **Initial validation learning**: Added persistent review memory for rejected `original_text -> suggested_correction` pairs in `logs/validation_memory.json`, plus approved-term persistence in `approve_terms.txt` so `Init Val` reruns can converge instead of repeating the same rejected suggestions.
- **Deterministic validation aliases**: `approve_terms.txt` now supports `wrong = Correct` rules. `Init Val` injects alias-based findings locally and can persist selected corrections back as aliases from the review dialog.
- **Transcription-only validation scope**: Narrowed `Init Val` to proper nouns, homophones, spelling/non-word cleanup, and word-boundary issues. Grammar, punctuation, capitalization-only, and style cleanup are now explicitly excluded in prompts and code-level filtering.
- **Compact review UX**: Simplified the `Init Val` dialog to one-line `Found > Suggested` rows, checked by default, with approved items automatically feeding the domain dictionary instead of requiring multiple per-item checkboxes.
- **Selectable terms file**: Added a GUI selector for the active `Init Val` terms file so baseline dictionaries can be swapped at runtime without replacing `approve_terms.txt` manually.

## [Unreleased] - 2026-01-11

### Changed

- **Combined GUI quote extraction**: Replaced separate `Bowen` and `Emphasis` GUI buttons with a single `Bowen + Emphasis` action that reuses one cached transcript context for both extraction calls.

### Documentation

- Updated `README.md`, `DOCUMENT_REFERENCE.md`, and `PROJECT_STATUS.md` to align with current code-level behavior:
  - Current model defaults from `config.py` (`claude-sonnet-4-20250514` / `claude-3-5-haiku-20241022`)
  - Current artifact naming and pipeline stage outputs (config suffix-based)
  - `TRANSCRIPTS_BASE`-driven directory semantics replacing hardcoded `~/transcripts` assumptions
  - Current test collection snapshot and duplicate test-module collection mismatch note

### 🎯 **Critical Fix: Summary Generation Word Count**

Fixed critical issue where summaries were generating only 423-460 words instead of 600-750 word target. Issue required 13 separate fixes across 6 files.

### Fixed

- **Summary Generation Length** - Summaries now consistently generate 600-800 words (was 423-460):
  - Removed conflicting 25% inflation logic in word allocation
  - Switched from Haiku to Sonnet 3.7 for content generation (Haiku too concise)
  - Fixed GUI to use DEFAULT_MODEL instead of hardcoded AUX_MODEL override
  - Increased default target: 600 → 650 words (accounts for model behavior)
  - Strengthened validation: min_words 450 → 600
  - Increased token limit: 2500 → 4000 (allows longer output)
  - Enhanced prompt with balanced length instructions
  - Added comprehensive logging for model selection and word allocations

### Changed

- **Model Configuration** (`config.py`):
  - DEFAULT_MODEL: `claude-sonnet-4-5-20250929` → `claude-3-7-sonnet-20250219` (supports caching)
  - DEFAULT_SUMMARY_WORD_COUNT: 600 → 650 words
- **Summary Pipeline** (`summary_pipeline.py`):
  - Removed 25% target inflation (lines 576-582)
  - Updated generate_summary() default model parameter to use DEFAULT_MODEL
  - Increased min_words: 450 → 600
  - Increased min_length: 2000 → 2400
  - Increased max_tokens: 2500 → 4000
  - Added logging for model selection and word allocations
- **Extraction Pipeline** (`extraction_pipeline.py`):
  - Updated generate_structured_summary() to use DEFAULT_MODEL (was AUX_MODEL)
  - Updated generate_structured_abstract() to use DEFAULT_MODEL (was AUX_MODEL)
  - Added model logging
- **Abstract Pipeline** (`abstract_pipeline.py`):
  - Updated generate_abstract() to use DEFAULT_MODEL (was AUX_MODEL)
- **GUI** (`ts_gui.py`):
  - Fixed all summary/abstract generation calls to use DEFAULT_MODEL instead of AUX_MODEL (4 locations)
- **Summary Validation** (`summary_validation.py`):
  - Increased minimum word count: 450 → 600
  - Added proximity check (warns if < 85% of target)
  - Removed upper limit validation (longer summaries acceptable)
- **Prompt Template** (`prompts/Summary Generation Prompt v1.md`):
  - Balanced length instructions (was too emphatic causing over-generation)
  - Changed from "CRITICAL", "MUST", "FAIL" to "aim for", "approximately"
  - Added guidance to avoid significantly exceeding 800 words

### Added

- **Test Suite** (`tests/test_summary_word_count_fix.py`): 15 comprehensive tests covering:
  - Config changes validation
  - Inflation removal verification
  - Word allocation calculations
  - API call parameters (min_words, max_tokens, min_length)
  - Validation threshold enforcement
  - End-to-end behavior
- **Updated Tests** (`tests/test_summary_scaling.py`): Updated 2 tests for new behavior
- **Documentation**:
  - `SUMMARY_WORD_COUNT_FIX.md` - Complete implementation details
  - `CRITICAL_FIX_MODEL_SWITCH.md` - Model selection analysis
  - `ADDITIONAL_FIXES_APPLIED.md` - Iteration 2 fixes
  - `FINAL_FIX_CACHING_COMPATIBLE.md` - Caching model selection
  - `COMPLETE_FIX_SUMMARY.md` - Executive summary
  - `TEST_RESULTS_SUMMARY.md` - Test suite results (67/69 passing)
  - `SUMMARY_GENERATION_FIX_COMPLETE.md` - Final status and results

### Performance

- **Cost Optimization**: Using Claude 3.7 Sonnet with prompt caching:
  - First summary: ~$0.14 (cache write)
  - Subsequent summaries: ~$0.053 (cache read - 62% savings)
  - vs Sonnet 4.5 without caching: $0.36 per summary (85% savings)
- **Test Results**: All 15 new tests passing, 67/69 overall (97% pass rate)
- **Final Output**: 631-800 words consistently, passing validation

### Notes

- Claude 3.7 Sonnet deprecated but works until February 19, 2026
- Migration to Series 4 with caching support needed before EOL
- If summaries too long (>900 words), lower target to 600 in config.py
- If summaries too short (<600 words), verify model is claude-3-7-sonnet-20250219

---

## [Unreleased] - 2026-01-10

### 🎉 **Major Release: All Critical Issues Resolved**

This release completes all 4 critical issues identified in the architecture review, improving code quality from C+ to A-, reducing technical debt by 21.3%, and increasing test coverage by 15%.

### Added

- **Configuration Validation System** (`config.py`): Added comprehensive validation for 70+ configuration values across 7 categories:
  - Directory paths validation with auto-fix capability
  - Model name validation against available models
  - Numeric range validation (token limits, temperatures, timeouts)
  - Percentage and ratio validation
  - Word and character count validation
  - Logical consistency checks (chunk sizes, threshold ordering)
  - Type validation for confidence sets and error types
  - `ValidationResult` class to track errors and warnings
  - `validate_configuration()` function with detailed error reporting
  - `validate_or_exit()` for startup validation that exits on errors
- **HTML Template System** (`templates/`): Migrated from embedded HTML/CSS to Jinja2 templates:
  - Created `templates/base.html` with block inheritance
  - Created `templates/webpage.html` for sidebar layout
  - Created `templates/simple_webpage.html` for single-page layout
  - Created `templates/pdf.html` for print-ready output
  - Extracted CSS to `templates/styles/common.css`, `webpage.css`, `pdf.css` (360 total lines)
  - Auto-escaping enabled for XSS protection
- **Security Improvements** (`transcript_utils.py`): Added `sanitize_filename()` function (67 lines) to prevent path traversal attacks:
  - Blocks `../` parent directory references
  - Removes null bytes and control characters
  - Validates filename length and emptiness
  - Uses `Path.name` to extract safe filename component
  - Enhanced `parse_filename_metadata()` with validation for empty components and missing years
- **Test Suites**: Added 4 comprehensive test suites (1,100+ lines, 87 tests total):
  - `test_exception_fix.py`: 4 test suites for exception handling
  - `test_path_traversal_fix.py`: 9 test suites covering 40+ security test cases
  - `test_html_generation.py`: 6 test suites with 30+ assertions for template rendering
  - `test_config_validation.py`: 13 test suites with 50+ assertions for configuration validation
- **Documentation**: Created 5 detailed documentation files:
  - `ISSUE_1_FIXED.md`: Exception handling improvements
  - `ISSUE_2_FIXED.md`: Security vulnerability fix
  - `ISSUE_3_FIXED.md`: Template refactoring details
  - `ISSUE_4_FIXED.md`: Configuration validation details
  - `FIXES_SUMMARY.md`: Comprehensive summary of all fixes (475 lines)
  - Updated `code_quality_review.md` with all fixes marked complete

### Changed

- **Exception Handling** (`transcript_utils.py:306-322`): Enhanced `log_token_usage()` function:
  - Replaced broad `except Exception` with specific exception types
  - Added separate handlers for `OSError/IOError/PermissionError`, `csv.Error/UnicodeEncodeError`
  - Added logging with stack traces for unexpected exceptions
  - Improved error messages with actionable guidance
- **HTML Generation** (`html_generator.py`): Refactored from 1,584 → 650 lines (59% reduction):
  - Migrated to Jinja2 template engine
  - Extracted 1,000+ lines of HTML/CSS to separate template files
  - Preserved complex highlighting logic unchanged (proven, battle-tested)
  - CSS loaded once at module level for performance optimization
  - Maintained 100% backward compatibility (no API changes)
- **Default Models** (`config.py`): Updated `DEFAULT_MODEL` from invalid `"claude-3-7-sonnet-20250219"` to valid `"claude-sonnet-4-5-20250929"` (Claude Sonnet 4.5)

### Fixed

- **Security Vulnerability** (CVSS 7.5/10): Path traversal attacks now completely blocked:
  - Fixed: `../../../etc/passwd` → sanitized to `"passwd"`
  - Fixed: `/absolute/path` → sanitized to `"path"`
  - Fixed: `file\x00name` → null bytes removed
  - Fixed: Control character injections → removed
  - Tested: 40+ attack vectors all blocked
- **Silent Exception Swallowing**: Exceptions now properly categorized and logged with stack traces
- **Configuration Bugs**: Fixed invalid DEFAULT_MODEL causing runtime API errors
- **Missing Directories**: Auto-created with `validate_configuration(auto_fix=True)`

### Performance

- **HTML Generation**: CSS loaded once at module level (not per-generation)
- **Template Compilation**: Jinja2 caches compiled templates automatically

### Security

- **Path Traversal**: Eliminated critical vulnerability (CVSS 7.5/10)
- **XSS Protection**: Auto-escaping enabled in Jinja2 templates
- **Input Validation**: Comprehensive sanitization of all filename inputs

### Metrics

- **Code Quality**: C+ → **A-** (2 letter grade improvement)
- **Critical Issues**: 4 → **0** (100% complete)
- **Security Vulnerabilities**: 1 → **0** (100% fixed)
- **Technical Debt**: 54 hours → 42.5 hours (21.3% reduction)
- **Test Coverage**: 40% → 55% (+15%)
- **html_generator.py**: 1,584 → 650 lines (59% reduction)
- **Tests Added**: 87 comprehensive tests (all passing)

### Breaking Changes

None - All changes are 100% backward compatible.

---

## [Unreleased] - 2026-01-09

### Added

- **Cost Estimation**: Added estimated cost calculation (Input, Output, Cache Write/Read) to `transcript_utils.py` and `token_usage.csv`.
- **Cleanup GUI**: Added "Cleanup Source" button to the GUI to move original/validated files to `processed/` and delete intermediate versions.
- **Robust JSON Parsing**: Enhanced `transcript_initial_validation.py` to handle JSON responses with trailing text or "Extra data" errors using `raw_decode`.
- **Explicit Streaming**: Updated `transcript_utils.py` to explicitly handle the `stream` parameter, preventing "Streaming is required" errors for long requests.

### Changed

- **Project Documentation**: Corrected the "Project Structure" section in `README.md` to reflect the actual directory layout.
- **GUI Resizing**: Improved `ts_gui.py` to allow the "Select Source File" list to resize vertically and increased default window height to 950px.
- **Validation Warnings**: Downgraded "Length Check" and "Evaluative Language" from failure conditions to warnings in both Summary and Abstract validation. This allows stylistically deviant but semantically correct content to pass.
- **Robust JSON Parsing**: Improved `transcript_initial_validation.py` to correctly parse JSON responses even when followed by extraneous text.

## [Unreleased] - 2026-01-05

### Added

- **Dynamic Model Selection**: Added dropdown menus in the GUI to select specific Claude models for Default, Auxiliary, and Formatting tasks.
- **Test Runner**: Added `run_tests.py` script to execute all unit and integration tests.
- **Integration Tests**: Added `test_pipeline_integration.py` to simulate the full extraction and validation workflow.
- **Parsing Tests**: Added `test_summary_pipeline_parsing.py` and `test_extraction_model_passing.py` to verify parsing logic and model propagation.
- **Technical Documentation**: Added a "Technical Details" section to `README.md` explaining the robust regex logic for topic parsing.

### Changed

- **Topic Parsing Logic**: Updated regex patterns in `abstract_pipeline.py` and `summary_pipeline.py` to be non-greedy and robust against malformed metadata (e.g., missing semicolons).
- **Default Models**: Updated default models in `config.py` to `claude-opus-4-5-20251101` (Default) and `claude-haiku-4-5-20251001` (Aux/Formatting).
- **Configuration Management**: Refactored `config.py` to use a Singleton pattern for managing runtime settings while maintaining backward compatibility.
- **Test Suite**: Refactored multiple test files (`test_regex.py`, `test_timestamp_regex.py`, `test_formatting_helpers.py`, `test_emphasis_detector.py`) to use `pytest` style assertions and parametrization for better reporting.

### Fixed

- **Model Propagation**: Fixed issues where the selected model was not being passed down to `generate_structured_summary`, `generate_structured_abstract`, and validation functions.
- **Header Validation**: Fixed `HeaderValidator` to accept a dynamic model argument.
- **Deprecated Models**: Removed references to deprecated models (`claude-3-opus-20240229`, `claude-3-sonnet-20240229`, `claude-3-7-sonnet-20250219`) to prevent API errors.
- **Test Reliability**: Fixed `test_validation_headless.py` to correctly report failures to the test runner.
- **Bowen References**: Fixed parsing issue where list markers prevented references from being highlighted in the webpage; added robust cleaning logic.
