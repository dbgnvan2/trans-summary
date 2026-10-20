# Plan: remove sentences still flagged after revision (RM0–RM9)

Status: **built 2026-10-19** (RM1–RM6). Approved 2026-10-19: "build RM1–RM6 with D1 off,
D2 yes, D3 leave blog out, D4 yes, D5 25%, D6 by hand." See **Built** at the end for each
ID and where the code differs from the text below.

## Why

- Since WO (2026-10-19, `docs/plan_warn_only_2026-10-19.md`) faithfulness flags warn and
  never block. When three attempts leave flagged sentences, the best draft is kept with
  them in it. The gate lists them; nothing takes them out.
- The WRONG-rule test (review branch `review/independent-2026-10-19`,
  `docs/calibration/2026-10-19_wrong_rule/`) found no prompt that separates WRONG from NOT
  QUITE RIGHT well enough to block on. The proposed rule caught 12 of 18 clear WRONG
  claims and would have blocked 17 of 42 clear NOT QUITE RIGHT ones. The severity step
  in use (`majority3`) is calibrated safe but downgrades almost no flags (0 of 12 and 2 of
  17 NOT QUITE RIGHT flags in `docs/calibration_judge_severity_2026-10-19.md`).
- So a judge verdict is not good enough to fail a run on, but a flagged sentence can be
  taken out. Removing a sentence cannot add a wrong statement. The run stays green; Dave
  sees every removed sentence at the end of the run and can put any back.

**Change from what I described in chat:** the removal is done in code, not by another LLM
call. The judge's claims are the artifact's own sentences (`extract_claims` is
deterministic), so code can find and delete them exactly. No new API calls.

## RM0 — Evidence (measured, no API calls)

Scripts and logs: `docs/calibration/2026-10-19_remove_flagged/` (`locate.py`,
`locate_output.txt`, `replay.py`, `replay_output.txt`).

**Locate rate.** Every artifact on disk in the three projects folders; each claim from
`extract_claims(text, source)`, with the FAQ tag `[in answer to: …]` removed
(`faithfulness_judge._claim_body`), looked up verbatim in the file:

| Artifact | Files | Claims | Found verbatim |
|---|---|---|---|
| summary | 3 | 110 | 110 |
| overview | 1 | 68 | 68 (15 of them also appear in the front-matter `faq` answers) |
| abstract | 15 | 105 | 105 |

The sample is small (3 summaries, 1 overview). A claim the code cannot find is kept with
a warning (RM1.c), so a lower rate elsewhere means less is removed, never a wrong removal.

**Replay.** The 12 summary drafts of the WO6 calibration
(`docs/calibration/2026-10-19_outside_facts/results.json`); 5 had flags. A scratch
prototype removed each flagged sentence and checked that the claims left equal the
unflagged claims before (RM1.g):

| Draft | Flagged | Removed | Words | Share removed | Check |
|---|---|---|---|---|---|
| 2021 Webcast Jan Societal Regression, k=1 | 1 | 1 | 797 → 778 | 2.4% | ok |
| 2021 Webcast Jan Societal Regression, k=2 | 1 | 1 | 769 → 739 | 3.9% | ok |
| 2021 Webinar Mar, k=2 | 3 | 3 | 808 → 736 | 8.9% | ok |
| 2021 Webinar April, k=1 | 1 | 1 | 761 → 717 | 5.8% | ok |
| 2021 Webinar April, k=2 | 3 | 3 | 765 → 695 | 9.2% | ok |

These drafts are first drafts. In a real run the revise step runs first, so fewer
sentences are left by the time removal runs.

**Correction after the build.** The scratch prototype had no RM1.f rule. The built code
(`tests/test_remove_flagged_rm.py::test_rm1g_replay_drafts_pass_check`, cap 25%) removes
8 of the 9 flagged sentences; the ninth is the only sentence under "Closing Paragraph"
and is kept by RM1.f. The deletion-only check passes on all 5 drafts.

## RM1 — The removal function

New module `flagged_removal.py`, pure functions (no file or API access), so each rule is
tested without a run. `remove_flagged_sentences(text, claims, *, source=None, names=())`
returns `(new_text, removed, kept)`: `removed` holds each removed sentence with the
sentence before and after it; `kept` holds each claim not removed with the reason.

| ID | Rule |
|---|---|
| RM1.a | A flagged claim (FQ tag removed) is removed where it is a whole sentence of the body, as `extract_claims` splits it, together with the space that separated it from its neighbour. Every occurrence in the body is removed. |
| RM1.b | A list item or line left with no text (only a list marker, or only a bold label such as `**Label:**`) is removed; runs of blank lines collapse to one. |
| RM1.c | A claim that is not found as a whole sentence is kept, with its reason: a heading claim, a name re-emitted from a heading or bold label, or not found. Headings are never edited. |
| RM1.d | A flagged sentence that is only part of a longer, unflagged sentence is not removed (adversarial, P7): "Kerr says X." is flagged, "Michael Kerr says X." is not. |
| RM1.e | Front matter: when a removed sentence also appears in the overview's front-matter `faq` answers, it is removed there too, so the page's FAQ data does not keep it. An answer left empty removes its `q`/`a` pair. The front matter must still parse with the same parser the page builder uses. |
| RM1.f | The last sentence under a heading is kept (reason: "only text under heading …"), so no section is left empty. |
| RM1.g | **Deletion-only check.** The result is used only if (1) a word-level diff of input to output has no insertions or replacements, only deletions; (2) `extract_claims(output)` equals `extract_claims(input)` minus the removed claims, in order; (3) headings and front-matter keys are unchanged. If any part fails, the input is returned unchanged, every claim goes to `kept` with "deletion check failed", and the caller warns. |
| RM1.h | **Share cap.** If the removals would take out more than `config.FAITHFULNESS_REMOVE_MAX_SHARE` of the body's words (D5: 0.25; the replay's largest was 9.2%), nothing is removed and the caller warns with the count and the share it would have removed. |
| RM1.i | With `names` (D4): each sentence of the body that contains a rejected name as a whole word is removed under the same rules. A name in a heading or the front matter cannot be removed and is kept with that reason. |

## RM2 — Wiring into generation

| ID | Rule |
|---|---|
| RM2.a | `_generate_until_faithful` keeps the best draft's issues as well as its text. After the last attempt, when the best draft has flags and the artifact is in `config.FAITHFULNESS_REMOVE_ARTIFACTS`, it calls the removal on the best draft, saves the result, and logs at the stage each removed sentence and each kept one with its reason (P2: "Removed 2 of 3 flagged sentence(s) from the summary: …; kept 1: …"). Applies to the summary and the overview. |
| RM2.b | The abstract's own loop (`generate_structured_abstract`) does the same after its last attempt. |
| RM2.c | The blog (`advisory=True`) is never changed (D3). With `config.FAITHFULNESS_REMOVE_FLAGGED = False`, every artifact behaves as today. |
| RM2.d | After a removal the entity check (`release_gate.check_entity_grounding`, lexical, free) runs again on the saved file. The stage result follows it, as in WO4: it fails only if a rejected name is still there. |
| RM2.e | **Summary coverage guard.** `summary_coverage` blocks publication. A sentence is not removed from the summary when removing it would drop a required coverage item (`summary_validation.generate_coverage_items`, `required=True`) to low keyword confidence (`check_keyword_coverage`); it is kept with the reason "only mention of required item …". Otherwise a removed sentence that was in fact fine could block publication, which the policy does not allow. |
| RM2.f | The faithfulness judge is not run again after a removal (it would be a full judge run per artifact). The gate judges the cleaned file at publish, as it does today for a kept draft (its cache key is the file's hash, and only a PASS is cached), and any new flag there is a warning. |
| RM2.g | A draft that passes on some attempt, or whose check is unavailable, is not touched, and no record is written for it. |
| RM2.h | The record needs the judge's label and reason for each removed claim. `_faithfulness_precheck` gets an optional argument that collects them; the blog precheck and the test fakes keep their current form. `release_gate._wrong_records` adds the first-pass `rationale` (an added key; nothing that reads the items changes). |

## RM3 — The record file

| ID | Rule |
|---|---|
| RM3.a | `<base> - removed-sentences.json` (`config.SUFFIX_REMOVED_SENTENCES`) in the project folder. One entry per artifact: removal time, the run's start time, the saved file's sha256, the draft before removal, and per removed sentence the sentence, the sentence before and after it, the reason (faithfulness, or the rejected name), the judge's label and rationale, and the severity evidence when there is one. Kept claims with their reasons. |
| RM3.b | The record is written before the artifact. If it cannot be written, nothing is removed and the stage warns: a removal is never made without its record. |
| RM3.c | Each generation of an artifact replaces that artifact's entry; a generation that removes nothing deletes it. Entries for other artifacts are left alone (P8). |

## RM4 — The end-of-run list

| ID | Rule |
|---|---|
| RM4.a | `flagged_removal.format_run_removals(base_name, since)` returns the list for one run: entries removed at or after the run's start, grouped by artifact, each sentence with the judge's reason and the sentence after it (where a "This …" or "He …" may have lost its referent), then the kept claims, then the record's path. An entry whose artifact file has changed since (sha256 differs) is listed as "file changed since; not shown". With no removals it says so in one line. |
| RM4.b | The GUI (`ts_gui._run_selected_stages`) logs it before the Token Usage Report on all three exits: complete, failed and paused. A resumed run uses its first start time, as the token report does. It is printed only when the run included the summary, overview or abstract stage. |
| RM4.c | The CLI (`transcript_process.main`) prints the same list before its token report (one function for both, P25). |
| RM4.d | Putting a sentence back: Dave edits the artifact by hand, using the record's sentence and its neighbours (D6). No restore command in this plan. |

## RM5 — Config

All in `config.py` (P4): `FAITHFULNESS_REMOVE_FLAGGED = True`,
`FAITHFULNESS_REMOVE_ARTIFACTS = ("summary", "overview", "abstract")`,
`FAITHFULNESS_REMOVE_MAX_SHARE = 0.25`, `SUFFIX_REMOVED_SENTENCES = " - removed-sentences.json"`,
and, if D1 is approved, `FAITHFULNESS_SEVERITY_MODE = "off"`.

## RM6 — Tests

New file `tests/test_remove_flagged_rm.py` unless a row names another. The first test
written is RM1.g (the deletion-only check), then RM1.d (the adversarial case), then
RM2.a (most likely to regress).

| ID | Test |
|---|---|
| RM1.a | `test_rm1a_flagged_sentence_removed_rest_unchanged`, `test_rm1a_fq_tag_ignored`, `test_rm1a_every_occurrence_removed` |
| RM1.b | `test_rm1b_bullet_left_empty_is_removed` (marker only, and bold label only) |
| RM1.c | `test_rm1c_heading_and_reemitted_name_kept_with_reason`, `test_rm1c_claim_not_found_kept` |
| RM1.d | `test_rm1d_part_of_longer_sentence_not_removed` |
| RM1.e | `test_rm1e_faq_copy_removed_front_matter_parses`, `test_rm1e_empty_answer_drops_pair` (fixture: the Kerr 2026-09-13 overview's front matter) |
| RM1.f | `test_rm1f_last_sentence_under_heading_kept` |
| RM1.g | `test_rm1g_changed_text_rejected_draft_unchanged` (a removal patched to change one word: the input comes back and every claim is kept), `test_rm1g_replay_drafts_pass_check` (the 5 flagged WO6 drafts) |
| RM1.h | `test_rm1h_cap_keeps_draft_and_announces` (a real-length draft whose flagged sentences are over 25% of its words) |
| RM1.i | `test_rm1i_name_sentences_removed`, `test_rm1i_name_in_heading_kept` |
| RM2.a | `test_rm2a_summary_last_attempt_sentence_removed_and_saved`, `test_rm2a_overview_sentence_removed_and_saved` (fake generate and precheck; the saved file, the stage result and the log line) |
| RM2.b | `test_rm2b_abstract_sentence_removed_and_saved` |
| RM2.c | `test_rm2c_blog_not_changed`, `test_rm2c_switch_off_keeps_flagged_draft` |
| RM2.d | `test_rm2d_entity_check_rerun_on_saved_file` |
| RM2.e | `test_rm2e_only_mention_of_required_item_kept` |
| RM2.f | `test_rm2f_no_judge_call_after_removal` (counts precheck calls) |
| RM2.g | `test_rm2g_passing_draft_untouched_no_record` |
| RM2.h | `test_rm2h_record_has_judge_rationale`; the existing WO and JS tests stay green |
| RM3.a | `test_rm3a_record_fields` |
| RM3.b | `test_rm3b_record_write_fails_nothing_removed` |
| RM3.c | `test_rm3c_dirty_state_clean_regeneration_clears_entry` (P8: run 1 removes a sentence, run 2 passes clean; the entry is gone and run 2's list is empty) |
| RM4.a | `test_rm4a_lists_this_run_only`, `test_rm4a_changed_file_not_shown`, `test_rm4a_none_says_so` |
| RM4.b | `tests/test_ts_gui_run_all.py::test_rm4b_list_before_token_report_on_complete_fail_pause` |
| RM4.c | `test_rm4c_cli_prints_list` |
| RM5 | `test_rm5_config_values` (types; each artifact name maps to a suffix) |

**Not testable in code (human review):** whether a summary reads well after a removal,
for example a following "This …" that lost its referent. RM4.a prints the sentence after
each removal for that reason. Proposal: after the first real run, Dave reads the list
and says whether any removal left the text broken; if so, that becomes a rule here.

## RM7 — Not changed

- The revise step and its prompt (`Revise Flagged Statements v1.md`). It already may
  rewrite or drop a sentence; removal only acts on what is left after the last attempt.
- The gate. It still judges every artifact at publish and lists flags as warnings.
- The blog (D3).
- No restore command (D6).
- Adjacent issue, not fixed: the abstract has its own copy of the generation loop instead
  of `_generate_until_faithful`, so RM2 wires removal into both. Moving the abstract onto
  the shared loop would remove the copy; that is a separate change.

## RM8 — Order

1. RM1 tests (fail), then `flagged_removal.remove_flagged_sentences`, in the order of RM6.
2. RM5 config.
3. RM3 record and RM2.h judge details.
4. RM2 wiring: shared loop, then the abstract loop.
5. RM4 list: the format function, then the GUI, then the CLI.
6. D1 config change, if approved.
7. Docs: `ARCHITECTURE_DESIGN.md` §4.3 (faithfulness paragraph), `PROJECT_STATUS.md` policy
   line, `CHANGELOG.md`, `TODO.md`, this plan's status and a Built table.
8. Full suite, then the `learning-qa` review of the diff, fixes, commit.

## RM9 — Decisions for Dave

| ID | Question | Recommended |
|---|---|---|
| D1 | Turn the severity step off (`FAITHFULNESS_SEVERITY_MODE = "off"`)? With removal, the step's only effect is that a downgraded flag is kept instead of removed, and it downgrades almost none (0–2 of 12–17 in the calibrations). Off saves 1–3 judge calls per flag, at generation and at the gate, and one moving part. The NQ plan (`docs/plan_severity_downgrade_2026-10-19.md`) would then not be needed. | Off |
| D2 | Include the abstract? Its length check only warns, so a shorter abstract does not fail anything. | Yes |
| D3 | Leave the blog out? It has its own advisory check and is written for a different reader. | Yes, leave it out |
| D4 | Also remove sentences with a name the entity check rejects, so the stage stops failing on them? If the name is in a heading or the front matter, the stage still fails as today. | Yes |
| D5 | Share cap: remove nothing if removals would take more than 25% of the words? | 25% |
| D6 | Put sentences back by hand from the record for now, with a restore command only if you find you need it? | By hand |

## Built (2026-10-19)

Tests: `python3 -m pytest tests/test_remove_flagged_rm.py tests/test_ts_gui_run_all.py`.

| ID | Status | Proof |
|---|---|---|
| RM1.a | done | `flagged_removal.remove_flagged_sentences`; `test_rm1a_flagged_sentence_removed_rest_unchanged`, `test_rm1a_fq_tag_ignored`, `test_rm1a_every_occurrence_removed`, `test_rm1a_last_sentence_of_line_takes_space_before`, `test_rm1a_bold_inside_sentence_removed`, `test_rm1a_partly_removed_flag_listed_as_kept` |
| RM1.b | done | `test_rm1b_bullet_left_empty_is_removed`, `test_rm1b_paragraph_removed_without_double_blank` |
| RM1.c | done | `test_rm1c_heading_and_reemitted_name_kept_with_reason`, `test_rm1c_claim_not_found_kept` |
| RM1.d | done | `test_rm1d_part_of_longer_sentence_not_removed` |
| RM1.e | done | `test_rm1e_faq_copy_removed_front_matter_parses`, `test_rm1e_empty_answer_drops_pair` |
| RM1.f | done | `test_rm1f_last_sentence_under_heading_kept` |
| RM1.g | done | `flagged_removal.deletion_problems`; `test_rm1g_changed_text_rejected_draft_unchanged`, `test_rm1g_replay_drafts_pass_check`, `test_rm1g_check_names_each_problem` |
| RM1.h | done | `test_rm1h_cap_keeps_draft_and_announces` |
| RM1.i | done | `test_rm1i_name_sentences_removed`, `test_rm1i_name_in_heading_kept`, `test_rm1i_name_left_in_label_listed_as_kept` |
| RM2.a | done | `extraction_pipeline._remove_still_flagged`; `test_rm2a_summary_last_attempt_sentence_removed_and_saved`, `test_rm2a_overview_sentence_removed_and_saved` |
| RM2.b | done | `test_rm2b_abstract_sentence_removed_and_saved` |
| RM2.c | done | `test_rm2c_blog_not_changed`, `test_rm2c_switch_off_keeps_flagged_draft` |
| RM2.d | done | `test_rm2d_entity_check_rerun_on_saved_file`, `test_rm2d_name_in_heading_stage_still_fails` |
| RM2.e | done | `extraction_pipeline._coverage_guard`; `test_rm2e_only_mention_of_required_item_kept`, `test_rm2e_keyword_in_bold_label_kept`, `test_rm2e_unplaced_item_keeps_every_sentence` |
| RM2.f | done | `test_rm2f_no_judge_call_after_removal` |
| RM2.g | done | `test_rm2g_passing_draft_untouched_no_record` |
| RM2.h | done | `test_rm2h_record_has_judge_rationale`; `tests/test_judge_severity_js.py` updated for the added `rationale` key |
| RM3.a | done, one field differs | `removal_record.write_entry`; `test_rm3a_record_fields` |
| RM3.b | done | `test_rm3b_record_write_fails_nothing_removed`, `test_rm3b_artifact_save_fails_stage_goes_on` |
| RM3.c | done, changed | `removal_record.clear_entry`; `test_rm3c_dirty_state_clean_regeneration_clears_entry`, `test_rm3c_refused_removal_recorded_and_listed` |
| RM4.a | done | `removal_record.format_run_removals`; `test_rm4a_lists_this_run_only`, `test_rm4a_changed_file_not_shown`, `test_rm4a_none_says_so` |
| RM4.b | done | `ts_gui._log_removed_sentences`; `tests/test_ts_gui_run_all.py::test_rm4b_list_before_token_report_on_complete_fail_pause` (also a stage that raises) |
| RM4.c | done, wider | `removal_record.print_run_removals`; `test_rm4c_cli_prints_list` (`transcript_summarize`), `test_rm4c_overview_cli_prints_list` (`transcript_overview`), `test_rm4c_process_cli_prints_list_on_both_exits` (source check; `main` is interactive) |
| RM4.d | done | no restore command; the list ends "To put a sentence back, edit the artifact by hand." |
| RM5 | done | `config.py`; `test_rm5_config_values` |
| D1 | done | `config.FAITHFULNESS_SEVERITY_MODE = "off"`; `test_rm5_config_values` |
| Human review | open | Read the first real run's list for a "This …" or "He …" that lost its referent (`TODO.md`). |

**Where the code differs from the text above:**

- **Signature (RM1).** `remove_flagged_sentences(text, flags, *, max_share, guard=None)`.
  Each flag is a `flagged_removal.Flag`, a `str` with `kind` ("claim" or "name"), `name`
  and the judge's `record`; a rejected name is a flag of kind "name" (RM1.i), not a
  separate `names` argument. `guard` is the summary coverage check (RM2.e).
- **RM1.f.** A section is left as it is, with its flags kept, when every sentence in it
  would be removed: "the last sentence" is the one left when the others are removed.
- **RM1.e front matter.** It is checked by structure, not parsed: each edited `a:` line
  must still be one double-quoted value, and the keys must be unchanged. PyYAML is a
  dev-only dependency, so runtime code does not import it; the tests parse the result
  with `yaml.safe_load`. When the FAQ copy cannot be removed, the body sentence is still
  removed and the kept reason says "still in the front matter's FAQ answers".
- **RM2.a log line.** "⚠️ Summary: removed N sentence(s) still flagged after the last
  attempt; K of M flagged item(s) left in. Record: … Removed: …", then "Summary: not
  removed: …" with each kept claim and its reason.
- **RM2.h.** The judge details travel on the `Flag` objects the prechecks return
  (`extraction_pipeline._claim_flags`, `_name_flags`), not in an extra argument to
  `_faithfulness_precheck`.
- **RM3.a.** The entry has no run-start field. RM4.a compares each entry's `removed_at` with
  the run's start time, which gives the same list.
- **RM3.c.** The entry is cleared when the stage writes its first new draft, not when the
  stage starts, so a stage that fails before writing anything keeps the old entry, which
  still matches the file on disk. When the kept draft has flags but nothing could be
  removed (cap, deletion check, section rule, not found, or an error), an entry with no
  removals and the kept flags is written, so the list shows "nothing removed" and the
  flags left in instead of "none this run" (learning-qa F3).
- **RM4.a.** The function is `removal_record.format_run_removals`, not in
  `flagged_removal`, which has no file access. An entry whose file changed is shown as
  "the file has changed since the removal; see the record."
- **RM4.c.** `transcript_process.main` step 4 runs `transcript_summarize.py` without
  `--generate-structured`, so on that path nothing is removed. The list is therefore also
  printed by the two scripts that can remove sentences, `transcript_summarize.py` and
  `transcript_overview.py` (learning-qa F2). Under `transcript_process.main` they do not
  print it (`removal_record.LISTED_BY_PARENT_ENV`); `transcript_process.main` prints it
  once, in a `finally` right after step 4 (cold sweep). `transcript_process.main` is
  interactive, so its test checks the source.
- **The removal step cannot fail a stage.** An error in it is logged and the draft is kept
  as it is; the coverage items for the guard are built inside that step. If saving the
  cleaned draft fails after the record is written, the draft is saved again as it was,
  the flags are recorded as kept, and the stage goes on (learning-qa F5; changed by the
  cold sweep, which found that clearing the entry undid F3). If that re-save also
  fails, the stage fails.
- **A flag removed in one place and kept in another** (a section's only text, a bold label,
  a heading, a coverage item) is listed as kept: "removed in part; one copy kept: …"
  (learning-qa F1). A coverage keyword in a bullet's bold label counts for that bullet's
  sentence; an item the guard names that no removed sentence mentions keeps every
  removal (learning-qa F4).
- **Review.** learning-qa ran on the diff before the commit and found 5 issues (F1–F5);
  all are fixed here, with the tests named above. The fixes were not re-reviewed.

## Cold sweep (2026-10-19, Mac mini1)

Three reviewers with no context from the writing session (learning-qa, correctness,
security) swept `28d37dd..8388592`; learning-qa and a correctness reviewer then swept the
fixes. Fixed on branch `fix/rm-cold-sweep-2026-10-19` (commits 11ef191, 347400b, b1a8b78),
each with a test that fails without it:

| Finding | Fix | Test |
|---|---|---|
| Two flags on one sentence cut it twice: an unflagged neighbour deleted, or every removal refused | one span per sentence; one Removed entry naming both reasons | `test_rm1i_claim_and_name_flag_same_sentence_cut_once`, `test_rm1a_fq_tagged_and_plain_copy_section_not_emptied`, `test_rm4a_two_reasons_listed` |
| The deletion check compared claims only, so a lost short sentence passed | every body sentence is checked | `test_rm1g_short_unflagged_sentence_lost_rejected` |
| `_EMPTY_LINE` backtracked exponentially on a run of list markers (a hang) | one marker per repetition | `test_rm1b_marker_run_line_does_not_backtrack` (child process with a timeout) |
| A split after "U.S.", "Ph.D.", "Sen.", "et al.", a month, or before a number left a fragment | such a split is uncertain: a claim there is kept ("sentence boundary uncertain"); a name takes the whole sentence. List: `config.FAITHFULNESS_REMOVE_UNSURE_ABBREVIATIONS` | `test_rm1a_unsure_sentence_boundary_kept`, `test_rm1a_unsure_boundary_more_abbreviations`, `test_rm1a_unsure_copy_kept_other_copy_removed`, `test_rm1i_name_in_unsure_split_takes_whole_sentence` |
| A removed sentence in an FAQ answer that is not one double-quoted line stayed, unreported | listed as kept, "still in the front matter's FAQ answers" | `test_rm1e_unreadable_faq_answer_listed_as_kept` |
| Older than the sweep: a bold lead sentence ("**Kerr says X.** …") was dropped with the line, unrecorded | bold text that ends like a sentence is not a label | `test_rm1b_bold_lead_sentence_not_dropped` |
| RM2.e: the guard skipped required items already at low keyword confidence, which the gate decides with an LLM check | such an item keeps the claim sentences ("could not place required item"); a name sentence still goes, and a claim in it is not listed as kept | `test_rm2e_item_already_low_keeps_claims_not_names`, `test_rm1i_claim_and_name_same_sentence_unplaced_item_not_kept` |
| F5: a failed save cleared the record (list said "none"); a failed re-save returned success over a possibly truncated file | flags recorded as kept; a failed re-save fails the stage | `test_rm3b_artifact_save_fails_stage_goes_on`, `test_rm3b_partial_save_restores_kept_draft`, `test_rm3b_both_saves_fail_stage_fails` |
| The catch around removal had no test | — | `test_rm2_removal_error_stage_goes_on` |
| "Every flagged sentence removed" when only names were flagged, or the judge errored | message built from the flags (`_all_removed_message`) | `test_rm2_names_only_message`, `test_rm2_partial_check_message_says_not_checked` |
| An unreadable record listed as "none this run"; the GUI passed no logger | says the record could not be read | `test_rm4a_unreadable_record_not_reported_as_none` |
| The CLI list printed twice, then (first fix) lost on a Ctrl-C after step 4 | `transcript_process` prints it once, in a `finally` after step 4; the scripts it runs do not | `test_rm4c_process_cli_prints_list_on_both_exits`, `test_rm4c_list_printed_once_under_transcript_process` |
| The kept reason for a body copy that could not be located said "heading, label or front matter" | "not found as a whole sentence" | `test_rm1a_body_copy_not_located_reason` |

**Trade-off for Dave (RM2.e):** a summary with any required coverage item at low keyword
confidence (including an item with no keywords) now keeps all its flagged claim sentences,
since the code cannot tell which sentence the gate's LLM check relies on. Names are still
removed. How often this happens was not measured (no project data on Mini1).

