# Plan: remove sentences still flagged after revision (RM0–RM9)

Status: **proposed 2026-10-19 — waiting for approval of the plan and of D1–D6.**
No code is written for it yet.

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
