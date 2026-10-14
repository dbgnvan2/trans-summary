# Plan: runs finish on output a person would accept (RS)

**Status:** awaiting approval (2026-10-14).

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
`prompts/revise_flagged_claims_v1.md`, one shared helper, used by summary, overview, blog
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
