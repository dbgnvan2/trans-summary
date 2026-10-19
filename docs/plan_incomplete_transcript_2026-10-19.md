# Plan: notice an incomplete source transcript (IT0–IT5) — 2026-10-19

Status: **waiting for approval and for decisions IT0.a–f.** No code changed. The count
(IT5) is done and reported below.

## Why

The raw Systems Biology transcript starts with this header line (written by the
transcription tool):

> Warnings: Cloud transcription used chunked upload (12 part(s), 480s each).; Cloud
> transcription incomplete: transcribed 5 of 12 chunks; missing time ranges (approx.):
> 00:24:00-00:32:00, 00:32:00-00:40:00, 00:40:00-00:48:00, 00:56:00-01:04:00,
> 01:04:00-01:12:00, 01:12:00-01:20:00, 01:28:00-01:36:00

Source: `/Volumes/CrucialX9/1 MY DISK/BTA ALL …/BTA Video Project - 03 Processed Transcripts ( Trans-Summ)/projects/Systems Biology Meets Bowen Theory Rethinking Cancer - Michael Kerr - 2021-06-25_20260718_155038_v-valid-5m/`.
The same line is in all four `.txt` copies in that folder (raw, `_v-valid-5m`,
`_v-valid-5m_validated`, `_validated`).

Chunks 1–3, 7 and 11 were transcribed: 00:00–00:24, 00:48–00:56 and 01:20–01:28. The
formatted transcript's section headings (repo fixture) jump from 00:23:30 to 00:48:00
and from 00:54:23 to 01:20:00. About 40 of the 88 minutes were summarised and judged.

**Nothing reads the line.** No file in the repo contains "transcription incomplete" or
"missing time ranges". `format_transcript` sends the raw text, header included, to the
formatting model. The formatted transcript has no header. Every later stage and the
faithfulness judge see only the formatted text. The judge checks claims against the
transcribed parts, so a summary of 40 minutes passes as faithful: it is faithful to the
text it was given. The 2026-07-18 run manifest for this project says
`ALLOW_WITH_WARNINGS` and never mentions the missing audio. This is failure pattern P2
(an input is cut and nothing says so).

## IT5 — How many projects are affected (scan done 2026-10-19)

Method: walked `KCFC ALL` and `BTA ALL =======================` on CrucialX9 and read the
first 12 lines of every `.txt`. 60 files have the transcription tool's header
(`TRANSCRIPT` / `Source file:` / `Duration:` / `Warnings:`).

| What | Count |
|---|---|
| Project folders scanned | 19: 12 in `KCFC ALL/projects`, 7 in the BTA processed `projects` folder (plus one empty nested `projects/projects`) |
| Project folders whose raw source was found, with the header | 18. KCFC raws are in `KCFC ALL/2021 videos` (all 12 found). BTA raws are in the project folder, or in `02 Transcripts to be Processed (From TRX)/xPending` for the older Systems Biology `_valid` project. Not found: `Emotional Regression in Society and Cancer … _20260411_170838…` (no raw and no formatted transcript in its folder). |
| **Raw sources with the "incomplete" warning** | **1 project**: Systems Biology `…_20260718_155038_v-valid-5m` (4 `.txt` copies) |
| Repo copies of that project | `tests/fixtures/prose_real/Systems Biology … _20260718_155038/` holds its outputs (no raw). It is the partial transcript. |

**Cross-checks that don't rely on the header:**

- **Words per minute** (words in the body ÷ the header's Duration). Normal transcripts:
  103–154 wpm. Systems Biology: 52–54 wpm. Three test files: 21–22 wpm
  (`TEST FILE - DAVE G - 2026-07014`, `TEST FILE 2 - DAVE G - 2026-07-14`,
  `Roots of Bowen TEST - Mike Kerr - 2026-07015`). They hold the first ~15 minutes of a
  full recording, with the full recording's header (Duration 01:28:40 / 01:31:52) and
  no warning. They are test files, but a header check can't see them (see IT0.e).
- **Largest gap between timestamps in each formatted transcript:** Systems Biology 29
  minutes (BTA project) and 25 minutes (repo fixture). Every other formatted transcript:
  9 minutes or less.

**A complete transcript of the same talk exists.** The older project
`Systems Biology … 2021-06-25_valid` was made from
`xPending/Systems Biology … 2021-06-25_valid_validated.txt`: a WhisperX transcript,
Duration 01:32:08, 115 wpm, largest timestamp gap 7 minutes, no incomplete warning. If
you want Systems Biology outputs that cover the whole talk, that is the source to use.

**Not scanned:** `/Volumes/davemini/Downloads/projects` (not mounted). The transcription
tool's own code is not on this Mac (searched `~/ProjectsLocal` for "transcription
incomplete" and "chunked upload"). So the parser below is built from the one real header
that has the warning, and checked against all 60 headers.

## IT0 — Decisions for you

| ID | Question | Recommendation |
|---|---|---|
| IT0.a | Is an incomplete transcript a run-stopping fault or a warning? | **Warning.** The outputs are faithful to what was transcribed: incomplete, not wrong. Under your rule (fail only on wrong content), the run goes on. The release gate gets a new advisory check, `source_completeness`. It returns WARN and is not in `config.GATE_BLOCKING_CHECKS`, so the decision is `ALLOW_WITH_WARNINGS`. Making it block later is a one-word config change. |
| IT0.b | Where are you told, before the summary and the judge run? | **Three places.** (1) A line in the GUI's Confirm dialog before a run starts ("The source transcript is incomplete: … Continue?"), so you can cancel. (2) A ⚠️ line at the top of the run log, after the run plan, on every GUI run, including a run of later stages only. (3) A warning in the Format stage's log, which also covers the Format button and the CLI `transcript_format.py`. Alternative: (2) and (3) only. |
| IT0.c | Print the gate's warnings when publication is allowed? | **Yes, for all checks.** Today the GUI prints `[WARN]` lines only when the gate blocks (`ts_gui.py:2408`, `_publication_blocked`). On `ALLOW_WITH_WARNINGS` they reach only the run-manifest JSON. Without this, the gate's completeness warning is in the manifest but not in the run log. Alternative: print only the `source_completeness` line. |
| IT0.d | Should the published pages (webpage, PDF, abstract) say the talk was transcribed in part? | **Not in this change.** It changes published content and templates and needs its own wording. I'd add it to TODO. |
| IT0.e | Add a second signal for transcripts whose header doesn't say they are incomplete (words per minute, or last timestamp against Duration)? | **Not now.** Only the three TEST files would trip it today, and its threshold would need measuring. I'd add it to TODO with the numbers above. |
| IT0.f | The other transcription warnings ("Dropped 6 of 650 segment(s) as suspected hallucination", "HF token missing. Diarization disabled", "Initial prompt truncated to 224 tokens") aren't read either. Show them? | **Yes, as one plain log line**, word for word, wherever the incomplete check runs (pre-run and Format). Only "incomplete" gets the ⚠️, the dialog line and the gate verdict. |

## Design

**New module `source_completeness.py`.** One job: read the transcription tool's header
and say whether the transcript is complete. It is used by `formatting_pipeline`,
`release_gate` and `ts_gui`. `formatting_pipeline.py` (1,447 lines) and
`release_gate.py` (1,615 lines) already have several jobs each. The existing header
helpers (`detect_transcript_source_format`, `strip_transcript_metadata_header`) stay
where they are: moving them is a refactor outside this task.

**Parsing rules.**

- The header is the lines before the first `-----` separator within the first 20 lines
  (the rule `strip_transcript_metadata_header` already uses), and only when the first
  line is `TRANSCRIPT` (after a byte-order mark, if any). The body is never read, so a
  speaker who says "transcription incomplete" can't trigger it.
- The `Warnings:` value is split on `;` into separate warnings, trimmed, empty ones
  dropped, each kept as written.
- A warning means "incomplete" when it contains a marker from a new
  `config.SOURCE_INCOMPLETE_MARKERS`, at first `("transcription incomplete",)`,
  case-insensitive. It is in config because it is the transcription tool's wording, and
  that can change.
- From that warning: `transcribed (\d+) of (\d+) chunks` gives the counts, and each
  `hh:mm:ss-hh:mm:ss` gives a missing range, kept as written.
- **Malformed:** if the marker is there but the counts or the ranges can't be read, the
  transcript still counts as incomplete. The message quotes the tool's warning as
  written and says its details could not be read. It is never a pass.

**Message** (run log and dialog):

> ⚠️ The source transcript is incomplete: the transcription tool transcribed 5 of 12
> chunks. Missing (approx.): 00:24:00-00:48:00, 00:56:00-01:20:00, 01:28:00-01:36:00.
> The summary, abstract and other outputs will cover only the transcribed parts.
> Source: `<file name>`.

Ranges that touch are joined for the message (00:24:00-00:32:00, 00:32:00-00:40:00 and
00:40:00-00:48:00 become 00:24:00-00:48:00). The gate items keep each range as written.
There is no "N minutes missing" figure: the tool's last range (01:28:00-01:36:00) runs
past the header's Duration (01:28:00), so a sum would overstate the gap.

**Which file the GUI checks.** `self.selected_file`, the file the run starts from. If
it no longer exists, the project's raw-source copy (` - raw-source.txt`, written at
format validation). If neither exists, a plain line: "Could not check whether the source
transcript is complete: no source file found." The run goes on in every case.

**Gate check `source_completeness` (advisory).**

- Reads `release_gate._raw_source_candidates(base_name)`: the project's raw-source copy,
  or else matching `.txt` files in the project, source and processed folders. These are
  the same files `source_fidelity` reads.
- **WARN** if any candidate reports incomplete. Detail: the message. Items: one per
  file, with the file name, the chunk counts, the missing ranges as written, and the
  tool's warning text.
- **PASS** "the transcription tool's header reports no missing audio" when the headers
  report nothing incomplete. **PASS** "no transcription-tool header; completeness not
  stated" for a plain transcript. The detail says which.
- **ERROR** when no raw source is found. It doesn't block: `_is_blocking` blocks only
  checks in `GATE_BLOCKING_CHECKS`. `source_fidelity` already blocks on a missing raw
  source.

The check writes nothing and keeps no state. The raw-source copy is overwritten at each
format validation, so a re-transcribed talk clears the warning on the next run.

## Items, criteria and tests

New test file `tests/test_source_completeness_it.py` unless a row names another file.
The "incomplete" test input is the real header, copied word for word from the Systems
Biology raw file.

| ID | Criterion | Test | Status |
|---|---|---|---|
| IT1.a | The real Systems Biology header parses as incomplete: 5 of 12 chunks, 7 ranges, first `00:24:00-00:32:00`, last `01:28:00-01:36:00`. The chunked-upload warning is kept as a separate warning. | `test_it1a_real_incomplete_header_is_parsed` | not done |
| IT1.b | Headers without the marker are complete, and every warning is kept as written. Three real headers: cloud chunked-upload only; the WhisperX line (prompt truncated / HF token missing); "Dropped 6 of 650 segment(s) as suspected hallucination". | `test_it1b_complete_headers_not_flagged` | not done |
| IT1.c | Malformed: (1) marker with no counts and no ranges, (2) counts with no ranges, (3) ranges written `00:24-00:32`. Each is incomplete; the message quotes the warning as written and says the details could not be read. | `test_it1c_malformed_header_still_flagged` | not done |
| IT1.d | No header (a plain transcript) → no header, not incomplete. A header after a byte-order mark is still read. | `test_it1d_plain_transcript_and_bom` | not done |
| IT1.e | Adversarial (P7): "transcription incomplete" in the body below the separator is not flagged. A header whose `Warnings:` line has "truncated" but not the marker is not flagged. | `test_it1e_body_text_and_near_miss_not_flagged` | not done |
| IT1.f | The message joins touching ranges, names the chunk counts and the source file, and has no minutes-missing figure. | `test_it1f_message_joins_touching_ranges` | not done |
| IT2.a | `format_transcript` logs the message at warning level when the raw transcript is incomplete, and still formats (returns True). With a complete header it logs no such warning. | `tests/test_formatting_pipeline.py::test_it2a_format_logs_incomplete_source` (uses that file's existing patch pattern) | not done |
| IT2.b | GUI: `_run_selected_stages` logs the ⚠️ message before the first stage, and every selected stage still runs. | `test_it2b_run_log_warns_before_first_stage` (headless GUI as in `tests/test_ts_gui_run_all.py`, mock runners) | not done |
| IT2.c | (if IT0.b (1)) The Confirm dialog text contains the message for an incomplete source and is unchanged for a complete one. | `test_it2c_confirm_dialog_names_missing_ranges` (patched `messagebox.askyesno`) | not done |
| IT2.d | Source file missing → the "Could not check" line, and the run goes on. | `test_it2d_missing_source_is_reported_not_fatal` | not done |
| IT2.e | (if IT0.f) Every header warning is logged word for word in one plain line. | `test_it2e_all_transcriber_warnings_logged` | not done |
| IT3.a | Gate check on a project whose raw-source copy has the real header → WARN; items carry the 7 ranges as written and 5 of 12. | `test_it3a_gate_warns_with_missing_ranges` | not done |
| IT3.b | Complete header → PASS; plain transcript → PASS whose detail says completeness is not stated. | `test_it3b_complete_and_plain_sources_pass` | not done |
| IT3.c | No raw source → ERROR, and `decide()` does not BLOCK on it. | `test_it3c_missing_source_is_nonblocking_error` | not done |
| IT3.d | `source_completeness` is in `DEFAULT_CHECKS` and not in `GATE_BLOCKING_CHECKS`; a gate whose only non-PASS is this WARN decides `ALLOW_WITH_WARNINGS`. | `test_it3d_incomplete_source_allows_with_warnings` | not done |
| IT3.e | The run manifest records the verdict with its ranges. | `test_it3e_manifest_records_missing_ranges` | not done |
| IT3.f | Malformed header in the raw-source copy → WARN. | `test_it3f_malformed_source_warns` | not done |
| IT3.g | Dirty state (P8): the same project gives WARN, then PASS after its raw-source copy is replaced by a complete transcript. | `test_it3g_replaced_source_clears_the_warning` | not done |
| IT3.h | (if IT0.c) On `ALLOW_WITH_WARNINGS`, `_publication_blocked` logs each `[WARN] check: detail` line and returns False. | `tests/test_run_fixes_rf.py::test_it3h_gate_warnings_logged_on_allow` | not done |
| IT4 | Documents: CHANGELOG entry; TODO.md (the 2026-10-19 adjacent item "Nothing reads the transcription tool's 'incomplete' warning" is closed; IT0.d and IT0.e added if you choose "not now"); `ARCHITECTURE_DESIGN.md:135` check list; the config comment above `GATE_BLOCKING_CHECKS`; `tests/fixtures/prose_real/README.md` says the Systems Biology fixture is the partial transcript; this plan's status. | Review of the diff | not done |
| IT5 | Count of affected projects. | This plan, section IT5; repeated in CHANGELOG | done (1 of 18 projects with a raw source) |

Existing tests that must still pass unchanged: `tests/test_validation_logic.py` (header
detection and stripping), `tests/test_validator_gating_r15.py` (it reads the
`DEFAULT_CHECKS` names), `tests/test_m5_fault_injection.py`,
`tests/test_consistency_check.py`, `tests/test_ts_gui_run_all.py`,
`tests/test_formatting_pipeline.py`. A gate test that expects `ALLOW` with the default
checks already has to provide a raw source for `source_fidelity`; a plain or complete
source gives this check PASS, so those tests should not change. If one does, I report
it rather than change its expectation silently.

No size or count caps are added, so there is no real-scale (P9) test. The real header
is the fixture.

## Order

1. IT1 tests (they fail: no module yet), then `source_completeness.py` and the config
   marker.
2. IT3 tests, then the gate check, its place in `DEFAULT_CHECKS`, and the config
   comment.
3. IT2 tests, then the `format_transcript` line and the GUI changes, as you decide
   IT0.b, IT0.c and IT0.f.
4. Full suite.
5. Live check, not in CI, no API calls, nothing written: run the parser on the 60 headed
   files and the gate check on the 7 BTA projects with `config.PROJECTS_DIR` pointed at
   the drive. Expected: exactly one WARN (Systems Biology `_20260718_155038_v-valid-5m`).
   The script stays in the session's scratch folder; the result goes in the CHANGELOG.
6. Documents (IT4).
7. learning-qa review of the diff, fix its findings, commit to main. No push unless you
   say so.

## Files shared with the judge-severity work

On 2026-10-19 the working tree holds uncommitted judge-severity changes (plan JS0–JS7)
in `release_gate.py` (the judge functions, lines 479–1200), `config.py` (the judge
section, lines 690–712), `extraction_pipeline.py`, `faithfulness_judge.py`, `conftest.py`
and the summary prompt. This plan edits other parts of `release_gate.py` (a new check
next to `check_source_fidelity`, and `DEFAULT_CHECKS`) and of `config.py` (the gate
policy comment and a new constant), plus `CHANGELOG.md` and `TODO.md`, which both
pieces of work update.

- Commits stage only this plan's hunks (a patch applied to the index), never
  `git add` of a whole shared file, so judge-severity work in progress is not swept in.
- The full suite is run on the combined tree. A failure in a judge-severity test is
  reported to you, not fixed here.
- The baseline run on 2026-10-19 had one failure, `test_rfc1_attempts_from_config`:
  `inspect.getsource(ep.summarize_transcript)` returned `_select_blog_lens`. That is the
  sign of `extraction_pipeline.py` being edited on disk while the suite ran. Run alone
  right after, it passed. Baseline otherwise: 1,710 passed, 23 skipped, 1 xfailed.

## Not code-testable

- Whether the dialog line and the log line are noticed. That is your judgement on the
  first real run.
- That the transcription tool always uses this wording. Its code is not on this Mac. A
  changed wording passes as complete unless it still contains a marker. The markers are
  in config, and IT0.e's second signal would cover a changed wording.

## Adjacent issues found, not fixed

- The GUI prints the gate's `[WARN]` lines only when publication is blocked. IT0.c fixes
  this if you approve it.
- `format_transcript` sends the 7-line header, `Warnings:` included, to the formatting
  model as part of the raw transcript. `strip_transcript_metadata_header` is used only
  in the word comparisons (`formatting_pipeline.py:872`, `:1055`). No formatted
  transcript shows the header, so this costs a few tokens and nothing else seen so far.
- `detect_transcript_source_format` needs all six header labels in the first 12 lines.
  A header missing one (for example, no `Speakers:` line) is treated as a plain
  transcript, and `strip_transcript_metadata_header` then leaves the header in the text
  it compares. All 60 real headers have all six. The new parser does not depend on that
  function.
- Calibration runs that used the Systems Biology fixture (for example SC1.d,
  `docs/calibration_summary_closing_2026-10-18.md`) measured a 40-minute transcript.
  They still test the prompts, because the judge compares against the same partial
  text, but their reports don't say the transcript is partial. IT4 adds the note to the
  fixture README only.
