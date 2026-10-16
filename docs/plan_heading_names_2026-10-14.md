# Plan: the name check stops flagging generated headings (HN)

**Status:** requested 2026-10-14 (author: "fix the heading name false flags and continue
until complete"); built 2026-10-15 (commit 4d4b6fb), revised the same day after two
learning-qa rounds; end-to-end run 11 passed.
Status per criterion under "Built" at the end.

**Goal:** a heading the model writes ("Closing Advice") or a date it writes out ("On June
25, 2021") is not reported as an invented name. A made-up name is still reported.

## Evidence

Every entity-check flag in the logs of end-to-end runs 1–10 (three public talks). Each
one cost a revision; none was a name:

| Flag | Where | Cause |
|---|---|---|
| Closing Advice (x2), Final Reflections, Hurtful Remark, Multigenerational Roots (x2), Patterns Identified, Swapping One Culprit, Replacing One Culprit | overview / blog headings and labels | heading words the talk does not use |
| On June (x3) | Systems Biology overview prose, "On June 25, 2021, ..." | the date comes from the filename (2021-06-25); the talk never says "June" |

The check (`abstract_validation.find_ungrounded_names`) takes every Title-Case span of two
or more words and flags it when none of its words of 4+ letters appears in the source.
Since review F2 (plan R6) it also checks the spans inside headings and bold labels. A
generated heading uses words of its own, so it reads as an invented name.

## HN.1 — A heading run is a name only when it looks like one

In headings and bold labels, a run of words not in the source counts only when
`abstract_validation.looks_like_name` says it could be a name:

- **Strong evidence, enough alone:** a word that is not English ("Doerfler", "José"), or a
  given name that is not an English word ("Sarah", "Jennifer").
- **Weak evidence:** a given name that is also a word ("Grace", "Mark", "Amy", "Sophia" —
  Webster's has "sophia"), or a surname that is a word, directly or through an
  inflection ("Walker", "Rogers"). **Two weak words count** ("Grace Walker", "Mark
  Turner", "Harper Baker", "Walker Hall").
- A run with at most one name-like word ("Closing Advice", "Young Adults", "Modern Art")
  is a generated heading.

Word lists (`data/`):

- `english_words.txt`: the lowercase entries of Webster's Second International (1934,
  public domain; `/usr/share/dict/web2` on macOS/FreeBSD), 210,626 words. An inflected
  word counts when its base form is listed ("reflections", "identified", "replacing",
  "swapped"), also after a common prefix that leaves 4+ letters ("multigenerational" →
  "generational"; `config.NAME_CHECK_WORD_PREFIXES`).
- `first_names.txt`: US Census 1990 female and male first names (public domain, as
  distributed in zxcvbn's frequency lists, MIT) plus BSD `propernames`, minus 50 entries
  that are ordinary words or titles ("the", "case", "root", "king"); the file header
  lists them. 5,259 names. Given names of 3+ letters are looked up
  (`config.NAME_CHECK_GIVEN_NAME_MIN_LEN`). A short word is kept at the start of a run
  when it is a given name ("Ben Kerman") and at the end when it is a surname ("Abigail
  Lee"); other short edge words are dropped as before ("Black Art", "Christmas Eve").
- Month and weekday names count as ordinary words ("Friday Session Highlights"); Webster's
  lists them capitalised only.
- `surnames.txt`: the 10,000 most frequent US Census 1990 surnames (public domain, zxcvbn).

Safety and reporting:

- If any list cannot be read, the failure is logged, not cached, and every heading run
  counts as a name: the check is then as strict as before, never looser.
- Runs not counted are handed back (`find_ungrounded_names(..., excused=[...])`); the
  entity gate (abstract, summary, overview) and the advisory blog check name them in
  their detail ("N heading phrase(s) not in the source and not counted as names: ...")
  and log them.
- The judge cache key covers the new functions, the three config tuples, the given-name
  length and a digest of the three lists, so a stricter list never serves a cached PASS.
- Prose is unchanged: a Title-Case span in a sentence is checked as before.

**Residual (accepted):** a made-up name written only as a heading with at most one
name-like word is not caught by this check: a given name missing from the lists that is
also an English word (Aria, Maverick, Willow, Zoe, newer than the 1990 lists; Hope,
Summer) with a surname that is a word ("Willow Green", "Hope Walker"); a given name that
is a word with a word that is not a listed surname ("Amy Post"); an organisation of common
words ("Alcoholics Anonymous"); or a run left with one surname after the given name is
found in the talk ("Grace Hall Speaks" in a talk that says "grace"). In prose the same
names are still caught. A single given name with an ordinary word ("Nick Today") is not a
name here, as a single name in prose never was.

**Residual false flag (accepted):** a short given name that is not a word at the start of
a generic heading ("Max Effort") still reads as a name. None seen on a real run.

## HN.2 — A written-out date is not a name

A span whose significant words are all month or weekday names ("On June", "In March",
"On Friday") is skipped (`config.NAME_CHECK_MONTHS`, `NAME_CHECK_WEEKDAYS`). A span with
any other word ("June Carter", "April Smith") is checked as before. Considered and not
done: adding the recording date's month to the grounded words. That would also ground a
made-up "June Carter" in a June talk.

## HN.3 — Measured before and after on real output

`docs/calibration/2026-10-14_heading_names/measure_heading_names.py`, old code (worktree
at a124e0d) against new. No API calls. Each artifact is checked against its own run's
transcript, runs in number order, so the numbers do not depend on argument order; the
results file records both commands. Results: `results_old_vs_new.txt` in the same folder.

| Set | Checks | Old flags | New flags | Change |
|---|---|---|---|---|
| same: each overview, blog, summary and abstract of runs 1–10 against its own talk (transcript + filename metadata, as the gate builds the source) | 106 | 1 ("Hurtful Remarks") | 0 | the one flag was a heading |
| cross: each artifact against another talk's source | 212 | 708 | 617 | 36 phrases no longer flagged: 35 concepts or headings ("Tissue Niche", "Emergent Features", "Relapse Cycle") and "Nick Today" (a first name with an ordinary word); none newly flagged |
| probe: run 9–10 headings, made-up names and dates added to real overviews | 63 | 43 | 24 | the 7 logged headings and the dates pass; made-up names flagged as before except "Hall Speaks" (residual above) |
| names: 31 real names from the talks, each as a heading | 31 | 25 | 24 | lost "Alcoholics Anonymous", "Narcotics Anonymous" (residual); gained "Ben Kerman" |
| pairs: 98 popular US given names of recent decades x the 50 commonest US surnames, as "## Notes From <given> <surname>" | 4,900 | 4,900 | 4,824 | 76 missed: Aria, Maverick, Willow, Zoe with surnames that are words (residual) |

## Review (learning-qa, 2026-10-15) and what changed

| Finding | Fix |
|---|---|
| An unreadable given-name list made the check looser; the empty list was cached for the process | every list must load or the run counts as a name; failures are not cached (`test_hn1_unreadable_word_list_keeps_the_check_strict`, all three lists) |
| BSD given names too narrow; short given names never looked up; inflection rules turned surnames into English ("Rogers"); measured 6.3% of name pairs lost | census given names and surnames; strong/weak evidence; 3-letter given names; short given names kept at run edges. Pairs lost: 6.3% (reviewer's set) → 1.6% (set above) |
| Judge cache key missed the new inputs | functions, tuples and a list digest in the key (`tests/test_judge_disk_cache_h2.py::test_hn_*`, `test_r9a_component_change_changes_key`) |
| Runs not counted were dropped silently | `excused` list; named in the gate verdict and logged (`test_hn1_excused_runs_are_reported`) |
| LEARNINGS overstated what is still caught | reworded |

Second round (learning-qa, 2026-10-15): round-1 fixes confirmed (missed made-up pairs
1.7% on the reviewer's 68,728-pair set, was 6.3%). New findings and fixes:

| Finding | Fix |
|---|---|
| The blog's name check (advisory) still dropped excused headings silently | `blog_ungrounded_claims` names them too (`test_hn_blog_check_reports_excused_headings`) |
| Keeping any short given name at a run edge made new false flags ("Black Art", "Christmas Eve") | start: given name only; end: surname only (`test_hn1_word_that_is_also_a_name_alone_is_not_a_name`); "Max Effort" pinned as a known false flag |
| "Amy" cited as a strong example; it is in Webster's | examples are "Sarah", "Jennifer"; "Amy Post" listed as residual |
| README said the gate blocker covers the blog; "100" names (98); LEARNINGS "35" (36); "non-name phrases" included "Nick Today"; old-code numbers depended on run order | corrected; measurement made order-independent |
| Residual wider than documented ("Hope", "Summer") | residual widened |
| Weekday and most month names read as not English ("Friday Session Highlights" flagged) | they count as ordinary words (`test_hn2_weekday_and_month_words_in_headings_are_not_names`) |

## Tests (fail on the old code: 60 of 86; the other 26 guard what must not change)

| Criterion | Test (`tests/test_heading_names_hn.py` unless named) |
|---|---|
| HN.1 the run 9–10 headings pass as heading, bold label, bold line | `test_hn1_generated_headings_not_flagged` |
| HN.1 made-up names in headings and labels still flagged (P7) | `test_hn1_made_up_names_in_headings_still_flagged`, `test_hn1_made_up_name_in_bold_label_still_flagged` |
| HN.1 one name-like ordinary word is not a name | `test_hn1_word_that_is_also_a_name_alone_is_not_a_name` |
| HN.1 prose unchanged | `test_hn1_prose_names_still_checked_strictly` |
| HN.1 residual documented | `test_hn1_known_residual_english_word_name_in_heading` |
| HN.1 word forms, prefixes, surnames a prefix must not explain | `test_hn1_english_word_forms` |
| HN.1 given-name list curated | `test_hn1_given_name_list_excludes_ordinary_words` |
| HN.1 unreadable list stays strict, not cached (P8) | `test_hn1_unreadable_word_list_keeps_the_check_strict` |
| HN.1 excused runs reported (P2) | `test_hn1_excused_runs_are_reported`, `test_hn_gate_passes_generated_headings_and_date`, `test_hn_blog_check_reports_excused_headings` |
| HN.1 known false flag pinned | `test_hn1_known_false_flag_short_given_name_at_start` |
| HN.1 the judge's re-emitted names follow the same rule | `test_hn1_generated_heading_not_sent_to_judge_as_name` |
| HN.1 judge cache key covers the new inputs | `tests/test_judge_disk_cache_h2.py::test_hn_name_check_vocabulary_changes_key`, `::test_hn_name_list_content_changes_key`, `::test_r9a_component_change_changes_key` (11 new cases; all fail without the key change) |
| HN.2 dates skipped; names with a month word still checked (P7) | `test_hn2_written_out_date_is_not_a_name`, `test_hn2_month_word_inside_a_name_still_checked` |
| HN.2 weekday/month words in headings are words | `test_hn2_weekday_and_month_words_in_headings_are_not_names` |
| gate: generated headings and date pass; made-up heading name fails | `test_hn_gate_passes_generated_headings_and_date`, `test_hn_gate_still_fails_made_up_name_in_heading` |

Changed tests (behaviour change, same commit): `tests/test_release_gate.py::test_r6b_label_with_no_source_words_is_flagged`
now asserts a made-up name in a label is flagged and "Role Absorption" is not;
`tests/test_run_fixes_rf.py::test_rfn1_lens_headline_fragment_not_judged` uses a headline
that is still sent to the judge (it has a word that is not English).

Mutation check: 21 hand-made mutants of the round-1 code and 5 of the round-2 changes
(edge rule, weekday words, blog report), run against the HN, R6 and gate tests: all 26
killed (tests were added for mutants that first survived).

## Adjacent issues found, not fixed

- `faithfulness_judge._name_shaped_bold_labels` sends every name-shaped `**Label:**` to the
  judge whatever its words; no run showed the judge flagging one, so it is left as is.
- The abstract's advisory name report (`validation_pipeline`, abstract coverage) grounds
  against the transcript only, without the filename metadata the gate adds.
- Proper adjectives and words newer than the 1934 list ("Freudian", "rehab", "allostatic")
  still read as names in a heading when the talk does not use them; seen only in the
  cross-talk set, never on a real run.
- A current given-name list (US Social Security names, public domain; needs a download)
  would close most of the residual (Aria, Willow, Maverick).
- Month names live in two config lists: `FAITHFULNESS_HEADING_MONTH_WORDS` (judge, no
  "may") and `NAME_CHECK_MONTHS`.

## Built

| ID | Status | Proof |
|---|---|---|
| HN.1 | done | `abstract_validation.looks_like_name`; `tests/test_heading_names_hn.py::test_hn1_*` |
| HN.2 | done | `abstract_validation.find_ungrounded_names` (date span skip); `::test_hn2_*` |
| HN.3 | done | `docs/calibration/2026-10-14_heading_names/results_old_vs_new.txt` |
| end-to-end round | done | run 11 (commit 4d4b6fb, $6.18): 48 of 48 stages passed, gate allowed all three talks, no name flags. Its headings were all grounded, so old and new code agree on it (0 and 0): the fix was not exercised live |
