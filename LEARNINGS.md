# trans-summary — failure-pattern playbook

This is the project's local failure-pattern log: how *this* pipeline tends to fail, and
the checks that stop it repeating a mistake. The generic pattern catalogue (P1–P18) lives
in `~/.claude/standards/learnings.md` and is authoritative for pattern definitions; this
file holds only the repo-specific instances, checklist items, and the fix log. Keep it lean.

## Patterns most load-bearing here

Pull from the global catalogue; the ones that bite this repo most:

- **P2 — Silent drop between pipeline stages.** A stage returns falsy on failure; a later
  stage or the caller can't tell "produced nothing" from "the call failed."
- **P5 — Sibling LLM/subprocess calls hardened inconsistently.** When one `summarize_transcript`
  / extraction call is fixed, fix every sibling wrapper and every standalone handler in the same change.
- **P6 — Trusting a status/derived path without the artifact.** Any code that decides "this stage
  already ran" must resolve the *exact* on-disk path the stage writes (`config.PROJECTS_DIR /
  base_name / f"{base_name}{SUFFIX}"`) and check it live, never a cached bit.
- **P8 — Dirty/second-run state.** `runtime_settings.json` persists between runs; loaders must
  survive unrelated keys, a stale default pointer, and stage keys removed in a later release.
- **P9 — Token/size caps in summarization** silently truncating real-scale transcripts.
- **P12 — Refactor-dropped side effect.** When collapsing an inlined pipeline into wrappers,
  every step (cost estimate, token-usage report, halt-on-failure, filename enforcement) must survive.
- **P13 — Guard at wrong scope.** A gate (e.g. the `_validated` filename check, or a pre-flight
  block) must guard exactly the steps it's meant to, and sit before `run_task_in_thread`.

## Review checklist (run before merging pipeline / GUI-run-path changes)

1. Each stage wrapper passes the *same* args/models/skip-flags as its standalone handler? (P5)
2. Any artifact-existence check resolved via the single shared path-builder, checked live? (P6)
3. Refactored run loop still does: cost estimate, halt-on-first-failure, token report, filename gate? (P12)
4. Guard chain ordered so no run can bypass the pre-flight block? (P13)
5. Persistence loaders tolerate a dirty file (unrelated keys, stale default, unknown stage keys), and *surface* dropped keys rather than silently ignoring? (P2/P8)
6. Dependency OR-groups match what the consuming stage actually reads (no false-negative that lets a doomed run start)? (P6)
7. **Producer/consumer format contract (P2/P14/P19).** For every LLM stage, does the *saver's* on-disk format exactly match what its *parser/validator/counter* re-reads (headings, blank lines between header & quote, `###` vs `> **`, bold-numbered `**N. Title**` vs `### Header`, verbatim vs paraphrase grounding)? Any parser/validator that can yield 0/zero from a non-empty artifact must call `warn_if_empty_parse` (`transcript_utils.py`) or an equivalent loud warning, never a clean-looking empty pass. Round-trip test on a **real** on-disk artifact (not an idealized synthetic one): save → re-parse → assert count preserved.
8. **Validator pass-on-empty / auto-pass (P7/P9/P1).** Does any gate report success without verifying anything? Watch for: `all(x for x in required)` where `required == []` returns `True`; a coverage/keyword check that auto-passes when it has nothing to ground on (`total_keywords == 0 → covered`); a status flag never counted (a report saved but its PASS/WARN/FAIL verdicts never parsed); and a **transient** failure (no API key / timeout) returning the same sentinel as a genuine absence, silently demoting a required check (P1). Fail closed, keep a retryable failure distinct from "genuinely absent," and count verdicts drift-tolerantly.
9. **A fix must not introduce a new silent drop.** When you narrow/normalize a parse (anchored `re.match` for a segment, a stricter regex, a fail-closed default), re-check the *widest real inputs* — a P19 fix that swaps one silent drop for another is a net loss. Adversarially verify every fix against real data before calling it done.
10. **A green test can verify nothing (test-validity).** "The suite passes" is not "the suite would catch a bug." Three failure modes when adding/reviewing tests: (a) *synthetic-format tests* asserting an idealized shape the real artifact never has — worst case, certifying the buggy shape as canonical (the `### header`-as-theme tests did exactly this); prefer a `tests/fixtures/` real artifact. (b) *vacuous tests* — no `assert` (only `print`/`return`), an assertion over a possibly-empty collection (`assert all([])`-shaped), or asserting a mock's own return value. (c) *unprotected logic* — thresholds, `required=` flags, and fail-closed returns that no test pins. Measure with mutation testing (`mut_harness.py`): if flipping a comparison or a `required=True`→`False` leaves the suite green, that logic is untested. Validators are the highest-value target — they are the layer meant to catch bad output, and scored lowest (9–36%).

## Open risks (found by review, not yet bitten)

- The `_validated` filename gate in `do_run_selected` blocks *any* selection whose source file
  lacks `_validated`, including late-only selections (package/webpdf/bowen_emphasis) that don't
  read the source file. Matches prior `do_all` behaviour and spec SS.10, so not a regression —
  but the gate is broader than the stages that actually consume the raw source file. Revisit if
  users hit spurious "run Init Val first" blocks when re-running only late stages.
- `_load_runtime_settings` resets to `{}` on corrupt JSON, but a *valid* non-dict top-level value
  (e.g. a hand-edited `[]` or string) would `AttributeError` on the first `.get`. Pre-existing,
  not introduced by the stage-selection change.
- ~~**Key-terms WEAK tier is definition-rescuable (P7).**~~ **Resolved** (pre-flight review, same
  session): `validate_key_terms_fidelity` now FAILs any term with `term_ratio < 0.50` regardless of
  definition support, so a paraphrased on-topic definition can no longer rescue an ungrounded term.
  Covered by `test_key_terms_ungrounded_term_with_ontopic_definition_still_fails`
  (`validation_pipeline.py:255`).

## Fix log

Newest first. Format: **Issue → Root cause (Pn) → What would have caught it → Fix → Rule.**

**Through-line for this session:** *producer/consumer format-contract drift that fails silent.*
An LLM stage's prompt/save format and its downstream parser/validator/counter drift apart; the
consumer returns empty / zero / a wrong count and reports **success** instead of erroring. Five of
the six below are instances. In-repo guard: `warn_if_empty_parse` (`transcript_utils.py`), now wired
into the key-terms, topics, and emphasis validators.

---

**Real-run audit — advisory validators could be fooled by grounded-but-wrong content (2026-07-15).**
- Issue: re-running the deterministic validators on a *real* run in both directions found three false-PASS gates and a crash. Key-terms rated a real term EXACT when its definition was swapped to describe a *different* transcript concept (def-support 0.87). Emphasis accepted a quote with a verbatim opening and a fabricated tail. The abstract shipped a fabricated researcher name ("Luciano Malorni") into the published HTML with nothing checking it. `_highlight_html_content`/`format_ref_list` crashed on 2-tuples after loaders moved to 3-tuples.
- Root cause (P7 + P19 + P2): each grounding check verified *presence of a proxy in the transcript*, not *correctness of the derived field*. Def-support measured overlap with the WHOLE transcript (any on-topic text scores high); emphasis matched only the first 15 words (the tail was never read); no check existed for abstract name grounding at all; and a producer/consumer tuple-arity contract drifted (3-tuple producer, 2-tuple consumer) with a stale shadowing copy of the formatter.
- What would have caught it: an adversarial "looks-right-but-wrong" input per grounding check (swapped-but-on-topic definition; verbatim-head + fabricated-tail quote; a fabricated proper name) — verified against the *real* artifact, not a synthetic ideal; a round-trip/arity test on the tuple contract.
- Fix: added LOCAL grounding for key-term definitions (`_best_local_grounding`, window around the term; valid ≥0.54 vs swapped ≤0.13); emphasis now probes head AND tail and returns a real bool; `find_ungrounded_names` advises on abstract names absent from source (fuzzy-tolerant of ASR spelling); both highlight consumers tolerate 2-/3-tuples and reuse the correct formatter; Bowen refs deduped; five call sites given named loggers. 18 real-artifact/adversarial/edge tests (`tests/test_validator_gate_hardening.py`, fixtures in `tests/fixtures/where_roots/`). Tier thresholds promoted to `config.*`.
- Rule: a grounding check must verify the *derived field itself*, not that some proxy exists somewhere in the source — keep a hard floor on the verbatim part and localise the paraphrase check; and always adversarially test the "grounded token, wrong content" case against a real artifact.

**Test-validity audit — the green suite verified little of the validator logic (2026-07-15).**
- Issue: critical bugs kept surfacing despite 300+ passing tests. Mutation testing of the audit's bug-prone functions caught only **33% of injected faults overall, 9% in `summary_validation`**; `required=True`→`False`, topic-threshold flips (`>=10`→`<10`), and a fail-closed `return False`→`return True` all left the suite green.
- Root cause (test-validity / P-new): the suite is dominated by *synthetic* tests (35 of 60 files; only 1 reads the real KCFC theme fixtures) and several *vacuous* ones (no assert / assert-on-empty). Historical bugs were each pinned by a specific contract test (all A1–A12 enforced), but the surrounding validator logic — thresholds, required/optional flags, coverage math — was unprotected, so the *next* bug in that neighborhood was invisible too. Two tests were additionally broken: one crashed before asserting (`unittest.mock` unimported), one never ran (mis-indented into another method).
- What would have caught it: mutation testing as a routine gate; a fixture-provenance check (real artifact vs idealized shape) on every parser/validator test.
- Fix: revived/repaired the 2 broken tests; added `tests/test_validator_logic_hardening.py` (15 tests) pinning the surviving decision points. Result: `summary_validation` 9%→28%, `abstract_validation` 36%→50%, `validation_pipeline` 24%→27%. Method + full survivor lists: `TEST_VALIDITY_REPORT.md`, `mut_harness.py`, checklist item #10.
- Rule: measure test *validity* (mutation), not just presence (coverage); pin thresholds and `required=` flags explicitly; never assert an idealized format a real artifact lacks.

**Multi-agent P19 contract audit — 12 findings across 3 clusters (2026-07-14).**
- Issue: a fan-out audit (one agent per LLM pipeline step, each verified against the **real KCFC artifacts** + an adversarial refutation pass) found 12 confirmed producer/consumer contract-drift bugs the happy path never surfaced.
- Root cause (P19, + P7/P1/P2): three recurring shapes — (a) **theme parsers gated on `###` first**, capturing scaffolding headers as themes and collapsing the real bold-numbered `**N. Title**` blocks (structural 1-of-3, interpretive 2-of-7 returned) [A1–A3]; (b) **validators reporting PASS on empty/zero** — `all([])==True`, `total_keywords==0 → covered`, header verdicts never counted, and a transient purpose-extraction failure demoting a required check [A5/A9/A10/A11]; (c) **parsers reading an abandoned format / a proxy accepted ungrounded** — single-group `re.findall` dropping the body, `re.match` truncating multi-segment ranges, the highlight verifier reading a dead quote format, and `top_lens` accepted without matching a generated lens [A4/A6/A7/A8/A12].
- What would have caught it: round-trip tests on **real** artifacts (not synthetic ideals); the P19/pass-on-empty checklist items above; adversarially verifying each fix against the widest real input.
- Fix: three shared helpers to stop re-drift — `parse_bold_numbered_theme_blocks` + `is_scaffolding_theme_name`, `count_header_verdicts`, and `config`-based editorial lists (`THEME_SCAFFOLDING_LABELS`, `ABSTRACT_CONCLUSION_PATTERNS`); fail-closed coverage/purpose validators; `_top_lens_is_grounded`; corrected range/body/word-count parsers. 40 contract tests (`tests/test_theme_parsing_contract.py`, `tests/test_validator_pass_on_empty_contract.py`, `tests/test_audit_medians_contract.py`), all on real formats. Two-pass `learning-qa` review caught 2 HIGH regressions the first pass introduced (an ungrounded-lens exhaustion fall-through; an anchored-`re.match` new silent drop) — both fixed. Full detail: CHANGELOG.md + TODO.md (A1–A12).
- Rule: audit the whole *class* against real artifacts, not one instance; and every P19 fix must be adversarially re-checked so it doesn't swap one silent drop for another.

**Emphasis round-trip: blank line between header and quote → 0 parsed.**
- Issue: `validate_emphasis_items` parsed 0 quotes from a non-empty `emphasis-scored.md`; validation silently passed on nothing.
- Root cause (P2/P14): saver wrote the header and quote as two blocks separated by a blank line; `parse_scored_emphasis_output` split on blank lines and required header **and** quote in the *same* block, so every item split apart and was dropped.
- What would have caught it: a save→re-parse round-trip test asserting `len(parsed) == len(saved)`; `warn_if_empty_parse` on the 0 result.
- Fix: saver keeps header+quote in one block (single `\n`); parser carries a `pending_header` so a header block followed by a quote block still pairs (`transcript_utils.py`, `extraction_pipeline.py:663`).
- Rule: the format a stage writes and the format its parser reads are one contract — change both together and prove it with a round-trip test.

**Key-terms parser required a `## Key Terms` heading the artifact lacks → 0 terms.**
- Issue: `validate_key_terms_fidelity` found 0 terms and logged a clean "No key terms found"; the real `key-terms.md` was full of `### Term` blocks.
- Root cause (P3/P14): `_parse_key_terms_section` only looked inside an `extract_section(content, "Key Terms")` window; the dedicated artifact has no such top-level heading.
- What would have caught it: parsing the actual on-disk artifact in a test (not a synthetic one with the heading); `warn_if_empty_parse`.
- Fix: fall back to the whole content when the section is absent (`validation_pipeline.py:169`).
- Rule: parse the artifact the producer *actually writes*, not an idealized shape; test against a real sample.

**Key-terms validator required verbatim definition grounding → 100% fail.**
- Issue: every valid term scored FAIL because the synthesized (paraphrased) definition never appears verbatim in the transcript.
- Root cause (P7, inverted): grounding proxy misaligned — it verified the paraphrase verbatim instead of the term.
- What would have caught it: an adversarial/real-pair test where a genuine term has a paraphrased definition and must **not** fail.
- Fix: ground on the TERM (alias-split on `/`, best matching part) and check the definition for topical keyword support via `_keyword_grounding_ratio`, never verbatim (`validation_pipeline.py:255`).
- Rule: don't demand verbatim grounding of a field that is a model paraphrase; ground the verifiable field, topic-check the synthesized one. A follow-up hardening (same session) FAILs any term with `term_ratio < 0.50` so definition-only support can't rescue an ungrounded term.

**Bowen attribution detector missed "Bowen's <adj> ideas" → valid refs dropped.**
- Issue: real Bowen-attributed passages ("Bowen's basic ideas…") failed the filter and vanished.
- Root cause (P3/P2): possessive regex only matched an immediately-adjacent noun (or "key"); an intervening adjective broke it, and the drop was silent.
- What would have caught it: table-driven positive/negative cases for the detector; a drop diagnostic on a 0-result.
- Fix: allow up to two intervening words (`bowen'?s\s+(?:\w+\s+){0,2}(?:ideas?|…)`); write a per-candidate drop diagnostic when 0 survive (`extraction_pipeline.py:400`, `_write_bowen_drop_diagnostic`).
- Rule: a matcher that silently excludes needs both positive/negative tests and a visible "here's what I dropped and why" path.

**Bowen `num_found` counter matched a format the saver never writes → "Found 0".**
- Issue: log said "Found 0 Bowen references" while the file held real references.
- Root cause (P14/P2): counter used `^\s*>\s*\*\*` but `_format_bowen_refs` emits `### Concept [ts]\n> "quote"` — the old pattern matched nothing.
- What would have caught it: asserting the counter against `_format_bowen_refs` output (now `tests/test_keyterms_bowen_fixes.py::test_bowen_reference_count_matches_saved_format`).
- Fix: count `^###\s` concept headers (`extraction_pipeline.py:818`).
- Rule: any count/metric derived by regex over a saved artifact must be tested against the *actual* formatter output, not an assumed shape.

**Stale GUI runtime nearly produced a false "the fix doesn't work" verdict.**
- Issue: fixes were correct on disk but the long-running Tk process kept serving old code; re-verifying looked like the fix had failed.
- Root cause (P16): logic runs from memory in a long-lived process; a source edit doesn't take effect until the process is actually restarted.
- What would have caught it: probing the running instance (restart, or confirm the new code path is live) before concluding anything about correctness.
- Fix: restart the GUI process to load the edited modules before judging behaviour.
- Rule: "edited + still looks broken" means "wrong/stale instance" until proven otherwise — restart and re-run before touching already-correct code.
