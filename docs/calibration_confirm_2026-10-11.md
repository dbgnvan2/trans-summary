# Calibration — confirm a faithfulness flag before it fails a run (CF.5, CF.6, 2026-10-11)

Plan: `docs/plan_judge_confirm_flags_2026-10-11.md` (CD1 majority of 3, CD2 faithfulness
judge only, CD3 current prompt). Model claude-sonnet-5-5, default effort, prompt sha
96e5ab257296 (unchanged), `FAITHFULNESS_CONFIRM_MODE = "majority3"`.

Two live rounds: r1 = first build (71e6bd5); r2 = after the learning-qa fixes (c98c6ce:
each re-sent flag carries the claim before it, full vote record). r2 is the code that
ships; its calibration file records cache/logic version 47669a16bca5bfd0 = HEAD.

## CF.6 — Kerr 2026-09-13 project, 10 fresh checks each

The files that passed the real run on 2026-10-10; `release_gate.check_faithfulness`
(transcript + metadata), fresh cache per check.

| | Failed checks | Flags overturned | Cost (10 checks) | File |
|---|---|---|---|---|
| Before (no confirmation) | **5 of 10** | — | $0.85 | `2026-10-11_framing_tf5_topicterm/k10_old.json` |
| r1 | **0 of 10** | 7 (in 5 runs) | $0.90 | `2026-10-11_confirm/cf6_r1.json` |
| r2 | **0 of 10** | 5 (in 5 runs) | $0.88 | `2026-10-11_confirm/cf6_r2.json` |

Overturned sentences, all supported by the transcript: "Michael Kerr calls a
multigenerational perspective the best entry point." (the interviewer asks for the best
entry point; Kerr: "extremely important"), "…societal regression, a concept Bowen
introduced in 1975." (interviewer: "in 1975 he said … He called it societal regression"),
and once "Years later he stood at Billy's grave and said, 'Billy, thank you for allowing
me to grow up.'" (verbatim in the transcript).

## CF.5 — gold set (43 cases), 3 runs each

| | Recall | Precision | Gold flags overturned | Misses (all pass-1 accepts) | Cost | File |
|---|---|---|---|---|---|---|
| Before (2026-10-10) | 0.91–0.95 | 1.00 | — | k4, k6 | — | `2026-10-10_sonnet55_default.json` |
| r1 | 0.91 ×3 | 1.00 ×3 | 0 | k4, k6 | $0.71 | `2026-10-11_sonnet55_confirm_r1.json` |
| r2 | **0.86**, 0.91, 0.91 | 1.00 ×3 | 0 | k4, k6; k5 in run 1 | $0.74 | `2026-10-11_sonnet55_confirm.json` |

- Real abstracts 3/3 every run (roots_bowen PASS; where_roots FAIL naming Malorni; dave_g
  FAIL naming nubbin); injected fabrication caught every run; themes 1.00/1.00 (one theme
  flip in each round, from the theme judge, which this change does not touch).
- **r2 run 1 is below the 0.90 bar.** The cause is pass 1: k5 ("The practical stakes are
  significant.") was accepted ("Vague framing statement… reasonable abstraction").
  Confirmation only re-judges flagged claims, so it never saw k5; in runs 2 and 3 k5's
  flag was confirmed 2 of 2. Across 6 runs no gold flag was overturned, and every flag
  that stood was rejected 2 of 2 (no third pass needed). The judge's first-pass variance on
  the borderline policy cases k4/k5/k6 exists with or without this change.

## Effect

Confirmation removed every false failure of the Kerr project in 20 checks and lost no
true flag on the gold set in 6 runs, for about 4–5% more cost per check. It cannot raise
recall: first-pass misses (k4, k5, k6) are unchanged.
