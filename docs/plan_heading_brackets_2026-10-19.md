# Plan: heading timestamps written without brackets (HB0–HB3)

Status: **built 2026-10-19** (see Built below).

## HB0 — Evidence

Run of 2026-10-19 (commit 5122d27), "3 & 4 Heartland Holt Panel Discussions 1 and 2 -
Michael Kerr - 2007-01-13": Format stopped with 41 errors. 40 were the heading contract.
Every heading was written

    ## Section 3 – Family Triangles and the Kaczynski Story (00:00:19).

where the contract is `([00:00:19]).`. Titles, numbering and timestamps were right; only
the square brackets were missing. The prompt's format line,
`## Section N – [Thematic Heading] ([hh:mm:ss]).`, uses square brackets both as a
placeholder marker and as literal text, so the model read both as placeholders.

The 41st error was one deletion (7 words of transcription-tool text in the source,
`ISO 639-1 code, or "auto" for detection,`). On its own it would not have stopped the run:
RS.3 restores the source's words when review is the only failure. The heading errors
kept RS.3 from running.

Checked on that run's output: with the brackets added, `verify_source_fidelity` reports
only the one difference that RS.3 restores; the heading-position check passes.

## HB1 — The Format stage adds the brackets

`formatting_pipeline.normalize_heading_brackets(text)` rewrites a `## Section N – …`
heading whose timestamp is written `(hh:mm:ss)`, `[hh:mm:ss]` or `([hh:mm:ss])`, with or
without the final period, to `([hh:mm:ss]).`. Only the timestamp suffix changes. Left as
written, for the validator to report: other lines; unpaired brackets (`(00:05:20]`);
two-group times (`(05:20)`, ambiguous); four-group times other than RS.4's
`([00:h:mm:ss]).` (e.g. `(00:01:02:04).` is fixed by neither and still stops Format); and
a heading with another hh:mm:ss before the last one (rewriting would leave a stray time
in the title and let it pass). `format_transcript` calls it **before**
`normalize_heading_timestamps`, which matches only bracketed headings, and logs how many
headings it changed, with one example.

This is a code fix, not a prompt rule (the user's rule: loosen the check on output a
person would accept, don't add prompt rules).

| ID | Test (`tests/test_heading_brackets_hb.py`) |
|---|---|
| HB1.a | `test_hb1a_bare_paren_timestamp_gets_brackets` — the run's form `(00:00:19).` |
| HB1.b | `test_hb1b_each_loose_form_is_rewritten` — `(ts)`, `[ts]`, `([ts])`, each with and without `.` |
| HB1.c | `test_hb1c_canonical_heading_unchanged` — including one with trailing spaces (not counted as a fix) |
| HB1.d | `test_hb1d_non_heading_lines_untouched` — body line ending `(00:05:20).`, `### Section`, hyphen form, two- and four-group times, unpaired brackets, a stray time in the title |
| HB1.e | `test_hb1e_run_headings_pass_contract` — headings from the failed run pass `validate_section_headings` after the rewrite |
| HB1.f | `test_hb1f_format_stage_saves_brackets_and_logs` — `format_transcript` with a fake reply saves `([…]).` and logs the count |
| HB1.g | `test_hb1g_brackets_added_before_timestamp_correction` — `(00:33:00).` against raw `0:33` is saved as `([00:00:33]).` (call order) |

## HB2 — Not changed

- The prompt's format line. The code fix covers the class; a prompt edit would change
  every Format run's output for a case the code now handles.
- The calibration scripts under `docs/calibration/` that call `normalize_heading_timestamps`:
  they record how past calibrations were run.
- The transcription-tool text in the source (`en          ; ISO 639-1 code, or "auto" for
  detection`): it looks like a settings line with its comment leaking from the
  transcription tool, which is not in this repo. RS.3 puts it back into the formatted
  text, because it is in the source. Recorded in TODO.md.

## HB3 — Order

Tests first (HB1.a–f fail), then `normalize_heading_brackets`, then the call in
`format_transcript`, then CHANGELOG and TODO.

## Built

| ID | Status | Proof |
|---|---|---|
| HB1.a | done | `tests/test_heading_brackets_hb.py::test_hb1a_bare_paren_timestamp_gets_brackets` |
| HB1.b | done | `::test_hb1b_each_loose_form_is_rewritten` |
| HB1.c | done | `::test_hb1c_canonical_heading_unchanged` |
| HB1.d | done | `::test_hb1d_non_heading_lines_untouched` |
| HB1.e | done | `::test_hb1e_run_headings_pass_contract` |
| HB1.f | done | `::test_hb1f_format_stage_saves_brackets_and_logs` |
| HB1.g | done | `::test_hb1g_brackets_added_before_timestamp_correction` |

Full suite after the review fixes: 1835 passed, 26 skipped, 1 xfailed. On the failed run's own output,
the function fixed all 40 headings; `verify_source_fidelity` then reports only the
section 31 deletion, which RS.3 restores.

### Review fixes (learning-qa, 2026-10-19)

- **Call order was untested.** Swapping the bracket fix to after
  `normalize_heading_timestamps` passed every test, but then `(00:33:00).` against raw
  `0:33` is not corrected and Format stops. Added HB1.g; with the order swapped it fails.
- **The regex was wider than stated.** Opening and closing brackets were chosen
  independently (`(00:05:20]` matched), and a heading with a second timestamp in its
  title was rewritten and passed the contract. Brackets now pair, a heading with another
  time before the last is left for the validator, and both are in HB1.d.
- Adjacent, not fixed: the calibration scripts copy Format's post-processing steps
  inline; a shared post-processing function would keep them in step.
