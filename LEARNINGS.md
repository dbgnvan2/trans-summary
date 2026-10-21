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
11. **Output inside input (P39).** Does any archive/export/report write under the directory or glob it reads (`logs/`, a project dir)? Is the set zipped/deleted exactly the list enumerated? Do the GUI and CLI share one implementation?

## Open risks (found by review, not yet bitten)

- The `_validated` filename gate in `do_run_selected` blocks *any* selection whose source file
  lacks `_validated`, including late-only selections (package/webpdf/bowen_emphasis) that don't
  read the source file. Matches prior `do_all` behaviour and spec SS.10, so not a regression —
  but the gate is broader than the stages that actually consume the raw source file. Revisit if
  users hit spurious "run Init Val first" blocks when re-running only late stages.
- ~~`_load_runtime_settings` non-dict JSON~~ — fixed by review C1 (`config.py`, `isinstance` reset).
- Judge disk cache (D2, 2026-10-11): a version bump re-keyed entries and dropped flags — fixed
  2026-10-12 (`_flagged_any_version`). The "flagged" marker can still be evicted by the 2000-entry cap,
  after which a PASS for that file is stored; the advisory blog-grounding check has no two-PASS rule.
- ~~**Key-terms WEAK tier is definition-rescuable (P7).**~~ **Resolved** (pre-flight review, same
  session): `validate_key_terms_fidelity` now FAILs any term with `term_ratio < 0.50` regardless of
  definition support, so a paraphrased on-topic definition can no longer rescue an ungrounded term.
  Covered by `test_key_terms_ungrounded_term_with_ontopic_definition_still_fails`
  (`validation_pipeline.py:255`).

- ~~**Quote typo tolerance credits real word changes (P7, review 2026-10-09).**~~ **Resolved**
  same session: J8 first accepted any one-letter difference in a 4+ letter word, so would/could,
  were/where, than/then swaps passed the blocking `verbatim_quotes` check. Now only a corrected
  one-off doubled-letter typo counts (`_doubled_letter_typo`: transcript spelling occurs once).
  Rule: a tolerance added for one real typo must be tested against real-word near-misses (P7),
  not only against a far-apart word. Covered by `test_j8d_adversarial_real_word_changes_fail`.

- ~~**Archive Logs deletes log files that are still open (P2/P39, found in CAPTURE 2026-10-09).**~~
  Fixed the same day: `archive_logs` enumerates before creating its own log file, and unlinks with a
  per-file guard that logs "removed N of M" plus the files it could not remove
  (`tests/test_archive_logs.py::test_archive_does_not_include_its_own_log`,
  `::test_archive_reports_originals_it_could_not_remove`). Still open: a line another live handler
  writes between the zip and the unlink is lost (a few lines at most).

- **Theme JSON has no reader yet (ST, pre-flight review 2026-10-14).** The version-2
  `*-themes.json` holds `rationale` (not for publication), and no gate or test checks that
  the `.json` agrees with the `.md` after save. An `OSError` writing the JSON leaves the
  previous run's `.json` next to a new `.md`. Harmless while every reader uses the `.md`.
  Before phase 2 switches readers to the JSON: exclude `rationale` from every reader by
  allowlist, and have the gate check that the `.json` and `.md` agree (or regenerate the
  `.md` from the `.json`).

- ~~**A line removed whole excused every mark on it (P7/P2, learning-qa 2026-10-20, commit 1
  of `docs/plan_removal_open_items_2026-10-20.md`).**~~ Fixed before the commit: the cut
  left "1975." alone on its line, `_EMPTY_LINE` read it as a list marker and dropped the
  line, and the deletion check let the dropped line's marks excuse the number, so an
  unflagged number went with no record. A dropped line now excuses only the marks at its
  start. Rule: an allowance for a removed unit covers what belongs to the unit, not what a
  cut left on it; and a test grid must vary what follows the cut, not only what precedes
  it (P33). Covered by `test_rm1g5_number_left_alone_on_dropped_line_refused`. Still open:
  the allowance is counted from the removed list, not from what left the text (TODO.md).

- ~~**The FAQ edit and the check shared one flat set of cut parts (P2/P26, learning-qa
  2026-10-20, commit 2 of `docs/plan_removal_open_items_2026-10-20.md`).**~~ Fixed before
  the commit: a part cut from the body only because it shares a sentence with a name
  ("Bowen moved to Washington, D.C." before "Zed Example joined him there.") went alone
  from an FAQ answer, where it is a whole sentence without the name, and the check passed
  it because it read the same set. The check also compared FAQ sentences as one count
  over all answers, so two answers swapped between questions passed. Both now read which
  parts were cut together and why (`_faq_goes`), and FAQ items are compared one by one.
  Rule: when an edit and its safety check both work from one summary of the change, the
  check cannot see what that summary drops; give it the structure (groups, reasons,
  items), not a flattened set. Covered by
  `test_rm1e2_part_split_off_with_name_stays_in_answer` and
  `test_rm1e2_faq_items_compared_in_order`. The first fix keyed "cut only for a name" on
  one reason string, so the second review found the sibling that reaches the same state
  by another path (the name only in the label, RM1.b.2), and a regression for a name
  sentence of three parts. Rule: classify by the property that matters (is the name in
  this part's own words?), not by the reason one code path wrote. Covered by
  `test_rm1e2_name_only_in_label_sentence_stays_in_answer` and
  `test_rm1e2_run_of_cut_sentence_with_name_goes_from_answer`. The third review found
  the same mistake one level down: "cut for its own flag" was looked up by a part's
  text, and the same text was cut for a claim on another line. Rule: a fact about one
  place (this part of this sentence) is keyed by that place, never by text that can
  occur twice. Covered by
  `test_rm1e2_part_cut_for_itself_elsewhere_is_still_a_rider_in_answer`. It also found
  that undoing YAML escapes on both sides of a comparison changed the body side, which
  is markdown ("C:\temp" lost its "\t"). Rule: undo a format's escapes only on the text
  written in that format; to match text whose format is unknown, compare against each
  reading. Covered by `test_rm1e1_body_sentence_with_backslash_copy_listed`.

## Fix log

Newest first. Format: **Issue → Root cause (Pn) → What would have caught it → Fix → Rule.**

**Through-line for this session:** *producer/consumer format-contract drift that fails silent.*
An LLM stage's prompt/save format and its downstream parser/validator/counter drift apart; the
consumer returns empty / zero / a wrong count and reports **success** instead of erroring. Five of
the six below are instances. In-repo guard: `warn_if_empty_parse` (`transcript_utils.py`), now wired
into the key-terms, topics, and emphasis validators.

---

**A warm review passed fixes that a cold one broke (2026-10-19, RM cold sweep).**
- Issue: the RM change shipped with an in-session learning-qa pass and 5 fixes (F1–F5), not re-reviewed. A cold sweep on another machine found 17 more, including a double cut that deleted an unflagged sentence, a regex that could hang the run, and F5 clearing the record that F3 had added. The first round of cold fixes then needed a third round: the uncertain-split rule missed most abbreviations and made a kept name fail the stage, and silencing a child script lost the list on Ctrl-C.
- Root cause: P26/P27. Each fix was checked against its own finding only. Interactions (F3 vs F5; a claim rule applied to name flags; a print moved from child to parent) were not checked, and some tests could not fail (a fake writer that raised before writing; a timing assert after a call that hangs).
- What would have caught it: re-sweeping every fix commit with a reviewer that did not write it, and a mutation check per fix (remove the fix, see the test fail).
- Fix: commits 11ef191, 347400b, b1a8b78 on `fix/rm-cold-sweep-2026-10-19`; every new test was run against the code before its fix.
- Rule: a fix is unreviewed code. For each fix, ask which other rule or exit path it changes, and prove its test fails without it. A test of a possible hang runs in a child process with a timeout.
- Miss rate (csdp calibration): cold sweep 17 findings on a range the warm pass had swept; re-sweep of the cold fixes 9 more.

**Rounds of tuning a check that did not need to block (2026-10-19, WO).**
- Issue: after the severity step (JS), a further plan (NQ) proposed $8.5–11.5 of calibration to make the step downgrade minor flags. The user asked why it was taking so long. Shown what the flags were, they chose to have faithfulness warn and never block.
- Root cause: each round (confirmation CF, speaker rule SA, severity JS, then NQ) took "a faithfulness flag blocks" as fixed and worked to make the block accurate. Nobody asked whether a block was needed. The entity check already blocks invented names, and the hand labels showed 17 of 29 flags were wording or order and 1 was badly wrong.
- What would have caught it: showing the user, with the first hand-labelled sample, what the check was blocking, and asking "block or warn?" before building a classifier to decide.
- Fix: WO (`docs/plan_warn_only_2026-10-19.md`): flags warn with a % score and the claims listed; generation still revises them; the prompts forbid outside facts.
- Rule: before making a check accurate enough to block on, show the user a sample of what it blocks and ask whether it should block at all.

**The severity step passed every ship test and changed no draft outcome (2026-10-19, JS).**
- Issue: the JS severity step was built so that runs fail only on WRONG content. In the JS6 calibration it downgraded 0 of 12 NOT QUITE RIGHT flags in fresh summary drafts and 3 of 90 in the review set; 9 of 12 drafts failed both before and after.
- Root cause (P33, checked along one axis): the ship rules (b, c, d) tested only that no WRONG claim is downgraded. None tested that NOT QUITE RIGHT flags are downgraded, which was the point of the change. The policy line "If you are unsure, answer WRONG" makes the first vote WRONG in nearly every case (22 of 22 draft judgements), and a first WRONG vote is final.
- What would have caught it: a pass rule for the intended effect written into the plan, e.g. "at least half of the hand-labelled NOT QUITE RIGHT draft flags are downgraded". The hand labels and the f-NQR set were already there to measure it.
- Fix: none to the step yet. It ships because it is safe, and the report (`docs/calibration_judge_severity_2026-10-19.md`) states the small effect. Loosening the policy is an open decision in `TODO.md` (2026-10-19).
- Rule: a change that relaxes a gate needs a pass rule for the intended effect as well as for safety. A safety-only test passes a change that does nothing.

**The name check read every generated heading as an invented name (2026-10-15, HN).**
- Issue: in runs 9 and 10 the entity check flagged "Closing Advice", "Final Reflections", "Multigenerational Roots" and five other overview/blog headings, and "On June" (from "On June 25, 2021"), as names absent from the source; each cost a faithfulness revision.
- Root cause (P7, wrong proxy): the check treated "Title-Case and not in the source" as "a name". Review F2 extended it to headings, where every word is capitalised and the model chooses its own words, so absence from the source says nothing about whether a span is a name. The date came from the filename metadata, which holds "2021-06-25", not "June".
- What would have caught it: running the F2 change over real overviews and blogs checked against a source that lacks their heading words (the cross-talk set in `docs/calibration/2026-10-14_heading_names/`): 36 phrases were flagged there: 35 concepts or headings and one first name with an ordinary word ("Nick Today").
- Fix: in headings and labels, an ungrounded run counts only when it looks like a name: a non-English word, a given name that is not a word, or two given names or surnames that are words (public-domain lists in `data/`); a span of only month/weekday words is a date. Measured old against new on runs 1–10: same-talk flags 1 → 0; 4,824 of 4,900 made-up people written as headings still flagged.
- The first version looked only at a small given-name list. The learning-qa review measured it letting 6.3% of made-up name pairs through and making the check looser when that list was missing; both were found by testing the misses, not the hits.
- Rule: a lexical check's signal must separate the classes it claims to separate. Before widening or loosening a check, run it on real samples of the text it will see, and measure what it now lets through as well as what it stops flagging.

**Checks held the output to a stricter bar than a person would, so runs kept stopping (2026-10-14, RS).**
- Issue: across end-to-end runs 4–8, every stage failure after the faithfulness fixes came from checks a careful person would wave through: one dropped "that," in 12,000 words stopped Format and blocked four publish stages; summaries of 580 and 562 words failed a 585-word floor; abstracts of 266–274 words were retried against a 249 limit; a retry for one flagged overview sentence rewrote the whole overview and made a new claim each time.
- Root cause: limits written as hard guards (raise after N tries) where they were really targets, and a retry that regenerated the whole artifact instead of fixing what was flagged. Each fix tightened a check; none asked whether failing the run was the right outcome.
- What would have caught it: asking, for each check, "would a person reject this output?" and "does a retry converge or start over?". The measurement answered the second: one retry passed about equally often either way (10 of 11 each), but revising changed 1–5% of a draft and rewriting 44–79%, so a rewrite can bring a new problem anywhere. The first measurement also ran the overview on the wrong model (the script did not set the main model as the e2e runner does); check the model line of a measurement before reading it.
- Fix: soft word limits (keep the closest near miss with a warning, `word_limits="soft"`, within `SOFT_WORD_LIMIT_TOLERANCE`); Format restores the source's words for differences in ordinary text; retries revise only the flagged sentences (`_revise_flagged`). Faithfulness stays strict. The review then found the soft path's own holes: a held reply lost on a later API error, no outer bound (a 56-word non-answer kept as an 800-word overview), and unjudged drafts competing as "best".
- Rule: a length or format target is not a guard; keep a near miss and warn. Retry by fixing what the check flagged, not by starting over. When softening a check, bound it and keep every other check hard.

**A prompt change based on a guess about the model did the opposite (2026-10-14, SL3).**
- Issue: summaries for long talks came in just under the stated 585-word floor. I guessed that stating the floor pulled drafts down toward it, removed it from the prompt and lowered the accepted floor.
- Root cause: an untested belief about model behaviour. Measured, the drafts without the stated minimum were shorter (490–608 words against 539–636).
- What would have caught it: measuring the prompt change before relying on it, which is what caught it here (nine drafts per prompt, about $0.70 each).
- Fix: the prompt keeps asking for 585–780; the check accepts from 553 (`docs/calibration_summary_floor_2026-10-14.md`).
- Rule: measure a prompt change against the current prompt on real inputs before shipping it; a plausible mechanism is not evidence.

**Theme layout drift needed a fix each run until the format was enforced (2026-10-14, ST).**
- Issue: the theme stages returned free-form markdown and every reader parsed it with patterns. In five days the model produced seven layout variants (a list layout, new labels "Summary" and "Closing paragraph:", closing notes read as evidence or published); each needed its own parser fix (T1, TM, TE, TD, TP).
- Root cause (P19): the format contract lived only in the prompt's wording, which the model follows loosely, and the prompts themselves asked for a closing paragraph after the list, so a note in some new form came back every run.
- What would have caught it: treating repeated parser fixes for one stage as a sign the boundary needs an enforced format, not another pattern.
- Fix: the stages return JSON checked against a schema (`output_config.format`) plus local checks the API does not enforce; the pipeline writes the markdown in one layout, and the closing note goes in a `rationale` field that is never rendered. A round-trip test over generated and real objects found one parser bug: a `^` anchor searched on a slice matched the slice's start, which is not a line start.
- Rule: when a model output is parsed, enforce its format at generation (schema) rather than widening the parser after each drift. Search with `pattern.search(text, pos)`, not on `text[pos:]`, when `^` must mean a real line start. (P19)

**Problems that only a full run shows (2026-10-13, end-to-end run, E2E).**
- Issue: one headless run of all 16 stages on three public talks found five problems the unit tests and earlier fixes had not: the abstract was given figures (coverage percentages) the transcript does not state, then blocked for stating one; a theme named a person the speaker never named; the emphasis reply ran past its token ceiling on a long talk; the GUI's Init Val ran without the approved-terms file; and the test suite wrote the real settings file.
- Root cause: fixes were checked one stage at a time with tests and calibrations, and the user's GUI run was the only full run, so each round found one new failure. Two were design mismatches (a generator given data its judge cannot check; a cap set before thinking models), one was a path rule, and one was a setter that reset a redirected path (P8).
- What would have caught it: running every stage end to end on real public talks before handing a change over. `scripts/e2e_run.py` does that and reports every failure in one list.
- Fix: E2E1–E2E5 (CHANGELOG). Tests: `tests/test_e2e_fixes.py`, `tests/test_e2e_runner.py`.
- Rule: a change is not done until a full run passes. Give a generator only what its judge can verify. A setter must not reset paths it does not own. (P6, P8, P9)

**A valid empty answer stopped Init Val (2026-10-13, real run, IV).**
- Issue: for a transcript chunk with nothing to fix, the model replied with a fenced empty list, "```json\n[]\n```" (14 characters). `call_claude_with_retry` rejects any reply under 50 characters by default, retried three times, and the run stopped at Init Val. The same transcript and model passed the day before because that chunk had findings.
- Root cause (P7/P1): a generic sanity check (minimum reply length) applied to a prompt whose correct answer can be very short. F13 fixed the same thing for a "YES/NO" reply, but the other callers on the default were not checked. The v1 validator also returned zero findings for a reply with no JSON list; the 50-character minimum hid that for short replies only.
- What would have caught it: a test that runs the real `call_claude_with_retry` with the shortest valid reply. The existing tests replaced the whole function, so the length check never ran.
- Fix: `config.MIN_REPLY_CHARS_JSON_LIST` (2) on both Init Val calls; v1 now stops on a reply with no list. A test lists every direct call left on the 50-character default and why its valid reply is always long; it does not see wrappers that pass `min_length` through, or explicit minimums still too high for an empty answer (the Bowen filter and extraction calls, open in TODO). Tests: `tests/test_init_val_empty_reply_iv.py`.
- Rule: a response check must allow the shortest valid answer for that prompt ("[]", "NO", an empty section). When one caller is fixed for this, check every caller of the same function, including through wrappers. A test of a validator must run the check it relies on, not replace it. (P7, P5)

**A rule for trailing notes cut real content, and its warning was mostly noise (2026-10-13, caught in review, TD).**
- Issue: to stop the model's unlabeled closing note being published with the last theme, the first rule dropped every paragraph after the last field's first one. That would also cut Key evidence bullets separated by blank lines, or a two-paragraph Description. Its warning fired 51 times on 65 real files, 45 of them on a bare `---` line, and repeated on every parse (7+ call sites).
- Root cause (P2/P19): the rule was written from the one example ("prose after a field"), not from the field's shape. The warning was placed in a parser that many callers run.
- What would have caught it: synthetic cases for each field shape (bullets with blank lines, multi-paragraph prose) before measuring on real files, and counting the warning on the real corpus.
- Fix: drop later paragraphs only after a theme-level meta field (one paragraph in all real files); keep Description and Key evidence whole; ignore `---`; report once per file from the gate (`trimmed_theme_notes`). Tests: `tests/test_theme_display_td.py::test_td2_multi_paragraph_last_field_is_kept`, `::test_td4_gate_reports_left_out_notes_once`.
- Rule: a rule that removes text must be tied to a structural cue, not to "anything after X". Report from the one place that acts on the result, not from a parser shared by many callers. (P2, P19)

**An exclusion list let non-evidence fields reach the theme judge (2026-10-13, TM/TE).**
- Issue: theme evidence was "every field except Description and the meta labels". A renamed meta label ("Nested under structural theme(s)", 21 of 25 files) and document-level paragraphs read into the last theme ("Summary paragraph") were sent to the judge as evidence.
- Root cause (P19): the set of fields was defined by what to leave out, so every new or renamed field was sent by default, with no signal.
- What would have caught it: a contract test that every field the judge reads in the real fixtures is classified. It must scan the parsed blocks (not raw text, which missed indented fields), and the fixtures must include a file with each field shape; the TE files were not fixtures until this fix.
- Fix: an allowlist of evidence labels (`config.THEME_EVIDENCE_LABELS`), the known non-evidence labels, and an unknown field still sent but reported once per file by the gate (`transcript_utils.unclassified_theme_fields`). Test: `tests/test_theme_evidence_te.py::test_te_every_real_fixture_label_is_classified`.
- Rule: when a model's output fields feed a judge, classify every field explicitly and test the classification against real files. A field nobody classified should be loud, not silently included or excluded. (P19)

**Tests for a new rule passed with the rule switched off (2026-10-12, caught in review, SW).**
- Issue: the first SW tests (changed first or last word in a quote) passed with `_stray_edge_words` replaced by `lambda *a: 0`. In one, the substitute word lay outside the alignment window; in the other, order-keeping alignment already failed it. The first version of the rule also missed a changed lead that aligned as two short blocks or three words, and rejected omissions marked with "...".
- Root cause (P7): adversarial tests checked the end result ("fails") without checking that the input passed before the change, so they never exercised the new code.
- What would have caught it: a mutation check, run as part of each adversarial test: switch the rule off, assert the input passes, then switch it on and assert it fails.
- Fix: each SW adversarial test asserts coverage 1.0 with the rule patched off and below 1.0 with it on (`tests/test_swapped_word_quotes_sw.py::_caught`). The rule takes the lead or tail as a run of blocks up to 4 words and exempts ellipsis-marked omissions. Measured on 835 real quotes: same 5 real changes caught, nothing else.
- Rule: an adversarial test for a new check must show the input passed without the check. Otherwise it may test nothing. (P7)

**Context added to a claim hid a name from the "already judged" check (2026-10-12, caught in review, FQ).**
- Issue: FQ attaches "[in answer to: <question>]" to an answer's first sentence. `extract_claims` judges an ungrounded heading name on its own only `if not any(name in c for c in claims)`. A fabricated name in a question heading then counted as already covered, inside a bracket the judge is not told to check.
- Root cause (P2/P7): a coverage check written for claim text, applied to claim text plus context.
- What would have caught it: an adversarial test with a fabricated name in a question heading.
- Fix: the check compares against the claim body (`faithfulness_judge._claim_body`). Test: `tests/test_speaker_attribution_sa.py::test_fq_name_in_question_heading_is_still_judged`. The same review moved the SA rule off the chunk windows: a window sees a third of the recording, its "entailed" is final, and the rule's role and stance tests need the whole source (`test_sa_chunk_windows_use_base_prompt`).
- Rule: when you add context to a unit of judgement, check every later test that asks whether something is already covered by that unit. (P2, P7)

**Changing what the judge reads silently cleared old flags (2026-10-12, caught in review, SA).**
- Issue: SA adds a note to the judge's source when a transcript has no speaker labels. The D2 "flagged" marker was keyed on `artifact-sha:source-sha:model`, so the new source text re-keyed every unlabeled project's entries. An artifact flagged before the change needed one PASS instead of two, and that PASS was stored.
- Root cause (P6/P8): a safety marker keyed on more than the thing it protects. The flag protects an artifact's text; the source text was in its key by accident.
- What would have caught it: a dirty-state test that flags an artifact, changes only the source text, and asserts it still needs two PASSes.
- Fix: flags match on artifact sha + model (+ kind), ignoring the source sha and logic version (`release_gate._flag_identity`). Test: `tests/test_speaker_attribution_sa.py::test_sa6_flag_survives_source_note`.
- Rule: key a safety marker on exactly what it protects. Every other field in its key is a way to lose it. (P6, P8)

**PASS-only judge cache would have turned a re-run into an override (2026-10-11, caught in review).**
- Issue: to stop a false FAIL being replayed from the judge disk cache ("sticky FAIL"), D2 first stored only PASS verdicts. learning-qa found the reverse problem: the judges (Sonnet 5.5) take no temperature and vary per run, so a real fabrication judged FAIL could be re-run until one PASS came up, and that PASS was then stored and replayed for good. The first fix missed 35 FAIL entries already in the real cache, written by the old code.
- Root cause (P1/P8 with a non-deterministic judge): a cache that keeps only one outcome of a varying check drifts toward that outcome; a format change to cached state ignored entries written before it.
- What would have caught it: a test sequence across cold processes (FAIL, PASS, next run) and a dirty-state test with an old-format FAIL entry on disk, asserting what is *written*, not only what is re-judged.
- Fix: a file once judged FAIL (marker or old FAIL entry) never gets a stored PASS, and a run passes it only when two judgements in a row pass (`release_gate._is_flagged`, `_judge_flag_aware`). Tests: `tests/test_judge_cache_pass_only_d2.py`.
- Rule: when caching the verdicts of a non-deterministic judge, ask which way repeated runs push the cached state; asymmetric caching is an override path unless the opposite verdict is remembered. (P1, P8)

**Framing-rule change to the faithfulness judge — tuned to its own test cases, not shipped (2026-10-11).**
- Issue: a narrower "writer's framing" rule scored recall 1.00 / precision 0.96–1.00 on the gold set in four versions, and one version cut the Kerr project's false-fail rate from 5/10 to 2/10. The learning-qa sweep found the prompt's examples paraphrased gold cases (k6, tf_u1, tf_e1) and a carve-out described the one Kerr sentence it was then measured on. The general version (v4) failed the Kerr files 7/10 and raised flags on a held-out overview from ~3 to ~8 per run.
- Root cause (P20, P7): the gold set rewards strictness and cannot show precision on real summaries; the prompt was fitted to the measurement data twice; one fresh real-project check was reported as a pass when the judge varies run to run (Sonnet 5.5 takes no temperature).
- What would have caught it: from the start, repeated fresh checks (≥10) on real artifacts that did not shape the prompt, compared with the current prompt; a test that no prompt example shares subject or shape with a gold case.
- Fix: not shipped; main keeps the old prompt. Tests for example/gold overlap and calibration-output prompt fingerprints exist on the archived branch `judge-framing` for any future prompt change. Record: `docs/calibration_framing_2026-10-11.md`.
- Rule: for a judge prompt change, measure real-artifact false fails with repeated runs against held-out material before deciding; never word a prompt rule or example after the case you will measure it on. (P20)

**Archive Logs zipped the folder it was writing into — the zip read itself (2026-10-09).**
- Issue: the GUI "Clean Logs → Archive" button ran `shutil.make_archive(base=logs/archives/logs_<ts>, root_dir=logs/)`. The zip was written inside the tree being zipped, so the walk read it: 20.5 GB after ~9 minutes from a few MB of logs, growing ~80 MB/s with 68 GB free. The user saw only "taking a long time" and killed the GUI. Earlier archives had also swallowed every older zip in `archives/`, plus `runtime_settings.json` and the judge cache.
- Root cause (new global **P39**, with P5/P32 sibling drift): output path inside the input root; and the code enumerated `*.log` + `*.csv` to delete but zipped all of `logs/`, so the deleted set and the archived set differed. The CLI (`transcript_clean_logs.py`) did the same job correctly via a temp copy — two implementations of one operation, only one right.
- What would have caught it: a test that puts a large old zip in `logs/archives/` and asserts the new zip is small and lists exactly the enumerated names; checklist item 11 below; one shared implementation instead of two.
- Fix: single `transcript_utils.archive_logs` zips the listed files by name (`zipfile`), writes `.zip.tmp` then renames, deletes originals only after success; `ts_gui._run_archive_logs` and `transcript_clean_logs.archive_logs` both call it. Tests: `tests/test_archive_logs.py` (only-listed-files + small with a 100 kB old zip present; failure keeps originals and leaves no zip; GUI and CLI both route through the shared function).
- Rule: enumerate once and act on exactly that list; never write output inside the tree you read; one implementation per operation across GUI and CLI. (P39)

**Theme grounding judge — a gold set of only the EASY extremes hid a partial-fabrication recall gap (2026-07-15).**
- Issue: a new theme GROUNDING judge (for interpretive themes, which the source-entailment faithfulness judge wrongly flags) calibrated at recall/precision 1.0 and was armed as a hard blocker. `learning-qa` caught that its 8-case ungrounded gold set was entirely the two *easy extremes* — wholesale fabrication + direct contradiction — with NO "mostly-grounded theme that weaves in one fabricated concrete specific" (a fake name/institution/date inside a real narrative). That is exactly the class that already bit this project in prose (the "Luciano Malorni" fabrication), and the theme judge is now the SOLE gate for it (entity_grounding is abstract-only; faithfulness excludes themes). The lenient "when unsure prefer grounded" prompt + whole-theme granularity biased a long, mostly-grounded description toward a pass.
- Root cause (P20 / P7): the perfect score measured only the classes the gold set contained. A separate P14 report bug rode along — `ClaimVerdict.faithful` hardcoded `label == entailed`, so a theme FAIL listed *every* theme (grounded ones included) as ungrounded.
- What would have caught it: a gold set covering the *hard* class (partial fabrication), not just the extremes; asserting the FAIL *items* content in a mixed 1-grounded/1-ungrounded test (not just the count).
- Fix: added 3 partial-fabrication gold cases (grounded narrative + an invented Yale fellowship / 2003 Nobel / Georgetown study), sharpened the prompt to make a fabricated concrete specific ungrounded "however grounded the surrounding narrative", re-calibrated (11 ungrounded, recall/precision still 1.0, real themes still pass). Fixed `faithful` to accept `grounded` too; added the mixed-report test.
- Rule: for an LLM judge, the gold set must exercise the *hard middle* (partial fabrication), not just the obvious extremes — especially when the judge is the only gate for a class. Assert the *content* of a FAIL report, not just that it failed. (Instance of P20.)

**M2 faithfulness judge — a curated gold set of ISOLATED claims gave a falsely-perfect calibration; the real-artifact smoke test is the true validator (2026-07-15).**
- Issue: the M2 semantic faithfulness judge cleared its gold-set calibration perfectly (recall 1.0 / precision 1.0 on 29 curated single-sentence claims, incl. the real 'Luciano Malorni' fabrication). On that basis it was about to be armed as a hard publish-blocker. A real-full-artifact smoke test (run before flipping the flag) showed it would false-BLOCK essentially every real run.
- Root cause (P10 test-validity, + P9): the gold set was *isolated, clean* claims — it never exercised the real extraction path. On real artifacts: (a) claim extraction pulled in THEMES scaffolding/metadata (bare "1." theme numbers, "Document: …" titles, "Coverage / role: ~55-60%" estimates) and the judge correctly called those "unsupported"; (b) structural/interpretive THEMES are interpretive BY DESIGN — they name patterns and apply frames ("Bowen theory") not literally in the transcript, so ~30/40 interpretive-theme claims read as "unsupported"; (c) even a real abstract's legitimate summary-level synthesis got over-flagged/mislabeled ("recurring pattern … nubbin of self" → "contradicted"). None of these shapes existed in the isolated gold set, so calibration was blind to them.
- What would have caught it: calibrating on claims extracted from REAL FULL ARTIFACTS (the actual abstract/themes files run through `extract_claims`), not hand-picked clean sentences — the P9/P10 "real-scale fixture" rule applied to an LLM-judge. A smoke test on real artifacts BEFORE arming (P6/P11: verify the end-to-end behaviour, not the proxy).
- Fix: did NOT arm (kept `FAITHFULNESS_JUDGE_ENABLED = False`). Scoped the judge to PROSE summaries (abstract/summary/overview/blog), dropped THEMES from `FAITHFULNESS_ARTIFACT_SUFFIXES` (source-entailment is the wrong check for interpretive content). Hardened `extract_claims` (skip scaffolding/meta lines via `config.FAITHFULNESS_SKIP_LINE_LABELS`, strip enumerators) and loosened the judge prompt toward synthesis tolerance. Remaining before arming: real-full-artifact gold cases + label-precision (contradicted vs unsupported) tuning + a structured description-only path for themes (TODO).
- Rule: an LLM judge's gold set must be built from the SAME extraction path production uses, on REAL artifacts — a set of idealized isolated examples measures the judge in a vacuum and hides the extraction + real-prose behaviour. Never arm a gate on a proxy calibration; smoke-test the end-to-end behaviour on a real artifact first.

**M3 schema contracts — a producer that DELETES a drifted artifact silences the gate meant to block on it (2026-07-15).**
- Issue: when the bowen producer's post-save schema self-check detected format drift, it `unlink`ed the just-written (populated) artifact and returned False — intending "don't leave a malformed file authoritative." A `learning-qa` pre-flight caught that this *inverts* the safety net.
- Root cause (P2/P1): the fail-closed design routes drift through the release gate (`check_artifact_contracts` ERRORs on a drifted on-disk file → BLOCK, loud, U4). But deleting the file removed the exact evidence the gate keys on (the check skips missing files), no caller retries or halts on the False return, and bowen isn't a required artifact — so a *deterministic* producer↔consumer format drift became a **silent absence with zero gate signal**, the opposite of intent. Also a P1 mislabel: a same-machine file re-read has no transient failure mode, so calling it "retryable" and deleting was a loud→silent inversion.
- What would have caught it: tracing the return value to its callers (none act on False) and the deleted-file to its consumer (the gate skips missing) — a full-path trace (P11), not just "the self-check raises."
- Fix: on drift the producer now LEAVES the `.md` on disk so the gate BLOCKs, invalidates any stale `.json` sidecar (so the two can't disagree), logs loudly, and returns False. Gate hard-blocks drift (`config.GATE_BLOCKING_CHECKS += artifact_contracts`); verified 0 false-rejects across all 6 real bowen artifacts on the drive before landing (P6). The `_has_body` discriminant also treats H3+ item headers as content so an all-headers-no-body drift can't read as a benign empty.
- Rule: when a fail-closed check lives at layer B (the gate), an earlier layer A (the producer) must NOT destroy the evidence layer B inspects. Leave the bad artifact for the blocker; never delete-and-return-a-status that nothing consumes. A "retryable" label is only honest if a retry path exists and the failure is actually transient.

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
