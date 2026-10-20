# WRONG-rule test (2026-10-19)

Tests a proposed rule for which flagged claims block a release, before any code in the
pipeline changes. Written on Mac mini1 as a follow-up to
`docs/review_independent_2026-10-19.md` (section B.0).

## The rule under test

Dave's bar (2026-10-19): invented quotes, reversed story points and invented facts are
WRONG and must be blocked or removed. A claim that is close in meaning but not word for
word is a warning.

A flagged claim is WRONG when any of these is true; otherwise it is a warning.

| Check | What it catches | How | Cost |
|---|---|---|---|
| F | Invented specific: a number, date, month, weekday or capitalised name in the claim that appears nowhere in the transcript or its file name | `specifics_check.py` | none |
| Q | Invented quote: a quoted passage of 4+ words that fails the gate's own verbatim matcher (`validation_pipeline.quote_is_verbatim_for_gate`) | `specifics_check.py` | none |
| J | Reversed point (W2), wrong person (W3), invented event or plan (W4) | `wrong_check.py`: 3 votes of `Wrong Check Prompt (test v1).md`; WRONG on 2 of 3. A W2/W3 vote counts only when its quoted evidence is found in the source (`faithfulness_judge._evidence_in_source`) | API |

The narrow prompt does not judge names, numbers or dates (F does), and its default when
unsure is "not quite right". The current severity prompt's default is WRONG.

## Baseline

The current severity step's stored verdicts on the same claims, read from
`../2026-10-19_judge_severity/results.json` (no API call).

## Results so far (Mac mini1, no API key; 32 of the 73 labelled claims)

Mini1 has the transcripts for 32 claims (10 WRONG, 22 not quite right). The other 41
(Holt 20, 2021 Webcast Sep Part 1 8, KCFC 2021 webinars 13) need davemini2.

| | WRONG caught | Not-quite-right blocked |
|---|---|---|
| Current severity step (stored) | 9 of 9 | 19 of 19 |
| F + Q only (free part of the new rule) | 2 of 10 | 0 of 22 |
| F + Q + J | not run yet | not run yet |

- The current severity step marks every one of these flagged claims WRONG, so on this set
  it does not separate WRONG from "not quite right" at all. (C1–C4 have no stored verdict.)
- F caught INJ-W1 ("1998 Georgetown study of 400 families") and INJ-W4 ("third book").
  It made no false hits on the 22 not-quite-right claims.
- The other 8 WRONG claims (C4, D4, INJ-W2, INJ-W3, R25, R34, R35, R37) are reversals,
  wrong-person or invented-event errors. Only J can catch them, so the rule depends on
  the paid run.
- Q flagged nothing: none of these 32 claims carries an invented 4+ word quote.

## How to run (davemini2, which has the API key and all transcripts)

```
cd docs/calibration/2026-10-19_wrong_rule
python build_cases.py "/Volumes/CrucialX9/1 MY DISK/KCFC ALL/projects" /Users/davemini2/projects
python specifics_check.py
python wrong_check.py --dry-run     # check: 73 claims, call count, token estimate
python wrong_check.py               # the paid run, about 3 calls per transcript
```

Add any other folder from `measure_severity.py` `DEV_SOURCES` to the `build_cases.py`
line if claims are still reported missing. Results go to `wrong_check_results.json`.

## What would count as a pass

Decide before reading the paid results:
- J + F + Q catches every non-borderline WRONG claim, and
- blocks no more than 2 of the not-quite-right claims (borderline ones reported apart).

If it passes, the next step is a spec for putting F, Q and the narrow prompt into
`faithfulness_judge.classify_severity` and making faithfulness blocking again for WRONG only.

## Files

- `build_cases.py` → `cases.json` (claims, hand labels, transcript paths; paths are per machine)
- `specifics_check.py` → `specifics_results.json`
- `Wrong Check Prompt (test v1).md` — the narrow prompt (test only, not used by the pipeline)
- `wrong_check.py` → `wrong_check_results.json` (the committed copy is from the Mini1 dry run: J empty)
