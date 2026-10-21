# Plan: the open removal items and Mini1's cold review of 813dd3c (2026-10-20)

Status: **approved 2026-10-20** ("build the plan … as written, with D3 (leave the
number) and D4 (do RM1.g.6) as recommended"). Commit 1 (RM1.g.4, RM1.g.5, RM1.g.7) and
commit 2 (RM1.e.1, RM1.e.2) are built; commits 3 and 4 are not. See **Built** at the end for what was built and where it
differs from the text below.

Scope: everything still open on sentence removal (`flagged_removal.py`) after 813dd3c,
except the work that needs a decision or paid runs (listed at the end). Sources:

- `TODO.md` items A, D, E, F7, F8 and the adjacent removal items.
- Mini1's cold review of 813dd3c `deletion_problems` (fresh reviewer, compared against
  d353c73, 21k fuzz documents, every finding reproduced by Mini1, no paid calls). It found
  4 problems, listed as M1–M4 below.
- Mini1's report on the PDF tests (T-BE1).

F6 is not here: the bold-label plan (`docs/plan_remove_flagged_2026-10-19.md`, RM1.g.3,
D2 approved) fixes it.

**Order.** The bold-label session (RM1.b.1, RM1.b.2, RM1.g.2, RM1.g.3) is changing
`_line_sentences`, `deletion_problems` and the test file now. This work starts after its
commit, on top of it. Until then I do not edit `flagged_removal.py`,
`tests/test_remove_flagged_rm.py`, `config.py`, `CHANGELOG.md`, `TODO.md` or
`docs/plan_remove_flagged_2026-10-19.md`. This plan is one new file, so it can be
committed now.

## What Mini1 found (M1–M4)

| ID | Goal | Found in | What happens |
|---|---|---|---|
| M1 | an unflagged claim is lost | new in 813dd3c | `"Zed Example spoke at length about the move. **He met Dr. Bowen at the center**"` with a name flag on Zed. The judge joins "Dr." and "Bowen" with one space, so `_line_sentences` cannot find that sentence in the raw line and stops listing the line. The cut leaves the bold run, `_EMPTY_LINE` reads it as a label, and the line is dropped. `from_lines` excuses the lost claim, because `own` (taken from `_line_sentences`) does not list it. d353c73 refused this removal. A tab or two spaces after "Dr." does the same. |
| M2 | a correct removal is refused | new in 813dd3c | `"Zed Example spoke at length about the move. 2. The group met again later."` with a name flag. The judge reads "2." as its own sentence. After the cut, "2. " starts the line and the judge strips it as a list number, so the check reports "2." as a lost claim and a lost sentence. The name stays, so the entity check fails the stage. RM1.g.1 covers "2) " only, which the judge does not split off. Also "+ 2." and "• 2.". |
| M3 | an unflagged front-matter sentence is cut | both versions | FAQ answer `"He trained in the U.S. Navy for two years. Kerr confirmed it."`, body `"He trained in the U.S. Army with Zed Example."`, name flag Zed. `_edit_front_matter` splits the answer with the judge's splitter, which splits after "U.S.", and drops the part equal to a removed text: the answer becomes "Navy for two years. Kerr confirmed it.". The same happens after "Sen.". The check does not look at what an FAQ answer says. |
| M4 | latent gaps in the check (direct `deletion_problems` calls; `_cut` cannot make these today) | 813dd3c or both | Deleting a mid-line "Note:" alone, or a mid-line "2)" alone, is accepted (new: both sides are compared without the label). Deleting a bold-only line, or "not" inside an FAQ answer, is accepted (both versions). A change after "Dr." plus two spaces is not seen, because `_line_sentences` stopped listing that line (both versions). |

Mini1's point on M4: the check is meant to be independent, but it uses the same sentence
positions as the code it checks. A line that `_line_sentences` cannot place is not
checked at all.

## Rules

Each rule's test is written first and checked to fail on the bold-label commit (and with
the rule reverted), unless it is marked as a guard.

### The deletion check (commit 1)

| ID | Rule | Closes |
|---|---|---|
| RM1.g.4 | The check reads each line's sentences from the judge's own split (`fj._split_sentences` on the cleaned line, after the same line-start stripping), not from removal's placement of them. `own` (the sentences of a dropped line) and `_body_sentences` both use this split, so a sentence that removal could not place is still counted, and a dropped line cannot excuse its loss. One helper (`_line_parts`) gives the split to both `_line_sentences` and the check. | M1, the double-space part of M4 |
| RM1.g.5 | The check counts what it compares without: in each body line, the bold label, an allowlisted plain label ("Note:") or a list number ("2)", "2.") at the start of the line or of a sentence, a sentence that is only a list number, and each bold-only line. None may be added. One may go only with a removed sentence that starts with it, or with a dropped line. A sentence that is only a list number ("2.") and the same number at the start of a line count as the same item, so "2." that moves to the start of its line is not lost. | M2, M4 (label or number alone, bold-only line), the TODO item on a repeated bold label |
| RM1.g.7 | `_cut` raises `ValueError` when two spans on one line overlap (spans that touch are fine). The caller in `extraction_pipeline.py` already catches an exception from removal, keeps the draft and records each flag as "removal failed: …". | E |

### The front matter (commit 2)

| ID | Rule | Closes |
|---|---|---|
| RM1.e.1 | Every copy of a removed sentence left in the front matter is listed as kept, with the reason "removed from the body; still in the front matter", also when a quoted FAQ copy was edited (an unquoted answer, or another key such as `description:`). For a name flag, a copy is listed only when the name is still in the front matter. `Removed.in_front_matter` is true only when the sentence was taken from an FAQ answer and no copy is left. This is Mini1's diff (stash "RM cold sweep open items A/B/C WIP", saved here as text), plus the name condition, which answers Mini1's point that the copy test is a substring match. | A |
| RM1.e.2 | `_edit_front_matter` splits an FAQ answer as `_line_sentences` does a line: a part after an uncertain split (an abbreviation from `config.FAITHFULNESS_REMOVE_UNSURE_ABBREVIATIONS`) joins the part before it. A joined sentence goes only when every part of it was removed. The check compares FAQ answers sentence by sentence, joined the same way: no sentence may be added or changed, and one may go only when every part of it was removed. The joining rule is one helper, used by `_line_sentences`, the FAQ edit and the check. | M3, the FAQ part of M4 |

### Removal rules (commit 3)

| ID | Rule | Closes |
|---|---|---|
| RM1.b.3 | `_line_sentences` finds a sentence in its line when the judge joined two parts with one space and the line has other whitespace there (a tab, a non-breaking space, two spaces). | M1: with the fix, a name inside such a sentence can be removed |
| RM1.b.4 | A line left with only list markers and an allowlisted plain label ("Note:", "- Note:") after its sentences are removed is removed. | F7 |
| RM1.b.5 | A bold run that opens a sentence and closes inside it (`"**Zed Example** spoke at length. Then he left."`) is cut with both of its markers, so no stray `**` is left. | the bold-label plan's adjacent item |
| RM1.i.3 | A claim flag whose every copy is on an uncertain split is not listed as kept when a name flag removes those sentences. The removal is recorded with both reasons ("faithfulness (also name 'Zed Example')") and the claim's judge record. If only some copies go, the claim is listed as "removed in part; one copy kept: sentence boundary uncertain …". | F8 |
| RM2.h.1 | A test that, when a name flag comes before a claim flag on the same sentence, the Removed entry carries the claim's record and the reason "faithfulness (also name …)". A probe on 813dd3c shows this already works, so the test is a guard. | D |
| RM1.g.6 | When the deletion check refuses a removal, removal is tried once more with only the name flags' sentences (and the claim flags on those same sentences). That attempt goes through the same cap, front-matter edit and deletion check. If it passes, the names go and each other flag is listed as kept with the first attempt's reason. If it fails, nothing is removed, as now. A kept name fails the stage through the entity check; a kept claim is only a warning. | the TODO item "one failed deletion check refuses every removal" |
| RM2.a.1 | When the faithfulness judge is off (`config.FAITHFULNESS_JUDGE_ENABLED` false), the names-only message says the judge is off and no claim was checked, instead of "no claim was flagged". Only `_all_removed_message` changes; its two call sites stay as they are. | the TODO item on the judge-disabled message |

### The PDF tests (commit 4)

| ID | Rule | Closes |
|---|---|---|
| T-BE1 | `tests/test_bundle_export.py` skips the three WeasyPrint tests (be7, be11, be12) when `import weasyprint` raises `ImportError` or `OSError`, with the error in the skip reason. On Mini1 the import raises `OSError` (uv's Python cannot find Homebrew's `libgobject`), and `pytest.importorskip` catches only `ImportError`, so the tests fail instead of skipping. | Mini1's report |

## Tests

All tests below are in `tests/test_remove_flagged_rm.py`, except T-BE1's. Each name
carries its rule ID.

| ID | Test |
|---|---|
| RM1.g.4 | `test_rm1g4_unplaced_sentence_on_dropped_line_not_excused`: Mini1's M1 input with a non-breaking space, a tab and two spaces after "Dr.", through `remove_flagged_sentences` and through `deletion_problems` directly. The removal is refused, with "a claim was lost that was not flagged". |
| RM1.g.4 | `test_rm1g4_change_after_unplaced_split_seen`: "He met Dr.  Kerr at the center. He was not sure." changed to "… He was sure." is refused. |
| RM1.g.4 | Guard: `test_rm1g4_label_line_still_goes`: the existing label-goes-with-its-line cases still pass through the new split. |
| RM1.g.5 | `test_rm1g5_number_sentence_moves_to_line_start`: Mini1's M2 input, also with "+ " and "• " leads. The name sentence goes, and the line becomes "2. The group met again later.". |
| RM1.g.5 | `test_rm1g5_label_or_number_alone_deleted_refused` (adversarial, P7): a mid-line "Note:" deleted alone, a mid-line "2)" deleted alone, a bold-only line deleted, and one of two "**Kerr Agreed:**" labels deleted from a line that stays. Each is refused. |
| RM1.g.5 | Guard: "Note: …" and "2) …" moving to the start of their line (the RM1.g.1 cases) still pass. |
| RM1.g.7 | `test_rm1g7_cut_refuses_overlapping_spans`: `_cut` raises on two overlapping spans and accepts two that touch. `test_rm1g7_overlap_keeps_draft`: with `_line_sentences` patched to give overlapping spans, the pipeline keeps the draft and records "removal failed". |
| RM1.e.1 | Mini1's two tests, `test_rm1e1_second_unquoted_faq_copy_listed_as_kept` and `test_rm1e1_copy_under_other_key_listed_as_kept`. The three cases of `test_rm1e_unreadable_faq_answer_listed_as_kept` change to the new reason. New: `test_rm1e1_name_copy_listed_only_when_name_left`, which uses M3's "U.S. Navy" answer, so the name flag is not listed as kept for the front matter. |
| RM1.e.2 | `test_rm1e2_faq_sentence_after_abbreviation_kept`: M3's two inputs ("U.S." and "Sen."). The answers are unchanged, and the body removal still happens. `test_rm1e2_faq_content_change_refused` (adversarial): `deletion_problems` refuses "not" deleted inside an answer, and refuses part of a joined sentence going. Guard: a whole joined sentence that was removed from the body also goes from the answer. |
| RM1.b.3 | `test_rm1b3_name_in_sentence_with_odd_space_removed`: "He met Dr. Zed Example at the center." The name sentence goes, and the line is cut cleanly. |
| RM1.b.4 | `test_rm1b4_plain_label_left_alone_line_goes`: leads "", "- ", "> ". The line goes, and the record holds the sentence. Guard: "Status:" (not allowlisted) stays as at HEAD. |
| RM1.b.5 | `test_rm1b5_bold_run_opening_sentence_cut_whole`: "**Zed Example** spoke at length. Then he left.", also after "- ". "Then he left." stays and no `**` is left. |
| RM1.i.3 | `test_rm1i3_unsure_claim_removed_by_name_not_kept`: "Kerr met Zed Example in the U.S. Army in 1990." with the name flag and the judge's claim "Kerr met Zed Example in the U.S.". Nothing is kept, the reason is "faithfulness (also name 'Zed Example')", and the record is the claim's. Partial case: a second copy elsewhere without the name. The claim is listed as removed in part. |
| RM2.h.1 | `test_rm2h1_name_flag_first_claim_record_kept` (guard). |
| RM1.g.6 | `test_rm1g6_name_removed_when_claim_removal_refused`: a claim removal that the check refuses (the existing `_cut` mutation pattern, applied to the claim's line only) plus a name on another line. The name goes, and the claim is kept with "deletion check failed: …". Adversarial: when the name-only attempt also fails, nothing is removed. |
| RM2.a.1 | Extend `test_rm2_names_only_message`: with the judge off, the message says the judge is off. With the judge on, it is unchanged. |
| T-BE1 | `test_be_weasyprint_guard_skips_on_oserror`: with the import patched to raise `OSError`, the helper calls `pytest.skip`. |

## Checks before each commit

- The test for the highest-risk rule is written first: RM1.g.4 (M1 is a silent loss that
  d353c73 caught).
- Grid check, no API calls: learning-qa's 2,142-shape grid (`probe4.py`) and the
  bold-label session's 2,080-line grid. A line that the bold-label commit removes
  correctly must not be refused after this work. Every change in outcome is listed in
  this plan's Built section, with its cause.
- Mutation check: each rule reverted alone makes its test fail (as `mutate_cb4.py` does).
- A read-only scan of the artifacts in the three projects folders counts the shapes
  Mini1 could not assess (odd whitespace after an abbreviation, an inline "2. ", FAQ
  answers with an abbreviation split). The scan reads files only and writes nothing
  there.
- Both suites run with `.venv/bin/python`. My earlier counts came from the system
  `python3`, which has no WeasyPrint and skips the three PDF tests; under `.venv` they
  pass on mini2.
- learning-qa reviews each diff, and its findings are fixed before the commit.
- `CHANGELOG.md`, `TODO.md` (the items leave the list) and this plan's Built section go
  in the same commit. `docs/plan_remove_flagged_2026-10-19.md` gets a pointer to this
  plan. `ARCHITECTURE_DESIGN.md` §4.3 is checked.
- Each commit stays on main locally. Nothing is pushed without Dave's OK.
- After commit 1, Mini1 does a cold review of it (no edits, commits, pushes or paid
  calls). It is the commit most likely to be wrong in a new way.

## Decisions for Dave

| ID | Question | Recommended |
|---|---|---|
| D3 | When the sentence before "2) Then …" or "2. The group …" is removed, the line starts with the number, and markdown shows it as a numbered list item. The words do not change. The other options are to cut the number too, which deletes an unflagged word (d353c73 did this for "2."), or to refuse the removal, which keeps the name and fails the stage. | Leave it as it is; keep it in `TODO.md` as known. |
| D4 | RM1.g.6 removes the names when the claim removals are refused. Should a refused removal instead keep everything, as now? | Do RM1.g.6. A kept name fails the stage; a kept claim is a warning. |

## Not in this plan (needs Dave)

- **RM2.e:** whether a summary with a low-confidence coverage item should keep every
  flagged claim sentence. This needs counts from paid real runs.
- **Paid real runs** on 2–3 other projects, to read the first real removal lists (RM6).
  These need Dave's OK for the API cost.
- **The judge's `_split_sentences`** (splits after "U.S.", "Ph.D.", "Sen.", months), and
  the judge reading a bold label differently after "- " and after "1. ". Changing either
  changes what the judge reads and what the gate blocks, so each needs its own
  calibration check.
- **"&gt; " lines** (an HTML-escaped quote marker). Neither the judge nor removal treats
  it as a marker. No artifact has this shape. I recommend leaving it.
- **Merging `refs/heads/claude/sad-wu-724a11`** (the abstract judge-error fix, built in
  its own session) into main.

## Built

### Commit 1: the deletion check (2026-10-20)

| ID | Status | Where | Tests |
|---|---|---|---|
| RM1.g.4 | done | `flagged_removal._split_line` reads a line as the judge splits it: the sentences removal placed and, from the first one it could not place, each of the rest with no span. `_all_sentences` returns both; `own` in `deletion_problems` and `_body_sentences` use it. `_line_sentences` still returns the placed ones only, so removal is unchanged. | `test_rm1g4_unplaced_sentence_on_dropped_line_not_excused` (3 cases), `test_rm1g4_unplaced_sentence_not_excused_when_placement_fails`, `test_rm1g4_change_after_unplaced_split_seen`, `test_rm1g4_unplaced_first_sentence_read_without_its_label`, `test_rm1g4_label_line_still_goes` |
| RM1.g.5 | done | `_sentence_marks`, `_body_marks` and the marks block in `deletion_problems`; the claim-loss and sentence-loss loops skip a number-only sentence, which the marks count. A line removed whole excuses only the marks at its start (`line_marks` of `_split_line`). | `test_rm1g5_number_sentence_moves_to_line_start` (6 cases), `test_rm1g5_label_or_number_alone_deleted_refused` (3), `test_rm1g5_label_added_refused`, `test_rm1g5_label_after_unplaced_split_counted`, `test_rm1g5_bold_only_line_deleted_refused`, `test_rm1g5_repeated_bold_label_deleted_refused`, `test_rm1g5_label_or_number_moving_to_line_start_passes` (3), `test_rm1g5_number_left_alone_on_dropped_line_refused` (6), `test_rm1g5_mark_of_cut_sentence_on_dropped_line_counted_once` (2) |
| RM1.g.7 | done | `_cut` | `test_rm1g7_cut_refuses_overlapping_spans`, `test_rm1g7_overlap_keeps_draft` |

Where it differs from the text above:

- The helper is `_split_line`, not `_line_parts`. It returns the placed sentences, the
  unplaced ones and the marks (labels, list numbers, a bold-only line). A new `_find` is
  the one place a sentence is placed in its line; RM1.b.3 (commit 3) changes it, and the
  RM1.g.4 tests patch it to make a sentence unplaceable.
- An unplaced first sentence is read without the bold label the judge reads with it, as
  a placed one is. Without this, 8 grid lines ("1. **Note:** Zed … **He met Dr. Bowen
  …**", non-breaking space) were refused for "a label was added".
- A bold-only line may be new after a cut (a bold lead sentence left alone on its line,
  `test_rm1b_bold_lead_sentence_not_dropped`); it may never be lost.
- The plan put the bold-only line and the repeated bold label in
  `test_rm1g5_label_or_number_alone_deleted_refused`; each has its own test. The repeated
  label is a guard: ec60324's bold-label count (`_label_runs`) already refuses it.
- `test_rm1g5_number_sentence_moves_to_line_start` also runs after "**Kerr Agreed:** "
  and "> **Kerr Agreed:** ". The second one fails when the marks are read from the
  sentence with its label (the shape of 442 false refusals in the first grid run).
- Two existing tests changed. `test_rm1g1_label_copy_lost_is_counted` now passes the
  texts removal really cuts (the "Note: X" copy, with its label) and also checks that one
  label too many lost is reported. `test_rm1g2_label_only_sentence_compared_as_is` now
  also expects "a list number was lost: '1.'", which is correct for its input.

learning-qa review of the commit (4 findings, all fixed before the commit except 2C):

1. **A number left alone on a line removed whole went unrecorded (high, new in this
   change).** "Zed Example founded the center that year. 1975." with a name flag: the cut
   left "1975.", `_EMPTY_LINE` read it as a list marker and dropped the line, both loss
   loops skip a number-only sentence, and the dropped line's marks excused it. ec60324
   refused this removal. Fix: `_split_line` also returns `line_marks`, the label and list
   number at the line's start (or the bold-only line), and a line removed whole excuses
   only those. Such a removal is refused again, so the name is kept. Test:
   `test_rm1g5_number_left_alone_on_dropped_line_refused` (6 shapes, from the review). My
   grid missed it: every "2." body had a sentence after the number (P33).
2. **A mark counted twice (high, reached only by calling `deletion_problems` directly).**
   A sentence both cut and on a dropped line gave its label or number once from the line
   and once from the cut text, and the spare one excused the same mark deleted from a
   line that stays (cases A and B). The fix for 1 closes both. Test:
   `test_rm1g5_mark_of_cut_sentence_on_dropped_line_counted_once`. Not fixed, case C: the
   allowance comes from the removed list, not from what left the text, so a removed list
   that does not match the edit could excuse a mark lost elsewhere. Removal builds the
   list from the spans it cuts, so this needs two bugs at once; closing it needs the check
   to match lines before and after. Recorded in TODO.md.
3. **Two branches had no test.** "A sentence that cannot be placed ends the line's list"
   (`test_rm1g4_sentence_after_unplaced_one_not_removable`) and the unplaced label read
   only when the judge's text starts with it
   (`test_rm1g4_unplaced_label_split_only_when_text_starts_with_it`).
4. **Literal non-breaking spaces in three test lines.** They are now `\u00a0`; with a plain
   space, `test_rm1g4_unplaced_sentence_on_dropped_line_not_excused` passes on ec60324 too.

Adjacent, not fixed (pre-existing, found by the review): in "1975. Zed Example founded
the center …" the judge strips "1975. " as a list number, so the year is never judged,
and removal deletes it with the line. Recorded in TODO.md.

Checks (scratch scripts, no API calls):

- Output grid, `grid_c.py`: 6,838 lines (name and claim flags × 2 headings × 9 leads ×
  15 labels × 13 bodies) against ec60324. 6,592 have the same output. 102 are now
  refused, all the M1 shape: ec60324 deleted the unflagged "He met Dr. Bowen at the
  center" with the flagged sentence. 144 now remove the flag, all "… the move. 2. The
  group met again later." (M2), which ec60324 refused; the line becomes "2. The group met
  again later." (D3). 18 have the same output with another refusal reason; both versions
  refuse them. 182 had no claim to flag. None raises.
- learning-qa's grid (`probe4.py`, 2,142 lines): all the same as ec60324. The bold-label
  session's grids (2,080 name lines, 672 claim lines): none worse than ec60324; the 36
  "&gt; " lines are refused by both.
- Mutation: 22 mutants, each reverting one part of RM1.g.4, RM1.g.5, RM1.g.7 or the
  review fixes, each fail at least one test.
- After the review fixes: the grids above give the same numbers. learning-qa's token
  grid (520 lines, 13 bodies, trailing numbers included): 0 removals delete a word that
  was not flagged (ec60324: 12, the M1 shape); 366 lines removed, against 339.
- Read-only scan of the artifacts in the three projects folders: 19 files (15
  abstracts, 1 overview, 3 summaries), 83 body lines, 6 FAQ answers. No line has a judge
  claim that removal cannot place, an inline number-only sentence, odd spacing after a
  period, or an FAQ answer with an uncertain split. M1–M3 have not occurred in a real
  artifact.
- Suites, with `.venv/bin/python`, after the review fixes: `-m pytest tests/ -q -p
  no:cacheprovider` 1,933 passed, 13 skipped; `-m pytest -q -p no:cacheprovider` 2,028
  passed, 23 skipped, 1 xfailed (the tree also held commit 4's T-BE1 test). The RM test
  file has 188 tests.

### Commit 2: the front matter (2026-10-20)

| ID | Status | Where | Tests |
|---|---|---|---|
| RM1.e.1 | done | `remove_flagged_sentences`: every removed sentence still in the head after the FAQ edit is in `left_in_head`, looked for with its whitespace collapsed (`_copy_in`) in two readings of the head (`_head_readings`): YAML's escapes undone in one pass (`_yaml_plain`), and as written with `''` undone; `_left_in_head(flag)` lists a name flag only while its name is in either reading; `Removed.in_front_matter` is `own in in_head - left_in_head`. The reason is `STILL_IN_FRONT_MATTER`, "removed from the body; still in the front matter", which replaces `IN_FAQ`. A q/a pair with another key stays whole. | `test_rm1e1_second_unquoted_faq_copy_listed_as_kept`, `test_rm1e1_copy_under_other_key_listed_as_kept`, `test_rm1e1_name_copy_listed_only_when_name_left` (2 cases), `test_rm1e_unreadable_faq_answer_listed_as_kept` (3, new reason), `test_rm1e_faq_copy_left_listed_for_each_flag`, `test_rm1e1_escaped_or_folded_copy_listed_as_kept` (6), `test_rm1e1_faq_pair_with_other_key_kept`, `test_rm1e1_folded_name_in_front_matter_listed_as_kept` (2), `test_rm1e1_escaped_claim_only_in_front_matter_reason`, `test_rm1e1_yaml_plain_undoes_escapes_in_one_pass` (11), `test_rm1e1_yaml_plain_matches_yaml` (21), `test_rm1e1_yaml_plain_never_raises`, `test_rm1e1_body_sentence_with_backslash_copy_listed` (3), `test_rm1e1_single_quoted_copy_with_quote_and_backslash_listed`, `test_rm1e1_claim_with_backslash_only_in_front_matter_reason` |
| RM1.e.2 | done | `_joined_to_previous`, the one joining rule, used by `_split_line`, `_answer_sentences` and the check; `_answer_sentences`, `_faq_sentences`, `_edit_front_matter`; `_faq_goes` (with `_cut_groups`, `_cut_for_itself` and `_is_run`), the one rule for which answer sentences may go, used by the edit and the check; in `deletion_problems`, "an FAQ answer sentence was added or changed", "an FAQ answer sentence was lost that was not flagged", and the item-by-item comparison (`_faq_item_problems`, `_item_changes`). | `test_rm1e2_faq_sentence_after_abbreviation_kept` (2 cases), `test_rm1e2_whole_joined_sentence_goes_from_answer`, `test_rm1e2_faq_content_change_refused`, `test_rm1e2_part_split_off_with_name_stays_in_answer` (2), `test_rm1e2_part_with_its_own_name_goes_from_answer`, `test_rm1e2_faq_items_compared_in_order`, `test_rm1e2_name_only_in_label_sentence_stays_in_answer` (3), `test_rm1e2_run_of_cut_sentence_with_name_goes_from_answer` (3), `test_rm1e2_same_question_twice_either_item_may_go` (2), `test_rm1e2_blank_line_between_faq_items`, `test_rm1e2_item_check_refuses_answer_sentence_that_may_not_go`, `test_rm1e2_faq_goes_rules` (8), `test_rm1e2_part_cut_for_itself_elsewhere_is_still_a_rider_in_answer`, `test_rm1e2_part_cut_for_itself_elsewhere_goes_alone_in_answer`, `test_rm1e2_parts_not_next_to_each_other_stay_in_answer`, `test_rm1e2_part_marked_by_any_name_cut_there` (4) |

Where it differs from the text above:

- The guard (a whole joined sentence removed from the body also goes from the answer)
  has its own test, `test_rm1e2_whole_joined_sentence_goes_from_answer`.
- A flag is listed once as kept for the front matter, even when more than one of its
  sentences is left there.
- Mini1's stash was not applied; RM1.e.1 was written from its saved text, with the name
  condition added. The stash can be dropped.

Checks (scratch scripts, no API calls):

- Front-matter grid, `grid_fm.py`: 648 texts against commit 1 (name and claim flags × 9
  body lines × FAQ answers built from each line: quoted, unquoted, single-quoted, with a
  sentence before or after it, × with and without a copy under `description:`). None
  refused, none raises. 496 the same. 12 have another output, all M3: commit 1 cut "He
  trained in the U.S." or "He met Sen." out of an answer and left "Navy for two years."
  or "Smith at the hearing."; commit 2 leaves the answer whole. 140 have the same output
  and another report: the new reason, and `in_front_matter` false where a copy is left
  in an unquoted answer or under `description:`.
- Mutation: 9 mutants, each reverting one part of RM1.e.1 or RM1.e.2, each fail at least
  one test.

learning-qa review of the commit (5 findings, 4 fixed before the commit):

1. **A part cut only for a name went alone from an FAQ answer (high, also at commit 1).**
   Body "Bowen moved to Washington, D.C. Zed Example joined him there." with a name
   flag: removal cuts both parts, the first because it shares the sentence. The FAQ
   answer "Bowen founded the center. Bowen moved to Washington, D.C." lost its second
   sentence, which there is whole and has no name; an answer of only "Kerr moved to the
   U.S." lost its q/a pair. The check passed both, because it read the same flat set of
   cut parts. Fix: `_cut_groups` gives the edit and the check the parts cut together
   (`joined`) and the parts cut only for a name (`riders`); `_faq_goes` lets an answer
   sentence go when it is one of those whole sentences or each part was cut for its own
   flag. Tests: `test_rm1e2_part_split_off_with_name_stays_in_answer` (the two inputs,
   and the check refusing the edit by hand), and a guard,
   `test_rm1e2_part_with_its_own_name_goes_from_answer`.
2. **A copy left in the front matter with YAML escapes had no kept entry (high; one
   case new in commit 2).** The copy was looked for as written, so `'one''s'`,
   `\"anxiety\"` and an answer folded onto two lines were missed. New in commit 2: the
   answer "He trained in the U.S. Kerr used the word \"anxiety\" often." is now kept
   whole, with the escaped copy inside it. Fix: `_yaml_plain` undoes the escapes and
   collapses whitespace on both sides, for `left_in_head`, the name test, and the two
   scaffolding tests (the siblings the review named). Writing those tests showed one
   more: a name folded onto two lines in another front-matter sentence was not reported
   at all; the name test now reads the plain head too. Tests:
   `test_rm1e1_escaped_or_folded_copy_listed_as_kept` (4),
   `test_rm1e1_folded_name_in_front_matter_listed_as_kept` (2),
   `test_rm1e1_escaped_claim_only_in_front_matter_reason`.
3. **A q/a pair with a third key lost its q and a lines (medium, also at commit 1).**
   "source:" was left under "faq:" (the front matter no longer parsed) or attached to
   the pair before. Fix: the edit drops a pair only when nothing is indented under it
   after the answer; otherwise the pair stays and the copy is listed as kept. Test:
   `test_rm1e1_faq_pair_with_other_key_kept`.
4. **The check missed edits the FAQ edit cannot make today (medium).** It compared FAQ
   sentences as one count over all answers, so dropping the second question with the
   first answer passed, and so did deleting a line of a folded answer. Fix:
   `_faq_item_problems` compares items in order: the questions left are the same and
   in order; a kept item keeps its lines except an answer that loses whole sentences;
   an item goes only when it is a question and a double-quoted answer whose every
   sentence may go. Test: `test_rm1e2_faq_items_compared_in_order`.
5. **Not fixed (low): a kept entry where there is no copy.** The claim "Bowen agreed."
   is listed as still in the front matter when the answer is "Murray Bowen agreed.". It
   over-reports, which is the safe direction; a tighter match (a sentence start) could
   miss a copy in a form the edit cannot read. Recorded in TODO.md.

Checks after the fixes (scratch scripts, no API calls):

- The review's front-matter grid (`qa_c2/grid2b.py`, 392 texts: 7 body lines × 14 FAQ
  shapes × name and claim flags × with and without a `description:` copy, checked with
  `yaml.safe_load`): commit 2 before the fixes had 63 problem rows (15 copies left with
  no kept entry, 16 wrong `in_front_matter`, 12 unflagged FAQ sentences or pairs lost, 20
  pairs whose keys changed); after the fixes, none. Both refuse none and leave 84 texts
  unchanged.
- `grid_fm.py` (648 texts against commit 1) and `grid_c.py` (6,838 body lines against
  commit 2 before the fixes): the same numbers as above; the body grid is unchanged in
  every line.
- Mutation: 14 more mutants, each reverting one part of the fixes, each fail at least
  one test; the 9 above still fail one.

Second learning-qa review, of the fixes (5 findings, all fixed before the commit):

1. **A sentence cut only for a name in its label went from an FAQ answer (high).** A
   rider was only a part with the "same sentence as name" reason. A sentence cut because
   the name is only in the bold label the judge reads with it (RM1.b.2: "1. **Zed
   Example:** Kerr agreed with the point about the move.", also after "+ ") has the
   reason "name 'Zed Example'", so the answer "Kerr agreed with the point about the
   move." lost its pair, and the check passed. Fix: a rider is any part whose own words
   do not hold what it was cut for (`_cut_for_itself`), unless it was also cut for its
   own flag. Test: `test_rm1e2_name_only_in_label_sentence_stays_in_answer` (3 leads;
   "&gt; " already worked).
2. **A name split across "U.S." stayed in an answer (high, a regression of the first
   fix).** Body "The U.S. Navy sent Zed Example to Washington, D.C. Bowen met him
   there." is one cut sentence of three parts. The answer "The U.S. Navy sent Zed
   Example to Washington, D.C." is two of them; it was not the whole cut sentence and
   held a rider, so it stayed with the name, which fails the stage. Fix: an answer
   sentence also goes when its parts are next to each other, in order, in one cut
   sentence (`_is_run`) and one of them was cut for itself; a run of riders alone
   stays. Tests: `test_rm1e2_run_of_cut_sentence_with_name_goes_from_answer` (3) and
   `test_rm1e2_faq_goes_rules` (6; the riders-only run cannot be reached through
   removal, since a name only in a label is cut only when its sentence is alone on the
   line).
3. **Two double-quoted escapes were not undone (low).** `\u2019` and a line break
   escaped with a backslash: the copy left had no kept entry. The review proposed
   reading the values with `yaml.safe_load`; PyYAML is only a dev dependency here, so
   `_yaml_plain` instead undoes YAML's escapes in one pass (`\uXXXX`, `\UXXXXXXXX`,
   `\xXX`, `\t`, `\n`, `\"`, `\\`, an escaped line break, `''`), and leaves an
   escape out of range as written. It reads the whole front matter, so an escape in an
   unquoted value is undone too; that can only add a kept entry. Tests: two more cases
   of `test_rm1e1_escaped_or_folded_copy_listed_as_kept`, and
   `test_rm1e1_yaml_plain_undoes_escapes_in_one_pass` (7).
4. **Two items with the same question (low, a false refusal).** The check matched each
   item left to the first item before with that question, so emptying the first of two
   `- q: "What?"` items was refused. Fix: it uses the first item with that question
   that the item left matches (`_item_changes`). Test:
   `test_rm1e2_same_question_twice_either_item_may_go` (2).
5. **Two parts of the item check had no test (low).** Trimming blank lines at an item's
   end (without it, a blank line between items makes an emptied item more than a q/a
   pair, and the removal is refused), and the test that each sentence gone from a kept
   answer may go (the count over all answers also checks it). Tests:
   `test_rm1e2_blank_line_between_faq_items`,
   `test_rm1e2_item_check_refuses_answer_sentence_that_may_not_go`.

Not fixed (the review's, low): q and a written as separate list items ("- q: …" then
"- a: …") are refused, so the name is kept; the prompt never writes that shape.
Recorded in TODO.md.

Checks after the second fixes (scratch scripts, no API calls):

- The review's probes for findings 1–4 give the right output; its other shapes (keys
  before or after `a:`, nested lists, comments, CRLF) are unchanged.
- `grid_fm.py` (648 texts) and `grid_c.py` (6,838 body lines), each against commit 2
  before the second fixes: the same output and report in every text and line. Against
  commit 1, the same numbers as above. `qa_c2/grid2b.py`: still no problem rows, 84
  unchanged.
- Mutation: 24 mutants (the 14 above, rewritten for the new code, and 10 more for the
  second fixes), each fail at least one test; the 9 of the commit itself still fail one.
- Suites, with `.venv/bin/python`: `tests/` 1,978 passed, 13 skipped; the root run 2,073
  passed, 23 skipped, 1 xfailed (both with the commit-4 test file in the tree, one more
  test). The RM test file has 233 tests.

Third learning-qa review, of the second fixes (6 findings, all fixed before the commit):

1. **A part cut for itself elsewhere let a rider go from an answer (high).** Body line 1
   "Zed Example moved to the U.S. Kerr visited Washington, D.C. Bowen met him there.",
   line 2 "Kerr visited Washington, D.C.", flags the name and that claim. The answer
   "Kerr visited Washington, D.C. Bowen met him there." went with its pair, though it
   holds no name: the run rule asked whether a part was cut for itself by its text, and
   the claim on line 2 counted. Fix: `_cut_groups` marks each part of a joined sentence
   with whether it was cut there for its own flag (`joined` holds (text, mark) pairs);
   `_is_run` needs a marked part in the run. The clause "not all riders" in `_faq_goes`
   is gone, since a run of riders has no marked part. Tests:
   `test_rm1e2_part_cut_for_itself_elsewhere_is_still_a_rider_in_answer`, two more cases
   of `test_rm1e2_faq_goes_rules`, and (from the mutation check below)
   `test_rm1e2_part_cut_for_itself_elsewhere_goes_alone_in_answer`: the same claim alone
   in an answer sentence still goes.
2. **A body sentence was read as YAML (high, new in the second fixes).** Escapes were
   undone on both sides, so the body sentence "Kerr saved the notes in C:\temp folder."
   lost its "\t", and its copy `"…C:\\temp folder."` had no kept entry. Fix: a body
   sentence is only spaced (`_copy_in`), and it is looked for in two readings of the
   head (`_head_readings`): escapes undone (a double-quoted value), and as written with
   `''` undone (a plain or single-quoted value). The docstring that called this the
   safe direction is corrected. Tests: `test_rm1e1_body_sentence_with_backslash_copy_listed`
   (3 quotings), `test_rm1e1_single_quoted_copy_with_quote_and_backslash_listed`.
3. **Some YAML escapes were not undone (low).** `\_`, `\N`, `\L`, `\P`, `\a`, `\b`,
   `\e`, `\f`, `\v`, a backslash and a tab; an escaped surrogate pair stayed two
   characters. Fix: `_YAML_ESCAPED` holds every escape YAML 1.1 has; `_yaml_plain`
   joins a surrogate pair into one character; an escaped line break also ends in CRLF
   (the review's open question). Tests: `test_rm1e1_yaml_plain_matches_yaml` (21
   escapes, against `yaml.safe_load`), `test_rm1e1_yaml_plain_never_raises`, four more
   cases of `test_rm1e1_yaml_plain_undoes_escapes_in_one_pass`.
4. **"Next to each other" in the run rule had no test (low).** Pinned as it is: an
   answer sentence of the name's part and a later part of the same body sentence,
   without the part between, is not a copy of it, so it stays and the name is listed as
   kept (the stage fails loudly). Tests:
   `test_rm1e2_parts_not_next_to_each_other_stay_in_answer`, a case of
   `test_rm1e2_faq_goes_rules`.
5. **The escaped line break had no test that needed it (low).** Test: the case
   `fami\` + line break + `ly` in `test_rm1e1_yaml_plain_undoes_escapes_in_one_pass`.
6. **Two comments were out of date (low).** The `deletion_problems` docstring and the
   FAQ comment now say what riders are and that a sentence goes as `_faq_goes` says.

Adjacent, not fixed in commit 2 (the review's): a claim on a doubtful part that the
name removed ("Zed Example moved to the U.S. Kerr visited Washington, D.C." with the
claim flagged) is listed as kept, "sentence boundary uncertain", though its body copy is
gone; its FAQ copy stays. The flag is listed, so nothing is dropped, but the reason is
wrong. RM1.i.3 in commit 3 fixes it: the claim goes with the name, from the body and the
FAQ (a scratch probe on the commit-3 tree; `test_rm1e2_part_cut_for_itself_elsewhere_goes_alone_in_answer`
pins the commit-2 report and changes with commit 3).

Checks after the third fixes (scratch scripts, no API calls):

- Mutation: 12 mutants, one for each part of the third fixes, each fail at least one
  test. The 33 earlier mutants, rewritten for the new code: 32 fail a test. "A rider
  with its own flag elsewhere" survived until
  `test_rm1e2_part_cut_for_itself_elsewhere_goes_alone_in_answer` was added; "a run of
  riders goes" is retired, since the clause it removes is gone.
- `grid_fm.py` (648 texts against commit 1): 496 the same, 12 other outputs (the M3
  fix), 140 other reports, none refused: the same numbers as above.
  `qa_c2/grid2b.py`: no problem rows, 84 unchanged. `grid_c.py` (6,838 body lines
  against commit 2 before the third fixes): the same output in every line.
Fourth learning-qa review, of the third fixes: no behaviour bugs, none against the hard
rules (it checked that the new `_faq_goes` lets a sentence go only where the old one
did, and that the two readings change only the report). Its test gaps, fixed:

1. The OR over two name flags cut at one place had no test.
   `test_rm1e2_part_marked_by_any_name_cut_there` (2 answers × 2 flag orders).
2. The scaffolding test's two readings had no test. A claim with a backslash, only in a
   double-quoted value: `test_rm1e1_claim_with_backslash_only_in_front_matter_reason`.
   The name tests read both readings for the same rule; no realistic name differs
   between them, so no test tells them apart.
3. Not changed: the review asked that the over-report in
   `test_rm1e2_part_cut_for_itself_elsewhere_goes_alone_in_answer` be a strict xfail.
   It is pinned as it is in commit 2 and changes to `kept == []` in commit 3, in the
   same series.
4. The `_head_readings` docstring now says the as-written reading can over-report a
   copy in a double-quoted value with a backslash.
5. A 141-character docstring line was rewrapped.

- Suites, with `.venv/bin/python`: `tests/` 2,018 passed, 13 skipped; the root run 2,113 passed, 23 skipped, 1 xfailed (both with the commit-4 test file in the tree). The RM test file has 273 tests. The first
  run failed the vacuous-test gate (`test_m6b1_no_new_vacuous_tests`):
  `test_rm1e1_yaml_plain_never_raises` had no assertion. It now asserts that each result
  is a spaced string.
