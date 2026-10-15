# Plan: runs finish on output a person would accept (RS)

**Status:** approved 2026-10-14 (author: "approved, go ahead with RS.3 auto-restore");
built 2026-10-14. Status per criterion under "Built" at the end.

**Goal (author, 2026-10-14):** "I just want to get to a point where the run doesn't fail,
especially on warnings. If a human generated all these items they wouldn't be perfect. The
app just has to be very good, not perfect."

Faithfulness stays strict: a claim the transcript does not support still blocks. This plan
covers checks that stop a run on output a careful person would accept.

## Evidence: every stage failure in end-to-end runs 1–8

| Run | Talk | Failed stage | Cause | Status |
|---|---|---|---|---|
| 2, 7 | Systems Biology, Beautiful Boy | Gen Abstract (then the 4 publish stages) | judge flagged a claim, correctly | fixed (E2E1, AQ) |
| 2, 3 | Systems Biology, Beautiful Boy | Bowen + Emphasis | reply cut off at the token limit | fixed (E2E6) |
| 4 | Beautiful Boy | Format (then the 4 publish stages) | one dropped word, "that," | **open → RS.3** |
| 6 | Systems Biology | Format (then the 4 publish stages) | one dropped word, "the,"; one heading timestamp written `[00:01:02:04]` | **open → RS.3, RS.4** |
| 7 | Beautiful Boy | Format (then the 4 publish stages) | dropped "I just remember, I just" and "that" | **open → RS.3** |
| 7 | Beautiful Boy, Systems Biology | Structured Summary | 580 and 562 words, under the floor on all 3 tries | narrowed (SL3); **still possible → RS.1** |
| 8 | Beautiful Boy, Systems Biology | none | summary 516 words, then passed on retry; abstract 274 and 266 words, then passed on the third try | **risk → RS.1** |
| 8 | Why Families | Overview Post (then the 4 publish stages) | judge flagged one claim on each of 3 tries, a different one each time: a made-up Bowen quote ("Murray Bowen told him, 'You have to heal in the system'"), "webinar-style", "A reader without this framework may keep reacting." | **open → RS.6** |

A Format failure also blocks the four publish stages (source-fidelity blocker), so one dropped
word costs five failed stages.

## RS.1 — A word-count miss never fails summary, abstract or overview

`transcript_utils.call_claude_with_retry` gets `word_limits="hard"` (default, as today) or
`"soft"`. In soft mode a reply outside `min_words`/`max_words` is retried as today; after the
last try, the reply closest to the range is kept and a warning names its word count and the
range. Every other check stays hard: empty reply, cut-off reply, refusal, `check_reply`.
The kept reply's tokens are logged as a normal call; the dropped replies as rejected.

Soft: summary (553–780), abstract (under 250), overview (800 or more).
Hard: formatting (its floor is half the raw word count, a guard against a cut-off reply).

The summary and abstract validators already treat length as a warning, so a kept reply
passes them.

| ID | Test (`tests/test_run_safe_rs.py`) |
|---|---|
| RS.1.a | `test_rs1a_soft_keeps_closest_after_last_try`: replies of 516, 540, 530 words against 553–780 return the 540-word reply with a warning; old code raises |
| RS.1.b | `test_rs1b_soft_returns_first_reply_in_range`: no extra calls |
| RS.1.c | `test_rs1c_hard_still_raises`: default mode raises after the last try |
| RS.1.d | `test_rs1d_soft_does_not_soften_other_checks`: a `check_reply` ValueError still raises |
| RS.1.e | `test_rs1e_summary_abstract_overview_use_soft`: each caller passes `word_limits="soft"`; formatting does not |
| RS.1.f | `test_rs1f_kept_reply_logged_as_call_not_rejected`: token log labels |

## RS.2 — A retried check logs a warning, not an error

Today each retried miss logs "Response validation failed" at ERROR, so a stage that passed
shows "2 error(s)" (run 8, Systems Biology abstract). Log at WARNING when another try
follows; at ERROR only when the helper gives up.

| ID | Test |
|---|---|
| RS.2.a | `test_rs2a_retried_miss_logs_warning` |
| RS.2.b | `test_rs2b_final_miss_logs_error` |

## RS.3 — Format puts the source's words back by itself

**This changes RF.L** (every dropped or changed word waits for a person's decision).

After format validation finds differences that need review, and the gross limits are not
exceeded, each difference in plain text is set back to the source's words, using the review
tool's existing "reject" action. Each one is recorded in the review log (reviewer
`auto (RS.3)`) and logged as a warning, e.g. "Restored the source's words in section 63:
'that,'". Validation then runs again. The published transcript is then word-for-word the
source, so this does not weaken the source-fidelity check.

Unchanged: a difference at a heading or speaker label still opens the review window (the
review tool refuses to edit there); a run over the gross limits still fails ("re-run
formatting"); stutters, artifact tags and chapter titles stay auto-allowed. The review window
stays available for the person to run themselves.

Where: the GUI Format stage (`ts_gui._run_format_and_validate`), which the end-to-end runner
also uses. `validate_format` stays read-only for the CLI and for the after-review re-check.

| ID | Test |
|---|---|
| RS.3.a | `test_rs3a_dropped_word_restored_and_format_passes`: the file holds the word again, the record says passed |
| RS.3.b | `test_rs3b_restore_is_logged_and_recorded`: warning line and review-log entry |
| RS.3.c | `test_rs3c_heading_boundary_difference_still_needs_review` |
| RS.3.d | `test_rs3d_gross_limits_still_fail` |
| RS.3.e | `test_rs3e_release_gate_source_fidelity_passes_after_restore` |
| RS.3.f | `test_rs3f_gui_format_stage_restores` (stage returns True, no review window) |

## RS.4 — A heading timestamp with an extra `00:` group is corrected

Run 6 wrote `([00:01:02:04]).` for 1:02:04. When a heading has four time groups starting
with `00`, and the last three occur in the raw transcript, rewrite to `([01:02:04]).` (same
rule as RF.A.1: only when the raw transcript confirms the value).

| ID | Test |
|---|---|
| RS.4.a | `test_rs4a_extra_zero_group_rewritten` |
| RS.4.b | `test_rs4b_not_rewritten_when_raw_lacks_the_time` |

## RS.5 — A correct Q&A note is not sent to human review

Run 8: both abstracts have a real Q&A sentence ("The question period addressed …"), yet the
abstract check lists "UNCERTAIN Q&A note" for review on both. The item's keywords are 12
alternative phrases (`config.ABSTRACT_QA_NOTE_MARKERS`); any one of them shows the note is
there, but `check_keyword_coverage` scores them like topic keywords, so 1 hit of 12 is
"medium" and every medium item goes on the review list. Give `CoverageItem` an any-of mode
(`match_any=True`, used by the Q&A item only): one hit is high confidence, none is low.

| ID | Test |
|---|---|
| RS.5.a | `test_rs5a_one_qa_marker_is_high_confidence`: old code returns medium |
| RS.5.b | `test_rs5b_no_qa_marker_is_low`: an abstract without a Q&A sentence still goes to review |
| RS.5.c | `test_rs5c_topic_items_unchanged`: one keyword of many on a topic item stays medium (pinned decision, `test_summary_keyword_one_of_many_is_medium`) |

## RS.6 — After a failed faithfulness check, fix the flagged sentences instead of rewriting

Run 8, Why Families overview: each retry wrote a new overview from scratch. It dropped the
flagged claim and made a new one, so three tries never converged and the gate blocked. The
judge was right each time; the retry method is the problem. The same loop serves the
summary and blog (`extraction_pipeline._generate_until_faithful`); the abstract has its own
copy (`generate_structured_abstract`), which failed the same way in runs 2 and 7.

Change: try 1 writes the draft as today. Tries 2 and 3 send the previous draft and the
flagged statements (with the transcript, already cached) and ask the model to change only
the sentences that make them: say what the transcript supports, or remove the sentence.
Every other sentence stays as written, so it cannot gain new problems. New prompt
`prompts/Revise Flagged Statements v1.md`, one shared helper, used by summary, overview, blog
and abstract. The existing checks stay: a draft that repeats a flagged claim or the
instructions is rejected; the judge checks the whole revised draft; if claims remain after
the last try, the gate still blocks (overview, summary, abstract) or warns (blog).

Measured before landing (rule: measure prompt changes): run 8's kept Why Families overview
and kept drafts from earlier failed runs, revised and re-judged 5 times each, against 5
regenerations with feedback; count how many pass. About $1–2.

| ID | Test |
|---|---|
| RS.6.a | `test_rs6a_second_try_revises_previous_draft`: try 2 calls revise(previous draft, claims), not generate; old code has no revise path |
| RS.6.b | `test_rs6b_revise_prompt_has_draft_claims_and_keep_rule` |
| RS.6.c | `test_rs6c_revision_repeating_a_claim_is_rejected` |
| RS.6.d | `test_rs6d_summary_overview_blog_abstract_pass_revise` |
| RS.6.e | `test_rs6e_all_tries_fail_still_blocks` (overview), still warns (blog) |

## Order

RS.2 and RS.1 (same function), then RS.5, then RS.4, then RS.3, then RS.6 (measured first). Tests first for each. Then the
learning-qa review, one end-to-end round (about $6), docs (CHANGELOG, TODO, LEARNINGS,
DOCUMENT_REFERENCE) in the same commit.

## Not changed

- Faithfulness judges and their retries.
- Header validation noise (13–30 "problematic terms" warnings per talk; sections marked
  FAIL). It never fails a run; quieting it is a separate change.
- Advisory checks (key terms, abstract coverage, Q&A note) stay advisory.

## Built (2026-10-14)

| ID | Status | Evidence |
|---|---|---|
| RS.1.a | done | `tests/test_run_safe_rs.py::test_rs1a_soft_keeps_closest_after_last_try`, `::test_rs1a_soft_keeps_closest_over_the_top` |
| RS.1.b | done | `::test_rs1b_soft_returns_first_reply_in_range` |
| RS.1.c | done | `::test_rs1c_hard_still_raises`, `::test_rs1c_unknown_mode_is_refused` |
| RS.1.d | done | `::test_rs1d_soft_does_not_soften_other_checks`, `::test_rs1d_soft_does_not_keep_too_few_characters`, `::test_rs1d_soft_keeps_earlier_miss_when_last_try_fails_otherwise` |
| RS.1.e | done | `::test_rs1e_summary_and_abstract_use_soft_limits`, `::test_rs1e_formatting_keeps_hard_limits`, `tests/test_overview_post.py::test_rs1e_overview_word_floor_is_soft` |
| RS.1.f | done | `::test_rs1f_kept_reply_logged_as_call_not_rejected` |
| RS.2.a | done | `::test_rs2a_retried_miss_logs_warning` |
| RS.2.b | done | `::test_rs2b_final_miss_logs_error`, `::test_rs2c_soft_keep_logs_no_error` |
| RS.3.a | done | `::test_rs3a_dropped_word_restored_and_format_passes` |
| RS.3.b | done | `::test_rs3b_restore_is_logged_and_recorded` |
| RS.3.c | done | `::test_rs3c_heading_boundary_difference_still_needs_review`, `::test_rs3c_restores_plain_ones_and_leaves_boundary_one` |
| RS.3.d | done | `::test_rs3d_gross_limits_still_fail` |
| RS.3.e | done | `::test_rs3e_release_gate_source_fidelity_passes_after_restore` |
| RS.3.f | done | GUI stage covered by RS.3.a–d (they run `_run_format_and_validate`); `validate_format` stays read-only: `::test_rs3f_validate_format_stays_read_only` |
| RS.4.a | done | `::test_rs4a_extra_zero_group_rewritten` |
| RS.4.b | done | `::test_rs4b_not_rewritten_when_raw_lacks_the_time` |
| RS.5.a | done | `::test_rs5a_one_qa_marker_is_high_confidence` |
| RS.5.b | done | `::test_rs5b_no_qa_marker_is_low`, `::test_rs5b_correct_note_leaves_no_review_item` |
| RS.5.c | done | `::test_rs5c_topic_items_unchanged` |
| RS.6.a | done | `::test_rs6a_second_try_revises_previous_draft`, `::test_rs6a_third_try_revises_the_second_draft` |
| RS.6.b | done | `::test_rs6b_revise_prompt_has_draft_claims_and_keep_rule` |
| RS.6.c | done | `::test_rs6c_revision_repeating_a_claim_is_rejected` |
| RS.6.d | done | `::test_rs6d_summary_passes_revise`, `tests/test_abstract_faithful_retry.py::test_rs6d_abstract_retry_revises_previous_draft`, `tests/test_run_fixes_rf.py::test_rfj2_blog_regenerates_with_feedback` (blog revise prompt), `tests/test_overview_post.py::test_rs6d_overview_retry_revises_previous_draft` |
| RS.6.e | done | `::test_rs6e_all_tries_fail_still_blocks_or_warns` |
| RS.6 measurement | done | Measured (`docs/calibration/2026-10-14_revise_flagged/`, $2.17): from three kept drafts that had failed every try (run 8 Why Families overview; runs 7 and 2 abstracts), one retry on the production models passed 10 of 11 times by revising and 10 of 11 by rewriting. Revising changed 1–5% of the draft, rewriting 44–79%; revise's one failure was a sentence it had not touched (already in the draft, flagged in run 7 too). The gain is that a retry no longer starts over: only the changed sentences can bring a new problem. Results: `results_overview_sonnet55.txt`, `results_all_cases_first_run.txt` (its overview rows ran on claude-sonnet-4-6, not the production model; re-run on claude-sonnet-5-5). |

### Review fixes (learning-qa, 2026-10-14)

| Finding | Fix | Test (`tests/test_run_safe_rs.py` unless named) |
|---|---|---|
| A held near-miss reply was lost, unlogged, when a later try raised (timeout, cut-off) | one success path (`_accept`); a later failure returns the held reply | `test_rs1d_held_reply_kept_when_later_try_times_out`, `_when_later_reply_is_cut_off`, `test_rs1d_no_held_reply_still_raises_on_api_error` |
| Soft limits had no outer bound (a 56-word non-answer kept as an overview) | keep only within `config.SOFT_WORD_LIMIT_TOLERANCE` (25%) of the range | `test_rs1g_far_miss_is_not_kept` |
| The Format stage's first check logged "Validation FAILED" (errors) before restoring | `validate_format(review_as_warning=True)` on the first check; the final check reports in full | `test_rs3a_*` (no error records, no ❌), `test_rs3c_heading_boundary_*` (errors when nothing restorable) |
| Placeholders in CHANGELOG and plan; wrong prompt file name | filled after the measurement; name corrected | — |
| The kept-length warning for summary and abstract went to module loggers the GUI does not show | the stage logs it (`_note_length`) | `test_rs1h_stage_log_names_a_kept_length_miss`, `tests/test_abstract_faithful_retry.py::test_rs1h_*` |
| A revision got no check for a comment before the text, echoed instructions, or a dropped front matter / heading | `_revise_reply_check` as the revision's `check_reply`; phrases in `config.REVISE_PREAMBLE_STARTS` | `test_rs6f_revision_reply_check`, `test_rs6f_revise_passes_the_reply_check` |
| A draft rejected for repeating a claim was never judged but could be kept as "best" | only judged drafts compete | `test_rs6g_unjudged_echo_draft_is_never_kept` (two RF.J.2 tests had one-letter claims that matched inside "draft 2"; fixed) |
| Q&A markers matched inside words ("question periodically") | whole-word match | `test_rs5d_qa_markers_match_whole_words` |
| Restore trusted a possibly stale check record | restore only when the record's hashes match the current formatted text and raw source | `test_rs3g_stale_check_record_restores_nothing` |
| Automatic restores counted with a person's rejects | counted apart (`auto_restored`) | `test_rs3b_restore_is_logged_and_recorded` |

Not changed: a revision that removes sentences from an overview just over 800 words can fall under the floor and costs two more calls before the closest is kept; the abstract loop still lacks the echo check (TODO).

## End-to-end run 9 (commit 59d64c8, $6.62)

All 39 stages passed on the three public talks; the gate allowed all three
(ALLOW_WITH_WARNINGS). Every faithfulness retry passed by its second revision (abstract
twice, summary once, overview three times, blog once). No length miss had to be kept.
Format was clean on all three talks, so RS.3 did not run live; replayed offline on the
real Format failures of runs 4, 6 and 7, it restored the dropped words, RS.4 fixed run
6's heading, the stage passed, and after the YAML step the gate's source check passed.

Follow-ups (same day): the revision check keeps front matter by the extractor's own
rule instead of the first line (a flagged title must stay fixable; run 9 showed
metadata judged as claims after a revision); the abstract Q&A check uses the
generator's threshold (`config.abstract_wants_qa_note`).
