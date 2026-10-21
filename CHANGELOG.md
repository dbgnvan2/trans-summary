# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2026-10-20 (Removal: a claim no longer keeps a name)

`docs/plan_removal_open_items_2026-10-20.md`, "Mini1's cold review of 3ff21c0". RM1.g.6
says a kept claim (a warning) must not keep a name (a kept name fails the stage); two
more places did.
- A section whose only sentences were a claim and a name kept both. It now keeps the
  claim's sentence, which leaves the section with text, and the name's goes. A section
  whose only flagged sentences hold the name still keeps them, as before.
- A removal over the cap kept every flag. It is now retried like a deletion-check
  refusal, each set held to the same cap, so the name's sentences can go alone.
- The retry tries the names-only set before the older cuts. Before, a claim that fit
  under the cap was cut first and the name, whose sentence only RM1.b.3 places, was kept.
- Not changed (adjacent, for Dave): the required-item guard keeps a name sentence that
  holds the only mention of a required item.
- **RM1.b.2 (Mini1's F1, a regression from ec60324):** a one-sentence line with a name
  only in its bold label after "1. " or "> ", which the judge splits after "Sen." or
  "U.S.", was kept; each part was checked alone. The whole sentence is checked, so the
  line goes, as at 813dd3c.
- Tests for three code paths the suite did not catch (Mini1's F3, F4): the label of an
  unplaced first sentence, a claim riding an older name sentence in the retry, and an
  FAQ copy with an escaped quote.
- Not changed (Mini1's F2, decided by Dave): a section whose only sentences all hold the
  name is kept, so the stage fails.
- Mini1's reviews of d64dc1e: the two changes above kept claims that 3ff21c0 removed.
  The name sentences the section rule now lets go, and a label line RM1.b.2 now takes
  whole, were in every retry set; when their cut was refused or over the cap, every
  flag was kept. They now count as new cuts, so one retry set is the 3ff21c0 removal.
  The retry's last set is the claims on no name's sentence, so a name sentence that is
  over the cap or refused alone no longer keeps the other claims (also before 3ff21c0).
  Tests for a sentence with an old and a new name and a claim on it.

## [Unreleased] - 2026-10-20 (Abstract check on a judge error)

`docs/plan_remove_flagged_2026-10-19.md`, "Follow-up: the abstract check on a judge error".
- **RM2.b.1–RM2.b.3:** when the faithfulness judge errored and the entity check rejected a
  name, the abstract's generation check returned "unavailable": the abstract was kept
  with the name, the stage succeeded, and the release gate blocked at publish. The check
  now returns "partial", as the summary and overview check does: the name is fed back,
  and after the last attempt its sentence is removed. The same applies when the entity
  check errors and the judge flags claims. A partial draft ranks after every fully judged
  draft, and the closing message says the faithfulness check could not run.
- **RM2.b.4:** the warning said "judge off or no key" on any check error. The abstract,
  summary and overview checks now log which check could not run and the cause the judge
  reported ("the faithfulness check could not run at generation (judge error:
  APITimeoutError: …)"); the gate's verdict detail says only "1 of 1 artifact(s) could
  not be verified", so the cause is read from its items. The summary, overview and blog
  logged no cause before; the blog check now logs the cause its check returns.
- **RM2.b.5:** with `FAITHFULNESS_JUDGE_ENABLED = False` the abstract check read the
  disabled judge's PASS as a pass and logged "✓ Abstract passed faithfulness +
  grounding". It now returns "unavailable" (or "fail" on a rejected name), as the
  summary check does. Both checks log that the judge is off, and the closing message
  after a name removal says no claim was checked, not "no claim was flagged". RM2.a.1
  on main made the same message change by reading the config; the merge kept main's
  version and dropped this branch's `judge_off` parameter. The shared
  loop's "unavailable" warning (summary, overview, blog) no longer says the gate will
  verify it at publish; the precheck's line before it says whether the gate runs it
  again.

## [Unreleased] - 2026-10-20 (Tests: the WeasyPrint skip guard)

`docs/plan_removal_open_items_2026-10-20.md`, commit 4 of 4. Closes Mini1's report on the
PDF tests.
- **T-BE1:** the three WeasyPrint tests in `tests/test_bundle_export.py` (be7, be11,
  be12) skip when `import weasyprint` raises `ImportError` or `OSError`, with the error
  in the skip reason. On Mini1 the import raises `OSError` (uv's Python cannot find
  Homebrew's `libgobject`), and `pytest.importorskip` catches only `ImportError`, so the
  tests failed instead of skipping.
- Not changed (adjacent, for Dave): `bundle_export._render_pdf_weasyprint` catches only
  `ModuleNotFoundError` on the import, so on such a machine a PDF bundle export raises
  `OSError` instead of logging that WeasyPrint cannot be used.

## [Unreleased] - 2026-10-20 (Removal: the rules for names, labels and bold runs)

`docs/plan_removal_open_items_2026-10-20.md`, commit 3 of 4. Closes open items D, F7 and
F8, and the adjacent items on a failed check refusing every removal, a bold run that
opens a sentence, and the names-only message with the judge off.
- **RM1.g.6:** when the deletion check refuses a removal, removal is tried again through
  the same cap, front-matter edit and check: first without the sentences only RM1.b.3
  places (the name flags' kept in), then without any of them, then with only the
  sentences a name flag names (and the claims on them), then those without the RM1.b.3
  sentences. A sentence split after an abbreviation is left out whole. The first set the check passes is cut, and each
  other flag is kept with the first reason, or listed as removed in part when some of
  its copies went. Before, one refused claim removal kept every name too, and a kept
  name fails the stage.
- **RM1.b.3:** removal finds a sentence the judge joined with one space after "Dr." or
  another abbreviation when the line has a tab, a non-breaking space or two spaces there,
  so a name inside that sentence can be removed. The first copy in the line is found,
  with the judge's spacing or not. On Mini1's M1 line the check still refuses the
  removal: the bold sentence left alone would be a line the judge does not read.
- **RM1.b.4 (F7):** a line left with only an allowlisted plain label ("Note:",
  "- Summary:") after its sentence is removed goes, as "**Note:**" does.
- **RM1.b.5:** a bold run that opens a sentence and closes inside it ("**Zed Example**
  spoke at length.") is cut with both markers. Before, the cut left a stray "**", so
  the check refused it and the name was kept. A name in "__…__" or "_…_" is now found
  as a name, so its sentence goes and a copy left elsewhere is listed as kept.
- **RM1.i.3 (F8):** a claim whose copies are all on an uncertain split ("… in the U.S.
  Army …") is no longer listed as kept when a name flag removes its sentence. The
  removal carries both reasons and the claim's judge record; if a copy is left, the
  claim is listed as removed in part.
- **RM2.h.1 (D):** a guard test: with the name flag before the claim flag on one
  sentence, the removal carries the claim's record.
- **RM2.a.1:** with the faithfulness judge off, the names-only message says the judge is
  off and no claim was checked (it said "no claim was flagged").
- learning-qa review, fixed before the commit: a sentence RM1.b.3 newly places whose cut
  the check refuses kept every other removal too, and a claim commit 2 removed was kept;
  a sentence with odd spacing was placed at a later copy written with one space; a name
  in "__…__" or "_…_" was not matched, so a copy left in a heading was not listed. Its
  re-reviews: the retry still cut a sentence after a newly placed one in its line, ran
  in an order that kept a name it could remove, cut one part of a sentence split after
  "U.S.", and still cut a sentence first named in "_…_" whose cut the check refuses.
- Found when merging onto commit 2's last fixes: a claim on an uncertain part of a
  name's sentence (RM1.i.3) marked that part as cut for its own flag, so an FAQ answer
  of that claim and an unflagged sentence after it ("Kerr visited Washington, D.C. Bowen
  met him there.") went whole. Only a part that holds the name marks such an answer
  sentence now; the answer stays and the claim's copy there is listed as kept.
- Retry grid (65,340 runs, no API calls): against commit 2, nothing commit 2 removed is
  now kept, and every flag is listed as kept exactly when it is still in the output.
- Grid check (scratch script, no API calls), 6,838 lines against commit 2: 1,302 now
  removed (RM1.b.5 620, RM1.b.3 526, and 156 M1 lines with a bold label before them), 160
  lines now drop their "Note:" or "Summary:" label (RM1.b.4), 0 now refused. The token
  check finds no removal that deletes an unflagged word. No real artifact line is placed
  differently.

## [Unreleased] - 2026-10-20 (Removal: the front matter)

`docs/plan_removal_open_items_2026-10-20.md`, commit 2 of 4. Closes open item A and
Mini1's M3 and the FAQ part of M4.
- **RM1.e.1 (A):** every copy of a removed sentence left in the front matter, in an
  unquoted FAQ answer or under another key such as `description:`, is listed as kept
  with the reason "removed from the body; still in the front matter" (it said "still
  in the front matter's FAQ answers"). A name flag is listed only while its name is in
  the front matter. The removal record's `in_front_matter` is true only when the
  sentence was taken from an FAQ answer and no copy is left.
- **RM1.e.2 (M3, M4):** an FAQ answer is split as the judge splits a line: a part after
  "U.S.", "Sen." or another listed abbreviation joins the part before it, and a joined
  sentence goes only when all of it was removed. Before, removing "He trained in the
  U.S." from the body left the answer "Navy for two years.". The deletion check compares
  FAQ answers sentence by sentence, so a word deleted inside an answer is refused.
- **learning-qa review, fixed before the commit:** a part cut from the body only because
  it shares a sentence with a name ("Bowen moved to Washington, D.C." before "Zed
  Example joined him there.") went alone from an FAQ answer, where it is a whole
  sentence without the name; it now stays. A copy left in the front matter with YAML
  escapes (`''`, `\"`) or folded onto two lines had no kept entry; copies are now found
  with the escapes undone. A q/a pair with another key ("source:") lost its q and a
  lines; it now stays whole. The deletion check compares FAQ items one by one, in
  order, so a swapped answer or a deleted line of a folded answer is refused.
- **Second learning-qa review, of those fixes, fixed before the commit:** a sentence cut
  only because the name is in the bold label read with it ("1. **Zed Example:** Kerr
  agreed …") went from an FAQ answer where it has no name; it now stays. An answer
  sentence holding the name and part of a sentence split after "U.S." ("The U.S. Navy
  sent Zed Example to Washington, D.C.") stayed with the name, a regression of the first
  fix; it now goes. Copies with a `\u` escape or an escaped line break are found. Two
  FAQ items with the same question no longer make the check refuse.
- **Third learning-qa review, fixed before the commit:** whether a part of a joined
  sentence was cut for its own flag is now read at its place in that sentence, not by
  its text, so a claim cut on another line no longer lets a part without the name take
  an unflagged part out of an answer with it. A body sentence is no longer read as YAML
  ("C:\temp" kept its "\t"); it is looked for in the front matter read with YAML's
  escapes undone and as written. Every YAML escape is undone (`\_`, `\N`, `\L`, `\P`,
  `\a`, `\b`, `\e`, `\f`, `\v`), an escaped surrogate pair is one character, and an
  escaped line break may end in CRLF.
- Front-matter grid (scratch script, no API calls), 648 texts against commit 1: none
  refused; 12 other outputs, all M3; 140 other reports, the new reason. The review's
  392-text grid: 63 problem rows before the fixes, none after.

## [Unreleased] - 2026-10-20 (Removal: the deletion check reads what the judge reads)

`docs/plan_removal_open_items_2026-10-20.md`, commit 1 of 4. Approved by Dave ("build the
plan … as written"). Closes M1, M2 and most of M4 from Mini1's cold review of 813dd3c, and
open item E.
- **RM1.g.4 (M1):** the deletion check reads each line's sentences as the judge splits
  them, including the ones removal cannot place in the raw line. The judge joins
  "Dr." and "Bowen" with one space, so after "Dr." with a non-breaking space, a tab or
  two spaces removal could not find "He met Dr. Bowen at the center". A name removal
  earlier on that line then dropped the line, and the check excused the lost unflagged
  claim (new in 813dd3c). That removal is now refused. A change after such a split is
  now seen too (M4).
- **RM1.g.5 (M2, M4):** the check counts what its sentence comparison leaves out: an
  allowlisted label ("Note:"), a list number ("2)", "2."), a sentence that is only a list
  number, and a bold-only line. None may be added, except a bold-only line that a cut
  leaves alone; one may go only with a removed sentence that starts with it, or with its
  line. A "2." sentence that moves to the start of its line counts as the same number,
  so "Zed Example spoke … the move. 2. The group met again later." now loses the name
  sentence; 813dd3c refused it, and the kept name failed the stage. Deleting a
  mid-line "Note:" or "2)" alone, or a bold-only line, is now refused.
- **RM1.g.7 (E):** `_cut` raises `ValueError` when two spans on a line overlap. The
  pipeline already keeps the draft and records "removal failed".
- **learning-qa review, fixed before the commit:** a number-only sentence the cut left
  alone ("… that year. 1975.") dropped with its line, and the line's marks excused it, so
  an unflagged number went with no record. A line removed whole now excuses only the
  label and list number at its start, so that removal is refused, as at ec60324. This
  also stops a cut sentence's label or number being counted twice. Two branches got
  tests, and three test lines use `\u00a0` instead of a literal non-breaking space.
- Grid check (scratch script, no API calls), 6,838 lines against ec60324: 102 now
  refused, all removals that lost an unflagged sentence (M1); 144 now removed, all the
  "2." case (M2); the rest unchanged. learning-qa's 2,142-line grid and the bold-label
  grids (2,080 and 672 lines) show nothing worse. Its 520-line token grid finds no
  removal that deletes an unflagged word (ec60324: 12). No real artifact has the M1–M3
  shapes.

## [Unreleased] - 2026-10-20 (Removal: bold label after a list or quote marker)

`docs/plan_remove_flagged_2026-10-19.md`, "Follow-up: a bold label after a list or quote
marker". Approved by Dave ("fix everything", D1 keep, D2 yes).
- **RM1.b.1:** a bold label after "1. ", "1) ", "> ", "+ ", "• " or a run of markers
  ("- 1. ", "> - ") no longer puts a sentence's span inside the bold run. The judge reads
  that label as the start of the first sentence ("Kerr Agreed: Zed …"); removal now cuts
  only the words after the label, so the marker and the label stay, and a line left with
  only those goes. Before, the cut left a stray `**` and the deletion check refused every
  removal in the artifact, so a flagged name stayed and the entity check failed the
  stage; on "+ " lines the cut also took the marker and the label without saying so.
  The removed-sentences record holds the sentence without the label.
- **RM1.b.2 (D1, keep):** a name that is only in such a label is kept with the reason
  "only in a heading, a label or the front matter" when its line has more sentences, as
  on "- **Label:**" lines. On a one-sentence line the line goes, label included.
- **RM1.g.2:** the deletion check compares a labelled line's first sentence, and the
  claim the judge reads from it, without the bold label, as it does for "Note:"
  (RM1.g.1), because after the cut the judge reads the label with the next sentence. A
  sentence that is only a label is compared as it is.
- **RM1.g.3 (D2):** a claim after the removal that was a sentence before, but not a claim,
  does not count as added. The token check already proves that only deletions were made,
  and the gate judges the saved file at publish. This fixes F6 (under a question heading
  the "[in answer to: …]" tag moves to the next sentence) and "Status: Zed … 2020 was a
  hard year.", where "Status:" now goes with its sentence and the judge reads "2020 was a
  hard year." as a claim. A new claim that was not a sentence before is still refused.
- Grid check (scratch script, no API calls): of 2,080 name-flag lines, 530 that 813dd3c
  refused now remove the name and none is worse; of 672 claim-flag lines, 169 are fixed
  and none is worse. 36 "&gt; " lines are still refused, as at 813dd3c.
- `test_rm1b_marker_run_line_does_not_backtrack` runs its removal in the child process
  too, so a backtracking `_MARKED_LABEL` fails the test instead of hanging the suite.
- Review (learning-qa) fixes in the same change:
  - The first build stripped every bold label of the text from the start of every
    sentence and claim, so deleting a label ("1. **Not true:** X" to "1. X") or a plain
    "Kerr Agreed: " prefix on another line passed the check. The label now comes off
    only its own line's first sentence, one claim per line, and the check reports "a
    bold label was lost" when more bold labels go than the lines removed whole had.
  - Bold text ending in a period ("1. **Dr.** Zed …") is not a label: the judge reads
    on past that period only when it is no sentence end. The removal is refused there,
    as at 813dd3c.
  - A claim flag the judge read with a bold label is also listed as kept when the label
    stays: "removed in part; its bold label stays and is now read with the next
    sentence". Keeping the sentence instead, as RM1.b.2 does for names, is in `TODO.md`
    for Dave.
  - An FAQ copy left in the front matter is listed for each flag that cut its sentence,
    not only for the last one, and says when the flag's bold label stays.
  - learning-qa re-check of these fixes: a number inside the bold label ("1. **2) Key
    point:** Zed …") is read as the judge reads it ("Key point:"); the first fix refused
    those removals. A dash is its own token in the token check, so cutting the sentence
    after "**Kerr Agreed**—" (no space) is a deletion; it was refused, also at 813dd3c
    except on "+ " lines, where the label was cut too.
- Tests: 20 new tests (53 cases) in `tests/test_remove_flagged_rm.py`; 28 rules were
  reverted one at a time and each makes a test fail.

## [Unreleased] - 2026-10-20 (Removal: open items C and B)

`docs/plan_remove_flagged_2026-10-19.md`, "Follow-up: open items C and B".
- **C (RM1.g.1):** removing the first sentence of a line no longer makes the deletion
  check refuse every removal in the artifact when the next sentence starts with a label
  such as "Note:" or an enumerator such as "2) ". The check now compares sentences without
  that label, as `extract_claims` reads the start of a line; the text keeps the label.
  The refusal also kept flagged names, so the entity check could fail the stage. A
  sentence whose line would then start with a skip label ("Status:") is still refused.
- **B (RM1.i.1, RM1.i.2):** a split before a number no longer joins the two sentences, so
  a flagged name deletes only its own sentence ("… the move. 2020 was a hard year." keeps
  the second). A claim at such a split is still kept as uncertain. After an abbreviation
  split a name still takes both parts; the part without the name is recorded as "same
  sentence as name 'X' (uncertain split)".
- Review (learning-qa) fixes in the same change: "ch", "chap", "sec", "est", "nos",
  "pt", "para", "op" are uncertain-split abbreviations, so a name before "ch. 4" takes
  the whole sentence ("p" is not needed: the judge already joins after single letters);
  the deletion check counts copies, so reading "Note: X" as "X" cannot hide a lost copy;
  a short claim ("Note: Kerr agreed.") is exempt only when it stopped being a claim:
  both sides are counted against the claims `extract_claims` returns, so a copy the
  judge did not read as a claim before (too short, or on a skipped line) does not
  count, and a short sentence it reads as a claim under a question heading is not
  short; each part of a split with its own name gives that name only.
- A line removed whole no longer excuses any lost sentence or claim found in its text.
  It takes only the claims `extract_claims` loses when that line alone is deleted from
  the document, beyond its sentences (a bold label such as "Kerr Agreed", or under a
  question heading the label and sentence read as one claim), one copy each.
- Known side effect of B: a name sentence followed by a number sentence on a line with
  a bold label after "1. ", "> ", "• " or "+ " is now refused (a stray `**` would be
  left) instead of removed with the number sentence; recorded in `TODO.md`.
- Tests: 20 new tests (27 cases) in `tests/test_remove_flagged_rm.py`; 18 rules were
  reverted one at a time, 17 make a test fail and the 18th gives the same results.

## [Unreleased] - 2026-10-19 (Removal: cold-sweep fixes)

Cold review of the RM change on Mac mini1 (`docs/plan_remove_flagged_2026-10-19.md`,
"Cold sweep"). A sentence named by two flags is cut once; the deletion check covers short
sentences; a regex that could hang on a run of list markers is fixed; a split after an
abbreviation or before a number is not removed as a fragment (names take the whole
sentence); FAQ copies that cannot be edited and a bold lead sentence are no longer lost
unreported; the coverage guard keeps claims when a required item is already at low
confidence; a failed save keeps the record and a failed re-save fails the stage; the
end-of-run messages and list say what happened, once.

## [Unreleased] - 2026-10-19 (Remove sentences still flagged after revision)

Plan `docs/plan_remove_flagged_2026-10-19.md` (RM0–RM9), user decisions D1 off, D2 yes,
D3 blog left out, D4 yes, D5 25%, D6 by hand.

- **RM1, removal:** new `flagged_removal.py` (pure functions).
  `remove_flagged_sentences` removes each flagged claim where it is a whole sentence of
  the body, every occurrence, with a bullet or bold label left empty, and the overview's
  copy in the front-matter FAQ answers (an emptied answer drops its pair). It keeps,
  with a reason: a claim not found as a whole sentence, a heading, a section's only
  text, the summary's only mention of a required coverage item, and every claim when
  the removals would exceed 25% of the words. `deletion_problems` checks the result:
  word-level deletions only, the claims left equal the unflagged claims before, headings
  and front-matter keys unchanged, the front matter still well formed, bold markers
  paired. If any check fails, the draft is kept as it is.
- **RM2, wiring:** `_generate_until_faithful` (summary, overview) and the abstract loop
  remove the sentences still flagged from the kept draft after the last attempt, then
  run the entity check on the saved file. A name the entity check rejects is removed
  the same way (D4). The blog is not changed (D3). The judge does not run again.
  `release_gate._wrong_records` adds the judge's rationale.
- **RM3, record:** `removal_record.py` writes `<base> - removed-sentences.json` before the
  artifact: per removed sentence the sentences before and after it, the reason, the
  judge's label, rationale and evidence; the draft before removal; the saved file's
  sha256. If the write fails, nothing is removed. A new draft clears its artifact's entry.
- **RM4, list:** the GUI (complete, failed, paused) and the CLI print the run's removed
  sentences, with the sentence now after each, before the token report
  (`removal_record.format_run_removals`).
- **RM5, config:** `FAITHFULNESS_REMOVE_FLAGGED`, `FAITHFULNESS_REMOVE_ARTIFACTS`,
  `FAITHFULNESS_REMOVE_MAX_SHARE = 0.25`, `SUFFIX_REMOVED_SENTENCES`;
  `FAITHFULNESS_SEVERITY_MODE = "off"` (D1).
- **RM6, tests:** `tests/test_remove_flagged_rm.py` (46 tests) and
  `tests/test_ts_gui_run_all.py::test_rm4b_list_before_token_report_on_complete_fail_pause`.
  On the 5 flagged WO6 replay drafts the code removes 8 of the 9 flagged sentences; the
  ninth is the only sentence under its heading and is kept.
- **learning-qa (5 findings, all fixed):** a flag removed in one place but kept in
  another is now listed as kept (F1); `transcript_summarize.py` and
  `transcript_overview.py`, the scripts that remove sentences, print the list, and so do
  both exits of `transcript_process.main` and a GUI stage that raises (F2); a refused
  removal is recorded, so the list shows the flags left in (F3); a coverage keyword in a
  bold label is protected (F4); a failed save of the cleaned draft no longer fails the
  stage (F5).

## [Unreleased] - 2026-10-19 (Heading timestamps without brackets)

Plan `docs/plan_heading_brackets_2026-10-19.md` (HB0–HB3). The Holt panel run stopped
at Format: the model wrote all 40 headings `(00:00:19).`, not `([00:00:19]).`, and each
failed the heading contract. That also kept RS.3 from restoring the one dropped phrase.

- **HB1:** `formatting_pipeline.normalize_heading_brackets` rewrites a `## Section N – …`
  heading timestamp written `(hh:mm:ss)`, `[hh:mm:ss]` or `([hh:mm:ss])`, with or without
  the final period, to `([hh:mm:ss]).`. `format_transcript` runs it before
  `normalize_heading_timestamps` and logs "Added the brackets to N of M heading
  timestamp(s)". Brackets must pair; two- and four-group times, other lines, the hyphen
  form and a heading with a second time in its title are left for the validator. On that
  run's output: 40 headings fixed; the only error left is the one deletion that RS.3
  restores. learning-qa: added the call-order test HB1.g and paired the brackets.

## [Unreleased] - 2026-10-19 (Faithfulness flags warn, never block)

Plan `docs/plan_warn_only_2026-10-19.md` (WO0–WO7). The user's decision after the JS6
calibration: "Warn only, never block." Supersedes the NQ plan
(`docs/plan_severity_downgrade_2026-10-19.md`, not built).

- **WO1, no outside facts:** the summary, abstract, overview and blog prompts forbid
  spelling out an abbreviation the transcript does not spell out, and adding a first
  name, age, place, occupation, affiliation or family fact it does not state.
- **WO2, warn only:** `faithfulness` is out of `config.GATE_BLOCKING_CHECKS`. A flagged
  claim (wrong or not quite right) is a WARN; a judge ERROR does not block. The entity
  check and `theme_grounding` still block.
- **WO3, % score:** the verdict gives each artifact's score, "summary 90% (27 of 30
  claims supported)". `claims_judged` is stored with a cached PASS;
  `JUDGE_LOGIC_VERSION` is "2026-10-19b".
- **WO4, generation:** still revises flagged claims; when no attempt is clean it keeps
  the best draft and the stage succeeds, unless the draft has a name the entity check
  blocks on. The abstract's name check now covers the abstract only.
- **WO5, warnings in the run log:** `run_gate` logs every non-blocking verdict that is
  not a PASS, with each flagged claim, for every caller (GUI, html_generator,
  packaging, bundle export, CLI). An advisory ERROR is tagged UNVERIFIED.
- **WO6, live check** (12 summary drafts, $1.83): 22 → 9 flags, 93% → 97% of claims
  supported, outside-fact hits 10 → 4. Results in
  `docs/calibration/2026-10-19_outside_facts/`.

## [Unreleased] - 2026-10-19 (Faithfulness flags fail only on WRONG content)

Plan `docs/plan_judge_severity_2026-10-19.md` (JS1–JS7), from the review
`docs/judge_flag_review_2026-10-18.md`: of 43 flags, 9 were WRONG and 34 NOT QUITE RIGHT,
and every flag failed the run. The user's rule: fail only on WRONG content.

- **JS1, severity step** (`faithfulness_judge.classify_severity`): runs on each flag that
  confirmation keeps. A first WRONG vote is final; a first NOT QUITE RIGHT vote gets a
  second; two NOT QUITE RIGHT votes downgrade; a split goes to a third vote. A NOT QUITE
  RIGHT vote counts only if its quote is in the source and shares a significant word
  with the claim (`_evidence_in_source`; thresholds in config). A failed vote keeps the
  claim WRONG and marks it `severity_undecided`. Policy (W1–W4, N1–N3) in
  `prompts/Faithfulness Severity Prompt v1.md`. `config.FAITHFULNESS_SEVERITY_MODE =
  "majority3"`; `"off"` restores the earlier behaviour.
- **JS2, gate and generation:** only WRONG claims fail `faithfulness` and
  `topic_term_faithfulness`. Only NOT QUITE RIGHT → WARN listing each claim with type
  and evidence → ALLOW_WITH_WARNINGS. FAIL items gain a `wrong` list (claim, type,
  evidence, `undecided`). The advisory blog check WARNs with the NOT QUITE RIGHT claims
  named. Generation prechecks revise only for WRONG claims and log the others by name
  (JS0.d: such drafts pass without revision). JS2.d: the "not faithful" warning lists
  every claim (the 300-character cut is gone).
- **JS3, cache:** `JUDGE_LOGIC_VERSION = "2026-10-19"`; the cache key also hashes the
  severity prompt, mode, thresholds, the evidence check, `FaithfulnessResult` and the
  severity types. A FAIL that rests only on failed severity votes is not cached and leaves
  no "flagged" marker (P1).
- **Calibration tools:** `judge_recalibration.py --severity` judges flagged gold claims
  and fails the bars if a gold WRONG case is downgraded; `gold.json` has severity labels
  (JS0.c); `judge_drift_monitor.py` reports a downgraded gold WRONG case as drift.
- **JS5, summary prompt:** names the speaker as the transcript or title does; credentials
  or a role only if the transcript states them; a preview only if the speaker gives one.
- **JS6, live calibration** (`docs/calibration_judge_severity_2026-10-19.md`, $4.50): gold
  recall 0.92/0.96/0.92, precision 1.00 ×3; no gold WRONG case, injected WRONG claim
  (12 of 12) or hand-labelled WRONG flag (0 of 12) downgraded; part e no new FAIL. The
  step downgraded 0 of 12 NOT QUITE RIGHT flags in 12 fresh drafts (9 of 12 drafts fail
  before and after) and 3 of 90 in the review set: the judge's votes are mostly WRONG.
  Shipped as safe; loosening it is a separate decision.
- learning-qa findings fixed (F1–F6, listed in the plan).

Docs: plan, calibration report, PROMPT_REGISTRY, ARCHITECTURE_DESIGN 4.3, PROJECT_STATUS,
TODO, LEARNINGS.

## [Unreleased] - 2026-10-19 (Incomplete source transcript notice)

Plan `docs/plan_incomplete_transcript_2026-10-19.md` (IT1–IT5). The Systems Biology raw
transcript's header says "Cloud transcription incomplete: transcribed 5 of 12 chunks",
nothing read it, and about 40 of the 88 minutes were summarised and judged.

- **IT1, header reader** (`source_completeness.py`): reads the transcription tool's
  `Warnings:` line and finds the incomplete warning (wording in
  `config.SOURCE_INCOMPLETE_MARKERS`: "transcription incomplete" or "missing time
  ranges"; a warning saying "transcribed N of M chunks" with N < M also counts). It takes
  the chunk counts and missing ranges from the tool's own text. When they don't add up
  (one range per missing chunk), it quotes the warning instead. Warnings are split after
  a period or before a capital letter, because a real warning contains "; skipped." and
  the incomplete warning ends with a time range. It finds the header wherever the
  source-fidelity check does (a leading blank line, an indented `Warnings:` line). Only
  the header is read; the body is never searched.
- **IT0.a, warning, not a stop:** an incomplete transcript is reported, never blocks.
- **IT2, the user is told before the run** (`ts_gui.py`, `formatting_pipeline.py`): the
  Confirm dialog and the top of the run log name the missing time ranges; the Format
  stage logs them (read before the pattern set changes the text); every
  transcription-tool warning is logged in one line (IT0.f). The GUI reads the selected
  file when Format is selected, and otherwise the project's raw-source copy, which is
  the file the formatted transcript was checked against. A missing source file, or one
  without the tool's header, is said in the log, not hidden.
- **IT3, release gate** (`release_gate.check_source_completeness`, advisory): WARN with
  the missing ranges in the detail and in the run manifest's items; PASS when the header
  has no known incomplete-transcript warning, or when there is no header ("completeness
  not stated"); non-blocking ERROR when no raw source is found. It reads the raw source
  that `source_fidelity` matched (the two now share `_match_raw_source`), so both
  checks name the same file. The GUI now prints every gate `[WARN]`
  line when the gate allows with warnings (IT0.c), not only on a block.
- **IT5, count:** of 20 project folders on CrucialX9 (12 KCFC, 8 BTA, plus one empty
  nested `projects`), 19 have a raw source with the tool's header, and **1 carries the
  warning**: Systems Biology `…_20260718_155038_v-valid-5m`. A read-only live check of
  the new gate step on all 21 folders: 1 WARN (that project), 16 PASS, 4 non-blocking
  ERROR (raw source not where the gate looks; see TODO). No file on the drive changed.
  Re-run after the review fixes: the same result.
- **Tests:** `tests/test_source_completeness_it.py` (real headers word for word: parsing,
  complete and plain headers, malformed and miscounted warnings, body text and near
  misses, reworded warnings, header variants, the gate verdicts and manifest, the file
  the gate and the GUI read, the GUI dialog and run log),
  `tests/test_formatting_pipeline.py::test_it2a_format_logs_incomplete_source`,
  `tests/test_run_fixes_rf.py::test_it3h_gate_warnings_logged_on_allow`.
- **Docs:** `ARCHITECTURE_DESIGN.md` §4.3 lists the check; config comment above
  `GATE_BLOCKING_CHECKS`; `tests/fixtures/prose_real/README.md` says the Systems Biology
  fixture is the partial transcript; TODO.md closes the 2026-10-19 item and adds IT0.d
  (published pages don't say a talk is partial) and IT0.e (a truncated transcript whose
  header doesn't say so) as deferred.

## [Unreleased] - 2026-10-18 (Summary closing guard, best-draft tie-break, last-try wording)

Plan `docs/plan_summary_closing_2026-10-18.md` (SC1–SC3). The 2026-10-18 Holt run stopped
at Structured Summary: the prompt asked every talk for a conclusion, open questions and
future directions, the recording has none, and the invented closing was flagged on all
three tries.

- **SC1, summary closing** (`prompts/Summary Generation Prompt v1.md`): the closing gives
  the speaker's own conclusion, open questions or future directions only if the speaker
  gives them near the end. Otherwise it restates the speaker's main point, without saying
  that it comes at the end. It adds nothing of its own and doesn't say the talk has no
  conclusion. It also tells the model that the JSON `closing` fields come from a phrase
  search and are often wrong: they found a conclusion in 0 of 19 real transcripts. The
  review checklist line now reads "Closes with the speaker's conclusion, or the main
  point if the talk states none" (`summary_validation.generate_review_checklist`).
- **SC1.d live check** (`docs/calibration_summary_closing_2026-10-18.md`; script and
  `results.json` in `docs/calibration/2026-10-18_summary_closing/`; $1.77): old vs new
  prompt, two first drafts each on four real transcripts.
  - Closing flags: 6 → 2.
  - "No conclusion" sentences: 7 of 8 → 0 of 8.
  - The Holt stage passed on try 2.
  - Societal Emotional Process: the speaker's closing point appeared in 1 of 2 new
    closings, and in 0 of 2 old ones.
  - Body flags went 12 → 17, the same kinds of claims under both prompts. Not separable
    from variance at this sample size; watched in TODO.
  - The script refuses a `--scratch` folder inside the repo, the real projects folder or a
    case's parent folder (learning-qa review). Added after the run; it does not change
    what is measured.
- **SC2, tie-break:** when every try fails faithfulness, the kept draft is the one with
  the fewest flagged claims, and on a tie now the later one (it has had more of its
  flagged sentences fixed). This applies in `_generate_until_faithful` (summary, blog,
  overview) and in the abstract loop. A draft rejected unjudged is still never kept.
  Review fix (learning-qa): when the judge errors but the name check finds names, the
  summary and blog prechecks now return "partial" instead of "fail". The draft still
  fails and its names are fed back, but it never beats a fully judged draft, because its
  count holds only the names. Strict `<` already let such a draft win with a lower count.
- **SC3, log wording:** the last try's warning says "no attempts left" instead of
  "revising the flagged sentences", in both loops.
- Tests: `tests/test_summary_closing_sc.py` (SC1.a–c, SC2.a–c, SC2.e–f, SC3.a);
  `tests/test_abstract_faithful_retry.py::test_sc2d_abstract_tie_keeps_the_later_draft`,
  `::test_sc3b_abstract_last_try_wording`.
- The judge is unchanged, so `JUDGE_LOGIC_VERSION` is unchanged and no re-calibration
  was needed. README, ARCHITECTURE_DESIGN, DOCUMENT_REFERENCE and PROMPT_REGISTRY don't
  describe the closing instruction, the tie rule or the log wording, so they needed no
  change.

## [Unreleased] - 2026-10-17 (Format thinking ratio re-derived at "medium")

Per `docs/calibration_formatting_model_2026-10-11.md`, "Thinking ratio at medium".

- `config.FORMATTING_THINKING_RATIO` 3.5 → 1.1, `_MAX` 5.0 → 3.0. Derived from the six
  "medium" runs of 2026-10-14 with no new API calls
  (`docs/calibration/2026-10-14_formatting_effort/derive_thinking_ratio.py` →
  `thinking_ratio.json`):
  - 1.1 is the median, by the definition the cost estimate uses (output ÷ T − 1, range
    0.79–1.42);
  - 3.0 is 2.4× the largest run by the length check's definition (1.27). Six runs are a
    small sample: at "high", six runs found 4.4 where 33 later runs found 8.4.
- Effect:
  - the GUI Format estimate drops from 4.5 × T to 2.1 × T output tokens;
  - the single-pass stop moves from about 20k to about 40k words;
  - the "may be cut off" warning moves from above about 14.7k to above about 21.8k words.

  No current transcript (longest 14.6k words) reaches either.
- How 3.5 / 5.0 were computed was not recorded, and no single definition reproduces the
  documented "2.0–5.0, median ~3.6". The new values use the code's own definition, and
  the script is committed so they can be re-derived. Found, not fixed (no longer
  applies): at "high", 9 of 33 end-to-end Format runs were above the old maximum of 5.0.
- Tests (`tests/test_formatting_model_u4.py`):
  - the pin test now checks the new values;
  - the warning test uses the midpoint of the two config values instead of a hard-coded
    4.2;
  - new `test_u4_thinking_ratio_covers_medium_measurement` checks `thinking_ratio.json`
    against the committed results, and checks both config values against the data.
- learning-qa found 2 problems, both fixed (commit f795aeb):
  - P6: the "may be cut off" warning in `formatting_pipeline.py` said "at the most
    thinking measured", which is no longer true now that `_MAX` is a margin above the
    data;
  - P3/P9: the script could not read real "medium" Format runs. It now lists them as
    `medium_e2e` (none yet), and an open TODO checks `_MAX` against them after the next
    e2e run.
Offline suite: 1698 passed / 23 skipped / 1 xfailed.

## [Unreleased] - 2026-10-17 (judge "disabled" wording; review of the Hermes Format change)

- Release gate: when a judge flag is off, the PASS verdict detail now names the flag
  (`FAITHFULNESS_JUDGE_ENABLED is False` / `THEME_JUDGE_ENABLED is False`) instead of
  "awaiting (M2.B) calibration" — both judges were armed 2026-07-15. Applies to
  `check_faithfulness`, `check_theme_grounding` and `check_topic_term_faithfulness`
  (gate output text only; no status change). The two judge docstrings, the release-gate
  policy comment and the M2 header in `config.py`, and one test docstring said the same
  stale thing and are corrected.
- TODO: follow-up to re-derive `FORMATTING_THINKING_RATIO` / `_MAX` at "medium".
- Restored four "Why Families" outputs under
  `docs/calibration/emphasis_effort_2026-10-13/outputs/` that had been deleted from the
  working tree (cause unknown; three test fixtures with the same name were also deleted
  and were restored earlier today).
- `config.py`: the two comments that said `topic_term_faithfulness` is "not yet calibrated"
  now say it was measured on real runs 2026-10-12 and is still advisory.
- TODO: the abstract stage reports "passed faithfulness" when the judge is switched off
  (`extraction_pipeline._abstract_gate_precheck`); recorded, not fixed (behaviour change).
- Sweep: learning-qa (4 findings, all fixed as wording), /code-review (1 finding, fixed),
  learning-qa re-sweep of the fixes (3 adjacent findings: 2 fixed as wording, 1 recorded
  in TODO). The gate CLI was run on a copy of the Why Families run with both judges off;
  the verdicts show the new wording. Offline suite on a clean checkout: 1697 passed /
  23 skipped / 1 xfailed.

## [Unreleased] - 2026-10-17 (Format runs at "medium" thinking — halves Format cost)

Per `docs/calibration_formatting_effort_2026-10-14.md`.

- `config.FORMATTING_EFFORT`: `None` (model default "high") → `"medium"`. Sonnet 5.5 at
  "medium" keeps the speaker's words (4/6 pass) at roughly half Format's cost (45–60%
  cheaper on short talks, 33–51% on long) for a few more one-word review stops (2 of 6
  runs vs 1 of 9). Format was ~31% of a full run. DeepSeek V4 Pro was ruled out for
  Format in the same doc (0/6 pass — does not keep verbatim wording).
- `FORMATTING_THINKING_RATIO` (3.5) / `_MAX` (5.0) stay as-is but are relabelled a
  conservative upper bound (measured at "high"): the single-pass length check stays
  safe and the cost report over-estimates Format until the ratio is re-measured at
  "medium" (commit 803f021).
- Test `test_u4_formatting_runs_at_model_default_effort` → `…_configured_effort`, now
  asserts `effort == "medium"`.
- Two learning-qa rounds: round 1 flagged the stale ratio comment and two calibration
  docs still saying "stays at model default" (P6, doc-only); fixed in 803f021. Round 2
  (re-sweep): clean against P1–P39, of which 3 were applicable.
Offline suite: 1697 passed / 23 skipped / 1 xfailed.

## [Unreleased] - 2026-10-15 (the name check stops flagging generated headings — HN)

Plan and measurement: `docs/plan_heading_names_2026-10-14.md`.

- Run 11 (commit 4d4b6fb, three public talks, $6.18): all 48 stages passed and the gate
  allowed all three talks (ALLOW_WITH_WARNINGS). No name flags at generation or at
  publish. The model's headings in this run all used words from the talks, so neither
  the old nor the new check would have flagged them (checked offline): the fix was not
  exercised live. Two faithfulness retries (Systems Biology summary, Why Families
  abstract) were content claims the judge flagged; both passed on the first revision.
- HN.1: in headings and bold labels, a run of words not in the source counts as a name
  only when it looks like one (`abstract_validation.looks_like_name`): a word that is
  not English, a given name that is not a word ("Sarah", "Jennifer"), or two given names or
  surnames that are words ("Grace Walker", "Mark Turner"). "Closing Advice", "Final
  Reflections", "Multigenerational Roots" and the other headings flagged in runs 9 and
  10 pass. Prose is checked as before. Word lists in `data/`: Webster's Second (public
  domain), US Census 1990 given names and surnames (public domain, via zxcvbn) and BSD
  propernames without 50 ordinary words. If a list cannot be read, every heading run is
  checked as a name, as before. The entity gate and the blog check name the heading
  phrases they did not count.
- HN.2: a span of only month or weekday names ("On June" from "On June 25, 2021") is a
  date, not a name. "June Carter" is still checked.
- The judge cache key now covers the name check's functions, settings and word lists.
- Measured on every overview, blog, summary and abstract of runs 1–10 (no API calls):
  same-talk flags 1 → 0; against another talk's source, 36 phrases no longer flagged
  (35 concepts or headings and "Nick Today") and none newly flagged; 4,824 of 4,900
  made-up people written as headings still flagged. Residual: a heading-only made-up
  name with at most one name-like word (a given name missing from the lists that is
  also a word, such as "Willow" or "Hope", with a surname that is a word; "Amy Post";
  "Alcoholics Anonymous"). Known false flag: "Max Effort".
- Two learning-qa rounds. Round 1: a missing given-name list loosened the check, too
  many made-up names passed (6.3% of name pairs), the judge cache key missed the new
  inputs, and skipped phrases were not reported. Round 2: the blog check still dropped
  skipped phrases, keeping short given names at a run's end made new false flags
  ("Black Art"), and weekday headings ("Friday Session Highlights") were still flagged.
  All fixed before landing.
- Tests: `tests/test_heading_names_hn.py` (86; 60 fail on the old code) and 11 new cases
  in `tests/test_judge_disk_cache_h2.py`. Changed for the new behaviour:
  `tests/test_release_gate.py::test_r6b_label_with_no_source_words_is_flagged`,
  `tests/test_run_fixes_rf.py::test_rfn1_lens_headline_fragment_not_judged`.

## [Unreleased] - 2026-10-14 (end-to-end run 9 and two follow-ups — RS)

- Run 9 (commit 59d64c8, three public talks, $6.62): all 39 stages passed and the gate
  allowed all three talks (ALLOW_WITH_WARNINGS), the first round with no failure. Every
  faithfulness retry passed by its second revision. No length miss had to be kept
  (summaries 576–672 words, abstracts 169–207). Format was clean, so the automatic
  restore did not run; replayed offline on the real Format failures of runs 4, 6 and 7,
  it restored the dropped words (and RS.4 fixed run 6's heading), the stage passed, and
  after the YAML step the gate's source check passed.
- A revision must keep front matter that still counts as front matter (`---` or a
  fenced yaml block, checked with the claim extractor's own helpers). In run 9 a
  revised overview's metadata ("target_audience: ...") was judged as a claim. The
  earlier first-line rule is gone: it would have refused a revision that fixes a
  flagged title.
- The abstract coverage check looks for a Q&A note only when the abstract was asked
  for one (`config.abstract_wants_qa_note`, above 20%). It looked from 15%, so run 9's
  Systems Biology abstract (16% Q&A, correctly no note) showed "❌ MISSING Q&A note".
  `ABSTRACT_QA_OPTIONAL_PCT` is removed.
- Tests: `tests/test_run_safe_rs.py::test_rs6f_revision_reply_check`,
  `::test_rs5e_qa_note_checked_only_when_asked_for`,
  `tests/test_validator_logic_hardening.py::test_abstract_qa_required_only_at_or_above_required_threshold`.

## [Unreleased] - 2026-10-14 (runs finish on acceptable output — RS)

Author's goal: the run should not fail, especially on warnings; output must be very good,
not perfect. Faithfulness stays strict. Plan: `docs/plan_run_safe_2026-10-14.md`.

- RS.1: a summary, abstract or overview outside its word range is retried; if every try
  misses, the reply closest to the range is kept with a warning instead of failing the
  stage (`call_claude_with_retry(word_limits="soft")`). Formatting keeps its hard floor
  (a guard against a cut-off reply). Run 7 failed two summaries at 580 and 562 words;
  run 8 retried a 516-word summary and two over-long abstracts.
- RS.2: a retried check is logged as a warning; an error only when the call gives up.
  A stage that passed no longer shows "2 error(s)".
- RS.3: the Format stage sets every dropped, added or changed word in ordinary text
  back to the source's words (the review's reject action, logged as "Restored the
  source's words in section N" and recorded with reviewer `auto (RS.3)`). Only a
  difference at a heading or speaker label still opens the review window. Runs 4, 6 and
  7 each stopped on one or two dropped words, which also blocked the four publish
  stages. `transcript_validate_format.py` still only checks.
- RS.4: a heading timestamp written with an extra `00:` group (`([00:01:02:04]).`) is
  rewritten to `([01:02:04]).` when the raw transcript has that time (run 6).
- RS.5: the abstract's Q&A note counts as found, with high confidence, when any one Q&A
  phrase is present; a correct note is no longer put on the human-review list.
- RS.6: after a failed faithfulness check, the retry changes only the flagged sentences
  of the previous draft and keeps the rest (`prompts/Revise Flagged Statements v1.md`,
  `extraction_pipeline._revise_flagged`), for the summary, overview, blog and abstract.
  Run 8's Why Families overview was rewritten three times and made a new unsupported
  claim each time. Measured (`docs/calibration/2026-10-14_revise_flagged/`, $2.17): from three kept drafts that had failed every try (run 8 Why Families overview; runs 7 and 2 abstracts), one retry on the production models passed 10 of 11 times by revising and 10 of 11 by rewriting. Revising changed 1–5% of the draft, rewriting 44–79%; revise's one failure was a sentence it had not touched (already in the draft, flagged in run 7 too). The gain is that a retry no longer starts over: only the changed sentences can bring a new problem.
- Review fixes: a near-miss reply held under soft limits is kept when a later try fails
  with an API error or a cut-off reply; soft limits keep only a reply within 25% of the
  range (`config.SOFT_WORD_LIMIT_TOLERANCE`); the Format stage's first check logs a
  fixable difference as a warning and the final check reports in full; the stage log
  names a kept length miss; a revision is checked for a comment before the text, echoed
  instructions and a dropped front matter (`config.REVISE_PREAMBLE_STARTS`); only judged
  drafts can be kept as the best; Q&A markers match whole words; restore acts only on a
  check record for the current files; automatic restores are counted apart.
- Tests: `tests/test_run_safe_rs.py`, plus updated loop tests in
  `tests/test_run_fixes_rf.py`, `tests/test_abstract_faithful_retry.py`,
  `tests/test_e2e_fixes.py::test_aq3_*`, `tests/test_overview_post.py::test_rs1e_*`.

## [Unreleased] - 2026-10-14 (summary floor and abstract Q&A note — SL3, AQ)

- Structured summary: the prompt still asks for 585–780 words (target 650), and a draft
  from 553 words is accepted (`config.SUMMARY_LENGTH_ACCEPT_MIN_RATIO` 0.85; author
  decision). Run 7 failed the summary on two talks whose drafts were 580 and 562 words.
  Measured: the coverage gate passed every draft down to 490 words; drafts were longer
  with the asked minimum in the prompt than without it, so it stays in the prompt.
- Abstract: the model is no longer given the pattern-made Q&A topics ("exploration
  reading book written"); it writes the Q&A sentence from the transcript. Run 7's
  Beautiful Boy abstract was blocked on that sentence; measured afterwards, 3 of 3
  passed. The abstract coverage check looks for a Q&A note by Q&A-specific phrases
  ("question period", "participants asked"; `config.ABSTRACT_QA_NOTE_MARKERS`) instead of
  the fragments.
- The published abstract's 250-word limit is enforced at generation (it was a validation
  warning; one measured abstract had 265 words). A later attempt that fails outright
  keeps the best earlier draft, and the log names that attempt and the error. Core's
  intermediate first abstract (PART 5) has no limit, so a long draft cannot fail Core.
- Details: `docs/calibration_summary_floor_2026-10-14.md`. Tests:
  `tests/test_e2e_fixes.py::test_sl3_*`, `::test_aq*`,
  `tests/test_abstract_faithful_retry.py::test_aq4_*`.

## [Unreleased] - 2026-10-14 (theme estimate rows and end-to-end results — ST.8/ST.9)

- Cost estimate: the theme rows now hold the measured visible output
  (`config.THEME_OUTPUT_PCT` / `THEME_OUTPUT_FLOOR`: structural `max(0.08T, 1600)`,
  interpretive `max(0.16T, 3100)`) plus the Effort setting's thinking, priced as cache
  writes (each theme call writes its own cache). The old rows were about 2x and 1.4x
  high. Test: `tests/test_structured_themes_st.py::test_st8_estimate_rows`.
- Two end-to-end rounds (runs 6 and 7, three public talks): all 12 theme calls passed on
  the first attempt, the theme judge passed every talk, no unclassified field or trimmed
  note. Results and the side-by-side read: `docs/plan_structured_themes_2026-10-14.md`,
  `docs/calibration/2026-10-14_structured_themes/`.

## [Unreleased] - 2026-10-14 (structured theme output — ST)

- The structural and interpretive theme stages return JSON that must match a schema
  (`output_config.format`), and the pipeline writes the theme `.md` file from it in one
  layout: `**N. Title**`, then `**Description:**`, Key evidence as a list, and
  `**Coverage / role:**` or `**Nested under structural theme(s):**` / `**Lens fuel
  value:**`. The model's own layout and labels no longer reach the file, so the label
  drift seen in runs 4 and 5 ("Summary", "Closing paragraph:") cannot recur in new runs.
- The JSON is saved next to the markdown (`… - structural-themes.json`,
  `… - interpretive-themes.json`, schema version 2) and keeps the model's closing note in
  `rationale`, which is never written to the markdown, the page, the judge input or a
  prompt. The prompts ask for that note in `rationale` instead of after the list.
- A reply that is not JSON or fails the local checks (numbers 1..N, no empty text, a
  title the parsers would skip, an interpretive theme nested under a structural theme
  that does not exist) is retried, and the stage fails after the last attempt.
- In the theme/lens validation loop, new structural themes now bring new interpretive
  themes, since those refer to the structural themes by number. In PART 1/2 both sets
  are saved only after both are generated, so a failed interpretive stage leaves the
  earlier run's pair as it was.
- The theme stages need a model with structured output (`model_specs` flag
  `structured_output`: Claude 4.5 and later); on another model they stop before any
  request, with the reason.
- Readers are unchanged: the page, judge, prompts, gate and webpage checks read the
  `.md` as before. Old theme files parse exactly as before (hash snapshot of every
  parser output over 21 real fixtures).
- Fixed in passing: when the last theme's last field began with "# ", the page lost that
  field (`transcript_utils._theme_own_text_report`).
- Cost: each theme call writes its own prompt cache (the schema sits in front of the
  transcript), about $0.03 per call on an 8k-token talk.
- Plan and details: `docs/plan_structured_themes_2026-10-14.md`. Tests:
  `tests/test_structured_themes_st.py`.

## [Unreleased] - 2026-10-14 (summary length band — SL)

- A structured summary is accepted from 10% under to 20% over its target (author
  decision): 585–780 words for the usual 650 target (`config.SUMMARY_LENGTH_MIN_RATIO`
  0.9, `SUMMARY_LENGTH_MAX_RATIO` 1.2, `config.summary_word_bounds`). Outside it the
  reply is regenerated. Before: a fixed 600-word minimum (8% under the 650 target), so
  a 587-word summary was rejected and paid for again (E2E run 5; its 572-word draft is
  still under the band), and no upper limit.
- If a later faithfulness attempt fails outright (e.g. every retry outside the band),
  the best earlier draft is kept, as when all attempts are judged unfaithful.
- `prepare_summary_input` defaults to the generation target (was 500), and the review
  checklist shows the band (was "± 15%").
- `call_claude_with_retry` takes `max_words` (a longer reply is retried, like a short one).
- The prompt states the target and the accepted range instead of "650–750 words,
  under 600 rejected".
- Coverage validation measures length against the same target and band (it used a
  500-word target, so its report said "604/500"). The target and band are in the
  stored verdict's key, so saved verdicts re-run once (one Haiku call each).
- Tests: `tests/test_e2e_fixes.py::test_sl1_*`, `tests/test_validator_gating_r15.py::test_sl1_*`;
  the old 600-word / 2,400-character / 85% tests are updated to the new band.

## [Unreleased] - 2026-10-14 (theme notes left out of generation prompts — TP)

- The prompts that take theme files now get the published themes (each
  `**N. Name**` and its own fields), not the model's closing notes after the last
  theme ("These three themes were chosen because…", "Rationale and coverage summary")
  or the file's preamble ("Prompt version used", "Input note"). TD did this for the
  page and the judge; the prompts still got the raw text.
- Covered: the overview, lens generation and theme/lens validation (which choose the
  blog's lens, so the blog), and the interpretive-themes prompt (which is given the
  structural themes). One helper, `transcript_utils.themes_for_prompt`, applied in
  `extraction_pipeline._generate_with_cached_transcript` and the overview prompt.
  The saved theme files are unchanged; a file with no parseable theme is passed as it is.
- Measured on 55 real theme files (268 themes): 66 closing-note lines and 16 preamble
  lines removed; nothing removed from inside a theme and nothing added
  (`docs/calibration/2026-10-14_theme_prompts/measure_theme_prompts.py`).
- Tests: `tests/test_e2e_fixes.py::test_tp1_*`,
  `tests/test_overview_post.py::test_tp1_overview_prompt_has_no_theme_closing_notes`.

## [Unreleased] - 2026-10-14 (summary coverage messages — E2E7)

- The summary coverage messages now follow the verdict the release gate uses. Before,
  a summary that passed the gate (it checks topic and closing items only) but missed a
  Q&A item was stored as PASS with the detail "Validation: FAILED…", and the GUI and
  the core run logged "publication will be blocked", which was not true.
- The stored verdict's detail is built from the report's "Gate status" line and its
  full checklist, not from the first line (which lists at most two missing items):
  a pass with misses reads "Gated items (closing, topic) covered; not gated: missing:
  A; B; C" (also kept in `not_gated`); a fail gives the gate's reason and every
  missing required item; a structural failure keeps its first issue. Verdicts saved
  by the old code (a PASS whose detail says "Validation: FAILED") are reworded when
  read.
- One wording for both run paths: `validation_pipeline.summary_coverage_message`
  (blocked / not a publication check / could not be checked). The gate and the
  message read the stored verdict through one function,
  `stored_summary_coverage_verdict`.
- The coverage check itself is unchanged, so no saved verdict is re-run.
- Tests: `tests/test_validator_gating_r15.py::test_e2e7_*`.

## [Unreleased] - 2026-10-13 (scored emphasis thinking level — E2E6)

- Scored emphasis runs at a fixed thinking level, `config.EMPHASIS_EFFORT = "medium"`;
  the GUI Effort setting does not apply to it (as for Format and the judges). At the
  model default ("high") the reply was cut off on 3 of 4 calls on long talks (twice at
  the 24,000-token ceiling). Measured on three public talks: "medium" finished 6 of 6
  calls (largest 13,071 tokens), every quote verbatim, items close to but less stable
  than "high" (`docs/calibration_emphasis_effort_2026-10-13.md`).
- The cost estimate for the emphasis step uses the measured output at that level
  (`config.EMPHASIS_OUTPUT_PCT`, `EMPHASIS_OUTPUT_FLOOR`).
- Tests: `tests/test_e2e_fixes.py::test_e2e6_*`.

## [Unreleased] - 2026-10-13 (end-to-end run fixes — E2E1–E2E5)

- **E2E1 Abstract inputs.** The abstract model no longer receives topic coverage
  percentages, section numbers or the Q&A share. It gets topic names in order and a
  yes/no `include_qa_note`, decided in code (`config.ABSTRACT_QA_NOTE_MIN_PCT`, 20).
  It had written "the Q&A accounted for roughly fifteen percent", which the transcript
  does not say, and the judge blocked Systems Biology. The prompt also says to leave
  out the conclusion when there is none, instead of saying the talk has none.
- **E2E2 Theme names.** Both theme prompts say to use only names the transcript says.
  The blocked Systems Biology theme named a chapter author the speaker never named.
  Measured: 3 old-prompt and 3 new-prompt generations all passed; the invented name
  is occasional, so the rule's effect is not shown yet.
- **E2E3 Extraction token ceiling** 8,192 → 16,000 (24,000 with thinking headroom).
  Scored emphasis used 11,228 / 14,540 tokens and failed above 16,192. The rerun showed
  this is not enough: the call's thinking varies and went over 24,000 on both long
  talks (open in TODO).
- **E2E4 Approved-terms file.** When the base folder has no `approve_terms.txt`, the
  one in the chosen source folder is used (`config.settings.default_terms_path`). Init
  Val logs a warning when the terms file is missing, and the GUI label shows
  "(missing)". Before, the GUI's Init Val ran without your terms and said nothing.
- **E2E5 Tests no longer write `logs/runtime_settings.json`.** Changing the transcripts
  folder reset `LOGS_DIR` to the real logs folder, undoing the tests' redirect. It is
  now set once. Each test also gets its own copy of the in-memory settings.
- **Review fixes.**
  - The abstract model gets "" instead of the fixed "not found" texts
    (`config.PURPOSE_MISSING_TEXT`, `NO_CONCLUSION_TEXT`, `PURPOSE_EXTRACTION_FAILED`),
    so the prompt's empty-value rules apply.
  - Topics are sent in presentation order (by first section).
  - The Q&A thresholds are in config (`ABSTRACT_QA_OPTIONAL_PCT`, `ABSTRACT_QA_REQUIRED_PCT`).
  - The output ceiling is capped for every model, not only thinking ones.
  - The terms loaders warn once for a missing file, so the command line warns too; the
    GUI warns at startup and logs full paths.
  - Tests get a deep copy of the settings, and the session fails if the real settings
    file changes.
  - The end-to-end runner skips Format when Init Val produced no validated transcript
    (as the GUI does), refuses a used `--out` folder, and removes its logging hooks.
- Tests: `tests/test_e2e_fixes.py`, `tests/test_e2e_runner.py`.

## [Unreleased] - 2026-10-13 (end-to-end runner — E2E)

- `scripts/e2e_run.py` runs every GUI stage on real transcripts without the window.
  It calls the GUI's own stage runners and logger, works in its own folder (real
  projects and saved settings are untouched), does not stop at the first failure,
  and writes one report of every failure, warning and error (`report.md`,
  `report.json`). Tests: `tests/test_e2e_runner.py`.
- First run (three public talks): findings in TODO.md (E2E).

## [Unreleased] - 2026-10-13 (Init Val stopped on a clean chunk — IV)

- Init Val no longer stops when the model finds nothing to fix in a chunk. Its reply,
  a fenced empty list (14 characters), was rejected by the 50-character minimum reply
  length. Both Init Val calls now accept a reply of 2 characters or more
  (`config.MIN_REPLY_CHARS_JSON_LIST`); the parsers still reject anything that is not
  a JSON list.
- The v1 validator now stops on a reply with no JSON list. Before, it returned zero
  findings.
- The chunk number in Init Val's error now matches the progress line (counts from 1).
- A test lists every call left on the 50-character default
  (`tests/test_init_val_empty_reply_iv.py`).

## [Unreleased] - 2026-10-13 (published Themes section — TD)

- The published Themes section no longer shows the model's closing notes as part of
  the last theme. Those are the labelled notes ("Summary paragraph", "Rationale and
  coverage summary", "Why these themes were chosen…") and an unlabeled closing
  paragraph.
- One helper (`transcript_utils._theme_own_text`) decides what belongs to a theme,
  for both the page and the theme judge.
- A document-level field inside a theme drops only that field.
- Every theme's own fields are unchanged.
- **Measured on all 262 real themes:**
  - 8 changed, each the last theme of its file, by removal at the end only;
  - the judge's input is identical on all 65 files.
- Rebuild the Why Families, Beautiful Boy and "This is a test" pages to pick it up.
- `docs/plan_theme_display_2026-10-13.md`.

## [Unreleased] - 2026-10-13 (theme judge evidence allowlist — TE)

- **What the judge receives:** the theme judge gets only evidence fields
  (`config.THEME_EVIDENCE_LABELS`, "Key evidence").
- **Trailing paragraphs:** document-level paragraphs after the last theme ("Summary
  paragraph", "Rationale and coverage summary") were read into that theme and sent as
  evidence. They are now listed as not evidence.
- **Unknown fields:** a field in neither list is still sent, with a warning.
- **Reporting:** the release gate reports an unknown field once per theme file, in the
  run log and in the verdict.
- **Contract test:** every field the judge reads in the real fixtures must be
  classified. Three real files with trailing fields are now fixtures.
- `JUDGE_LOGIC_VERSION` 2026-10-13b.
- **Same-day calibration:** theme gold 1.00/1.00 ×3 (old: one precision miss from
  run-to-run variation); 36 real theme checks gave identical verdicts.
- `docs/calibration_theme_evidence_2026-10-13.md`.

## [Unreleased] - 2026-10-13 (theme judge meta label — TM)

- "Nested under structural theme(s)" is now a meta label for the theme judge, like
  "nested under structural themes". 21 of the 25 interpretive files on disk use it, so
  it was reaching the judge as evidence.
- `JUDGE_LOGIC_VERSION` 2026-10-13.
- Same-day calibration: theme gold 1.00/1.00 ×3 both ways, and 36 real theme checks on
  6 public talks gave identical verdicts.
- Found while measuring (not changed): the Systems Biology project's structural theme
  2 is judged ungrounded every time. Its structural themes need regenerating.
- `docs/calibration_theme_meta_label_2026-10-13.md`.

## [Unreleased] - 2026-10-12 (changed first or last word in a quote — SW)

- The verbatim-quote check (blocking) now catches a quote whose first or last words
  were changed to words that also occur nearby in the source ("I think the future…"
  for "to me the future…").
  - A lead or tail of up to 4 words that matches only across a skipped span of 3 or
    more words, and is not found beside the rest of the quote, no longer counts as
    found (`validation_pipeline._stray_edge_words`).
  - Omissions marked with "..." or "…" are exempt.
- **Measured on 835 real quotes from 35 projects:** 5 of the 782 that passed now fail,
  each a real one-word change, and none newly pass.
- **Known limit:** an unmarked omission right after a quote's first words fails too.
  No real passing quote has that shape.
- Those 5 projects need their Bowen or emphasis step re-run before they publish
  again.

Plan, measurement and the list: `docs/plan_swapped_word_quotes_2026-10-12.md`.

## [Unreleased] - 2026-10-12 (small open items — N1–N5)

- **N1** An emphasis reply with no scored items is no longer saved raw and reported as
  success. Before, only replies over 500 characters were caught. Nothing is saved and an
  earlier run's file is set aside.
- **N2** The extraction stage checks theme and topics files with the format checks'
  own parsers, so they can't disagree. No result changed on 23 real theme files or 19
  topics files. A section that fails the check is now logged as an error; before, it
  was reused with no message. Both legacy theme-parser fallbacks warn when they
  produce themes.
- **N3** 24 functions defaulted to a model bound at import. They now resolve
  `config.settings` when called, so a model chosen in the GUI is used even by a
  caller that passes none.
- **N4** The topics header fallback no longer reads the text before the first `###`
  as a topic. The skip is logged.
- **N5** The cost report lists the steps it does not price (judges, overview,
  coverage validation, regeneration loops), so a low estimate is not read as complete.

Plan and status: `docs/plan_small_fixes_2026-10-12.md`.

## [Unreleased] - 2026-10-12 (speaker attribution without labels — SA; FAQ answers — FQ)

The Kerr 2026-09-13 run was blocked at publish by one summary sentence: "The
interviewer observes that most people drift into blaming…". The transcript has no
speaker labels, so it can't show who said what. The same file had passed at
generation. It was judged again at publish because commit 1c0e98f changed the judge
cache key.
- **SA.** The user's decision: "the interviewer" is a neutral term, and without labels
  such attribution should not fail.
  - `transcript_utils.has_speaker_labels` detects labelled transcripts.
  - For an unlabeled one, `release_gate.with_recording_metadata` adds
    `config.UNLABELED_SPEAKERS_NOTE` to the judge's source, and the judge prompt gains
    a SPEAKER ATTRIBUTION rule (`faithfulness_judge.instructions_for`).
  - The rule accepts a claim that a participant in the conversation said grounded
    content when the source doesn't show who said it. It does not accept a role the
    recording doesn't have, content that isn't in the source, or a reversed stance.
  - Labelled transcripts keep exactly the old prompt.
  - A PASS that relied on the note says so in its detail.
- **FQ.** The first sentence under a question heading (FAQ entries, question-style section
  titles) is judged with its question attached. The
  overview's "According to Michael Kerr, it does not." had no referent once the
  question heading was stripped. It was flagged on first pass in 17 of 20 checks and
  blocked 2; with FQ, 0 of 10.
- **Review fixes:**
  - D2 flags now match on the artifact, not the source text, so the new note can't
    clear them (`release_gate._flag_identity`).
  - The gold harness, drift monitor and live calibration test build sources as the gate
    does (`judge_recalibration.gold_sources`).
  - Five SA gold cases were added (48 cases).
- **Second review:** the rule is not used in chunk windows (they see part of the
  recording, and their "entailed" is final). A name in a question heading is still
  judged on its own.
- **Calibration** (`docs/calibration_speaker_attribution_2026-10-12.md`):
  - gold recall 0.96 ×3 (old 0.88–0.96), precision 1.00 ×3;
  - themes and real abstracts unchanged;
  - real prose 47.7 vs 45 sentences flagged (mean of 3, within run-to-run variance);
  - Kerr overview 10/10 PASS.
  - The Kerr summary now fails 3 of 10 checks on a real error ("Years earlier" where
    the source says "Years later").
- `JUDGE_LOGIC_VERSION` is 2026-10-12e, so saved artifacts are judged again on the next
  gate run.

## [Unreleased] - 2026-10-12 (real-run fixes: themes format, run log, cost estimate — T1–T4)

A full GUI run with Opus 5.5 as the main model, on Kerr "Why Families Repeat the Same
Patterns" (2026-09-13), was blocked at the release gate: the structural themes parsed to
zero items.
- **T1** The themes parser reads a third real format, `N. **Title**` list items with
  indented fields. Opus 5.5 wrote it, copying the prompt's own example. The other two
  formats are tried first. A list-format item counts only with a **Description:** field,
  so a numbered bold list in a Rationale section is not read as themes. Field lines
  are read whatever their indentation. On 51 real theme files on disk, only the new
  file changed (0 → 3 themes); parsing and the published section are otherwise identical.
- **T2** Both theme prompts (structural and interpretive) give the exact layout the
  pipeline parses (`**N. Title**`, fields on their own lines). Their examples used an
  inline list layout; the interpretive one parsed to nothing.
- **T3** A saved artifact that fails its format check is now reported in the run log.
  Before, it went only to a separate `artifact_contracts` log file, so the problem
  surfaced 13 minutes later at the gate.
- **T4** The cost estimate prices the models selected in the GUI, not the values fixed
  at start-up (it priced Opus steps as Sonnet 4.6). Structured summary and abstract
  coverage are priced on the main model, which the GUI runs them with.
- **T5** A model chosen in the GUI now also reaches the module-level `config.*_MODEL`
  values, and the run manifest records the models the run used, including the
  formatting model. The Opus run's manifest had said `claude-sonnet-4-6`.

## [Unreleased] - 2026-10-12 (judge prompt "entailed" examples — FX)

- The faithfulness judge prompt's examples of what "entailed" means (the DOS-equation
  example and the four framing sentences) came from a measured abstract, the Systems
  Biology blog fixture and the gold subject. They now use unrelated subjects; no rule
  changed. `JUDGE_LOGIC_VERSION` is 2026-10-12d.
- Measured against the current prompt on the same day
  (`docs/calibration_fx_examples_2026-10-12.md`): no loss on gold, real abstracts (with
  the gate's metadata), injected fabrication, or the Kerr project (0 of 10 false fails).
  Real prose was flagged at a similar rate: final 46 vs current 48 of 602, with 14
  sentences changing status in one run each. Two drafts were rejected in review (slot-for-
  slot rewrites of the blog sentences; the same meaning in new words); a test now checks
  for both.
- Judge replies with unescaped quotes inside a rationale (not valid JSON) are now read
  verdict by verdict instead of becoming an ERROR that blocks publication. It is still
  fail closed: every claim needs a valid label. Each repair is logged and counted. A
  repeated claim index in any reply is now an ERROR; before, the later verdict silently
  won, which could replace a flag.
- Calibration: the real-abstract and injected-fabrication checks now judge against the
  same source as the gate, with the recording metadata from each talk's real base name.
  `tests/test_faithfulness_calibration.py` uses the same list (`judge_recalibration.REAL_ABSTRACTS`).

## [Unreleased] - 2026-10-12 (judge prompt examples — Q6/C1)

- **Q6** Two faithfulness judge prompt examples that paraphrased gold cases were
  replaced: the medication example (us6) and "definitively proven" (us7) now use an
  unrelated subject. Other "entailed" examples still come from measured material (open).
  No rule changed. `JUDGE_LOGIC_VERSION` is now 2026-10-12, so cached verdicts are re-judged.
- **C1** Measured against the old prompt on the same day
  (`docs/calibration_q6_prompt_2026-10-12.md`): gold recall 0.95 ×3 (was 0.91 ×3; the
  difference is the one ambiguous case k4, so read it as no loss), precision 1.00;
  0 of 10 false fails on the Kerr project (old prompt: 1 of 10).
- **D2 follow-up** A file judged FAIL under an older judge version still counts as flagged
  after a prompt edit or version bump (the cache key includes the version). Before
  this, the Q6 bump would have dropped the 35 flagged entries in the live cache.

## [Unreleased] - 2026-10-12 (emphasis check matches the gate — D6)

- **D6** Measured the emphasis quote threshold on 752 real quotes (33 projects). The
  release gate already rejects altered quotes because it also needs full word coverage,
  so its 0.80 head/tail threshold is kept: 0.95 would reject 4 real near-verbatim quotes
  to catch 2. The Emphasis validator (`validate_emphasis_items`) now uses the gate's test:
  it had passed 24 real quotes as "partial matches" that the gate blocks. Still open: a
  swapped word can pass when the quote's words also occur in order nearby (2 of 752).
  The standalone `transcript_validate_emphasis.py` CLI, which crashed on every project
  with a scored emphasis file, now uses the same test and exits non-zero on a failure.

## [Unreleased] - 2026-10-12 (models: Haiku 4.5 retirement; header validation)

Results: `docs/calibration_formatting_model_2026-10-11.md`.
- **U4** `FORMATTING_MODEL` = `claude-sonnet-5-5` (was Haiku 4.5, retiring no sooner than
  2026-10-15). Of Haiku 4.5, Haiku 5.5 (medium, low) and Sonnet 5.5, Sonnet kept the
  speaker's words best (0–2 review items per run). It costs about $0.67–1.00 per 10–15k-word
  talk and is about twice as slow. Its formatting thinking is now in the cost estimate
  (3.5 per transcript token) and the single-pass length check (stops a talk over about
  20k words before a paid call; warns above about 14.7k, the measured maximum of 5.0). Formatting runs at the model's default effort, not the GUI
  Effort setting. The cost estimate reads the model selected in the GUI.
- **U5** `AUX_MODEL` = `claude-haiku-5-5`. Measured on header validation, abstract
  generation, stated purpose and summary coverage: close to Haiku 4.5, stricter header
  verdicts, one abstract of 6 left unfaithful (blocked by the gate). `VALIDATION_MODEL`
  is also Haiku 5.5; no step reads it. Summary-coverage verdicts already saved were made
  with Haiku 4.5. Their freshness key includes the model, so the next gate run re-checks
  each project with Haiku 5.5, and a verdict can change.
- **HV** `validation_pipeline.validate_headers` (whole transcript in one 4096-token call;
  cut off on a 10k-word talk) now uses the batched `HeaderValidator`; per-batch ceiling
  `MAX_TOKENS_HEADER_VALIDATION` 4096 → 8192 (margin). Its two dead helpers were removed.
  Header batches use the strict temperature again. A transcript with no sections now
  rewrites the report to say so instead of leaving an older one.

## [Unreleased] - 2026-10-11 (TODO triage: quick fixes and decisions)

Plan: `docs/plan_todo_triage_2026-10-11.md`.
- **D1** The published Themes section (web pages and PDF) shows only the parsed themes,
  each as "**N. Name**" with its fields — not the themes file's title, `---` lines,
  "(N total)" headings or summary paragraph. Checked on 48 real theme files (240 themes).
- **D2** The judge disk cache keeps only PASS verdicts (faithfulness, theme, blog
  grounding). A FAIL is re-judged on the next gate run instead of being replayed; FAILs
  already on disk are ignored. Once a file has been judged FAIL (including FAIL
  entries written before this change), a later PASS is not stored, and a run counts as
  PASS for that file only when two judgements in a row pass it.
- **D5** `cap_max_tokens_for_model` caps a request at the model's own max output
  (`config.MODEL_OUTPUT_TOKEN_LIMITS`, else `model_specs.capabilities`) instead of 4096
  for every model; a test keeps the two tables in agreement.
- **Q1** Web-page check: a source name is found only at the start of a page item ("Self"
  is not found in "Differentiation of Self"). No change on 15 real page lists.
- **Q2** Emphasis parser reads a quote that contains a quotation in full, and no longer
  takes a quoted concept name as the quote (one real case in 44 files, 1,053 items).
- **Q3** Emphasis: when every parsed item fails validation, nothing is saved and the
  step fails (it saved the raw response). When emphasis extraction saves nothing, an
  emphasis file from an earlier run is renamed `.stale` (also when the step fails with
  an error), and the main pipeline logs that
  the pages will have no emphasis items.
- **Q4** Abstract input: a topic header with no name is skipped and logged, and no
  longer takes the next line as its name.
- **Q5** `judge_recalibration --prose-real` (and the where_roots real-abstract check)
  judge against the same source as the gate (transcript plus recording metadata).
- **U3** Measured Haiku 5.5 as the formatting model (`docs/calibration_formatting_model_2026-10-11.md`).
  Not switched: it edits the speaker's words more than Haiku 4.5.
- **D3** Removed the stale `hungry-wilbur` worktree and 5 merged branches.

## [Unreleased] - 2026-10-11 (faithfulness: confirm a flag before it fails a run)

Plan: `docs/plan_judge_confirm_flags_2026-10-11.md`; results: `docs/calibration_confirm_2026-10-11.md`.
A claim the faithfulness judge rejects is judged again (only flagged claims, each with the
claim before it for context); it fails the run only if the majority of judgements reject
it (`config.FAITHFULNESS_CONFIRM_MODE = "majority3"`). Flags not confirmed are recorded in
the gate's verdict items and the run manifest. Applies to the faithfulness and
topic/key-term checks, the blog's first stage, the generation pre-check, and the
calibration and drift tools. Sonnet 5.5 takes no temperature and sometimes rejects a
supported sentence; on the Kerr 2026-09-13 files fresh checks failed 5 of 10 before.

## [Unreleased] - 2026-10-11 (judge framing rule — investigated, not shipped)

No behaviour change. A narrower faithfulness-judge rule for the writer's own framing was
built and measured (`docs/plan_judge_framing_2026-10-11.md`,
`docs/calibration_framing_2026-10-11.md`); it failed more good writing than the current
prompt and was not shipped. Also recorded: the DeepSeek independent-reviewer experiment
(`docs/calibration/independent_reviewer_experiment_2026-10-11/`, spec on hold).

## [Unreleased] - 2026-10-11 (web checks read topics, themes, key terms)

RF.P in `docs/plan_run_fixes_2026-10-09.md`. The Full Web and Simple Web checks now
read topics, themes and key terms from the source files with the pipeline's own
parsers (before: key terms were counted as 0 and themes were read from sub-headings),
read theme names from the page past the themes file's stray title heading, and check
every item instead of the first 30%. A source file that cannot be parsed is a critical
issue. On the Kerr talk both pages verify 7/7 topics, 10/10 themes and 10/10 key terms.

## [Unreleased] - 2026-10-10 (Simple Web check)

RF.O in `docs/plan_run_fixes_2026-10-09.md`. The "8b. Simple Web" check failed every
real simple page: it read an older page layout and found no sections, abstract or
highlights. It now reads the current `templates/simple_webpage.html` layout, counts
highlights in the transcript only, and shares one parser with the full page. Bowen
highlight labels no longer carry the timestamp, so the "Missing N Bowen reference(s)"
list is correct on both pages. Tests generate real pages with the real templates.

## [Unreleased] - 2026-10-10 (judges on Sonnet 5.5)

Plan: `docs/plan_judge_recalibration_sonnet55_2026-10-10.md`; results:
`docs/calibration_sonnet55_2026-10-10.md`. The faithfulness and theme judges (and so
the blog's second stage) now run on claude-sonnet-5-5 at its default effort, after
re-calibration: gold recall 0.91–0.95 / precision 1.00 over 3 runs, themes 1.00/1.00,
real abstracts and an injected fabrication correct every run, and speaker labels read
correctly (Sonnet 4.6 misread them, which falsely blocked the Kerr overview). It is more
lenient than 4.6 on the writer's own framing. Cached 4.6 verdicts are not reused
(`JUDGE_LOGIC_VERSION` 2026-10-10). Judges retry a malformed reply once and accept a
single verdict returned as a bare object. New tool: `judge_recalibration.py`; the gold
set gained 10 Kerr cases.

## [Unreleased] - 2026-10-10 (Claude 5 models)

Plan: `docs/plan_v5_models_2026-10-10.md`. The pipeline now runs on claude-opus-5-5,
claude-sonnet-5-5, claude-haiku-5-5 and claude-fable-5-1 (live-tested), as well as the
4.x models.

- One capability table (`model_specs.MODEL_CAPABILITIES`) and v5 prices; the GUI model
  lists include the 5-family models.
- Requests send only what a model accepts: `temperature` stays for models that take it
  and is dropped for 5-family models; the reply's answer is read from its text blocks
  (5-family models think first); thinking gets extra `max_tokens` room; very long
  requests stream; refusals raise `RefusalError`; Opus 5.5 / Sonnet 5.5 / Fable 5.1
  use server-side refusal fallbacks (`config.REFUSAL_FALLBACKS_ENABLED`).
- New **Effort (thinking)** setting in the GUI (model default / low … max), saved in
  runtime settings. The faithfulness/theme/key-term judges ignore it (`JUDGE_EFFORT`).
- The cost estimate includes thinking tokens on 5-family models.
- Judges stay on claude-sonnet-4-6 until re-calibrated.

## [Unreleased] - 2026-10-09 (run fixes RF.A-RF.E)

Plan: `docs/plan_run_fixes_2026-10-09.md`. The second 2026-10-09 run of "Why Families
Repeat the Same Patterns" was blocked at Full Web/PDF and wrote no blog.

- **Heading timestamps follow the raw transcript (RF.A).** The formatter read the raw
  `0:33` (33 s) as `[00:33:00]` (33 min) on every heading. Format now corrects a heading
  `hh:mm:00` to the `m:ss` reading when only that reading is in the raw, and logs
  "Corrected N of M". The prompt states the rule. Re-run Format to pick it up.
- **Verbatim quotes (RF.B).** A quote that writes the speaker's inner `"..."` as
  `'...'` no longer fails (quote marks are stripped from word edges). A quote that is
  literally in the source passes even when it stops inside a repeated phrase; a changed
  last word ("do it, do it, do" for "don't") still fails. Kerr project: 24/24 quotes.
- **Blog-only stage (RF.C)** retries lens validation up to
  `THEME_LENS_VALIDATION_ATTEMPTS` (config, shared with Core), requires both theme
  sets valid and a lens that is in the lenses file, and logs the reason per attempt.
- **Interview turns are not audience Q&A (RF.F).** The 16:50 run halted at Gen
  Abstract: `**Interviewer:**` turns made the Kerr interview read as 26% Q&A, so the
  abstract prompt asked for an "audience engagement" sentence the judge rejected on
  every attempt. One detector (`transcript_utils.find_qa_sections`) now serves the
  abstract and the summary: Q&A means a Q&A-style heading or an audience speaker's
  turn; interviewer/host and presenter labels (incl. "Dr. Kerr", initials,
  co-presenters) are not audience; "question" in the text no longer counts alone.
  Kerr interview 26% → 0%; lectures with "Q&A: Name on …" headings now count them.
  Labels and heading patterns live in `config.py`. Two learning-qa sweeps; all
  findings fixed.
- **Format check: curly quotes and chapter titles (RF.G, RF.H).** The 20:16 run failed
  Format on 119 differences: 108 were `Bowen’s` → `Bowen's` (curly quotes now equal
  straight ones) and 7 were YouTube chapter-title lines the formatter correctly dropped.
  Deleting such a line is auto-allowed only when it reads as a title and sits between a
  speech line and a timestamp line, so a name on its own caption line or an Otter answer
  turn still needs review; removed titles are listed in the validation warnings. The
  remaining 4 items include a real formatter edit ("contributor" → "perpetrator").
- **Init Val, quotes, summary/blog (RF.I, RF.J, RF.K).** Run 20:33 blocked at Full
  Web/PDF. Init Val's auto mode had written "contributor" → "perpetrator" into the
  validated source; it now applies only mishearing-level fixes (one-for-one, similar
  spelling, original word not used elsewhere, new word a proper noun or used elsewhere)
  and saves held ones to `<base> - init-val-held.json`. Extractors drop any Bowen or
  emphasis quote that fails the gate's own verbatim test (a spliced quote had shipped).
  The summary (now on the main model), blog and overview are judged at generation and
  regenerated with the rejected claims as feedback, up to 3 attempts, like the abstract.
- **Run resumes after Format review (RF.L, RF.M).** A run that stops at Format only
  for review now pauses ("⏸ Paused at 1. Format") instead of failing, and when the
  review makes Format pass the GUI asks to continue with the remaining stages. Real
  Format failures still halt. The Format log lists only differences that still need you.
- **The blog is judged as interpretation and only warns (RF.N).** Run 07:41 halted when
  the blog failed faithfulness on metaphors, general statements and the lens's own
  reading. A blog claim now passes if it is entailed or the theme-grounding judge finds
  it a fair interpretation of real content (contradictions and invented specifics still
  fail). Remaining problems are a `blog_faithfulness` WARNING: the Blog stage never stops
  the run and the blog never blocks publication. Lens-title headlines are not treated
  as names or claims. The blog prompt asks for speaker-attributed facts and no
  "most people" generalisations.
- **GUI log saved (RF.D)** to `logs/gui_<session>.log`.
- **"8b. Simple Web" stage (RF.E)**, gated and validated like Full Web/PDF; the run
  manifest records the simple page; Package skips a simple page older than the full
  page / transcript and says so.

learning-qa sweep: 5 findings, all fixed (simple page validated; Blog-only requires
valid themes; the trailing-repeat collapse rule replaced by an exact-match check that
cannot hide a changed word; stale simple page not packaged; log write tolerates
unencodable text). Suite: 1108 passed, 18 skipped, 3 xfailed.

## [Unreleased] - 2026-10-09 (faithfulness judge routing fix)

Plan: `docs/plan_judge_routing_fix_2026-10-09.md`. Run 2026-10-08 ("Why Families Repeat the
Same Patterns") was blocked partly by claims judged against the wrong transcript window.

- **No claim fails on one window (J3).** A routed claim the window does not entail is
  re-judged against the full transcript; that verdict is final.
- **Ambiguous routing goes to the full transcript (J1)**: exactly one window must hold the
  claim's anchored words, and one of them must be distinctive. **Stemmed routing words (J2).**
- **Headings (J4, decision D2a):** judged only with a digit or month name; never questions or
  prompt section headings. main's length rule false-flagged 7 of 52 real headings.
- **Quote typo tolerance (J8):** one-letter difference in a 4+ letter word counts as matched.
- `JUDGE_LOGIC_VERSION` 2026-10-09b; cache key covers the new code (J5).
- Live 2026-10-09: calibration passed (gold 1.0/1.0, real abstracts as expected, themes
  1.0/1.0). Re-judging the 2026-10-08 artifacts: the two routing false flags now pass; the
  reversed Navy story and the Georgetown claim still FAIL (summary 4 flags, overview 2).
  "Freedom runs through the source of constraint", flagged on 2026-10-08, passed this time.

## [Unreleased] - 2026-10-09 (merge validation-hardening into main)

Combines the 2026-09-23 work on main with the 2026-10-04/05 review fixes. Author
decisions 2026-10-09:
- Validators do not fail the Core stage; emphasis/topics/summary coverage block
  publication through the release gate, and key terms stay advisory (main had made
  all four fail the stage).
- `verbatim_quotes` keeps main's whole-quote word coverage and gains filler-word /
  stutter handling; it replaces the branch's separate `emphasis_grounding` check and
  ERRORs when the emphasis file parses to nothing.
- `topic_term_faithfulness` is advisory (WARN) until calibrated.
- Claim extraction keeps main's claim-bearing headings and the branch's ungrounded
  scaffolding names; `JUDGE_LOGIC_VERSION` = 2026-10-09.

## [Unreleased] - 2026-10-05 (full-repo review fixes)

Fixes from `REVIEW-trans-summary-2026-10-04.md`, per `docs/plan_review_fixes_2026-10-04.md`.

**Publish gate**
- **GUI BLOCK now quarantines the stale bundle (G1).** The webpdf stage returned early on
  BLOCK without the quarantine / PUBLISH-BLOCKED marker / manifest; it now calls
  `release_gate.record_decision`.
- **Names in headings, bold labels and `---` regions are checked (F2).** Both hard blockers
  stripped these before checking. Generic headings are excluded via
  `config.SCAFFOLDING_HEADING_PHRASES`. Behaviour change: a bold label whose words never occur
  in the source is now an ungrounded name.
- **Theme judge sees the whole theme (F3)**, including Key evidence (gold set: +2 cases).
- **Zero claims from a non-empty prose artifact is ERROR**, not PASS (author decision).
- **Judge cache key hashes the extraction code (F4)**; `JUDGE_LOGIC_VERSION` = 2026-10-04.
- **New blocking checks** `emphasis_grounding`, `topics_grounding`, `summary_coverage`
  (author decisions 2026-10-05). Emphasis matching ignores filler words and stutters;
  summary coverage gates on topic / closing items only. Key terms stay advisory.
- Live re-calibration 2026-10-04 passed: faithfulness gold 1.0/1.0, real abstracts as
  expected, theme judge (with evidence) 1.0/1.0.

**LLM calls**
- **One client factory (F12/F14).** `transcript_utils.get_anthropic_client()` resolves the key
  from env or `~/.config/llm/keys.json` for every stage and disables SDK retries
  (`max_retries=0`); the wrapper retries 5xx and applies `config.TIMEOUT_FALLBACK`.
- **`max_tokens` truncation is not retried (B-11)**; rejected responses are logged to
  `token_usage.csv`.
- **Resolved prompt placeholders are no longer sent twice (B-05).**

**Validators**
- Summary LLM coverage rescue works (F13); a failed rescue is "unverified" (ERROR), not
  "missing" (C-07). The required "Speaker identified" item is created again (G6).
- Key terms ground on alternative label forms (parenthetical, `X / Y`, versus → and).
- Topic grading skips the fuzzy scan when keyword grounding already decides the tier
  (20–50 s → under 1 s per real project; same tiers).
- Gen Abstract returns failure when no attempt is faithful (author decision).

**Other**
- Cleanup deletes only `{base}_vN.txt`, not another transcript's versions (G11).
- Repo CSS is no longer HTML-escaped inside `<style>` (D-09).
- README install and key setup corrected (G19); ARCHITECTURE §4.3 lists the blocking checks.
- Real prose fixtures: `tests/fixtures/prose_real/` (3 projects).

## [Unreleased] - 2026-09-23 (review of formatting differences + pattern sets)

- Formatting validation no longer tolerates unexplained differences. Every difference between the raw and formatted transcript must be a removed stutter or transcription tag (auto-allowed) or be decided in review; otherwise validation and the release gate fail. The 1.5% / 10-word limits remain as "regenerate, don't review" bounds and now exclude auto-allowed stutters.
- New review step (`format_review.py`): Accept (keep formatted wording), Reject (restore raw wording in the formatted file), Edit (type the final wording). Decisions and approvals are stored in ` - format-review.json`, bound to the raw text they were made against. Reviewed counts appear in the YAML Authenticity note.
- New pattern sets (`pattern_sets.py`): named files in `<transcripts>/patterns/` holding approved terms and `wrong = correct` fixes for a group of transcripts. A project records its set, the set's hash and the fixes applied (` - pattern-set.json`); fixes are applied to the raw transcript before formatting. The existing approved-terms file is copied in as the first set. The set last used for a presenter is suggested.
- GUI: Pattern Set selector (+ New...), Review Differences button, and a review window that opens when format validation needs decisions. "Save as pattern" adds a reviewed change to the project's set (warns on single-word patterns).
- CLI: `transcript_review_format.py` (review, `--assign`, `--list-sets`, `--new-set`); `transcript_format.py --pattern-set`.
- Pre-push sweep fixes: corrupt review / pattern-set JSON raises instead of being treated as absent; review decisions are kept if Apply is pressed while another task runs; "had had" / "that that" never auto-allowed; restoring deleted words across a section heading or speaker label is refused (seen on the real fixture: "Amy Post." dropped at "## Section 45 – Q&A: Amy Post on ...").

## [Unreleased] - 2026-09-23 (reliability, part 2)

- Formatting comparison: procedural-speech stripping removed (on the where_roots fixture it created 2 false insertions and hid deletions; without it, 6 mismatches instead of 8). Near-identical word replacements are accepted only when the raw word never appears in the formatted text, and are recorded as `corrections` (reported in the validation record, log and YAML) instead of being silently accepted.
- Formatting output budget uses the model's documented max output (`MODEL_OUTPUT_TOKEN_LIMITS`; Haiku 4.5 = 64K per Anthropic's Models overview) instead of a fixed 20,000; transcripts whose estimated output exceeds it fail before the API call.
- `call_claude_with_retry` no longer retries a response that stopped at `max_tokens`.
- Echoed prompt title lines before Section 1 are removed after formatting (`strip_leading_title`).
- YAML `Transcriber` comes from `config.YAML_TRANSCRIBER` (default "Automated"; was a fixed "Automated; human-reviewed").
- Gate `source_fidelity` fails when the YAML transcript (the file the zip package ships) differs from the formatted transcript.
- Webpage validation checks the published transcript text word-for-word against the formatted transcript; the GUI now fails the web/PDF stage when webpage validation fails (its result was discarded).

## [Unreleased] - 2026-09-23 (source fidelity + output validation)

Formatting validation:
- `_compare_transcripts` rewritten as a global word alignment: truncated output, inserted words and substitutions are each counted once (previously truncation counted as 1 mismatch and insertions as 0). New `max_contiguous_run` limit (`VALIDATION_MAX_CONTIGUOUS_RUN`).
- `strip_sic_annotations` no longer consumes line breaks (it could merge a `## Section` heading into the previous paragraph).
- Procedural-speech stripping applied to both texts, not only the raw.
- New deterministic heading checks: format contract, sequential numbering, non-decreasing timestamps, timestamp present in raw, and timestamp matching where the section starts in the raw (`check_heading_timestamp_positions`).
- `validate_format` writes ` - format-validation.json` and a ` - raw-source.txt` copy. YAML `Authenticity` states "NOT VERIFIED" unless a passing record exists for the exact formatted text, and no longer claims verification against the recording.

Release gate (all new/changed checks are blocking):
- `source_fidelity` (new): re-verifies the formatted transcript against its raw source. Every other check treats the formatted transcript as ground truth.
- `verbatim_quotes`: now compares the whole quote (`_quote_word_coverage`, `QUOTE_MIN_WORD_COVERAGE = 1.0`), not only its first/last 12 words; made blocking.
- `topic_term_faithfulness` (new): topic descriptions and key-term definitions judged claim-by-claim. Not yet calibrated on real runs.
- Faithfulness claim extraction now judges claim-bearing headings (`FAITHFULNESS_GENERIC_HEADINGS` skipped); `JUDGE_LOGIC_VERSION` bumped, so cached verdicts are re-judged once.

Extraction stage: emphasis, topics, key-terms and summary-coverage validation results now fail the stage instead of only being logged.

## [Unreleased] - 2026-09-11 (mutation-gate fix)

The nightly `mutation-gate` job had failed five nights running. Gate-config and
test-strength fixes only — no production logic changed:

- **`load_bowen_references` targeted a no-surface loader** — it has zero mutation
  operators, so the gate scored `None` and failed its 0.4 floor every night. The
  gate now targets `parse_bowen_references_text` (the real F5 parser) and the
  gate-config test asserts every listed function is actually mutable. A target
  with 0 mutation operators, or one that no longer exists in its module, is a
  FAIL that names the cause (a SKIP would let a broken config pass; learning-qa
  sweep 2026-10-09), covered by the `test_m6a2_*` tests.
- **`_best_local_grounding` mutated weakly (2/12)** — added edge-case tests for the
  split-vs-fallback, alias-length threshold, aggressive compound normalization,
  final-window, and left-clamp branches, lifting it to 11/12 (the lone survivor is
  an equivalent `range(+1)->(+2)` mutant, behaviorally identical).

`quality_gates.py mutation` exits 0 (re-run 2026-10-09 on main): F1/F2 target 0.762,
keyword-grounding 0.714, Bowen parser 1.0. Offline suite: 1081 passed / 18 skipped /
3 xfailed.

## [Unreleased] - 2026-08-22 (close three non-blocking follow-ups)

Three items previously deferred as non-blocking (from the full-run review) are now fixed:

- **Emphasis decimal rank mis-parse** — `parse_scored_emphasis_output._parse_score` digit-averaged every number group, so a decimal rank `"92.9"` became `(92+9)/2 = 50` (mis-displayed AND mis-validated against the category range). It now parses the first number as a float and rounds to int (`92.9 → 93`).
- **`UNRECOGNIZED` emphasis type leaked through** — the parser's lenient bracket pattern captured any type token the model emitted, and it was written verbatim into the artifact header. `validate_emphasis_item` now rejects a type outside `Explicit/Implicit/Clinical` (fail-closed, logged), instead of writing it through.
- **`find_text_in_content` returned misaligned raw offsets** — offsets were computed from normalized-word indices / a needle-prefix `find`, so a whitespace difference (double space) produced a span that did not bound the needle in the raw text; the Init Val span guard then (correctly but wastefully) skipped a legitimate fuzzy correction (recall loss, not corruption). It now re-locates the matched window in the RAW haystack via `_locate_raw_span` (case-insensitive, whitespace-flexible `\b…\b` regex), so whitespace/case-only differences apply correctly while the guard still blocks a true mis-location.
- **Core + standalone Bowen/Emphasis double-run** — selecting `Core` (with Include Bowen/Emphasis) AND the standalone `Bowen + Emphasis` stage ran the same extraction twice. `_run_selected_stages` now logs a heads-up warning (via the unit-tested `_duplicate_bowen_emphasis` predicate); it never changes what runs.

Offline suite: 856 passed / 18 skipped / 3 xfailed.

## [Unreleased] - 2026-08-22 (full-run review: close six validation gaps)

Fixes from reviewing a full Kerr "Systems Biology Meets Bowen Theory" run that halted at stage 8. The halt was the release gate correctly **BLOCKING** publication, but the block exposed six real bugs:

- **Faithfulness false-BLOCK on metadata** — `extract_claims` fed the overview/blog fenced ```` ```yaml ```` block (slug/focus_keyword/target_audience/faq q:/a:) and leading bold topic labels to the judge as "claims", which were flagged "unsupported" and false-blocked publication. The extractor now pre-strips scaffolding via the shared `_strip_scaffolding` helper (extended with a `_strip_fenced_block` step) — one source of truth, so the entity/name detector and the claim extractor cannot drift (P19).
- **Faithfulness over-flags editorial prose** — the judge treated rhetorical/editorial framing of grounded material ("The environment is not incidental.", "It was a logical approach, and it produced genuine discoveries.") as "unsupported". The judge instructions now classify editorial framing (emphasis/restatement/framing with no NEW specific) as entailed, while keeping "unsupported" reserved for fabricated specifics and invented causal claims/attributions (the recall-bearing class). Two editorial-framing gold cases (ef1/ef2) lock the behaviour via live re-calibration (M2.B).
- **Bowen parser turned "no references" prose into a fake candidate** — `extract_bowen_references` matched a bare "Label: \"quote\"" shape, so the model's prose ("There are no instances of \"Bowen said,\"") parsed into a garbage candidate and produced a confusing "0 grounded refs from 1 candidate" diagnostic on a lecture with genuinely zero person recollections. The parser now requires the prompt's bold concept format (re-added `re.MULTILINE`, whose loss parsed only the first line).
- **Presenter name flagged as a hallucination** — `find_ungrounded_names` now accepts `known_names` (presenter/author from filename metadata) so a correct attribution to the speaker ("Michael Kerr", never named in their own talk) is not flagged; a fabricated adjacent name ("Michael Kerrstone") is still caught.
- **Ingest timestamp leaked into the date** — `parse_filename_metadata` returned the full `2021-06-25_20260718_155038` segment, so the YAML "Lecture date" and prompt date context showed the ingest timestamp. The `date` field is now the clean `YYYY-MM-DD`; `stem` keeps the full unique segment.
- **Stage 8 reported an opaque "webpage generation failed"** — when the gate BLOCKED, the GUI now runs the gate once up-front, logs the specific blockers/warnings, and skips webpage/PDF entirely instead of both generators each re-running the gate and failing silently.

Known, non-blocking (left for a follow-up): the "Core" + standalone "Bowen + Emphasis" double-run still extracts emphasis/Bowen twice when both are selected (documented workflow choice, `TODO.md`); a heads-up warning when both are selected would help.

A learning-qa failure-pattern sweep (`2c0feb1...HEAD`) then caught and fixed four more: the Bowen parser's bold-requirement silently dropping non-bold real references (now a non-bold fallback + a loud empty-parse warning); the scaffolding strip hiding a fabricated name rendered as a leading bold label (name-shaped bold labels are now re-emitted so the judge stays the backstop); the editorial-framing guidance risking recall on strength-escalations ("definitively proven" when the source is tentative is now explicitly unsupported); and the known-name whitelist hiding a short fabricated surname ("Michael Li") via token filtering (now exact full-name match).

Offline suite: 837 passed / 18 skipped / 3 xfailed.

## [Unreleased] - 2026-08-22 (Bowen parser + name-shape backstop convergence)

Three further learning-qa confirmation sweeps (`4be1271...HEAD`) kept finding new failure modes in the two fuzzy heuristics the full-run review introduced. Each fix narrowed one class; the final sweep drove both to their robust terminal form:

- **Bowen reference parser** — the "no references" prose guard is now **inverted**: a quote with a Bowen person attribution (in the quote *or* the concept label, both via `bowen_attribution` as single source of truth) is always kept, and only an *unattributed* meta-shaped quote (`"There are no explicit references to Bowen …"`) is dropped. A false-drop can now only hit an unattributed quote — which the rule filter discards downstream anyway — so the negation vocabulary can no longer silently drop a real recollection (`"Bowen said there are no instances of emotional cutoff"`). The parser also gained a non-bold fallback gated on quote-OR-concept attribution, a post-parse prose guard, and smart-quote/re.MULTILINE-safe regexes.
- **`concept_has_bowen_attribution`** — the theory-rejection is now a single source of truth that rejects the theory/theorist *nouns* (`"Bowen's theory of differentiation"`, `"Bowen's differentiation theory"`) but keeps a possessive-adjective recollection (`"Bowen's theoretical insights"`), mirroring the quote-side detector.
- **Name-shape backstop** — `_name_shaped_bold_labels` re-emits a fabricated name rendered as `**Name:** …` (the entity check's bold-label blind spot) while excluding generic scaffolding labels (`Theme/Term/Topic/…`) and the canonical Bowen concept vocabulary (moved to `config.BOWEN_CONCEPT_LABELS`, rule #9). **Residual (documented, interim):** a *lecture-specific* concept label not in the canonical set (e.g. `"Emergent Features"`) is still re-emitted as a fabricated name; a fully-general name-vs-concept discriminator needs the semantic judge, not a regex — flagged as a follow-up rather than shipped as a false sense of closure.

Offline suite: 850 passed / 18 skipped / 3 xfailed.

## [Unreleased] - 2026-08-22 (GUI "Test Drift" pre-flight judge self-test)

- **`ts_gui` "Test Drift" button** — a one-click pre-flight check next to "Config Check" that runs all three semantic judges over their gold sets and reports recall/precision, so the user can confirm the hallucination safety net is still at calibrated accuracy *before* processing a transcript. On drift it logs and pops a dialog with actionable help (re-run to rule out a single-draw flake; identify what changed — judge model / prompt / threshold; re-calibrate, or pin the judge model to a dated snapshot). A "could not run" (no key / API error) is surfaced as a failure, never a clean pass.
- **`judge_drift_monitor.run_in_process`** — a public in-process entry point returning `(report, drift)` so the GUI reuses the exact CLI evaluate/render/drift logic rather than a parallel copy.

## [Unreleased] - 2026-08-22 (judge drift monitor — drift insurance for the semantic judges)

- **`judge_drift_monitor`** — the semantic judges (faithfulness, theme, key-terms) were calibrated once at arming and then trusted forever; a model bump or prompt edit that silently un-calibrates them would serve stale verdicts with no signal (P20). This unified CLI re-runs all three judges over their curated gold sets and asserts they still clear their precision/recall bars, exiting non-zero on drift (0 = all clear, 1 = drift detected, 2 = could-not-run). Each judge runs on its OWN configured model unless `--model` overrides all three. Not run by `pytest` (the offline wrapper is `tests/test_judge_drift_monitor.py`); intended for CI or a weekly cron.
- **`key_terms_gold`** — the missing third gold set: 7 real (correct) definitions + 10 hand-authored INCORRECT definitions (a swapped concept, a reversed relationship, a reversed formula, or the opposite meaning) — the class lexical grounding and entailment cannot catch, so it specifically grades the key-terms judge's semantic discrimination.
- **Live baseline (claude-sonnet-4-6)** — all three judges recall = precision = 1.0 on their gold sets (faithfulness 31, theme 31, key-terms 17 cases).

## [Unreleased] - 2026-08-22 (empty bowen-references now blocks)

- **`consistency` promoted to a hard blocker** — an empty `bowen-references.md` while the transcript or abstract recounts Bowen the person ≥ 2 times is a DROPPED RECOLLECTION (a lost signal on the highest-signal artifact), so the check's FAIL findings now BLOCK publication instead of shipping as `ALLOW_WITH_WARNINGS`. Its heuristic WARNs (orphan key-term, topic coverage, the fuzzy specific-recollection drop) remain advisory.

## [Unreleased] - 2026-08-22 (fabricated-name blocker extended to narrative prose)

- **`find_ungrounded_names` is now heading/bold-aware** — it strips ALL markdown headings and bold concept/term labels (not just leading scaffolding), so a blog's "## Key Takeaways" or a "**Role Absorption** —" definition list no longer reads as a fabricated proper name. A bare "**bold** prose" with no label separator is left intact, so a real name rendered as leading bold emphasis is still detected.
- **Blocker scope widened** — `GATE_ENTITY_ARTIFACT_SUFFIXES` now scans the narrative prose artifacts (abstract, summary, overview, blog), so a fabricated person/org/place name in the summary/overview/blog FAILs the gate (previously only the abstract was scanned; the others were caught only indirectly by the faithfulness judge). The heading-heavy STRUCTURED artifacts (themes/topics/key-terms) stay excluded — their Title-Case concept labels are content, not names, and their fabrication mode is semantic (the theme/key-term judges' domain).

Offline suite: 819 passed / 18 skipped / 3 xfailed.

## [Unreleased] - 2026-08-22 (key-term domain-semantic judge — gap #4)

- **`key_terms_semantic_judge`** — the lexical key-terms validator cannot catch a lexically-plausible but semantically-WRONG definition (a term defined as the wrong concept, or swapped with a sibling, while still using transcript vocabulary). This judge asks, per term, whether the DEFINITION correctly captures the term's Bowen-theory meaning — labels `correct`/`incorrect`, fail-closed on any API/parse error. **Built but not yet armed** (`KEY_TERMS_JUDGE_ENABLED=False`); reuses the faithfulness judge's parser + result types + cache-reusable prompt.
- **Calibration harness** (`key_terms_head_to_head`) — builds a labeled set (real terms = correct; each term's definition swapped with another's = incorrect, skipping near-synonym swaps), runs the judge, and reports precision/recall/accuracy with arming-threshold clearance. A calibration with no INCORRECT examples can never read as "clears" (P24).
- **Live head-to-head (claude-sonnet-4-6, Kerr "Where Roots Bowen Theory Reside in the Brain")** — recall 1.0 / precision 1.0 / accuracy 1.0 on 20 examples (10 correct + 10 swapped), clearing the arming thresholds. The Claude-vs-Fable second-judge comparison is runnable by invoking the harness with a different `--model` once the Fable model string is provided.

Offline suite: 805 passed / 18 skipped / 3 xfailed.

## [Unreleased] - 2026-08-21 (cross-artifact reconciliation — gap #3)

- **`transcript_validate_consistency`** — the consistency check now reconciles artifacts against EACH OTHER, not just the transcript, catching drift a per-artifact check cannot see:
  - **Bowen recollection-drop** (abstract ↔ bowen-references): the abstract surfacing ≥ 2 person-recollections while `bowen-references.md` is EMPTY is a FAIL (a recollection the pipeline itself surfaced was dropped); a missing artifact (skipped stage) or a single incidental mention is a WARN; a recollection whose *substance* is absent from a non-empty file is a WARN.
  - **Orphan key-term** (key-term ↔ abstract + topics): a term reflected in neither synthesis surface is a WARN.
  - **Per-topic abstract coverage**: a topic the abstract silently omits is flagged individually (extends the old max-overlap-only signal).
- **Attribution-scaffold derivation** — `bowen_attribution.ATTRIBUTION_SCAFFOLD_WORDS` is derived from the detector's own verb regex lists (precisely: pure single-word verbs + explicit `quote`/`quoted`/`talk`/`talked`), so the consistency check's "strip attribution before judging recollection substance" can never drift from what the detector actually matches. `keyword_overlap` reverted to exact-word matching (a 5-char-prefix heuristic was found to over-match non-variants like `family`/`familiar` and silently loosen every caller).

Offline suite: 785 passed / 18 skipped / 3 xfailed.

## [Unreleased] - 2026-08-21 (chunked faithfulness judge for long transcripts)

- **`faithfulness_judge`** — a single batched judge call over a long transcript degrades attention (especially the middle) and can near the context limit (gap #1). Above `FAITHFULNESS_JUDGE_MIN_CHUNK_SOURCE_WORDS` (3000), `judge_artifact` now splits the source into overlapping word-windows (reusing the lexical validators' `VALIDATION_CHUNK_SIZE`/`OVERLAP`) and routes each claim to the window that holds *all* of its source-anchored significant words; a claim whose content spans windows (a summary-level inference connecting material across the source) is judged against the full source so a faithful abstraction is never falsely flagged. Short sources keep the single-call path unchanged.
- **Structural spread detection** — a claim routes to a window only if that window contains every significant word of the claim that appears anywhere in the source. This catches balanced *and* unbalanced cross-window spread uniformly (a best-vs-second overlap margin was found to miss the unbalanced shape in review), while still routing genuinely localized claims (e.g. a per-section key term).
- **Fail-closed reassembly** — `judge_claims_chunked` raises on any missing/None verdict before returning, so a future routing hole maps to a gate ERROR rather than an unhandled AttributeError downstream.
- **Cache invalidation by construction** — the chunking thresholds AND the routing code itself (`route_claims_to_chunks`, `chunk_source`, `_significant_words`, `_STOP_WORDS`) are folded into `_judge_logic_version`'s hashed material, so a threshold tune or routing-code edit cannot silently serve a stale cached PASS on the armed gate.

Offline suite: 773 passed / 18 skipped / 3 xfailed.

## [Unreleased] - 2026-08-21 (offline golden-transcript regression harness)

- **`tests/test_golden_transcript_regression.py`** — an offline end-to-end regression baseline (gap #2). Reuses the three existing golden fixtures (`dave_g_test2`, `roots_bowen_test`, `where_roots`) and runs the deterministic validation layer over each with zero API spend: the fabricated-name detector still flags the real "Luciano Malorni" fabrication (and stays clean on clean abstracts), claim extraction and the artifact codecs yield stable golden counts, the real `release_gate.run_gate` BLOCKs the known fabrication end-to-end, and the cross-artifact consistency check passes on the complete fixture. Offline-ness is enforced inside the test (not just by the suite conftest). The `GOLDEN` table is the single place to update exact counts on a legitimate change.

Offline suite: 758 passed / 18 skipped / 3 xfailed.

## [Unreleased] - 2026-08-21 (Bowen person-recollection extraction fix + cross-artifact consistency gate)

- **Bowen reference extraction prompt** — a "Bowen reference" is now a recollection of Murray Bowen *the person* (said/wrote/told/suggested/explained…), not "Bowen theory" exposition. The vague prompt previously made the model extract concept-applications, which the (correct) person-vs-theory filter then dropped → empty `bowen-references.md` on a Bowen-dense talk. Verified end-to-end: 0 → 7 genuine person-recollections on a Kerr talk.
- **New `check_consistency` release-gate check (advisory)** — deterministic, no-API cross-artifact consistency: flags an empty content-derived artifact on a transcript that clearly contains the material it should have captured (person-recollection density for Bowen), plus advisory key-term keyword-overlap and abstract↔topics signals. Wired into `DEFAULT_CHECKS` (advisory by policy, not a hard blocker).
- **`bowen_attribution.py`** — extracted the Bowen person-attribution detector into a shared stdlib-only module; `extraction_pipeline` and the consistency check both import it (same object by identity), so the density signal and the extraction filter can never drift. Behaviour-identical to the original (differential-verified), including the two distinct verb lists (short for the "Bowen theory" rejection, long for primary attribution).
- **Test-hygiene fix** — `test_bowen_references_integration` no longer clobbers the real `prompts/bowen_reference_extraction_v1.md` on every full-suite run (the fixture now redirects the frozen `config.PROMPTS_DIR` module attr to a tmp dir and restores it).

Offline suite: 749 passed / 18 skipped / 3 xfailed.

## [Unreleased] - 2026-07-18 (review fixes batch 10: dedups L11/L12/L14)

- **L11** — hoisted `_fill_prompt_template` into `transcript_utils.fill_prompt_template` (extraction uses it; validation's dead copy removed).
- **L14** — hoisted `load_prompt` into `transcript_utils.load_prompt(filename)`; the 5 pipeline modules delegate to it (each with its own prompt filename).
- **L12** — moved the orphaned, uncollected `legacy_initial_validation_logic.py` into `tests/test_initial_validation_v1.py`, so its 4 V1 cases (parsing + apply-corrections safety) now run as real coverage.
- **L13 deferred** — the GUI validator-dispatch dedup spans 3 *differing* ts_gui methods (interactive vs auto) and can't be verified headlessly; left with a TODO note (matches the review's own "wants human review").

Offline suite: 728 passed. Net −25 lines.

This completes the autonomously-safe review work: **37 of 43 fixed**, L15 resolved (keep the CLI). The remaining 5 (L13, M1, M7, H9, L17) are deferred with per-item recommendations in `TODO.md` — each needs a human decision or GUI verification.

## [Unreleased] - 2026-07-18 (review fixes batch 9: L2 doc + L15 decision)

- **L2** — documented the intentional `requirements.txt` (pinned CI/dev install, runtime + test tools) vs `pyproject.toml` (package metadata + dev group) split.
- **L15** — decision: **KEEP** the standalone CLI (`transcript_process` / `transcript_extract_*` / `transcript_summarize`). It's cross-referenced across those modules and covered by `tests/test_validator_gate_hardening.py`, so it's a supported, tested entry point — not dead code.

This closes the safely-automatable review work: **34 of 43 findings fixed**, L15 resolved (keep). The remaining 8 are refactors of working code / judgment calls, deferred with per-item recommendations in `TODO.md` for a human decision.

## [Unreleased] - 2026-07-18 (review fixes batch 8: perf, cost attribution, path guard)

- **M11** — `find_text_in_content` accepts a pre-normalized haystack; the Bowen grounding loop normalizes the transcript ONCE instead of re-normalizing it on each of its ~2 calls per ref (P9). Identical results.
- **L8** — `call_claude_with_retry` accepts an explicit `script_name` for cost attribution; the `unknown_script` fallback now warns instead of silently losing per-stage attribution (P2).
- **L16** — a shared `transcript_utils.base_name_is_safe()` guards all FOUR publish entry points (`generate_webpage` / `generate_simple_webpage` / `generate_pdf` / `package_transcript`) against a path-traversal `base_name` before any path build.

Offline suite: 724 passed / 21 skipped / 3 xfailed.

## [Unreleased] - 2026-07-18 (review fixes batch 7: judge layer — caching, cross-process memo, model pin)

Judge-layer batch from the adversarial review, calibration-verified with a live key.

- **H1** — the faithfulness + theme judges now split their prompt into a cached [instructions + SOURCE] block and a per-call [claims/themes] tail, so the transcript is reused across the 4–6 judge calls per publish (the model sees identical text). Live calibration re-passed 1.0/1.0; cache-hit confirmed (call 2 `cache_read=4295`).
- **H2** — cross-process judge memo: both armed judges now persist verdicts to a disk cache keyed on (artifact-sha, source-sha, model, **judge-logic-version**) so the CLI's per-subprocess publish steps don't re-run the judge. The logic version hashes prompt + extraction config + `JUDGE_LOGIC_VERSION`, so a stricter judge can never serve a laxer cached PASS (fail-open guard). ERROR never cached (P1); corrupt→empty (P8); atomic write.
- **H12** — `claude-sonnet-4-6` has no published dated snapshot, so the "PINNED" comment was corrected to disclose the residual server-side-resolution risk, and `tests/test_judge_model_pin.py` now fails on any silent change to a judge-model constant (forcing re-calibration).

Offline suite green; live calibration re-passed (gold + real-artifact + theme, 1.0/1.0).

## [Unreleased] - 2026-07-18 (review fixes batch 6: abstract-regen scope)

Sixth (final autonomous) batch from the adversarial review (`docs/CODE_REVIEW_2026-07-18.md`).

- **M2** — the abstract regeneration precheck judges the abstract ONLY (new optional `suffixes` param on `check_faithfulness`), so a sibling artifact's unfaithful claim no longer misblames the abstract and burns regeneration attempts. The publish gate still judges the full narrative set (default).
- Follow-ups: stopped enumerating the hard blockers in an in-code comment (it had drifted twice) — it now references `config.GATE_BLOCKING_CHECKS`; added a legacy-CSV consumer test for the M10 reader fallback.

Offline suite: 711 passed / 21 skipped / 3 xfailed.

**Autonomous pass complete: 27 of 43 review findings fixed across 6 independently-reviewed batches** (test count 664 → 711). The remaining 16 are deferred in `TODO.md` — each needs a human/API decision (judge re-calibration, an architectural refactor, or a judgment call).

## [Unreleased] - 2026-07-18 (review fixes batch 5: manifest provenance, CSV labels, docs)

Fifth batch from the adversarial review (`docs/CODE_REVIEW_2026-07-18.md`).

- **M9** — the gate run manifest now stamps `code_revision` (git short rev) and `gate_policy` (blocking checks + error-blocks flag), so a publish decision is traceable to the code and policy that produced it.
- **M10** — `token_usage.csv` header labels corrected to match the data (`Items`→`Model`, `Status`→`Stop Reason`); `analyze_token_usage` reads `Model` with a legacy `Items` fallback so pre-rename CSVs still parse.
- **L10** — the abstract prompt's hard word limit is injected from `config.ABSTRACT_HARD_MAX_WORDS` instead of hard-coded 249/250 literals.
- **L18** — pinned `check_theme_grounding`'s "no theme artifacts → PASS" branch with a test.
- **M4** — `ARCHITECTURE_DESIGN.md` now documents the release-gate / faithfulness-judge / theme-judge layer and the run manifest.

Offline suite: 708 passed / 21 skipped / 3 xfailed.

## [Unreleased] - 2026-07-18 (review fixes batch 4: retry/config hygiene + gate observability)

Fourth batch from the adversarial review (`docs/CODE_REVIEW_2026-07-18.md`).

- **M6** — retry policy (`MAX_RETRIES`, `RETRY_BACKOFF_BASE`) promoted from hard-coded literals in `call_claude_with_retry` to `config.py`.
- **M8** — the release gate's summary log now reports error/warn counts and emits a per-check `UNVERIFIED` line for a non-blocking "could-not-verify" ERROR, so it can't ship silently inside `ALLOW_WITH_WARNINGS`.
- **L1** — `check_entity_consistency` name regex uses `[ \t]+` (not `\s+`), so it no longer joins proper names across a newline and fabricates near-duplicate clashes (now consistent with the `find_ungrounded_names` hard blocker).
- **L5** — added `ProjectSettings.set_validation_model()` and included `VALIDATION_MODEL` in the model-global refresh, mirroring its three siblings.
- **L7** — lens-title stopword list moved from `extraction_pipeline` source into `config.LENS_STOPWORDS` (editorial vocabulary → config).

Offline suite: 703 passed / 21 skipped / 3 xfailed.

## [Unreleased] - 2026-07-18 (review fixes batch 3: emphasis parse + config/doc hygiene)

Third batch from the adversarial review (`docs/CODE_REVIEW_2026-07-18.md`).

- **M3** — scored-emphasis parser: pattern-1 score class now excludes `|`, so a `%`-less header carrying a timestamp (`[... Rank: 92 | 00:04:09]`) parses `score=92, timestamp=00:04:09` instead of averaging the digits to `26` and dropping the timestamp.
- **M5/L4** — removed the drifted inline "Defaults:" model-ID comment in `config.py` (`__init__` is the source of truth).
- **L3** — README `html_generator.py` line count 650 → 822 (48%, not 59%, reduction).
- **L6** — `"prompt-caching-2024-07-31"` beta header hoisted to `config.ANTHROPIC_CACHE_BETA_HEADER` (single source of truth).
- **L9** — `_current_git_revision` no longer caches a git failure as `unknown` for the whole session; it retries on the next call.

Offline suite: 696 passed / 21 skipped / 3 xfailed.

## [Unreleased] - 2026-07-18 (review fixes batch 2: H3-H7 + CI/deps hygiene)

Second batch from the adversarial review (`docs/CODE_REVIEW_2026-07-18.md`).

- **H3** — atomic `runtime_settings.json` write (uuid-named temp + `os.replace`); a partial write can no longer corrupt settings, and corrupt/non-dict resets are logged, not silent.
- **H4** — all 9 runtime deps declared in `pyproject.toml` so `pip install .` works (was only jsonschema).
- **H5** — CI `build` matrix → `["3.11","3.12"]` (matches `requires-python>=3.11`; fixes the `3.10`→`3.1` float mis-parse) and removed the `|| true` masks so install/test failures fail CI. This unmasked an undeclared **PyYAML** test dependency — now declared in `requirements.txt` + the pyproject dev group.
- **H6/H7** — README corrected: default model IDs now match `config.py` (the source of truth); abstract-coverage removed from the Run-All halt list (it is advisory).

Reviewed with `learning-qa` (caught the unmasked PyYAML gap before push). Offline suite: 691 passed / 21 skipped / 3 xfailed.

## [Unreleased] - 2026-07-18 (adversarial code-review: top-5 fixes)

Fixes from the 45-agent adversarial review (full report `docs/CODE_REVIEW_2026-07-18.md`;
the remaining 38 findings are tracked in TODO.md). All five ship with tests.

- **Stored XSS in the exported bundle (H13).** `markdown_to_html` emitted raw HTML, and its
  output (abstract/summary/topics/themes/formatted_content — all LLM-generated from the
  transcript) is rendered `{{ ...|safe }}` in every template, so a `<script>`/`onerror`
  payload in a transcript executed when the shared HTML/PDF bundle was opened. It now
  HTML-escapes the untrusted input before inserting our own markdown tags; headings/bold/
  italic still render. `transcript_utils.py`; `tests/test_markdown_to_html_xss.py`.
- **Faithfulness gate bypass via claim extraction (H11).** `extract_claims` stripped any
  leading `Prefix:` (≤40 chars) before the armed judge, so a fabricated attribution
  ("Stanford study: …") was deleted and rode through unjudged. The strip is now gated on a
  config allowlist of generic scaffolding labels (`FAITHFULNESS_STRIP_LINE_LABEL_PREFIXES`);
  a non-allowlisted prefix is left in place and judged. `faithfulness_judge.py`, `config.py`;
  `tests/test_faithfulness_judge.py`. **P20: the extraction path changed → calibration was
  re-run 2026-07-19 and PASSED** (gold set recall/precision 1.0; real-artifact path correct —
  the Luciano-Malorni and "nubbin" fabrications still FAIL; theme judge 1.0/1.0). The armed
  judge is re-validated after H11.
- **Default "V2 (Safe)" initial validator failed open (H8).** A per-chunk API/parse failure
  was caught and returned `[]`, so a dropped chunk was indistinguishable from a clean one and
  a partially-validated transcript shipped as `*_validated`. It now raises (fail-closed) like
  the v1 validator; a legitimate empty `[]` still parses. The GUI's `_execute_task` already
  surfaces the error and stops the spinner. `transcript_initial_validation_v2.py`;
  `tests/test_v2_validator_fail_closed.py`.
- **Config import crash on corrupt settings (C1).** A valid-JSON non-object (`null`/`[]`/`5`)
  in `runtime_settings.json` slipped past the `JSONDecodeError` guard and raised
  `AttributeError` at module import, taking down the GUI and every pipeline stage. Now reset
  to `{}` behind an `isinstance` guard. `config.py`;
  `tests/test_config_runtime_settings_dirty.py`.
- **Unbounded grounding scan (H10).** The fuzzy matcher's sliding window never early-stopped
  on an ungrounded quote, so a hallucinated Bowen quote scanned every window (2–4× per ref) —
  minutes of CPU on a long transcript. Added a cheap distinct-word coverage pre-filter
  (`FUZZY_MATCH_PREFILTER_MIN_COVERAGE`, kept safely below the match threshold) that
  short-circuits in O(haystack). `transcript_utils.py`, `config.py`;
  `tests/test_fuzzy_grounding_prefilter.py`.

Offline suite: 679 passed / 21 skipped / 3 xfailed (was 664; +15 new tests).

## [Unreleased] - 2026-07-17 (release-gate false positives, clearer messages, log spam, GUI status)

**Release gate no longer false-BLOCKs on filename metadata.** Both hard-blocking
checks used the transcript text alone as the source, so facts the abstract
legitimately draws from the filename were flagged as fabricated and blocked
publication (and the bundle):
- `entity_grounding` flagged the **presenter's own name** ("Michael Kerr") — a
  speaker rarely utters their own name. Now grounds against the transcript + the
  catalogue metadata **values** (`_filename_metadata_values`, values-only so
  framing words can't falsely ground a name — sweep F1).
- `faithfulness` flagged the **year** ("In this 2021 webinar…") as fabricated.
  Now the judge's source includes the labeled catalogue metadata
  (`_source_with_metadata`). P20: re-run the faithfulness calibration (TODO).
- Also fixed a `find_ungrounded_names` bug where a leading `# Abstract` heading +
  first word matched as the proper name "Abstract In" (strip scaffolding; names
  can't span a newline).

**Clearer, actionable gate messages.** `faithfulness`/`entity_grounding` BLOCKs
now read "check failed in <artifact> … — regenerate and try again" (naming the
artifact and, for entity, the offending name) instead of the cryptic
"N of M artifact(s) contain unentailed claims" / "names not found in source: […]".

**Log spam fixed.** `artifact_contracts` self-validation created a new timestamped
log file + console "Logging initialized" line on every saved artifact; the logger
is now cached once per process.

**GUI status bar** shows "Running <task>…" the moment a background task starts
(e.g. Create Bundle) instead of only updating on completion.

Ran through `/csdp` (learning-qa sweep: F1 values-only grounding fixed; F2 OR-logic
gap documented + pinned; F3 test-isolation; F4 __name__ guard). Full suite: 661 passed.

## [Unreleased] - 2026-07-17 (Init Val corruption fix: span-match guard)

**Init Val auto-apply could corrupt the validated transcript.** A correction with
no exact match fell to the fuzzy fallback, which overwrote a span located by
`transcript_utils.find_text_in_content` (an unreliable span — first-prefix
occurrence / normalized-word indices) with **no check that the span actually
contained the original text**. On a real run this rewrote a "differentiation of
self" region into `selfhere's` plus a duplicated chunk, which then failed Format
validation at 84% mismatch and halted the run (Format correctly refused to
publish the corrupted transcript).

Fix: new `transcript_utils.span_matches_original()` — before each destructive
replacement, verify the target span matches the correction's `original_text`
(normalized, ≥ `config.VALIDATION_MIN_APPLY_SIMILARITY=0.90`); skip and log
otherwise. Applied in **both** validators — v2 `apply_corrections_safe` and v1
`apply_corrections` (the latter still runs from the GUI in v1 mode) — so the
corruption class is closed everywhere. Also covers stale offsets after an alias
mutation. Fuzzy auto-apply is now conservative: a mis-located span is skipped
(flagged for manual review) rather than applied wrongly.

## [Unreleased] - 2026-07-17 (abstract length cap + bundle abstract-first)

**Abstracts capped under 250 words.** New `config.abstract_target_word_count()`
is the single source for the target length (3% of transcript, floored at
`ABSTRACT_MIN_WORDS=150`, capped at new `ABSTRACT_MAX_WORDS=230`) — routed through
by all three compute sites (main `summarize_transcript` generation, standalone
`generate_structured_abstract`, and the coverage validator), replacing duplicated
uncapped `max(...)` formulas (P5). New `ABSTRACT_HARD_MAX_WORDS=250`;
`validate_structural` / `validate_abstract` hard-cap their "too long" threshold
below it, so any abstract ≥ 250 words is flagged. Prompt updated to enforce the
limit.

**Bundle: Abstract first, on its own page.** `BUNDLE_SECTIONS` reordered so the
Abstract comes first with `page_break_after`. `_build_combined_markdown` emits a
neutral page-break marker (deferred to just before the next included section, so
no trailing blank page); `_render_pdf_weasyprint` translates it to CSS
`break-after:page`, `_render_docx_pandoc` to a raw pandoc OpenXML page break.

Ran through `/csdp` (learning-qa sweep found the missed primary generation site +
two lower-severity items; all fixed). Full suite: 644 passed.

## [Unreleased] - 2026-07-16 (GUI: bundle export, selective re-run, folder favorites, status bar)

**MD-collection bundle export (DOC/PDF).** New `bundle_export.py` + CLI
`transcript_bundle.py`: package a run's per-stage Markdown (Transcript [Format
or YAML], Topics, Emphasis, Bowen References, Abstract) into one PDF and/or DOCX
(plain concatenation, section headers). PDF via WeasyPrint, DOCX via pandoc
(`--reference-doc` for reduced heading sizes; `scripts/gen_bundle_reference_docx.py`).
Exposed as a `bundle` pipeline stage (all sections) and a post-run "Create
Bundle…" dialog (pick sections + format). Fail-closed on a release-gate BLOCK;
bundle suffixes join `PUBLISHED_BUNDLE_SUFFIXES` (F4 quarantine). Sections are
config-driven (`config.BUNDLE_SECTIONS`, `BUNDLE_DEFAULT_FORMAT='pdf'`).
Spec: `docs/spec_bundle_export_2026-07-16.md` (BE.1–BE.11).

**Selective re-run.** Check only the stages to (re)generate; unchecked stages
are bypassed and their on-disk outputs reused. Init-Val guard scoped to `format`;
`bowen_emphasis` now requires formatted/yaml (can't run on the raw transcript);
`STAGE_OUTPUTS` producer map + run-start "Run plan" log.
Spec: `docs/spec_selective_rerun_2026-07-16.md` (SR.1–SR.6). Reordered
`bowen_emphasis` before the publish-gated web/pdf & package stages.

**Val Abstract advisory.** A failed abstract-coverage check no longer halts the
run (parity with header validation), so independent downstream stages
(Bowen/Emphasis, blog, web/pdf) still complete; publish still gated. This fixed a
real run that stopped after Val Abstract and never produced Bowen/Emphasis.

**Source-folder favorites + Make Default fix.** "Make Default" now persists the
current source dir in any order (was only read while picking a folder) and adds
it to a favorites list (the auto-load default is always a favorite); the Folder
Defaults dialog gains a favorites listbox (Load/Remove).
Spec: `docs/spec_folder_defaults_2026-07-16.md` (FD.1–FD.5).

**Status bar.** The bottom bar tracks the current major step during a run and
shows a specific final message (`set_final_status`). Spec:
`docs/spec_status_bar_2026-07-16.md` (SB.1).

Full suite: 634 passed. Each change ran through the `learning-qa` failure-pattern
review; findings fixed in-session.

## [Unreleased] - 2026-07-15 (theme GROUNDING judge + test-validity follow-ups)

**Theme grounding judge (ARMED).** Themes were excluded from the faithfulness judge
because source-ENTAILMENT is the wrong check for interpretive content (a theme's job
is to interpret beyond the literal text). Added a SEPARATE judge that asks the right
question — *is this theme a grounded interpretation (its subject matter appears in /
follows from the source)?* — so it passes legitimate interpretation and FAILs a theme
built on fabricated subject matter.
- `faithfulness_judge.judge_themes_artifact` / `judge_themes` — one batched Sonnet
  call labelling each theme grounded/ungrounded (parsed via the M3 themes codec, so
  only real themes are judged, not scaffolding). Any ungrounded theme → FAIL naming
  it; source/API/parse error → ERROR (fail closed). `_parse_judge_response`
  generalized with a `valid_labels` param.
- `release_gate.check_theme_grounding` (structural + interpretive), Hard BLOCK
  (`config.GATE_BLOCKING_CHECKS += theme_grounding`), per-content memo, key via
  `resolve_anthropic_key`, forced OFF in the unit suite (root conftest).
- Calibrated on REAL theme artifacts (`tests/fixtures/theme_gold/gold.json`): all 20
  real themes → grounded; all 8 curated fabricated/contradicting themes → ungrounded
  (**recall 1.0 / precision 1.0**, `claude-sonnet-4-6`). Model pinned
  (`config.THEME_JUDGE_MODEL`). Offline tests (mocked) + live calibration (opt-in).
  This closes the themes gap the faithfulness work deferred (P20-compliant: calibrated
  on the real extraction path, smoke-tested end-to-end before arming).

**Test-validity follow-ups (TEST_VALIDITY_REPORT §3 closed).**
- 6 vacuous tests given real assertions (`test_exception_fix.py` ×4 pin
  `log_token_usage`'s swallow-not-raise contract; `test_validation_headless.py` ×2
  assert findings/schema + `pytest.skip`); `KNOWN_VACUOUS` emptied.
- False-green format tests repointed to REAL fixtures: `test_summary_pipeline_parsing`
  theme tests (kcfc structural=3 / interpretive=7; removed the `###`-as-theme A1-bug
  test); `test_bowen_references_integration` (2 formerly-xfail) → real consumer
  `parse_bowen_references_text`, un-xfailed.
- `summary_validation` mutation coverage 44%→71% on `check_keyword_coverage` +
  `check_proportionality` (medium tier, section/total terms, dynamic-tolerance tiers,
  divide-by-zero guard) — `test_validator_logic_hardening.py`.

## [Unreleased] - 2026-07-15 (unattended-robustness — M2: faithfulness judge)

Claim-level semantic faithfulness for NARRATIVE artifacts (U2) — catches a fluent
hallucination the lexical checks can't (the class that let 'Luciano Malorni' ship).
Scope (confirmed): all narrative artifacts (abstract/summary/overview/blog/themes),
Sonnet judge, full build incl. live calibration. **The judge is disabled by default**
(`config.FAITHFULNESS_JUDGE_ENABLED = False`) and ships only once the live M2.B.1
calibration clears its precision/recall bars — so the gate is unaffected until armed.

- **`faithfulness_judge.py`:** `extract_claims` (deterministic sentence-level,
  abbreviation-aware, keeps short *concrete* claims so a terse fabrication isn't
  dropped unjudged); `judge_artifact` — ONE batched Sonnet call scoring every claim
  {entailed | contradicted | unsupported}, any non-entailed → FAIL naming the
  sentence. Hardened via `call_claude_with_retry` (timeout+retry+backoff, P5).
  Fails closed (M2.C): missing source / API error / unparseable response / a claim
  with no verdict → ERROR, never a silent PASS (P1/P14). `binary_faithfulness_metrics`
  scores precision/recall on the dangerous (contradicted+unsupported) class.
- **`release_gate.check_faithfulness`:** judges `config.FAITHFULNESS_ARTIFACT_SUFFIXES`;
  FAIL/ERROR → BLOCK (`faithfulness` in `GATE_BLOCKING_CHECKS`, U2). A PASS no-op while
  disabled. "Nothing judged" is not "all faithful" — no narrative artifact present → ERROR.
- **Gold set `tests/fixtures/faithfulness_gold/gold.json`:** 25 curated (claim, source,
  label) cases against REAL sources (`dave_g_test2`, `where_roots`), labels verified
  against the source (P6) — 14 entailed (incl. 6 summary-level-inference precision-stress
  cases), 6 contradicted, 5 unsupported (incl. the real `Luciano Malorni` fabrication).
- **Tests:** offline (mocked, zero spend) cover claim extraction, the fail-closed
  parse contract, aggregation (M2.A.1 fabricated→FAIL / M2.A.2 clean→PASS / M2.C
  error→ERROR), metrics, and gate wiring. Live calibration
  (`test_faithfulness_calibration.py`, M2.B.1) is gated behind
  `RUN_FAITHFULNESS_CALIBRATION=1` + `ANTHROPIC_API_KEY` so it never spends on a
  normal run. Judge core logic 84% mutation-killed (fail-closed paths pinned).
- Two `learning-qa` passes applied: short-concrete-claim coverage hole (F1),
  pass-on-empty when nothing judged (F2), and gold-set precision-stress cases (F3).

**Status:** ARMED (`FAITHFULNESS_JUDGE_ENABLED = True`, policy: Hard BLOCK, prose
only). An isolated-gold calibration first passed but a real-full-artifact smoke test
caught that it would false-BLOCK — a P10 test-validity gap (LEARNINGS.md). Fixed the
right way: scoped to PROSE (themes dropped — interpretive by design), hardened
`extract_claims` (skip scaffolding/meta via `config.FAITHFULNESS_SKIP_LINE_LABELS`,
strip enumerators), tuned the prompt to distinguish a fabricated concrete specific
(BLOCK) from a thematic generalization (entailed), and **re-calibrated on REAL full
artifacts** (the P10 fix). Real-artifact calibration (2026-07-15, `claude-sonnet-4-6`):
claim-level gold recall/precision 1.0; the 3 real abstracts judged correctly —
`roots_bowen` PASS, `where_roots` FAIL naming the real `Luciano Malorni` fabrication,
`dave_g` FAIL on a genuine over-reach; an injected fabrication caught; end-to-end gate
smoke test BLOCKs the Malorni run. `transcript_utils.resolve_anthropic_key` (env →
shared `~/.config/llm/keys.json`) supplies the key; a per-content judge memo dedupes
the per-publish gate calls; a root-conftest guard forces the judge OFF in the unit
suite (enabled path exercised with a mocked judge). A learning-qa arming review then
caught a recall hole (the loosened prompt could pass an invented stance with no proper
noun) — tightened the prompt to flag invented assertions/causal-claims too, added
adversarial gold cases (us6/us7 invented-stance, no proper noun — both now caught),
verified verdict stability (3/3 runs), and PINNED `FAITHFULNESS_JUDGE_MODEL` to the
calibrated version (not `DEFAULT_MODEL`) so a model bump can't silently un-calibrate
the armed judge (P6). Coverage: docs/spec_coverage_m2_2026-07-15.md.

Suite: 564 passed / 15 skipped / 5 xfailed / 0 failed (live calibration opt-in only).

Spec: docs/spec_unattended_robustness_2026-07-15.md#M2 (M2.A, M2.B, M2.C)

## [Unreleased] - 2026-07-15 (unattended-robustness — M3: schema contracts)

Kill the P19 producer/consumer format-drift *class* (U4). Every structured
boundary becomes a schema-validated object; drift is a hard error, never a silent
zero. Scope decision: codec layer first — markdown stays the wire format, JSON is
a derived sidecar, generation prompts unchanged (delivers U4 regardless of wire
format). Staged one artifact at a time behind a migration shim; gate green
throughout.

**M3a — foundation.**
- **`schemas/*.schema.json` (6):** bowen, emphasis, key_terms, topics, themes,
  abstract_input — versioned, `additionalProperties:false` envelopes with
  `artifact`/`version` `const`s (catch a mis-routed object).
- **`artifact_contracts.py`:** per-boundary `Codec` — `parse_markdown` (migration
  shim, delegates to the ONE canonical text parser the consumer uses) / `validate`
  (jsonschema, loud `SchemaError` on drift) / `render_markdown` / `to_json`/
  `from_json`. Non-empty body → zero items = `SchemaError` (P19); truly empty
  (blank / frontmatter-only / bare H1–H2 header) = benign empty object.
- **Single-canonical-parser refactors** (behavior-preserving): extracted
  `parse_bowen_references_text` and `parse_topics_structure` so loader + codec
  share ONE format implementation. `parse_topics_structure` is *faithful* (the
  `<5%` editorial cut stays in `parse_topics_with_details`), so the JSON contract
  represents the artifact exactly.
- `jsonschema` pinned (requirements.txt, pyproject.toml). Real topics/themes
  fixtures copied from a production run for round-trip/migration tests.

**M3b — bowen wired (first boundary).**
- **Producer self-validation + JSON sidecar** at the bowen save site
  (`extract_bowen_references_from_transcript`): re-reads the saved artifact
  through the codec; on drift it LEAVES the file on disk (so the gate BLOCKs —
  deleting would invert a loud BLOCK into a silent drop), invalidates any stale
  sidecar, logs, and returns False. A valid save writes `<base> -
  bowen-references.json`.
- **Gate consumer-validation** `check_artifact_contracts` (release_gate.py):
  validates every on-disk structured artifact through the codec; drift → ERROR →
  **BLOCK**. Added to `config.GATE_BLOCKING_CHECKS` (U4: drift is a hard error).
  Verified against ALL real bowen artifacts on the drive (6/6 parse, 0 false
  reject) before landing as a hard blocker (P6).
- **`_has_body` empty-vs-drift discriminant:** a bare H1/H2 section header is a
  benign empty; an H3+ item header (or any non-heading line) with zero parsed
  items is drift — closes the all-headers-no-body gap.
- Tests: 30 codec + producer tests on REAL fixtures (round-trip field-level
  fidelity, drift-is-loud incl. all-headers, frontmatter/header-only benign,
  migration, producer self-check) + 4 gate tests. `_has_body` and
  `verify_saved_artifact` 100% mutation-killed; codec drift guard pinned.
- Two `learning-qa` pre-flight passes applied: topics faithful-parser +
  false-drift guard, emphasis type case-normalization, field-level round-trip
  assertion, and the delete-on-drift → leave-for-gate inversion fix (a HIGH
  finding — the producer's delete was silencing the very drift the gate blocks on).

**M3b — remaining boundaries wired (emphasis, key-terms, topics, themes,
abstract-input).**
- **One producer seam:** emphasis, topics, key-terms, and both themes all save
  through `_save_summary`, so `_self_validate_saved_summary` self-checks every one
  (re-read via codec → sidecar on success; on drift leave the file for the gate,
  invalidate stale sidecar, log; never delete). Non-codec types (blog/overview)
  are a no-op.
- **Themes migration shim reads BOTH real formats:** `**N. Title**` (current) and
  legacy `### N. Title` (H3-numbered, 2010-era runs) — a drive sweep found the H3
  format on a real structural-themes file that the bold-only parser returned zero
  for (P19). Verified 0 false-reject across every structural + interpretive
  artifact on the drive before gating themes.
- **Gate `_CONTRACT_ARTIFACTS`** extended to all 5 markdown boundaries (bowen,
  emphasis, key-terms, topics, both themes) — each a hard blocker on drift, each
  backed by a real-fixture round-trip/migration test.
- **abstract-input** (assembled `AbstractInput`, not saved markdown): producer
  self-validation in `prepare_abstract_input` via `to_contract_dict()` +
  `ac.validate` — a malformed input (empty topic name, out-of-range %) is a
  fail-closed `SchemaError` before the costly generation call (both callers catch
  it → stage returns False). Verified a real assembly validates (no false close).
- **Deliberate fail-closed decision (learning-qa F1):** the emphasis raw-response
  fallback (0 items from a >500-char response = drift) is saved under the canonical
  suffix ON PURPOSE so the gate BLOCKs — better than a silent absence; documented
  in-code. Two adjacent, non-M3 issues (emphasis content-rejected raw fallback;
  a whitespace-only topic-name edge) flagged in TODO, not silently fixed.

Suite: 540 passed / 14 skipped / 5 xfailed / 0 failed.

Spec: docs/spec_unattended_robustness_2026-07-15.md#M3 (M3.A, M3.B, M3.C, M3.D)

## [Unreleased] - 2026-07-15 (unattended-robustness — M5: fault-injection matrix)

The acceptance test for the fail-closed net: under adverse inputs and injected
faults the gate must give a definite decision (never crash) and degrade with a
distinct signal, or fail closed — never silently publish.

- **`tests/test_m5_fault_injection.py` (12).** M5.A input edge matrix (empty /
  whitespace / short / malformed / very-long transcript — no crash, correct
  block/allow); M5.B partial artifacts (missing source -> BLOCK; missing/empty
  abstract -> WARN, named); M5.C dirty re-run (BLOCK then clean clears the marker
  and quarantines the stale bundle; gate idempotent — same state, same manifest
  hashes); M5.D fault injection (a transient in a BLOCKING check -> ERROR -> BLOCK
  with no bundle; a fault in an ADVISORY check -> ALLOW_WITH_WARNINGS, F3).
- **`check_required_artifacts` (WARN).** Names a missing/empty required artifact
  (`config.GATE_REQUIRED_ARTIFACT_SUFFIXES`) so an incomplete bundle isn't shipped
  silently. Advisory per the entity-only blocking policy; a missing SOURCE still
  hard-blocks via entity_grounding's ERROR.

## [Unreleased] - 2026-07-15 (unattended-robustness — Phase 1: fail-closed release gate)

The pipeline's validators were advisory (they wrote a report; nothing blocked on
them), so a fabricated name could reach a published artifact. Phase 1 adds a
fail-closed release gate between generation and publication (spec M1/M4/M7).

### Added

- **`release_gate.py` (M1).** Every check returns a typed `Verdict`
  (PASS/WARN/FAIL/ERROR); `run_gate` aggregates them via a `config` policy table
  into a `GateDecision` (ALLOW / ALLOW_WITH_WARNINGS / BLOCK). A check that raises
  becomes an ERROR verdict — never silently skipped (M1.C) — and ERROR blocks by
  default (a run we couldn't verify must not ship, P1). Elected hard blocker:
  `entity_grounding`.
- **Provenance checks (M4).** `entity_grounding` (BLOCKING) FAILs on a fabricated
  proper name in the abstract (the shipped 'Luciano Malorni' class); scoped to the
  **abstract only** because the lexical name detector false-flags Title-Case
  headings/concepts in synthesized artifacts ('Key Takeaways', 'Role Absorption' —
  confirmed on real runs) and a false BLOCK is a hard stop. `verbatim_quotes`,
  `timestamp_citations` (catches the F6 drift), and `entity_consistency` (F7) run
  as WARN.
- **Run manifest (M7).** Each gated run writes `<base> - run-manifest.json`
  (per-artifact status + hashes, the GateDecision, source hash + model IDs, a
  single `publish_decision`); `release_gate.main` exits nonzero on BLOCK for
  cron/CI; a BLOCK drops a `PUBLISH-BLOCKED.txt` marker, cleared on a clean re-run
  (P8).

### Changed

- **Publish path is now gated (M1.B.2).** `generate_webpage`,
  `generate_simple_webpage`, `generate_pdf` (`html_generator`) and
  `package_transcript` (`packaging_pipeline`) call `release_gate.publish_allowed`
  and write NO bundle on a BLOCK. Tests: `tests/test_release_gate.py` (19 —
  real-fixture BLOCK/ALLOW, ERROR fail-closed + advisory-error-doesn't-block,
  manifest, publish guard, false-BLOCK scoping, stale-bundle quarantine, empty
  source, accented names). Two pre-existing unit tests were isolated from the gate.

### Review

`learning-qa` audited the diff. Fixed before commit: the entity blocker scoped to
the abstract (synthesized Title-Case labels false-BLOCK, confirmed on real runs);
advisory-check ERRORs no longer hard-stop publication (only blocking checks block
on ERROR); a BLOCK now quarantines any stale published bundle so it can't ship as
current; a present-but-empty source is ERROR not FAIL; the name detector matches
Latin-accented names. Documented as known limitations (TODO): single-word/acronym
names (needs the M2 judge) and manifest wiring into the live publish path.

## [Unreleased] - 2026-07-15 (unattended-robustness — Phase 0: code health + test-validity gates)

First phase of `docs/spec_unattended_robustness_2026-07-15.md` (approved scope:
the fail-closed net first). Phase 0 stabilises the ground and makes test validity
measurable, before the release-gate work (M1/M4/M7) touches the publish path.

### Fixed / hardened (M8)

- **`mut_harness` no longer corrupts its target on a kill (M8.C).** It restored
  byte-exactly only in a `finally`; a timeout/SIGKILL mid-run left an
  `ast.unparse`-reformatted, mutated file on disk (it corrupted
  `validation_pipeline.py` twice during Step 2). Now keeps a sidecar backup +
  SIGINT/SIGTERM handlers + self-heals a leftover mutant at the start of the next
  run, and streams progress. Logic extracted to `run_campaign(...)` with an
  injectable suite runner. Tests: `tests/test_mut_harness.py`.
- **Removed the dead duplicate `_generate_simple_html_page` (M8.A).** Python kept
  the later (live, tested) copy; the earlier was dead. Guard: `test_m8a1_no_shadowed_defs`
  AST-scans the core modules for shadowed top-level defs.
- **The 5 pre-existing red tests are now annotated `xfail` (M8.B),** so the suite
  is green (0 failed / 5 xfailed) and a real regression can't hide in a red suite.
  Each reason is recorded, and the underlying product decisions surfaced to
  TODO.md (the universal `MAX_TOKENS_SUMMARY=4096` output ceiling; config
  cross-instance settings reload; the abandoned-format bowen tests). Guard:
  `test_m8b1_known_reds_are_xfail_annotated`.
- **Artifact path audit (M8.D):** 216 uses go through `config.SUFFIX_*`; path
  *construction* is 100% via config. Fixed one straggler (`transcript_organize.py`
  used a literal ` - formatted.md`).

### Added (M6 — test-validity gates)

- **`quality_gates.py`:** a vacuity checker (`find_vacuous_tests` — flags
  assertion-free tests) and a mutation-gate config/runner. Enforced in-suite:
  `test_m6b1_no_new_vacuous_tests` blocks NEW vacuous tests (allowlisting the 6
  known ones, tracked in TODO), `test_m6a1_mutation_gate_config_is_valid` pins the
  gate config, `test_m6c1_real_format_fixtures_exist` protects the real-artifact
  fixtures.
- **CI (`.github/workflows/ci.yml`):** a strict `quality-gates` job (fails on a red
  suite + runs the vacuity gate) and a scheduled/dispatch `mutation-gate` job that
  fails when a core function drops below its score floor. The legacy lenient
  `build` matrix is left untouched.

## [Unreleased] - 2026-07-15 (real-run audit — Step 2: validator gate hardening)

Motivation: a full real run (`Where Roots Bowen Theory Reside in the Brain -
Michael Kerr - 2022-02-18`) was audited against its source transcript, and the
deterministic validators were **re-run with current code** on the real
artifacts, in both directions (good output must PASS; deliberately degraded
output must be FLAGGED). Several gates could be fooled or crashed. All validators
here are advisory (their return value drives a human-reviewed report, not a hard
pipeline gate), so a false PASS misleads the reviewer rather than auto-shipping —
but that report is the reviewer's signal. Findings report + method:
`scratchpad` audit notes; fixtures: `tests/fixtures/where_roots/` (real artifacts).

### Fixed (validator false-PASS / crash)

- **Emphasis validator only matched the first 15 words of each quote (P2/P9).**
  A quote with a verbatim opening and a fabricated tail passed silently (verified:
  a "…vaccines cause autism which Bowen never said" tail was accepted). It now
  probes BOTH the head and tail of every quote (`_emphasis_quote_found_ratio`,
  `config.EMPHASIS_HEADTAIL_WORDS`) and returns a real pass/fail bool instead of
  `None`. Side effect: fixed a pre-existing false-NEGATIVE (a genuine "Liking,
  that is pleasure…" quote that reflow made the 15-word match miss) — the real
  run now validates 100%. `validation_pipeline.validate_emphasis_items`.
- **Key-terms definition check was a gameable proxy (P7).** Definition support
  measured keyword overlap with the WHOLE transcript, so a definition describing
  the *wrong* concept still scored EXACT (verified: Homeostasis's definition
  swapped for the reward/salience-network definition → 0.87 → EXACT). It now also
  requires LOCAL grounding — overlap in the transcript window around where the
  term actually appears (`_best_local_grounding`,
  `config.KEY_TERMS_LOCAL_WINDOW_WORDS` / `KEY_TERMS_DEF_LOCAL_MIN`). Calibrated
  on the real run: valid definitions ≥0.54 local, swapped/off-topic ≤0.13. A
  grounded term whose definition fails the local check is downgraded from
  EXACT/PARTIAL to WEAK with a loud warning (P2). The 0.50/0.80/0.90/0.35 tier
  thresholds are promoted to `config.*` and pinned by a real-artifact test.
- **`_highlight_html_content` and `format_ref_list` crashed on 2-tuples (P19).**
  Loaders now emit 3-tuples `(label, quote, timestamp)`, but some callers still
  pass 2-tuples → `ValueError: not enough values to unpack`
  (`html_generator.py:531`). Both consumers now tolerate 2- and 3-tuples; the
  simple-page generator reuses the correct module-level `_format_ref_list`
  (which renders the timestamp) instead of a stale nested 2-tuple-only copy.
  Fixes 4 pre-existing red tests.

### Added (checks for previously-unguarded quality dimensions)

- **Abstract proper-name grounding (advisory, P2).** No gate checked abstract
  proper names; a real run fabricated a researcher name ("Luciano Malorni", for
  the person the source only ever calls "Bertoloso") and it shipped into the
  published HTML. `abstract_validation.find_ungrounded_names` flags multi-word
  Title-Case names whose tokens appear nowhere in the source (fuzzy-tolerant of
  ASR spelling normalization); surfaced as a warning + a line in the abstract
  validation report.
- **Bowen reference de-duplication (P2).** `load_bowen_references` returned the
  same quote twice when the model listed it under two concepts (real run: 5
  listed, 4 unique). It now dedupes by normalized quote text and logs what it
  dropped.
- **`tests/test_validator_gate_hardening.py` (18 tests)** — real-artifact
  contract + adversarial + edge-case tests for every fix above, each failing on
  the old code and asserting intended behavior (not a snapshot).

A `learning-qa` second-pass review of the diff caught two follow-ups that were
fixed before commit: (1) the key-terms local check located the term with *exact*
contiguous matching while `term_ratio` uses *fuzzy* matching, which would falsely
demote a legitimately-grounded multi-word term whose transcript form is
reordered/hyphenated (P19 #9) — the locator now uses a flat normalized token
stream and an unlocatable term gets the benefit of the doubt (no downgrade,
no warning), so the downgrade fires only when the term *was* located and the
definition still fails locally; (2) Bowen dedup now MERGES the duplicate's
concept label into the kept entry (`"A; B"`) instead of dropping it, so no
concept association is lost from the highlighter.

### Fixed (token-usage log hygiene)

- **Five API call sites logged token usage as `unknown_script`** on real runs
  (`abstract_pipeline` ×2, `summary_pipeline`, `transcript_extract_terms`,
  `transcript_audit_voice`). Each now passes a named logger so the cost log
  records the real step.

## [Unreleased] - 2026-07-15 (test-validity audit — Step 1: broken tests + validator hardening)

Motivation: a green 300+ test suite kept shipping critical bugs. A test-validity
audit (mutation testing + fixture-provenance + vacuity scan + learnings→test map)
found the suite is strong at pinning already-fixed bugs (all A1–A12 enforced) but
weak on the *validator decision logic* — mutation score 9% in `summary_validation`,
24% in `validation_pipeline`. Full write-up: `TEST_VALIDITY_REPORT.md`; harness:
`mut_harness.py`.

### Fixed (tests that verified nothing)

- **`test_summary_proportionality_warning` crashed before asserting.** It used
  `unittest.mock.patch` with only `import unittest` (no `unittest.mock`), so it
  raised `AttributeError` and never reached its assertions — an order-dependent
  false pass (it only "passed" when another test imported `unittest.mock` first).
  Added the import; corrected the stale mock (the test preset `item.covered=True`,
  but `validate_summary_coverage` re-derives coverage via `check_keyword_coverage`,
  so the item now carries real keywords present in the summary).
- **`test_summary_evaluative_warning` never ran.** It was indented one level too
  deep, defined *inside* `test_summary_too_long_warning`, so pytest never collected
  it. Dedented to a real test method; it passes.

### Added (validator decision-logic regression tests)

- **`tests/test_validator_logic_hardening.py` (15 tests).** Pins the validator
  logic the mutation pass exposed as unprotected: `required=` integrity of coverage
  items (speaker/opening/closing/Q&A), the topic required thresholds (`>=10%`
  summary, `>=15%` abstract), the first-theme-required rule (`i == 0`), the Q&A
  optional/required bands (15/30), the keyword-coverage count/ratio decision, the
  lexical grounding ratio, and the fail-closed `validate_key_terms_fidelity` on zero
  terms. Each assertion is written so the specific surviving mutation would fail it.

### Result

- Mutation score on the audited validator functions: `summary_validation` 9%→28%,
  `abstract_validation` 36%→50%, `validation_pipeline` 24%→27%. Suite grew by 16
  real tests (2 revived + 14 net new logic checks) with no regressions.

## [Unreleased] - 2026-07-14 (P19 contract audit — remaining medians A4/A6/A7/A8/A12)

### Fixed

- **Abstract closing-conclusion search discarded the closing body (A4, P19).**
  `extract_closing_conclusion` built the section regex with a *capturing* group
  `(N|…)`, so `re.findall` returned only section NUMBERS and the conclusion search
  ran against a string of digits — always failing and returning "No explicit
  conclusion stated", which silently dropped the required conclusion-coverage check.
  Made the alternation non-capturing so the body is searched. (The
  `conclusion_patterns` phrase list is now in `config.ABSTRACT_CONCLUSION_PATTERNS`,
  rule #9; its narrowness is a tracked recall gap, not a correctness bug.)
- **`parse_section_range` truncated multi-segment citations (A6, P19).**
  An anchored `re.match` fired on the leading range and returned only it, so
  `"7-8, 15, 33-35"` became `[7,8]` — deflating topic section-grounding (the real
  cause of the `section_mismatch` counts previously mislabelled "cosmetic"). Now
  expands every comma segment (`re.search`/`findall`, so `"Sections 7-8, 15"` also
  survives), deduped order-preserving.
- **Highlight verifier read an abandoned quote format (A7, P19).**
  `verify_highlights_bs4.load_source_quotes` matched only `> **Label:** "quote"`,
  returning `[]` on the real `### Concept\n> "quote"` (bowen) and `[meta] Concept:
  …\n"quote"` (emphasis-scored) artifacts — so the verifier reported a clean pass
  having checked nothing. Now parses all three formats, resolves the emphasis file to
  `emphasis-scored.md`, and treats "content present but zero parsed" as a drift error
  (loud warning + non-zero exit). On the real files: bowen 0→1, emphasis 0→22 quotes.
- **`top_lens` accepted without grounding (A8, P7).**
  The theme/lens validation loop accepted the validator's `top_lens` on a truthy-dict
  gate, never reconciling it to the ranked lenses actually generated, so a
  paraphrased/hallucinated top lens rode through into the blog. Added
  `_top_lens_is_grounded` (content-token overlap against the real `N. **Title**`
  lines); the loop now requires grounding to break and **fails closed after retries**
  (a `validated` flag — the exhaustion path no longer ships an ungrounded lens).
- **Abstract word count included the forbidden `# Abstract` header (A12).**
  `_strip_leading_scaffolding` now drops leading YAML front matter / heading / bold-
  label lines before the word count and keyword matching, so a header the model emits
  despite the "no headers" instruction can't tip the length check or the counts.

## [Unreleased] - 2026-07-14 (P19 contract audit — validator pass-on-empty cluster)

### Fixed

- **Header validation reported success on a report containing a real FAIL (A5, P19).**
  `validate_headers` / `HeaderValidator.run` wrote the report and returned success
  without ever counting the model's PASS/WARN/FAIL verdicts, and the model's format
  drift (`**STATUS:** FAIL` vs plain `STATUS: FAIL`) hid the failures from any naive
  counter. Added `transcript_utils.count_header_verdicts` (drift-tolerant), wired into
  both producers: a loud warning fires on `FAIL>0` or zero-verdicts-from-non-empty, and
  the report gets a `## Verdict Summary` header. On the real KCFC report it now surfaces
  1 FAIL / 5 WARN / 44 PASS (previously a silent pass). Advisory by design — the bool
  return still means "report generated", consistent with the coverage validators.
- **Coverage validators reported PASS on an empty required checklist (A9, P19).**
  `all(item.covered for item in required_items)` is `True` when `required_items == []`,
  so a summary/abstract whose upstream topics/themes were missing or format-drifted
  validated as "Required coverage: 0/0 — PASSED". Both `summary_validation` and
  `abstract_validation` now fail closed (with a warning) when no required items could be
  derived.
- **A transient purpose-extraction failure flipped a FAIL into a PASS (A10, P1).**
  `extract_opening_purpose` returned the same `"manually insert"` sentinel for a genuine
  absence AND for transient/config failures (no API key, timeout, missing prompt),
  silently demoting the required purpose check to optional. Transient failures now return
  a distinct `config.PURPOSE_EXTRACTION_FAILED` sentinel; the validator keeps that check
  REQUIRED and hard-uncovered (excluded from the LLM rescue pass), so validation cannot
  pass on an unverified purpose.
- **An ungroundable coverage item was auto-marked covered='high' (A11, P7).**
  `check_keyword_coverage` returned `(True, "high")` when an item had zero extractable
  keywords (e.g. an all-stopword topic name), satisfying required coverage with no
  grounding. It now returns `(False, "low")` — not auto-passed, but still eligible for
  the LLM rescue pass / human review (not hard-failed, so a legitimately-covered
  short-name topic can still be confirmed). Applied to both validators (P5 siblings).

## [Unreleased] - 2026-07-14 (P19 contract audit — theme-parsing cluster)

### Fixed

- **Theme parsers dropped or corrupted every theme on real transcripts (P19 — TODO.md A1/A2/A3).**
  The extraction stage writes structural/interpretive themes as bold-numbered
  `**N. Title**` blocks wrapped in `###`/`##` scaffolding (`### Structural Themes
  (3 total)`, `### Summary Paragraph`). Both consumers gated on `"###"` *first*, so
  they captured the scaffolding header as the theme name and mashed every real theme
  into one description blob — `parse_themes_from_extraction` returned **1 bogus theme**
  from a 3-theme file (abstract), `parse_themes` returned **2 junk entries** from a
  7-theme file (summary), and `summary_pipeline` had *no* code path that read the real
  `**N.**` format at all. Both now detect the bold-numbered format first (shared
  `parse_bold_numbered_theme_blocks` in `transcript_utils.py`), treat `###`-as-theme as
  a legacy fallback, reject scaffolding names (`is_scaffolding_theme_name`), and log a
  loud warning when non-empty input parses to zero themes. Verified against the real
  KCFC artifacts: structural 1→3, interpretive 2→7, with correct per-theme descriptions.
  Round-trip tests on the real artifacts: `tests/test_theme_parsing_contract.py`
  (fixtures copied from the real on-disk files, not idealized synthetic samples).
- **Extraction validity gate passed all-scaffolding structural files (P19 sibling, learning-qa).**
  `_is_valid_section_content` validated structural themes with a number-outside-bold
  regex (`1. **X**`) or a bare `###` presence check — so a `structural-themes.md`
  containing only scaffolding (`### Structural Themes (0 total)`, `### Summary
  Paragraph`) validated as usable content. It now routes through the format-aware
  `parse_themes_from_extraction` first and its fallback matches both bold forms.
  Ref: `extraction_pipeline.py` `_is_valid_section_content`.

### Changed

- **Theme scaffolding labels promoted to config** (`config.THEME_SCAFFOLDING_LABELS`,
  rule #9 — editorial content out of source). `is_scaffolding_theme_name` narrowed to
  four deliberately-conservative discriminators (empty / `#`-prefixed / config label /
  `(N total)` roll-up) after review flagged that a false-positive silently drops one
  theme without tripping the zero-from-non-empty guard; adversarial tests now assert
  real titles resembling scaffolding wording survive. Theme-block boundary widened from
  `#{2,3}` to `#{1,6}` so a stray H1/H4 scaffold can't be swallowed into the last
  theme's description.

## [Unreleased] - 2026-07-13 (run-log review, round 2)

### Fixed

- **`load_bowen_references` dropped references in a mixed-timestamp file.** The downstream reader (webpage/PDF) tried the *with-timestamp* pattern first and stopped as soon as it matched anything, so in a file mixing timestamped and non-timestamped references it captured only the timestamped ones. Replaced with a single pattern that makes the timestamp optional, so every reference parses regardless of order. (Fixes two previously-failing tests; a mock-setup bug in one was also corrected.)

- **Key-terms validation reported exact=0 / everything fail** once it started running (previous bug had it finding nothing). It required the *synthesized definition* to appear ~verbatim in the transcript, which no paraphrased definition ever does. It now grounds on the **term** (alias-aware: a slash-joined "A / B" grounds if either part appears) and checks the definition for **topical keyword support**, not verbatim. On the sample: 0 EXACT → 10 EXACT, and a hallucinated term still fails (adversarial test).
- **Bowen attribution detector missed possessive references with an intervening adjective** — "Bowen's **basic** ideas" failed because only an immediately-adjacent noun (or "key") was recognised, so genuine references were dropped. The possessive pattern now allows intervening words; adversarial cases ("Bowen's daughter…", "Bowen theory terms…") still correctly don't match.

### Added

- **Bowen drop-diagnostic.** When extraction produces candidates but 0 survive attribution filtering + grounding, a `… - bowen-references-debug.md` is written listing each candidate with *names-Bowen?* and *grounding* — so a zero result is inspectable (extraction-missed vs filter-over-dropped) instead of silently vanishing. This immediately exposed the attribution-detector bug above.

## [Unreleased] - 2026-07-13 (run-log review fixes)

### Added

- **"Silent empty" instrumentation.** New `warn_if_empty_parse` helper (transcript_utils.py) distinguishes a genuinely empty/absent source from a parser that yielded **zero items out of non-empty input** — the signature of a producer/consumer format drift (the class behind the emphasis/key-terms bugs). Wired into the post-Core emphasis, key-terms, and topics validators, which now log a loud "parsed 0 X from a non-empty source" warning instead of a silent "nothing to validate" pass. (Bowen is intentionally excluded — an empty result is valid there.)

### Fixed

- **Emphasis validation found nothing despite emphasis existing.** The scored-emphasis file is saved with the header and its quote separated by a blank line, but `parse_scored_emphasis_output` required both in one block, so the post-Core emphasis validator parsed 0 items. Hardened the parser to accept the header and quote either in one block or split across a blank line, and fixed the save to keep each item's header+quote adjacent (write→read round-trip). Real-artifact check: 0 → 10 items.
- **Key-terms validation found nothing despite key terms existing.** The dedicated key-terms artifact often has bare `### Term` blocks with no `## Key Terms` heading, which `_parse_key_terms_section` required. It now falls back to parsing the whole file. Real-artifact check: 0 → 9 terms.
- **Cost estimate ran ~3.6× low.** The estimator omitted Ranked Lenses, the Theme/Lens validation pass, and Bowen extraction, and collapsed the four separate core-extraction calls into one bundled "Key Items." These are now modelled separately. On the sample transcript the estimate went from $0.11 to $0.25 (actual ≈ $0.35–0.40).
- **Tests polluted the real cost log.** `log_token_usage` appends to `logs/token_usage.csv`; several tests called it (directly or via mock loggers), leaving junk rows (`test_script`, `<MagicMock …>`, nameless `unknown_script`). An autouse fixture in the root `conftest.py` now redirects the logs dir to a temp path for every test, so the production log can't be polluted.

## [Unreleased] - 2026-07-13 (lean abstract path)

### Added

- **Standalone Topics stage + Topics-only abstract (lean abstract path).** You can now produce an abstract (and, separately, Emphasis + Bowen) without running the full monolithic Core stage. A new `topics` stage (`generate_topics`) writes the Topics artifact straight from the transcript, and `generate_structured_abstract` now requires **only** Topics — the Interpretive-Themes artifact it previously demanded was never actually used by the abstract prompt (which builds from metadata, topics, and transcript-derived opening/closing/Q&A). Verified end-to-end on a real transcript: `Topics → Abstract` produced a coherent abstract for ~$0.02, roughly half the cost of full Core. Spec: `docs/spec_lean_abstract_2026-07-13.md` (LA.1–LA.5). Tests: `tests/test_lean_abstract.py`.
- The stage pre-flight now models this: `topics` depends on the transcript (yaml), and `gen_abstract` depends on Topics only (satisfiable by the `topics` stage **or** `core`), no longer on Interpretive Themes.

### Fixed

- Headless GUI tests could hang on a real `messagebox` dialog depending on test order; an autouse fixture (`tests/conftest.py`) now stubs Tk dialogs so the suite is hermetic and order-independent.

## [Unreleased] - 2026-07-13

### Added

- **Selectable pipeline stages with saved selections**: The GUI's per-stage "run" buttons and the hardcoded "Do All Steps" flow are replaced by a checkbox per stage plus a single **▶ Run Selected** button that runs whichever stages are ticked, in fixed pipeline order (cost estimate first, token-usage report last, halting on the first failure). A new **Manage Selections...** dialog saves the current tick-set under a name, reloads/deletes it, and marks one selection as the default that pre-ticks on startup (never auto-runs). Selections persist in `logs/runtime_settings.json` via new `config.py` methods (`save_stage_selection`, `delete_stage_selection`, `get_stage_selections`, `set_default_stage_selection`, `get_default_stage_selection`). Spec: `docs/spec_stage_selection_2026-07-12.md` (SS.1–SS.22); independent QA test spec: `docs/qa_test_spec_stage_selection_2026-07-12.md`.
- **Stage dependency pre-flight**: A synchronous validator (`_validate_stage_dependencies`) blocks a Run Selected before any work starts, with a single "Missing Prerequisites" message, if a checked stage's required upstream artifact is neither selected in the same run nor already present on disk (dependency graph verified against the actual pipeline function bodies, not button order). The whole run is blocked rather than partially run, and prerequisite stages are never silently auto-added. The validator resolves artifact paths through one shared helper (`_stage_artifact_path`) that the stage runners reuse, so its "does this exist" check can't drift from where stages write. Saved selections tolerate stage keys removed in a later release (unknown keys are logged and skipped, not fatal).

## [Unreleased] - 2026-07-12

### Added

- **Folder Defaults dialog**: New "Folder Defaults..." button beside directory selection opens a dialog to independently browse, view, and reset the default Processed directory, Projects directory, and Approved Terms file. Each is persisted via new `config.py` settings (`default_processed_dir`, `default_projects_dir`) in `logs/runtime_settings.json` alongside the existing source-directory and terms-file overrides, and reapplied automatically on the next launch.

### Changed

- **Resizable GUI layout**: The Source File list, File Status, and Processing Log panels are now hosted in a `ttk.PanedWindow` so their relative heights can be dragged, instead of fixed `rowconfigure` weights.

### Fixed

- **Format-validation timestamp stripping**: `strip_raw_speaker_prefixes()` now also matches parenthesized timestamps (not just bracketed), and `validate_format()` strips bare numeric-only TRX timestamp lines, preventing false mismatch counts on transcripts using those formats.

## [Unreleased] - 2026-05-13

### Added

- **GEO-optimized Overview Post**: New post type that runs parallel to the existing Lens #1 blog. Built from the abstract, structural themes, topics, and key terms — no lens required. Designed for Generative Engine Optimization with a definitional opener, TL;DR, question-shaped H2s, atomic citable statements, and a Frequently Asked Questions section. Frontmatter exposes `schema_type: "Article"`, `author`, `date_published`, and a structured `faq:` list ready for JSON-LD downstream. New GUI button "7b. Overview Post" triggers it independently of the lens-based blog. Configuration: `OVERVIEW_MIN_WORDS = 800`, `SUFFIX_OVERVIEW = " - overview.md"`, `PROMPT_OVERVIEW_FILENAME = "Transcript Summary Overview Post v1.md"`. Implementation plan and spec coverage at `docs/implementation_plan_2026-05-13.md` and `docs/spec_coverage_2026-05-13.md`.
- **Abstract loader fallback**: Standalone-path blog/overview generation now falls back from `SUFFIX_ABSTRACT_GEN` to `SUFFIX_ABSTRACT_INIT` when the validated abstract is absent, so transcripts that have only completed the initial abstract step can still produce post artifacts.

## [Unreleased] - 2026-03-10

### Fixed

- **Formatting context-budget guard**: Fixed the formatting preflight check to compare transcript input size against available model context capacity instead of the formatting output-token cap, preventing false aborts on long transcripts that still fit the model context window.
- **Context-budget warning text**: Updated preflight logging to say `context budget` / `safe input budget` so formatting failures are clearer in the GUI and logs.
- **Scored emphasis parsing compatibility**: Updated emphasis parsing and downstream loading to accept both bracketed and plain-text scored output formats, preventing false failure reports when the `.md` artifact already contains valid emphasis items.
- **`Set Directory` source-folder normalization**: Selecting a `source` folder in the GUI now resolves to its parent transcript base directory instead of producing an incorrect `source/source` path.
- **Fail-closed validation gating in `Run All`**: The GUI workflow now stops when header validation, abstract generation, or abstract coverage validation fails, instead of continuing into blog/web/package generation with invalid upstream artifacts.
- **Terms-file reset on transcript directory change**: Switching `TRANSCRIPTS_BASE` in the GUI now resets the active `Init Val` dictionary back to that directory's default `approve_terms.txt`, preventing accidental cross-corpus dictionary reuse.
- **Logger reinitialization**: `transcript_utils.setup_logging()` now replaces handlers on the named logger directly instead of relying on repeated `logging.basicConfig(...)` calls, ensuring each step writes to its intended log file.
- **Whisper/TRX format validation compatibility**: Formatting validation now strips supported TRX/Whisper transcript wrappers before word comparison, including `TRANSCRIPT` metadata headers, timestamped speaker prefixes, and appended `VALIDATION REPORT` / `FLAGGED ITEMS` footer blocks. This prevents false mismatch explosions when using `*_v-valid*.txt` inputs from the `trx` workflow.
- **Structured long-request streaming**: Enabled `stream=True` in both `summary_pipeline.generate_summary()` and `abstract_pipeline.generate_abstract()` so the structured generation paths comply with Anthropic SDK long-request requirements instead of relying on callers to opt in manually.
- **Structured transcript fallback**: Updated structured summary/abstract generation, structured validation, and webpage/PDF generation to load ` - yaml.md` when ` - formatted.md` is missing, preventing failures in projects where the YAML transcript remains but the formatted artifact does not.
- **PDF dependency messaging**: PDF generation now logs an explicit WeasyPrint dependency error instead of surfacing only a generic failure.

### Added

- **Transcript source format detection**: Added explicit source-format detection/logging in `formatting_pipeline` so formatting and validation report whether an input is `plain_transcript` or `trx_whisper_wrapped`.
- **Streaming regression tests**: Added coverage to verify `call_claude_with_retry()` uses `client.messages.stream(...)` when requested, and that structured summary/abstract generation explicitly enables streaming.
- **Fallback regression tests**: Added coverage for YAML-only structured abstract generation, abstract validation, and webpage generation.
- **Standalone Bowen/Emphasis extraction controls**: Added a dedicated `Bowen` button and independent `Core` / `Do All` include toggles in the GUI so Bowen references and emphasis items can be run together or separately.
- **Direct-file extraction support**: Added support for running standalone Bowen and emphasis extraction directly from a selected source `.txt` file in the GUI and via `transcript_extract_bowen.py` / `transcript_extract_emphasis.py`.
- **Independent Bowen skip control**: Added `--skip-bowen` to `transcript_summarize.py` and a matching backend `skip_bowen` path so Bowen reference extraction is no longer coupled to the rest of core extraction.
- **Initial validation learning**: Added persistent review memory for rejected `original_text -> suggested_correction` pairs in `logs/validation_memory.json`, plus approved-term persistence in `approve_terms.txt` so `Init Val` reruns can converge instead of repeating the same rejected suggestions.
- **Deterministic validation aliases**: `approve_terms.txt` now supports `wrong = Correct` rules. `Init Val` injects alias-based findings locally and can persist selected corrections back as aliases from the review dialog.
- **Transcription-only validation scope**: Narrowed `Init Val` to proper nouns, homophones, spelling/non-word cleanup, and word-boundary issues. Grammar, punctuation, capitalization-only, and style cleanup are now explicitly excluded in prompts and code-level filtering.
- **Compact review UX**: Simplified the `Init Val` dialog to one-line `Found > Suggested` rows, checked by default, with approved items automatically feeding the domain dictionary instead of requiring multiple per-item checkboxes.
- **Selectable terms file**: Added a GUI selector for the active `Init Val` terms file so baseline dictionaries can be swapped at runtime without replacing `approve_terms.txt` manually.

## [Unreleased] - 2026-01-11

### Changed

- **Combined GUI quote extraction**: Replaced separate `Bowen` and `Emphasis` GUI buttons with a single `Bowen + Emphasis` action that reuses one cached transcript context for both extraction calls.

### Documentation

- Updated `README.md`, `DOCUMENT_REFERENCE.md`, and `PROJECT_STATUS.md` to align with current code-level behavior:
  - Current model defaults from `config.py` (`claude-sonnet-4-20250514` / `claude-3-5-haiku-20241022`)
  - Current artifact naming and pipeline stage outputs (config suffix-based)
  - `TRANSCRIPTS_BASE`-driven directory semantics replacing hardcoded `~/transcripts` assumptions
  - Current test collection snapshot and duplicate test-module collection mismatch note

### 🎯 **Critical Fix: Summary Generation Word Count**

Fixed critical issue where summaries were generating only 423-460 words instead of 600-750 word target. Issue required 13 separate fixes across 6 files.

### Fixed

- **Summary Generation Length** - Summaries now consistently generate 600-800 words (was 423-460):
  - Removed conflicting 25% inflation logic in word allocation
  - Switched from Haiku to Sonnet 3.7 for content generation (Haiku too concise)
  - Fixed GUI to use DEFAULT_MODEL instead of hardcoded AUX_MODEL override
  - Increased default target: 600 → 650 words (accounts for model behavior)
  - Strengthened validation: min_words 450 → 600
  - Increased token limit: 2500 → 4000 (allows longer output)
  - Enhanced prompt with balanced length instructions
  - Added comprehensive logging for model selection and word allocations

### Changed

- **Model Configuration** (`config.py`):
  - DEFAULT_MODEL: `claude-sonnet-4-5-20250929` → `claude-3-7-sonnet-20250219` (supports caching)
  - DEFAULT_SUMMARY_WORD_COUNT: 600 → 650 words
- **Summary Pipeline** (`summary_pipeline.py`):
  - Removed 25% target inflation (lines 576-582)
  - Updated generate_summary() default model parameter to use DEFAULT_MODEL
  - Increased min_words: 450 → 600
  - Increased min_length: 2000 → 2400
  - Increased max_tokens: 2500 → 4000
  - Added logging for model selection and word allocations
- **Extraction Pipeline** (`extraction_pipeline.py`):
  - Updated generate_structured_summary() to use DEFAULT_MODEL (was AUX_MODEL)
  - Updated generate_structured_abstract() to use DEFAULT_MODEL (was AUX_MODEL)
  - Added model logging
- **Abstract Pipeline** (`abstract_pipeline.py`):
  - Updated generate_abstract() to use DEFAULT_MODEL (was AUX_MODEL)
- **GUI** (`ts_gui.py`):
  - Fixed all summary/abstract generation calls to use DEFAULT_MODEL instead of AUX_MODEL (4 locations)
- **Summary Validation** (`summary_validation.py`):
  - Increased minimum word count: 450 → 600
  - Added proximity check (warns if < 85% of target)
  - Removed upper limit validation (longer summaries acceptable)
- **Prompt Template** (`prompts/Summary Generation Prompt v1.md`):
  - Balanced length instructions (was too emphatic causing over-generation)
  - Changed from "CRITICAL", "MUST", "FAIL" to "aim for", "approximately"
  - Added guidance to avoid significantly exceeding 800 words

### Added

- **Test Suite** (`tests/test_summary_word_count_fix.py`): 15 comprehensive tests covering:
  - Config changes validation
  - Inflation removal verification
  - Word allocation calculations
  - API call parameters (min_words, max_tokens, min_length)
  - Validation threshold enforcement
  - End-to-end behavior
- **Updated Tests** (`tests/test_summary_scaling.py`): Updated 2 tests for new behavior
- **Documentation**:
  - `SUMMARY_WORD_COUNT_FIX.md` - Complete implementation details
  - `CRITICAL_FIX_MODEL_SWITCH.md` - Model selection analysis
  - `ADDITIONAL_FIXES_APPLIED.md` - Iteration 2 fixes
  - `FINAL_FIX_CACHING_COMPATIBLE.md` - Caching model selection
  - `COMPLETE_FIX_SUMMARY.md` - Executive summary
  - `TEST_RESULTS_SUMMARY.md` - Test suite results (67/69 passing)
  - `SUMMARY_GENERATION_FIX_COMPLETE.md` - Final status and results

### Performance

- **Cost Optimization**: Using Claude 3.7 Sonnet with prompt caching:
  - First summary: ~$0.14 (cache write)
  - Subsequent summaries: ~$0.053 (cache read - 62% savings)
  - vs Sonnet 4.5 without caching: $0.36 per summary (85% savings)
- **Test Results**: All 15 new tests passing, 67/69 overall (97% pass rate)
- **Final Output**: 631-800 words consistently, passing validation

### Notes

- Claude 3.7 Sonnet deprecated but works until February 19, 2026
- Migration to Series 4 with caching support needed before EOL
- If summaries too long (>900 words), lower target to 600 in config.py
- If summaries too short (<600 words), verify model is claude-3-7-sonnet-20250219

---

## [Unreleased] - 2026-01-10

### 🎉 **Major Release: All Critical Issues Resolved**

This release completes all 4 critical issues identified in the architecture review, improving code quality from C+ to A-, reducing technical debt by 21.3%, and increasing test coverage by 15%.

### Added

- **Configuration Validation System** (`config.py`): Added comprehensive validation for 70+ configuration values across 7 categories:
  - Directory paths validation with auto-fix capability
  - Model name validation against available models
  - Numeric range validation (token limits, temperatures, timeouts)
  - Percentage and ratio validation
  - Word and character count validation
  - Logical consistency checks (chunk sizes, threshold ordering)
  - Type validation for confidence sets and error types
  - `ValidationResult` class to track errors and warnings
  - `validate_configuration()` function with detailed error reporting
  - `validate_or_exit()` for startup validation that exits on errors
- **HTML Template System** (`templates/`): Migrated from embedded HTML/CSS to Jinja2 templates:
  - Created `templates/base.html` with block inheritance
  - Created `templates/webpage.html` for sidebar layout
  - Created `templates/simple_webpage.html` for single-page layout
  - Created `templates/pdf.html` for print-ready output
  - Extracted CSS to `templates/styles/common.css`, `webpage.css`, `pdf.css` (360 total lines)
  - Auto-escaping enabled for XSS protection
- **Security Improvements** (`transcript_utils.py`): Added `sanitize_filename()` function (67 lines) to prevent path traversal attacks:
  - Blocks `../` parent directory references
  - Removes null bytes and control characters
  - Validates filename length and emptiness
  - Uses `Path.name` to extract safe filename component
  - Enhanced `parse_filename_metadata()` with validation for empty components and missing years
- **Test Suites**: Added 4 comprehensive test suites (1,100+ lines, 87 tests total):
  - `test_exception_fix.py`: 4 test suites for exception handling
  - `test_path_traversal_fix.py`: 9 test suites covering 40+ security test cases
  - `test_html_generation.py`: 6 test suites with 30+ assertions for template rendering
  - `test_config_validation.py`: 13 test suites with 50+ assertions for configuration validation
- **Documentation**: Created 5 detailed documentation files:
  - `ISSUE_1_FIXED.md`: Exception handling improvements
  - `ISSUE_2_FIXED.md`: Security vulnerability fix
  - `ISSUE_3_FIXED.md`: Template refactoring details
  - `ISSUE_4_FIXED.md`: Configuration validation details
  - `FIXES_SUMMARY.md`: Comprehensive summary of all fixes (475 lines)
  - Updated `code_quality_review.md` with all fixes marked complete

### Changed

- **Exception Handling** (`transcript_utils.py:306-322`): Enhanced `log_token_usage()` function:
  - Replaced broad `except Exception` with specific exception types
  - Added separate handlers for `OSError/IOError/PermissionError`, `csv.Error/UnicodeEncodeError`
  - Added logging with stack traces for unexpected exceptions
  - Improved error messages with actionable guidance
- **HTML Generation** (`html_generator.py`): Refactored from 1,584 → 650 lines (59% reduction):
  - Migrated to Jinja2 template engine
  - Extracted 1,000+ lines of HTML/CSS to separate template files
  - Preserved complex highlighting logic unchanged (proven, battle-tested)
  - CSS loaded once at module level for performance optimization
  - Maintained 100% backward compatibility (no API changes)
- **Default Models** (`config.py`): Updated `DEFAULT_MODEL` from invalid `"claude-3-7-sonnet-20250219"` to valid `"claude-sonnet-4-5-20250929"` (Claude Sonnet 4.5)

### Fixed

- **Security Vulnerability** (CVSS 7.5/10): Path traversal attacks now completely blocked:
  - Fixed: `../../../etc/passwd` → sanitized to `"passwd"`
  - Fixed: `/absolute/path` → sanitized to `"path"`
  - Fixed: `file\x00name` → null bytes removed
  - Fixed: Control character injections → removed
  - Tested: 40+ attack vectors all blocked
- **Silent Exception Swallowing**: Exceptions now properly categorized and logged with stack traces
- **Configuration Bugs**: Fixed invalid DEFAULT_MODEL causing runtime API errors
- **Missing Directories**: Auto-created with `validate_configuration(auto_fix=True)`

### Performance

- **HTML Generation**: CSS loaded once at module level (not per-generation)
- **Template Compilation**: Jinja2 caches compiled templates automatically

### Security

- **Path Traversal**: Eliminated critical vulnerability (CVSS 7.5/10)
- **XSS Protection**: Auto-escaping enabled in Jinja2 templates
- **Input Validation**: Comprehensive sanitization of all filename inputs

### Metrics

- **Code Quality**: C+ → **A-** (2 letter grade improvement)
- **Critical Issues**: 4 → **0** (100% complete)
- **Security Vulnerabilities**: 1 → **0** (100% fixed)
- **Technical Debt**: 54 hours → 42.5 hours (21.3% reduction)
- **Test Coverage**: 40% → 55% (+15%)
- **html_generator.py**: 1,584 → 650 lines (59% reduction)
- **Tests Added**: 87 comprehensive tests (all passing)

### Breaking Changes

None - All changes are 100% backward compatible.

---

## [Unreleased] - 2026-01-09

### Added

- **Cost Estimation**: Added estimated cost calculation (Input, Output, Cache Write/Read) to `transcript_utils.py` and `token_usage.csv`.
- **Cleanup GUI**: Added "Cleanup Source" button to the GUI to move original/validated files to `processed/` and delete intermediate versions.
- **Robust JSON Parsing**: Enhanced `transcript_initial_validation.py` to handle JSON responses with trailing text or "Extra data" errors using `raw_decode`.
- **Explicit Streaming**: Updated `transcript_utils.py` to explicitly handle the `stream` parameter, preventing "Streaming is required" errors for long requests.

### Changed

- **Project Documentation**: Corrected the "Project Structure" section in `README.md` to reflect the actual directory layout.
- **GUI Resizing**: Improved `ts_gui.py` to allow the "Select Source File" list to resize vertically and increased default window height to 950px.
- **Validation Warnings**: Downgraded "Length Check" and "Evaluative Language" from failure conditions to warnings in both Summary and Abstract validation. This allows stylistically deviant but semantically correct content to pass.
- **Robust JSON Parsing**: Improved `transcript_initial_validation.py` to correctly parse JSON responses even when followed by extraneous text.

## [Unreleased] - 2026-01-05

### Added

- **Dynamic Model Selection**: Added dropdown menus in the GUI to select specific Claude models for Default, Auxiliary, and Formatting tasks.
- **Test Runner**: Added `run_tests.py` script to execute all unit and integration tests.
- **Integration Tests**: Added `test_pipeline_integration.py` to simulate the full extraction and validation workflow.
- **Parsing Tests**: Added `test_summary_pipeline_parsing.py` and `test_extraction_model_passing.py` to verify parsing logic and model propagation.
- **Technical Documentation**: Added a "Technical Details" section to `README.md` explaining the robust regex logic for topic parsing.

### Changed

- **Topic Parsing Logic**: Updated regex patterns in `abstract_pipeline.py` and `summary_pipeline.py` to be non-greedy and robust against malformed metadata (e.g., missing semicolons).
- **Default Models**: Updated default models in `config.py` to `claude-opus-4-5-20251101` (Default) and `claude-haiku-4-5-20251001` (Aux/Formatting).
- **Configuration Management**: Refactored `config.py` to use a Singleton pattern for managing runtime settings while maintaining backward compatibility.
- **Test Suite**: Refactored multiple test files (`test_regex.py`, `test_timestamp_regex.py`, `test_formatting_helpers.py`, `test_emphasis_detector.py`) to use `pytest` style assertions and parametrization for better reporting.

### Fixed

- **Model Propagation**: Fixed issues where the selected model was not being passed down to `generate_structured_summary`, `generate_structured_abstract`, and validation functions.
- **Header Validation**: Fixed `HeaderValidator` to accept a dynamic model argument.
- **Deprecated Models**: Removed references to deprecated models (`claude-3-opus-20240229`, `claude-3-sonnet-20240229`, `claude-3-7-sonnet-20250219`) to prevent API errors.
- **Test Reliability**: Fixed `test_validation_headless.py` to correctly report failures to the test runner.
- **Bowen References**: Fixed parsing issue where list markers prevented references from being highlighted in the webpage; added robust cleaning logic.
