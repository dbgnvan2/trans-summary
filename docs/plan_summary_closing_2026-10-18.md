# Plan: summary closing guard, best-draft tie-break, last-try log wording (SC1–SC3) — 2026-10-18

Status: **proposed 2026-10-18, waiting for approval.** No code changed yet.

## Why

On 2026-10-18 the run of "1 A and B Heartland Conference 2007 joe Holt interview" stopped
at Structured Summary (`logs/gui_20261018_173321.log`, 17:49–17:52). The summary failed
the faithfulness check on all three tries. Try 1's three flagged claims were fixed by
revision. Tries 2 and 3 each had one flagged sentence, both in the Closing Paragraph:

- Try 2: "…leaving the relationship between emotional process and psychiatric diagnosis
  as a productive open question." The transcript doesn't say this.
- Try 3: "Kerr closes by noting that Murray Bowen wanted to keep his theory open to new
  knowledge…, and expresses his own view that an interdisciplinary, systems way of
  thinking will eventually bring these ideas together." The first half is in the last
  section (33). The second half is Kerr's opening remark (Section 1), not his close.

**Cause.** The summary prompt says "State the conclusion, open questions, and future
directions" for the closing (`prompts/Summary Generation Prompt v1.md:31`). This
recording stops one paragraph into a panel discussion (Section 32 is "let's break till
three"; Section 33 is the last). It has no conclusion, open question or future direction,
so the model wrote them. The checker was right to flag try 2. Flagging try 3 is
defensible. The abstract prompt already has a guard for this ("If closing_conclusion is
empty, leave this component out"); the summary prompt has none.

**The closing fields in the JSON can't be used for the guard.** `summary_pipeline.extract_closing_content`
found a conclusion in **0 of 19** real formatted transcripts (the Downloads and
KCFC ALL project folders plus `tests/fixtures`). The open-question and future-direction
values it did find are mostly unrelated phrases ("next person in the queue", "questions,
Maisie?", "next day he came…"). So the guard is written in terms of the transcript,
and it tells the model not to rely on those fields.

Two smaller faults showed up in the same run:

- **Tie-break.** Tries 2 and 3 both had one flagged claim. The loop keeps the *first*
  draft with the fewest claims (`len(issues) < best_count`, `extraction_pipeline.py:1449`),
  so it saved try 2, whose sentence was invented, and not try 3, whose sentence only
  misplaced real content. With revision, a later draft is the earlier one with its flagged
  sentences fixed, so on a tie the later one should be kept.
- **Log wording.** The try-3 warning says "revising the flagged sentences". The
  attempts are used up, so no revision follows.

## Items, criteria and tests

New test file `tests/test_summary_closing_sc.py` unless a row names another file.

| ID | Criterion | Test | Status |
|---|---|---|---|
| SC1.a | The summary prompt no longer contains "State the conclusion, open questions, and future directions." The Closing Paragraph instruction says: (1) state a conclusion, open question or future direction only if the speaker gives one near the end; (2) if the talk ends without one (at a break, mid-discussion, or with thanks and goodbyes), close by restating the main point the speaker makes, without saying it comes at the end; (3) add none of the writer's own; (4) don't say the talk has no conclusion; (5) the `closing` fields in the JSON come from a phrase search and are often empty or wrong. | `test_sc1a_closing_asks_only_for_what_the_speaker_says` (reads the prompt file, checks the old sentence is gone and a key phrase from each of the five points is present) | not done |
| SC1.b | The guard reaches the model. The prompt `generate_summary` sends contains it, and `str.format` raises no error (no stray braces). | `test_sc1b_guard_is_in_the_prompt_sent` (fake `call_claude_with_retry` captures the prompt, as in `test_sl3_prompt_asks_for_more_than_the_check_accepts`) | not done |
| SC1.c | The summary review checklist (`summary_validation.generate_review_checklist`) no longer lists "Closes with conclusion" as if every talk had one. New line: "Closes with the speaker's conclusion, or the main point if the talk states none". | `test_sc1c_review_checklist_closing_line` | not done |
| SC1.d | **Live check, not in CI (LLM output).** Old prompt vs new prompt on four real transcripts, two first drafts each, each draft judged by the stage's own check (`_faithfulness_precheck`). A flagged claim counts as a closing flag when its text is in the Closing Paragraph. Pass: (1) new-prompt drafts have no more closing flags than old-prompt drafts; (2) no new-prompt draft says the talk has no conclusion; (3) on Societal Emotional Process, the new closing still gives the speaker's closing point (identity as the key issue); I quote every closing paragraph in the report so you can read them; (4) the real stage, run once on the Holt transcript with the new prompt, has no flagged claim in its Closing Paragraph. If the stage fails on a body sentence, I report that as it is. | Script `docs/calibration/2026-10-18_summary_closing/measure_closing.py`; results file next to it; report `docs/calibration_summary_closing_2026-10-18.md` | not done |
| SC2.a | `_generate_until_faithful`: when two judged drafts have the same number of flagged claims, the later one is kept. | `test_sc2a_tie_keeps_the_later_draft` (three fails of one claim each → "draft three" saved, returns False) | not done |
| SC2.b | Adversarial: a later draft with more flagged claims never replaces an earlier one with fewer. | `test_sc2b_fewer_claims_beat_a_later_draft` (1, 2, 2 claims → "draft one" saved) | not done |
| SC2.c | A draft rejected unjudged (it repeats a flagged claim) is still never kept, including on a tie. | `test_sc2c_unjudged_draft_never_kept_on_a_tie` (judged 1 claim, judged 1 claim, echo → "draft two" saved) | not done |
| SC2.d | The abstract's own retry loop (`generate_structured_abstract`) gets the same tie rule. It is the sibling loop (P5). | `tests/test_abstract_faithful_retry.py::test_sc2d_abstract_tie_keeps_the_later_draft` (reuses that file's `_setup`) | not done |
| SC3.a | `_generate_until_faithful`: the warning for the last try says "no attempts left", not "revising the flagged sentences" or "regenerating with corrective feedback". Earlier tries keep their wording. | `test_sc3a_last_try_does_not_say_it_will_revise` (logger mock; checks the warning text for tries 1–3) | not done |
| SC3.b | The abstract loop's last-try warning gets the same change. | `tests/test_abstract_faithful_retry.py::test_sc3b_abstract_last_try_wording` | not done |

Existing tests that cover the same code and must still pass unchanged:
`test_rfj2_summary_all_fail_keeps_best_and_fails`, `test_rs6e_all_tries_fail_still_blocks_or_warns`,
`test_rs6g_unjudged_echo_draft_is_never_kept`, `test_r11a_all_attempts_fail_returns_false_and_keeps_least_bad_draft`,
`test_summary_prompt_structure.py`, `test_sl3_prompt_asks_for_more_than_the_check_accepts`.
None of them has a tie, so SC2 doesn't change what they expect.

### SC1 prompt text (proposed)

Replaces line 31 of `prompts/Summary Generation Prompt v1.md`:

> End with the speaker's own conclusion, open questions or future directions, if the
> speaker gives them near the end of the talk. If the talk ends without them (it stops at
> a break, in the middle of a discussion, or with thanks and goodbyes), close by restating
> the main point the speaker makes in the talk, without saying that it comes at the end.
> In both cases, add no conclusion, open question or future direction of your own, and do
> not say that the talk has no conclusion. The `closing` fields in the JSON come from a
> phrase search and are often empty or wrong; take the closing from the transcript.

### SC1.d cases

Each case is copied into a scratch projects folder first, so no real project file is
overwritten.

| Case | Source | How the talk ends |
|---|---|---|
| Holt (this run) | `/Volumes/davemini/Downloads/projects/1 A and B Heartland…` | Recording stops one paragraph into a panel discussion |
| 2021 Webcast Sep Part 1 | `/Volumes/CrucialX9/1 MY DISK/KCFC ALL/projects/2021 Webcast Sep Part 1 - Michael Kerr - 2021-09-` | Part 1 stops mid-sentence |
| Societal Emotional Process | `tests/fixtures/prose_real/…2021-12-12_v-valid` | The speaker gives a closing point ("it all came down… to identity being the key issue"), then goodbyes |
| Systems Biology | `tests/fixtures/prose_real/…2021-06-25_20260718_155038` | Ends in Q&A with no closing statement |

Model: the stage's default (`config.settings.DEFAULT_MODEL`, now claude-sonnet-4-6),
judged by `config.FAITHFULNESS_JUDGE_MODEL` (claude-sonnet-5-5) with confirmation, as in
the run. **Cost: about $2.** The whole 3-try summary stage in this run cost $0.26
(`logs/token_usage.csv`). Sixteen judged first drafts are about $1.50, plus one stage run
on Holt. Judge verdicts vary from run to run, so with two drafts per case this is a check
that the change helps and doesn't make things worse, not a precise rate.

## Order

1. SC2 and SC3 tests first (they fail on the current code), then the change in both loops
   (`<` → `<=`; last-try wording) and their docstrings (`Spec:` this plan, `Tests:` the new
   names). Run the full suite.
2. SC1.a–c tests, then the prompt line and the checklist line. Run the full suite.
3. SC1.d: write the script, run it, write the report. If (1)–(4) don't hold, I stop and
   report before going further. A prompt that makes closings worse is not kept.
4. Documents: CHANGELOG entry; this plan's status and table; TODO.md, where the
   "Meta-claims about the talk get flagged" item gets its summary part marked done (the
   overview part stays open) and the adjacent issues below are added. README,
   ARCHITECTURE_DESIGN, DOCUMENT_REFERENCE and PROMPT_REGISTRY don't describe the closing
   instruction, the tie rule or the log wording (checked), so they need no change.
5. learning-qa review of the diff, fix its findings, commit. Push only when you say so.

Not affected: the faithfulness judge's prompt, extraction and parsing are unchanged, so
`config.JUDGE_LOGIC_VERSION` stays as it is and no judge re-calibration is needed.

## Not code-testable

- Whether the model follows the new closing instruction. SC1.d measures it on real
  transcripts. It can't be checked in CI without a live model, and a mocked model would
  test nothing.
- Whether the new closings read well. That's your judgement: the SC1.d report quotes every
  closing paragraph, old and new.

## Adjacent issues found, not fixed

- `summary_pipeline.extract_closing_content` finds no conclusion in 0 of 19 real
  transcripts. Its other two fields are mostly noise, and all three are still sent to the
  model in the JSON. Same class as the TODO item "Abstract conclusion detection has narrow
  phrase recall". The new prompt tells the model not to rely on them. Removing or fixing
  the extractor is a separate change. Note: `summary_validation` adds a "Closing:
  conclusion" coverage item only when a conclusion was found, so today that item never
  appears.
- The GUI stops the whole run when the summary fails faithfulness after keeping its best
  draft (`ts_gui.py:2725`, by design, RF.J.2). The release gate blocks publication anyway.
  Letting the run continue is a design decision for you, not part of this plan.
- The final error line shows "❌ ⚠️": the GUI adds ❌ to error lines and the message starts
  with ⚠️. Cosmetic.
- Not code: this run's filename has "Michael Kerrr" (three r's) and date 2026-01-26, while
  the title says 2007 and the original filename said 01-26-2006. Both go into metadata and
  page titles.
