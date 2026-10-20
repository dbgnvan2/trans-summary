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
| RM1.g | **Deletion-only check.** The result is used only if (1) a word-level diff of input to output has no insertions or replacements, only deletions; (2) `extract_claims(output)` equals `extract_claims(input)` minus the removed claims, in order (a line removed whole also takes the claims `extract_claims` loses when only that line is deleted, beyond its sentences, such as a bold label; a claim too short to count once its label is stripped at the start of its line is not lost; copies are counted, 2026-10-20); (3) headings and front-matter keys are unchanged. If any part fails, the input is returned unchanged, every claim goes to `kept` with "deletion check failed", and the caller warns. |
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
| A split after "U.S.", "Ph.D.", "Sen.", "et al.", a month, or before a number left a fragment | such a split is uncertain: a claim there is kept ("sentence boundary uncertain"); a name takes the whole sentence (since 2026-10-20, RM1.i.1: only after an abbreviation; before a number a name takes its own part). List: `config.FAITHFULNESS_REMOVE_UNSURE_ABBREVIATIONS` | `test_rm1a_unsure_sentence_boundary_kept`, `test_rm1a_unsure_boundary_more_abbreviations`, `test_rm1a_unsure_copy_kept_other_copy_removed`, `test_rm1i_name_in_unsure_split_takes_whole_sentence` |
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


## Follow-up: open items C and B (plan, 2026-10-20)

Status: **built 2026-10-20**. Approved 2026-10-20: "build RM1.g.1, RM1.i.1 and RM1.i.2 as
planned." See **Built (2026-10-20)** at the end of this section. Dave asked for items C
and B from `TODO.md` ("Open, from the correctness re-review"), C first. Both were reproduced on `d353c73` with
`remove_flagged_sentences` (no API calls):

- **C.** `"Kerr says the move happened in the spring of that year. Note: the family was
  anxious about the move to the city. …"` with the first sentence flagged: nothing is
  removed, kept reason "deletion check failed: a claim was added or changed". The same
  text with a name flag on the first sentence gives the same refusal, so the name stays
  and the entity check fails the stage. Without "Note:" the name sentence is removed.
  Cause: once the first sentence goes, "Note: the family …" starts the line, where
  `extract_claims` and `_line_sentences` strip the label, so the check compares
  "Note: the family …" (before) with "the family …" (after).
- **B.** `"Zed Example spoke at length about the move. 2020 was a hard year for the whole
  family. …"` with a name flag on Zed Example: both sentences are removed, the second
  recorded as "name 'Zed Example'". A split before a number joins the two sentences into
  one group, and a name takes its whole group. With an abbreviation split (`"Zed Example
  served with Sen. Smith on the committee for years."`) both parts go, which is right,
  but "Smith on the committee for years." is recorded under the name it does not contain.

| ID | Rule | Test (`tests/test_remove_flagged_rm.py`) |
|---|---|---|
| RM1.g.1 (C) | Before the deletion check compares claims and body sentences, it removes from each one, before and after and in the removed set, a leading label from `config.FAITHFULNESS_STRIP_LINE_LABEL_PREFIXES` ("Note:") and then a leading enumerator ("2) ", "3. "). This is what `extract_claims` does at the start of a line, so a sentence that moves to the start of its line reads the same before and after. The text itself is not changed: "Note:" stays in the artifact. | `test_rm1g1_label_after_removed_claim_removed`, `test_rm1g1_label_after_removed_name_removed`, `test_rm1g1_enumerator_after_removed_name_removed` |
| RM1.g.1 (adversarial, P7) | A real loss is still caught: an unflagged "Note: …" sentence deleted outright is reported as lost. A sentence with a skip label (`config.FAITHFULNESS_SKIP_LINE_LABELS`, e.g. "Status:") that moves to the start of its line makes `extract_claims` drop that whole line, so the judge would stop seeing its claims; that removal is still refused. | `test_rm1g1_unflagged_label_sentence_lost_still_caught`, `test_rm1g1_skip_label_moved_to_line_start_still_refused` |
| RM1.i.1 (B) | A split before a number marks both sentences uncertain, as now (a flagged claim on either side is kept, "sentence boundary uncertain"), but does not join them: a name takes only its own sentence. A split after an abbreviation (`_DOUBTFUL_END`) still joins them, and a name takes every part. | `test_rm1i1_name_before_number_split_takes_only_its_sentence`, `test_rm1i1_claim_before_number_split_still_kept`; existing `test_rm1i_name_in_unsure_split_takes_whole_sentence` still passes |
| RM1.i.2 (B) | When a name takes the parts of an abbreviation split, a part without the name is recorded as "same sentence as name 'X' (uncertain split)", in the record and in the end-of-run list. | `test_rm1i2_split_part_without_name_has_own_reason` |

Each new test is checked to fail with its rule reverted. Done also means:
`python3 -m pytest tests/ -q -p no:cacheprovider` and `python3 -m pytest -q
-p no:cacheprovider` pass; learning-qa reviews the diff before the commit; CHANGELOG.md,
TODO.md (C and B leave the open list) and the Built table in this file are updated in the
same commit; ARCHITECTURE_DESIGN.md §4.3 is checked (it does not describe the split rules
now, so it probably needs no change). No API calls, no paid runs. Commit on main locally;
no push without asking.

Order: RM1.g.1 first (the enumerator test needs RM1.i.1, so it is written with RM1.i.1),
then RM1.i.1, then RM1.i.2. Files: `flagged_removal.py` (`deletion_problems`,
`_line_sentences`, the name branch of `remove_flagged_sentences`) and the test file.

Not in this change:
- Items A, D and E stay open in `TODO.md`.
- Mini1's parked stash ("RM cold sweep open items A/B/C WIP") is not used. Its B and C
  parts are superseded by this change; whether to redo A from it or drop it is Dave's call.
- Adjacent, not fixed: one failed deletion check refuses every removal in the artifact,
  name removals included, so a kept name can still fail the stage for another cause.
  Retrying with the name removals alone would narrow this; it is a separate change.
- Adjacent, not fixed: the abstract treats a judge error with a flagged name as
  "unavailable" and keeps the name (proposed separately as its own session).

### Built (2026-10-20)

All three IDs are built in `flagged_removal.py` with the tests named above, each checked
to fail with its rule reverted. Mini1's stash tests for B and C (4 tests, 5 cases) also
pass against the fix. Both suite runs pass. learning-qa reviewed the diff and found 5
problems in it; all are fixed, each with a test that fails without its fix:

| Finding | Fix | Test |
|---|---|---|
| "ch. 4", "est. 1950" were joined only by the number rule, so after RM1.i.1 a name left a fragment ("4 of the book.") | "ch", "chap", "sec", "est", "nos", "pt", "para" and (after the re-check) "op" added to `config.FAITHFULNESS_REMOVE_UNSURE_ABBREVIATIONS`; "no", "art", "ex" left out (they often end a sentence; the judge already joins after "no"); "p" not needed (the judge joins after single letters) | `test_rm1i1_name_after_abbreviation_before_number_takes_both_parts` |
| The short-claim exemption accepted a removal whose line then starts with "Status:", which the judge skips | the exemption counts only sentences that are not claims (`fj._is_claim` on the text the judge reads); the final form is in the re-check table below | `test_rm1g1_short_claim_on_skipped_line_still_refused`, `test_rm1g1_long_claim_judge_no_longer_reads_is_lost` |
| With "Note: X" read as "X", removing one X let an unflagged "Note: X" copy go too | `deletion_problems` counts copies: it takes a Counter of the cut sentences, and no more copies of a claim or sentence may go than were cut | `test_rm1g1_label_copy_lost_is_counted` |
| With a name in each part of a split, a part was listed as "same sentence as" the other name | a part with its own reason gives that reason only | `test_rm1i2_two_names_each_part_gives_its_own_name` |
| Comments in `config.py`, on `_Sentence.group` and in the cold-sweep table said a name takes the whole sentence at a number split | updated | — |

Differences from the plan text: the short-claim exemption ("Note: Kerr agreed." is a
claim, "Kerr agreed." is not) and the copy counting were not in the plan; both come from
the same cause as C. `test_rm1g1_skip_label_moved_to_line_start_still_refused` now puts
the rest of the paragraph on its own line, so the refusal it checks is the one for the
"Status:" sentence.

learning-qa re-checked the fixes twice. Each problem below is fixed with a test that
fails without the fix. The last design counts from the judge's own output
(`extract_claims`) instead of copying its line rules into removal, which is where three
of these problems came from:

| Finding | Fix | Test |
|---|---|---|
| Re-check 1 #1: the short-claim exemption counted a "Kerr agreed." already on another line, not a claim, so the "Note: Kerr agreed." claim lost to a "Status:" line was excused | only sentences that stopped being claims count: `shorter` = the short sentences of `after` (`_is_claim` on the text the judge reads, keyed by the text without its label) that `extract_claims(after)` does not return, less every sentence of `before` that `extract_claims(before)` does not return | `test_rm1g1_short_claim_copy_on_other_line_does_not_excuse_loss` (2 cases) |
| Mutation run: a "Status:" line the cut makes the judge read added its short sentences to the exemption | the `before` side counts every sentence the judge did not return, including those on skipped lines (above) | `test_rm1g1_sentence_on_line_judge_skipped_does_not_excuse_loss` |
| Re-check 1 #2: a line removed whole excused any lost sentence or claim found in its text, without counting copies | the substring exemption is gone. A removed line takes the claims `extract_claims` loses when only that line is deleted from the document, less its own sentences (counted as cut), one copy each: its bold label. Two earlier tries were dropped: passing only what is left of the line after the cut refused "1. **Kerr Agreed:** …", whose label is part of the cut sentence; reading the line alone refused the question-heading lines below | `test_rm1g1_dropped_line_text_does_not_excuse_loss`, `test_rm1g1_dropped_line_sentence_counted_once`, `test_rm1g1_label_claim_goes_with_its_line` (2 cases) |
| Re-check 2 #1 (regression): under a question heading the judge reads the first line's label and sentence as one claim ("Kerr Agreed — Zed Example …", "• **Kerr Agreed:** …"); reading the removed line alone missed it, so the removal was refused and the name stayed | the line's claims are read in the document (above) | `test_rm1g1_label_line_under_question_heading_goes` (2 cases) |
| Re-check 2 #2: a short first sentence under a question heading is a claim (the judge adds the question), but removal counted it as short, which excused a claim lost elsewhere | short sentences are counted less the claims `extract_claims` returns, on both sides | `test_rm1g1_question_tagged_short_sentence_is_a_claim` |
| Re-check 1 #3: removal's `_judge_skips` and `extract_claims` disagreed on lines under a question heading (`_QA_INSERT_AT`) | `_judge_skips` and the `read_only` filter are removed: with the counts taken from the judge's claims they changed no result (a sentence left on a line that came to be skipped keeps its text, so it is short only if it was before); the TODO item is dropped | all of the above still pass |

The rules of this change were reverted one at a time (18 mutations,
`mutate_cb4.py` in the session scratchpad): 17 make a test fail. The 18th, deriving the
`before` side from `_is_claim` instead of from `extract_claims(before)`, gives the same
result for every deletion (a deletion cannot move a sentence off the start of its line
or out from under its question heading); the form taken from the judge is kept.

Side effect of RM1.i.1, not fixed here (in `TODO.md`): learning-qa's grid of 2,142
synthetic line shapes, run against HEAD's module, has 126 lines that HEAD removed whole
and this change refuses. All have a name sentence followed by a number sentence
("… the move. 2020 was hard."), where HEAD also deleted the unflagged number sentence
(item B). Taking only the name's sentence then trips two older problems: a bold label
after "1. ", "> ", "• " or "+ " is inside the sentence's span, so the cut leaves a stray
`**`; and under a question heading the question tag moves onto the next sentence (F6).
The name is kept, so the entity check fails the stage instead of a correct sentence
being lost unreported.

Older problems learning-qa found, not fixed here (in `TODO.md`, for Dave to decide):
the FQ version of C (a question heading's tag moves onto the next sentence, which becomes
a claim, so the check refuses and a name stays); a line left with only "Note:" after its
sentence goes; a claim listed as kept when a name removed its sentence.

## Follow-up: a bold label after a list or quote marker (plan, 2026-10-20)

Status: **built 2026-10-20** (see "Built" at the end of this section). Approved by Dave:
"fix everything", D1 keep, D2 yes. The `TODO.md` item "`_line_sentences`
starts a sentence's span inside a bold run …". Reproduced on 813dd3c (no API calls):

- `"1. **Kerr Agreed:** Zed Example spoke at length about the move. Then the family moved
  …"` with a name flag on Zed Example: nothing is removed, "deletion check failed: … a
  line was left with an unpaired bold marker". The same for "1) ", "- 1. ", "> ", "> - ",
  and for "2020 was hard." as the second sentence (the RM1.i.1 case). The name is kept,
  so the entity check fails the stage.
- Cause: `_INLINE_BOLD_LABEL` matches a label only at the start of a line or after "- "
  or "• ". After other markers the judge reads the label as the start of the first
  sentence ("Kerr Agreed: Zed Example …"), and removal's span for that sentence starts
  after "1. **", inside the bold run.
- "+ " lines: the span starts at the "+", so a cut also takes the marker and the label,
  and nothing reports the label as gone.
- "• " lines are right outside a question heading. Under one, the judge reads the label
  with the sentence ("• Kerr Agreed: Zed …"), so after the cut it reads "• Kerr Agreed:
  Then …", a claim it did not have before, and the check refuses.
- No artifact in the three projects folders has this shape today: their 190 bold-label
  lines all start with "- ". I did not find learning-qa's 67 real lines in those folders.

| ID | Rule |
|---|---|
| RM1.b.1 | `_line_sentences` also finds a bold label after list, quote or number markers ("- ", "* ", "+ ", "> ", "• ", "1. ", "1) ", in any order). The label shapes are those of `_INLINE_BOLD_LABEL`, less bold text that ends with a period ("**Dr.**"), which the judge reads on past only when the period is no sentence end. Where the judge reads the label as the start of the first sentence, that sentence's span starts after the label. A cut then leaves the markers and the label, and a line left with only those is removed (RM1.b, unchanged). The sentence keeps the judge's reading (label included), so a claim flag still matches it. The record holds the words that were cut, without the label. A sentence that lies wholly inside the label (`"**Kerr Agreed.**"`, which the judge splits off as its own sentence) is handled as it is now. |
| RM1.b.2 | A name that is only in such a label, and not in the sentence after it, removes that sentence only when its line goes with it, so the label goes too (as at HEAD). Otherwise the name is kept with the reason "only in a heading, a label or the front matter", and the line is not touched, as for a "- **Label:**" line (RM1.i). Without this rule, RM1.b.1 would cut the sentence after the label even though the name is in the label, which stays. |
| RM1.g.2 | The deletion check compares a labelled line's first sentence, and the claim the judge reads from it, without the bold label and the markers before it. RM1.g.1 does the same for "Note:". After the cut the judge reads the label with the next sentence ("Kerr Agreed: 2020 was hard."), which is the same sentence as before. Only that sentence of that line is read without the label, one claim per line; a claim that is only the label is compared as it is. No more bold labels may go than the lines removed whole had ("a bold label was lost"). *(Revised after learning-qa: the first build stripped every label of `before` from every sentence.)* |
| RM1.g.3 (D2) | A claim in `after` that was already a sentence in `before`, not a claim, does not count as added. The judge now reads more of the text, and the token check already proves that only deletions were made. |

D2 also fixes F6: under a question heading, the question tag moves to the next sentence,
and the check then counts that sentence as a new claim.

**Grid check (scratch script, HEAD against a prototype; all existing RM tests pass on
both).** The grid has 2,080 name-flag lines: 13 leads × 8 label shapes × 2 sentence
positions × 5 second sentences × with and without a question heading.

- RM1.b.1, RM1.b.2 and RM1.g.2:
  - 304 lines that HEAD refused now remove the name.
  - 68 lines that HEAD refused now keep the name with the label reason (RM1.b.2).
  - 12 lines get worse, all "+ " or "1. - " lines whose second sentence is short and not a claim ("Then he left."). HEAD removed the name there only by cutting the marker and the label with it, unreported. The fix keeps the label, the judge then reads "Key point: Then he left." as a new claim, and the check refuses.
- With RM1.g.3 added:
  - 530 lines that HEAD refused now remove the name.
  - 0 lines get worse.
  - 36 lines are still refused, all "&gt; " lines, which HEAD refuses too.
- The 672 claim-flag lines show the same pattern:
  - without RM1.g.3: 68 fixed, 6 worse;
  - with RM1.g.3: 169 fixed, 0 worse.

Tests (`tests/test_remove_flagged_rm.py`). Each is checked to fail on 813dd3c and with
its rule reverted, unless it is marked as a guard:

| ID | Test |
|---|---|
| RM1.b.1 | `test_rm1b1_name_sentence_after_marked_label_takes_own_span`: leads "1. ", "1) ", "- 1. ", "> ", "> - ", "+ ", with a second sentence that is a long claim or "2020 was hard.". The line becomes `{lead}**Kerr Agreed:** {second}`, the record holds "Zed Example spoke …", and nothing is kept. Guard cases: "• " and "- ", which already pass at HEAD. |
| RM1.b.1 | `test_rm1b1_marked_label_under_question_heading`: "1. ", "> ", "• ", "+ " under "### What did Kerr say?". |
| RM1.b.1 | `test_rm1b1_last_sentence_after_marked_label_line_goes`: a one-sentence line for each lead. The line goes, and the record holds the sentence without the label (at HEAD it held the label too). |
| RM1.b.1 | `test_rm1b1_claim_flag_after_marked_label`: the judge's claim "Kerr Agreed: Zed …" as the flag. The sentence is cut and the label stays. |
| RM1.b.1 | `test_rm1b1_marked_label_regex_does_not_backtrack`: runs of "1. ", "*", "> " in a child process with a timeout, as `test_rm1b_marker_run_line_does_not_backtrack` does. |
| RM1.b.2 | `test_rm1b2_name_only_in_marked_label_kept`: "1. **Zed Example:** He spoke … Then …" is kept with the label reason and the line is unchanged. A name sentence elsewhere in the same text is still removed (HEAD refused everything). Guard: a one-sentence line goes. |
| RM1.g.2 | `test_rm1g2_label_read_with_next_sentence_passes`: calls `deletion_problems` directly. Adversarial guards (P7): an unflagged sentence after the label that goes is still reported, and a changed label is still reported. |
| RM1.g.3 | `test_rm1g3_label_makes_short_sentence_a_claim` ("+ **Key point:** Zed … Then he left."), `test_rm1g3_question_tag_moves_to_next_sentence` (F6). Adversarial guard: two sentences merged into one new claim are still refused. |

Files: `flagged_removal.py` (`_line_sentences`, `_Sentence`, the name branch and the
record fields of `remove_flagged_sentences`, `deletion_problems`) and the test file.
`CHANGELOG.md`, `TODO.md` (the item leaves the list; F6 too with D2) and this plan go in
the same commit. `ARCHITECTURE_DESIGN.md` §4.3 is checked. Both suite runs must pass,
learning-qa reviews the diff, and its findings are fixed. The commit stays on main
locally, with no push. No API calls.

**Decisions for Dave**

| ID | Question | Recommended |
|---|---|---|
| D1 | A name only in a label on a line with more sentences: keep it with the label reason (RM1.b.2, as on "- " lines), or remove the label with the first sentence? Removing them would make the stage pass, but it edits a label, which RM1.i does not do anywhere else. | Keep |
| D2 | Include RM1.g.3? Without it, 12 grid lines get worse than at HEAD. It also fixes F6, which is in `TODO.md` as yours to decide. | Yes |

Adjacent, not fixed:
- A bold run that opens a sentence but is not a label (`"**Zed Example** spoke … Then
  …"`, also after "- ") has the same span problem. The removal is refused and the name is
  kept. The fix would put the opening marker inside the span; that is a separate change.
- "&gt; " (an HTML-escaped quote marker): neither the judge nor removal treats it as a
  marker. HEAD refuses there when the label looks like a name; otherwise it cuts the
  marker and the label with the sentence. No artifact has this shape.
- The judge drops a bold label after "- " or "• ", but reads it as part of the first
  sentence after "1. ", "> " or "+ " (`abstract_validation._INLINE_BOLD_LABEL`). Making the
  judge consistent would change what it reads, so it needs its own calibration check.

**Built (2026-10-20).** Code in `flagged_removal.py`: `_MARKER_RUN`, `_MARKER_PREFIX`,
`_MARKED_LABEL`, `_Sentence.label` and `.own`, `_line_sentences`, `_names`, `_label_runs`,
`_labelled_firsts`, `_unlabelled`, `deletion_problems`, and in `remove_flagged_sentences`
the record, the FAQ lookup, the label reason and `LABEL_LEFT`. The first build stripped
labels with one pattern for the whole text (`_label_pattern`); learning-qa's finding 1
below replaced it. Tests beyond the table above:

- `test_rm1b1_faq_copy_of_sentence_after_marked_label_removed`: the FAQ copy of a sentence
  after a marked label is found by its own words. Fails on 813dd3c.
- `test_rm1g2_label_only_sentence_compared_as_is` (P7): added because no test needed the
  `(?=\S)` in the first build's `_label_pattern`. A sentence that is only a label is
  compared as it is; stripped to nothing, a lost label-only line would cancel against a
  line the cut left with only its label. In the final code N3 fails it.
- `test_rm1g3_name_sentence_on_skip_label_line_removed`: D2 also changes "Status: Zed …
  2020 was a hard year." from refused to removed. "Status:" goes with its sentence, and the
  judge then reads "2020 was a hard year." as a claim. This closes the `TODO.md` note
  "stricter since RM1.i.1".
- `test_rm1b_marker_run_line_does_not_backtrack` now runs its removal in the child process.
  With a backtracking `_MARKED_LABEL` its removal in the test process hung the suite.

**learning-qa (2026-10-20)** reviewed the first build. Its findings, all fixed in this
change, each with a test that fails on the first build:

| # | Finding | Fix | Test |
|---|---|---|---|
| 1 (medium–high, P7) | `_label_pattern` stripped every bold label of `before` from the start of every sentence and claim, so deleting a label ("1. **Not true:** X" to "1. X") or a plain "Kerr Agreed: " prefix on another line passed the check. 813dd3c caught both. | RM1.g.2 revised: `_labelled_firsts` and `_unlabelled` take the label off only a labelled line's first sentence, one claim per line; sentences compare by `.own`; the check reports "a bold label was lost" when more bold labels go than the dropped lines had. | `test_rm1g2_deleted_label_still_caught`, `test_rm1g2_label_prefix_lost_on_other_line_caught` |
| 2 (medium, P6) | A claim flag the judge read with its label is cut; the label stays and is read with the next sentence, unjudged, and nothing said so. | The flag is also listed as kept (`LABEL_LEFT`) while the label stays. Keeping the sentence instead, as RM1.b.2 does for names, is in `TODO.md` for Dave. | `test_rm1b1_claim_flag_after_marked_label`, `test_rm1b1_faq_copy_of_sentence_after_marked_label_removed` |
| 3 (low) | "**Dr.**" after "1. " counted as a label, so "1. **Dr.** Then …" was accepted. | `_MARKED_LABEL` no longer takes "**X.**". The removal is refused, as at 813dd3c. | `test_rm1b1_abbreviation_in_bold_is_not_a_label` |
| 4 (low, P2) | Two labelled copies of one sentence with different flags: only one flag said its FAQ copy was left. | One `Kept` per flag. | `test_rm1e_faq_copy_left_listed_for_each_flag` |

learning-qa then re-checked these fixes. Its four repro inputs give the right result, and
nothing new hides a non-deletion change. It found:

| # | Finding | Fix | Test |
|---|---|---|---|
| R1 (medium) | `_labelled_firsts` keyed a label on its raw bold run, but the judge reads "**2) Key point:**" after "1. " as "Key point:", so those removals were refused (813dd3c made most of them). | Key on the label as `_line_sentences` read it, markers removed. | `test_rm1b1_number_inside_bold_label` |
| R2 (low) | "**Kerr Agreed**—Zed …" (no space): the cut leaves "**Kerr Agreed**—Then", a new token, so the token check refused (also at 813dd3c, except on "+ " lines, where the label was cut too). | A dash is its own token. | `test_rm1g_dash_after_label_is_its_own_token` |
| R3 (low) | A labelled line's first sentence pairs with the first claim that reads like it, so a plain copy above it makes a removal be refused (also at 813dd3c). | Recorded in `TODO.md` as a known limit. | none |
| R4 (low) | A flag listed for its FAQ copy did not say its label stays. | The FAQ reason adds `LABEL_STAYS`. | `test_rm1e_faq_copy_left_listed_for_each_flag` |

Not fixed, in `TODO.md`: the deletion check counts copies, so losing the plain copy of a
sentence that is also after a bold label, instead of the cut one, is not seen (813dd3c
has the same limit for plain duplicates); a bold label ending in a period on a "- " line
is not counted.

The grids were run again on the final code: the same numbers as the prototype (530 and
169 fixed, 0 worse, 36 "&gt; " lines still refused).

Each rule of the final code was reverted alone and `tests/test_remove_flagged_rm.py` run
against it. All 28 make a test fail:

| # | Rule reverted | Fails |
|---|---|---|
| M1 | RM1.b.1: the span is not moved past the label | 32 cases |
| M2 | RM1.b.1: "+" is not a marker | 6 cases |
| M3 | RM1.b.1: ">" is not a marker | 9 cases |
| M4 | RM1.b.1: numbers are not markers | 21 cases |
| M5 | RM1.b.1: a marker run that backtracks (`[-*+>•]+` inside the repeat) | both backtrack tests, in their 20 s timeout |
| M6 | RM1.b.1: the record holds the judge's reading | 27 cases |
| M7 | RM1.b.1: the FAQ lookup uses the judge's reading | 2 tests |
| M8 | RM1.b.2: the name is matched on the judge's reading | `test_rm1b2_name_only_in_marked_label_kept` |
| M9 | RM1.b.2: no one-sentence-line clause | `test_rm1b2_name_in_label_of_one_sentence_line_goes` |
| M10 | RM1.b.2: label reason from `_INLINE_BOLD_LABEL` only | `test_rm1b2_name_only_in_marked_label_kept` |
| M11a | RM1.g.2: claims keep their label | 27 cases |
| M11b | RM1.g.2: sentences compared with their label | 33 cases |
| M12 | RM1.g.2: markers not taken off a claim | 8 cases |
| M13 | RM1.g.2: any label taken off any claim | `test_rm1g2_label_prefix_lost_on_other_line_caught` |
| M13b | RM1.g.2: not one claim per line | `test_rm1g2_label_prefix_lost_on_other_line_caught` |
| M14 | RM1.g.3 off | 5 cases |
| M15 | RM1.g.3 accepts any new claim | 3 tests |
| N1 | no label count | `test_rm1g2_deleted_label_still_caught` (2 cases) |
| N2 | label count ignores lines removed whole | 15 cases |
| N3 | "**X.**" is a label again | `test_rm1b1_abbreviation_in_bold_is_not_a_label`, `test_rm1g2_label_only_sentence_compared_as_is` |
| N4 | no `LABEL_LEFT` keep | 4 cases |
| N5 | `LABEL_LEFT` also when the line goes | 3 cases |
| N6 | `LABEL_LEFT` for name flags too | 18 cases |
| N7 | FAQ keep for one flag per sentence | `test_rm1e_faq_copy_left_listed_for_each_flag` |
| R1 | the label keyed on its raw bold run | `test_rm1b1_number_inside_bold_label` (2 cases) |
| R2 | a dash is not its own token | `test_rm1g_dash_after_label_is_its_own_token` (4 cases) |
| R4 | the FAQ reason without the label part | `test_rm1e_faq_copy_left_listed_for_each_flag` |
| R4b | `LABEL_LEFT` also after an FAQ keep | `test_rm1e_faq_copy_left_listed_for_each_flag` |

Docs: `CHANGELOG.md`, `TODO.md` (the item leaves the list, F6 is marked fixed, the three
adjacent items above are added), `ARCHITECTURE_DESIGN.md` §4.3 (the claims left may include
a sentence now read as a claim), and this plan. 20 new tests (53 cases); the RM file has
153 tests. Both suite runs pass: `python3 -m pytest tests/ -q -p no:cacheprovider` and
`python3 -m pytest -q -p no:cacheprovider`.
