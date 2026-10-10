# Plan: fixes from the 2026-10-09 Kerr run (RF.A–RF.E)

Status: awaiting approval. Source: the run of
`Why Families Repeat the Same Patterns - Michael Kerr - 2026-09-13` that was
blocked at 15:06 on 2026-10-09 (`PUBLISH-BLOCKED.txt`, `run-manifest.json`), plus
the GUI status-panel review. User chose A, B, C, D and E.

## RF.A — Heading timestamps match the raw transcript

Problem: the raw transcript uses `m:ss` (`0:33` = 33 s). The formatter wrote
`[00:33:00]` (33 min) for every heading, so `source_fidelity` blocked publication.
The prompt only says "padded to `[hh:mm:ss]`".

- RF.A.1 `formatting_pipeline.normalize_heading_timestamps(formatted, raw)` rewrites
  a heading timestamp `hh:mm:00` to `00:hh:mm` (as seconds, `hh*60+mm`) only when
  the written value does not occur in the raw transcript and the reinterpreted
  value does. Returns the text and a list of rewrites. Headings already present in
  the raw, `00:00:00` fallbacks, and values that match neither are left unchanged
  (the existing validator still fails the last kind).
  - Test: `tests/test_run_fixes_rf.py::test_rfa1_mss_read_as_hmm_is_rewritten`
    (real Kerr raw + formatted fixture: all 21 headings rewritten; result passes
    `validate_section_headings`).
  - Adversarial (P7): `test_rfa1_heading_present_in_raw_is_not_rewritten` (an
    `h:mm:ss` raw with a real `[00:33:00]` heading stays as is) and
    `test_rfa1_unmatched_timestamp_left_for_validator` (a value that matches
    neither reading is unchanged and still reported as an error).
- RF.A.2 `format_transcript` applies it before saving and logs
  "Corrected N of M heading timestamp(s) (m:ss read as h:mm)" (P2: surfaced).
  - Test: `test_rfa2_format_transcript_saves_corrected_headings` (LLM call
    patched to return the Kerr formatted text with wrong headings).
- RF.A.3 Prompt `Transcript Formatting Prompt v12-Lite.md` states that `m:ss` /
  `mm:ss` means minutes:seconds (`0:33` → `[00:00:33]`).
  - Test: `test_rfa3_prompt_states_mss_rule` (line present in the prompt file).

Validation is not changed to repair files: validation reports, Format repairs
(rule 2). The Kerr project must be re-formatted to pick this up.

## RF.B — Quote-within-a-quote is verbatim

Problem: the emphasis quote turns the speaker's inner `"He's smiling…"` into
`'He's smiling…'`. `_without_disfluencies` keeps `'` inside its word pattern, so
the token `'he's` does not equal `he's` and the quote scores 0.932 (< floor).

- RF.B.1 `validation_pipeline._without_disfluencies` maps `‘` to `'` (it already
  maps `’`) and strips leading/trailing apostrophes from each word, keeping inner
  ones (`he's`, `don't`).
  - Test: `test_rfb1_nested_single_quotes_are_verbatim` (the real Kerr quote vs
    the real formatted text scores >= `EMPHASIS_QUOTE_FOUND_RATIO`).
  - Adversarial: `test_rfb1_changed_word_inside_nested_quote_still_fails` (same
    quote with one word changed inside the inner quote still scores below floor).
  - `test_rfb1_contractions_kept` (`he's` ≠ `hes`; `don't` stays one token).

## RF.C — Blog-only stage retries lens validation and checks the lens

Problem: the Blog-only path (`extraction_pipeline.py` ~1627) makes one
theme/lens-validation call, takes `top_lens` without `_top_lens_is_grounded`, and
on failure logs only "No validated top-ranked lens available". The Core path
retries 3 times and checks grounding.

- RF.C.1 Promote the literal `max_attempts = 3` to
  `config.THEME_LENS_VALIDATION_ATTEMPTS` and use it in both paths (P4).
  - Test: `test_rfc1_attempts_from_config` (both paths read the config value;
    patched to 2 → validator called at most 2 times in the blog path).
- RF.C.2 Blog-only path retries the validation call up to that limit and accepts
  a top lens only if it is grounded in the lenses on disk. It does not regenerate
  themes or lenses (those belong to Core and are already on disk).
  - Test: `test_rfc2_blog_retries_until_grounded_lens` (first call returns no
    top lens, second a grounded one → blog written).
  - Adversarial: `test_rfc2_blog_rejects_ungrounded_lens` (validator always names
    a lens not in the file → no blog, returns False).
- RF.C.3 On exhaustion, the error names the last reason per attempt: output not
  JSON / no top lens returned / top lens "X" not among the generated lenses.
  - Test: `test_rfc3_blog_failure_reason_logged`.

## RF.D — The GUI log is saved to a file

Problem: the GUI log exists only in the window, so the blog failure could not be
diagnosed afterwards.

- RF.D.1 `TranscriptProcessorGUI.log` also appends each line, with a timestamp, to
  `logs/gui_<YYYYmmdd_HHMMSS>.log` (one file per GUI session, created on first
  line). A write error is reported once in the window and does not stop the run.
  - Test: `test_rfd1_log_lines_written_to_session_file` (LOGS_DIR patched to
    tmp_path; two lines → one file containing both, in order).
  - `test_rfd1_log_file_error_does_not_raise` (unwritable dir → no exception, one
    warning line).
- RF.D.2 The log-cleanup action already archives/deletes `*.log`, so these files
  are covered. No change; checked by reading `_run_archive_logs`.

## RF.E — "8b. Simple Web" stage

Problem: the status panel lists "Simple Web" but no GUI stage writes it.

- RF.E.1 `STAGE_DEFINITIONS` gains `("simple_web", "8b. Simple Web")` after
  `webpdf`, before `package` (so the zip includes it). Dependencies as `webpdf`;
  `STAGE_OUTPUTS["simple_web"] = ["SUFFIX_WEBPAGE_SIMPLE"]`.
  - Tests: update `test_stage_definitions_order` (16 stages) and
    `test_stage_runners_cover_all_keys`; new `test_rfe1_simple_web_before_package`.
- RF.E.2 Runner `_run_stage_simple_web` runs the release gate once; on BLOCK it
  records the decision and logs each blocker (shared helper with
  `_run_web_pdf_generation`, so both log the same way), and writes nothing.
  Otherwise it calls `pipeline.generate_simple_webpage`.
  - Tests: `test_rfe2_simple_web_calls_generator_on_allow`,
    `test_rfe2_simple_web_block_writes_nothing_and_logs_blockers`.
- RF.E.3 The run manifest (`release_gate._MANIFEST_SUFFIXES`) records
  `SUFFIX_WEBPAGE_SIMPLE`.
  - Test: `test_rfe3_manifest_lists_simple_webpage`.

## Order

1. Commit the mutation-gate work (separate, already reviewed).
2. RF.B (smallest, unblocks verbatim_quotes) → RF.A → RF.C → RF.E → RF.D.
   Tests first for each. One commit per item.
3. Full suite; learning-qa sweep on the combined diff; fix findings.
4. CHANGELOG; push main.

## Not code-testable

- Whether the regenerated Kerr summary/overview clear the three faithfulness
  flags. Human check after re-running from Format.

## Adjacent issues found, not fixed

- `mut_harness.run_suite` counts a 120 s timeout as "killed". The full suite now
  takes ~90 s per mutant, so a slow machine can count survivors as killed and
  inflate the score.
- `tests/test_bowen_references_integration.py` writes log files into the real
  `logs/` directory on every run (dozens per mutation campaign).

## RF.F — Interview turns are not audience Q&A (approved 2026-10-09)

Problem: run 16:50 halted at Gen Abstract. `calculate_qa_percentage` counted every
section with two `**Name:**` labels as Q&A; the Kerr interview's 7 sections with
`**Interviewer:**` gave 26% (> 20%), so the abstract prompt was told to add a Q&A
sentence ("extensive audience engagement…") that the faithfulness judge rejected on
every attempt. Retries could not fix it: each got the same input.

- RF.F.1 One detector, `transcript_utils.find_qa_sections`, used by the abstract
  (`calculate_qa_percentage`) and the summary (`analyze_qa_content`). A section is
  Q&A when its heading matches `config.QA_HEADING_PATTERNS` ("Q&A: …", "Questions
  and Answers", "Question About …") or it has a turn by an audience speaker. A
  `**Label:**` is audience when it contains a `config.QA_AUDIENCE_SPEAKER_LABELS`
  word, else when it is neither a host role (`config.QA_HOST_SPEAKER_LABELS`) nor
  a presenter (surname alone, or first name + surname; titles and initials
  ignored; co-presenters split on and/&/,). Words like "question" in the text no
  longer count on their own.
  - Tests (`tests/test_run_fixes_rf.py`): `test_rff1_interview_is_not_qa` (real
    Kerr interview → 0% for abstract and summary), `test_rff1_audience_section_still_detected`,
    `test_rff1_one_named_questioner_is_qa`, `test_rff1_dr_label_is_presenter`,
    `test_rff1_presenter_first_name_alone_is_audience`, `test_rff1_presenter_label_not_qa`,
    `test_rff1_qa_heading_counts`, `test_rff1_numbered_and_accented_labels`,
    `test_rff1_question_words_alone_are_not_qa` (P7),
    `test_rff1_lecture_heading_with_question_is_not_qa` (P7),
    `test_rff1_presenter_label_variants`.
- RF.F.2 `prepare_abstract_input` and `prepare_summary_input` pass the presenter
  (`metadata["presenter"]` from the filename, falling back to `"speaker"`).
  - Test: `test_rff2_inputs_use_presenter_from_filename_metadata`.

Effect on the real fixtures: Kerr interview 26% → 0%. Lectures whose Q&A sections
are headed "Q&A: Name on …" now count them (the old code never read headings).

Adjacent, not fixed: the abstract prompt calls every event a "webinar" unless the
transcript says otherwise; the Kerr talk is an interview.

## RF.G — Curly and straight quotes are the same word (approved 2026-10-09)

Run 20:16 failed Format: 108 of 119 differences were `Bowen’s` → `Bowen's`.
- RF.G.1 `_normalize_word_for_validation` maps ‘ ’ to ' and “ ” to ".
  - Tests: `tests/test_run_fixes_rf.py::test_rfg1_curly_quotes_are_not_differences`,
    `test_rfg1_real_kerr_no_quote_only_differences`; adversarial
    `test_rfg1_changed_word_still_reported` (contributor → perpetrator).

## RF.H — A deleted chapter-title line needs no review (approved 2026-10-09)

The raw transcript carries YouTube chapter titles on their own lines ("Who Was
Murray Bowen?"); the formatter drops them in favour of section headings.
- RF.H.1 A deletion is auto-allowed ("chapter title") only when it covers exactly
  one whole raw line that looks like a title: 2 to `config.CHAPTER_TITLE_MAX_WORDS`
  words, title case (minor words in `config.CHAPTER_TITLE_MINOR_WORDS` may be
  lower case), no sentence-ending punctuation other than "?".
  - Tests: `test_rfh1_deleted_title_line_is_auto`, `test_rfh1_real_kerr_titles_auto`;
    adversarial `test_rfh1_title_plus_speech_word_needs_review`,
    `test_rfh1_deleted_speech_line_needs_review`, `test_rfh1_changed_title_needs_review`.

## RF.I / RF.J / RF.K (approved 2026-10-09, run 20:33)

Run 20:33 reached Full Web/PDF and the gate blocked on: 2 unreviewed format
differences; faithfulness (summary 8/64 claims, blog 2/79); one spliced emphasis
quote. Behind the first: Init Val auto-applied "contributor" → "perpetrator" and
"back" → "aback" into `_validated.txt`, which every later check treats as the source.

### RF.K — Extracted quotes pass the gate's verbatim test or are dropped
- RF.K.1 `validation_pipeline.quote_is_verbatim_for_gate(quote, transcript)` is the
  single test (ends ≥ EMPHASIS_QUOTE_PARTIAL_RATIO and coverage ≥
  QUOTE_MIN_WORD_COVERAGE) used by `release_gate.check_verbatim_quotes`.
- RF.K.2 `extract_scored_emphasis` and the Bowen grounding step drop quotes that fail
  it and log "kept N of M" with each dropped label (P2). Both Core and the standalone
  Bowen + Emphasis stage go through these functions.
  - Tests: `tests/test_run_fixes_rf.py::test_rfk1_gate_uses_shared_predicate`,
    `test_rfk2_spliced_emphasis_quote_dropped` (real Kerr spliced quote),
    `test_rfk2_verbatim_quote_kept`, `test_rfk2_bowen_spliced_quote_dropped`.

### RF.I — Init Val auto-applies only mishearing-level fixes
- RF.I.1 `transcript_initial_validation_v2.is_mishearing_fix(original, suggestion,
  transcript)`: after removing timestamps and punctuation, every changed word pair has
  the same first letter, similarity ≥ `config.INIT_VAL_AUTO_MIN_SIMILARITY` (0.8) and
  the original word appears nowhere else in the transcript; a split/merge
  ("abit" → "a bit") also qualifies; alias (proper-noun) findings keep their own path.
  Inserted or deleted words do not qualify.
- RF.I.2 The GUI auto mode applies only qualifying findings; each held finding is
  logged ("Held for review: 'contributor' → 'perpetrator'") and not applied.
  - Tests: `test_rfi1_mishearing_fixes_qualify` (homostasis, Bowan, abit),
    `test_rfi1_meaning_changes_held` (contributor→perpetrator, mother→father,
    patient→parent, their→there when "their" occurs elsewhere, back→aback),
    `test_rfi2_auto_mode_applies_only_qualifying` (GUI runner with stub validator).

### RF.J — Summary and blog are checked and regenerated like the abstract
- RF.J.1 The structured summary uses the main model (`settings.DEFAULT_MODEL`), not Haiku.
- RF.J.2 `_faithfulness_precheck(base_name, suffix)` runs the gate's faithfulness
  check on one artifact; the summary and the blog regenerate with the rejected claims
  as feedback up to `config.GENERATION_FAITHFULNESS_ATTEMPTS` (3). All attempts fail →
  keep the least-bad draft, log loudly, return False (as the abstract, plan R11).
  Judge unavailable → keep the draft (the gate verifies at publish).
  - Tests: `test_rfj1_gui_summary_uses_default_model`,
    `test_rfj2_summary_regenerates_with_feedback`, `test_rfj2_summary_all_fail_keeps_best_and_fails`,
    `test_rfj2_blog_regenerates_with_feedback`, `test_rfj2_unavailable_judge_keeps_draft`.

Not code-testable: whether the regenerated Kerr summary/blog pass the live judge.

### Sweep on RF.I/J/K (learning-qa, 2026-10-09) — 10 findings, all fixed
- RF.I rule tightened: one-for-one swaps only (no split/join), no negation change, and
  evidence for the new word (proper noun, or used elsewhere in the transcript);
  "perpetuate→perpetrate", "adapt→adopt", "should→shouldn't", "any one→anyone" held.
  Held findings saved to `<base> - init-val-held.json`; an "alias" finding skips the
  check only when the pair is in the approved terms file.
- RF.K: all emphasis dropped → error, nothing saved; extractors check quotes against
  the gate's text (`_gate_source_text`); Bowen drop diagnostic reports match/coverage.
- RF.J: precheck adds entity grounding; a disabled judge is "unavailable", a missing
  artifact fails; a draft echoing the feedback is rejected; the overview uses the loop.
Tests: `test_rfi2_unapproved_alias_is_checked`, `test_rfk2_all_emphasis_dropped_fails_and_saves_nothing`,
`test_rfk2_extractor_checks_against_gate_text`, `test_rfj2_precheck_includes_entity_grounding`,
`test_rfj2_disabled_judge_is_not_a_pass`, `test_rfj2_draft_echoing_feedback_is_rejected`.
Open (noted, not fixed): `quote_is_verbatim_for_gate` re-normalizes the transcript per
quote (reverses the M11 one-pass optimisation; ms-scale on real transcripts).

## RF.L / RF.M (approved 2026-10-10, run 07:41)

Run 07:41 stopped at Format for review; after the review passed the run did not
resume and the last line read "apply review decisions completed successfully".
- RF.L A Format failure that only needs review (validation record: `review_needed`
  and that one error) pauses the run ("⏸ Paused at 1. Format"), reports usage so far
  and remembers the remaining stages for that project. When the review makes Format
  pass, the GUI asks to continue and runs them (dependency pre-flight re-checked,
  usage report covers the whole run). Gross-limit or heading errors still fail. The
  paused state is dropped on a new run, another file, standalone Format, or a review
  that cannot make Format pass. A decision that cannot be applied is named.
  - Tests: `test_rfl1_format_review_pauses_and_remembers_rest`,
    `test_rfl1_real_format_failure_still_halts`, `test_rfl1_gross_format_failure_is_not_a_pause`,
    `test_rfl2_review_pass_offers_resume`, `test_rfl2_resume_not_offered_for_another_file`,
    `test_rfl2_unappliable_decision_is_not_a_failure`.
- RF.M The Format log's mismatch list leaves out auto-allowed and approved differences.
  - Test: `test_rfm1_mismatch_sample_excludes_resolved`.
Adjacent, not fixed: the review dialog applies decisions to `self.base_name` at apply
time, not the project it was opened for; switching files with the dialog open would
apply them to the wrong project.
