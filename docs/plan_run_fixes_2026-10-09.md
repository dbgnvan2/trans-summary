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
