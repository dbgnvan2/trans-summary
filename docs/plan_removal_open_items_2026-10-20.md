# Plan: the open removal items and Mini1's cold review of 813dd3c (2026-10-20)

Status: **approved 2026-10-20** ("build the plan … as written, with D3 (leave the
number) and D4 (do RM1.g.6) as recommended"). Commit 1 (RM1.g.4, RM1.g.5, RM1.g.7) is
built; commits 2–4 are not. See **Built** at the end for what was built and where it
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
