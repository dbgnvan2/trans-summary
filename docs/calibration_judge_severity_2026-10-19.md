# Judge severity step, live calibration (JS6) — 2026-10-19

Plan: `docs/plan_judge_severity_2026-10-19.md` (JS6). The severity step runs on each
faithfulness flag that confirmation keeps, and decides WRONG (fails) or NOT QUITE RIGHT
(passes with a warning). This report measures it before it ships.

## Settings

- Judge `claude-sonnet-5-5`, default effort, `FAITHFULNESS_CONFIRM_MODE` majority of 3,
  `FAITHFULNESS_SEVERITY_MODE = "majority3"`, `JUDGE_LOGIC_VERSION = "2026-10-19"`.
- Severity prompt `prompts/Faithfulness Severity Prompt v1.md`, sha `38d9fcf8c7bd`.
- Summary drafts (part d): summary stage model `claude-sonnet-4-6`, summary prompt sha
  `9a123330129e` (with the JS5 change), one attempt per draft
  (`GENERATION_FAITHFULNESS_ATTEMPTS = 1`).
- Old = severity off (any confirmed flag fails); new = severity on (only a WRONG flag
  fails). Both are read from the same judge run (plan deviation "one judge run per draft").
- Scripts and data: `docs/calibration/2026-10-19_judge_severity/`
  (`measure_severity.py`, `results.json`, `results.log`, `gold_severity.json`/`.log`,
  `blind_flags.md`, `hand_labels.json`, `join_labels.py` → `join.json`,
  `rescore_evidence.py` → `rescore_evidence.json`).

## Result

| Part | Pass rule | Result | Pass |
|---|---|---|---|
| a. Gold detection | recall 0.86–0.96, precision 0.96–1.00 per run | recall 0.92, 0.96, 0.92; precision 1.00 ×3 | yes |
| b. Gold severity | no gold WRONG case downgraded | none downgraded in 3 runs (70 flagged claims judged) | yes |
| c. Injected | each of 4 injected WRONG claims FAILs 3 of 3 | 12 of 12 judged WRONG; every run FAILs | yes |
| d. Held-out drafts | no claim I label WRONG is downgraded | 0 of 10 WRONG-labelled flags downgraded | yes |
| e. Regression | no new FAIL in 10 gate checks | old FAIL 3, new FAIL 2 + WARN 1 | yes |
| f. Development set | report only | WRONG 39 of 39 runs agree; NOT QUITE RIGHT 3 of 90 | — |

b, c and d pass, so the step ships as planned (`majority3`). It is safe on every WRONG
claim measured. It downgrades few NOT QUITE RIGHT flags, so it changes few outcomes
(see "What the step does not do").

## a. Gold detection

`judge_recalibration.py --repeats 3 --severity` (`gold_severity.log`). Misses: k5 in
run 1, k6 in all runs, k4 in run 3. Every run passes its bars. The command exits 1
because it exits 1 on any flip across runs, and there were 2 (k4, k5 found in 2 of 3
runs). The finding step did not change in this plan. Recall per run is within the
measured range, so the flips are judge noise, not a bug.

## b. Gold severity

Flagged gold claims judged per run: 23, 24, 23. WRONG-labelled gold claims downgraded:
none. NOT QUITE RIGHT gold claims (k5, k6; labels from JS0.c) are only judged when the
finding step flags them: k5 was downgraded in run 2 (1 of 1) and kept WRONG in run 3
(0 of 1); k6 was never flagged.

## c. Injected claims

Four WRONG claims (an invented study, a swapped relationship, a participant's story
credited to the presenter, an invented future plan) inserted into the real Why Families
summary: kept WRONG in each of 3 runs, and each run FAILs. The same summary has 4 real
flags (C1–C4 below), all judged WRONG in every run.

## d. Held-out first drafts

12 drafts, 2 each from Where Roots and the KCFC 2021 talks Jan, Feb, Mar, April and Jun.
22 confirmed flags. I labelled each flag from `blind_flags.md` before reading any
outcome (`hand_labels.json`: each label has its source quotes, and a script checked
that every quote is in the source). Labels follow the approved policy (JS0.a). For
example, a name, age or venue that the source does not contain is W1 even when it is
true elsewhere. "Borderline" means a careful reader could put the claim in the other
class; the note says which way.

| Flag | Claim (start) | My label | Judged | Downgraded |
|---|---|---|---|---|
| D1 | Kerr draws an explicit parallel: Bowen theory may currently occupy the… | NQR N2 (borderline) | 1 | 0 |
| D2 | Resistance signals paradigm-level threat, not error. | NQR N2 (borderline) | 1 | 0 |
| D3 | Kerr extends the logic: family regression under stress follows the sam… | NQR N2 | 1 | 0 |
| D4 | Kent Berridge's research at Michigan then establishes that wanting (do… | WRONG W4 | 1 | 0 |
| D5 | Kerr's point is structural: correct ideas can face organized instituti… | NQR N2 (borderline) | 1 | 0 |
| D6 | Kerr draws an explicit parallel to Bowen's individuality and togethern… | NQR N2 | 1 | 0 |
| D7 | Kerr notes that advertising targets wanting rather than liking, and th… | NQR N2 (borderline) | 1 | 0 |
| D8 | Moving the electrode millimeters in any direction eliminated the effec… | NQR N1 | 1 | 0 |
| D9 | He frames this as an open question for Bowen theorists, suggesting tha… | NQR N3 | 1 | 0 |
| D10 | Kerr also presents the systems biology work of Italian philosopher of … | WRONG W1 (borderline) | 1 | 0 |
| D11 | Bertoloso's central claim—that genes are "only like the keys on a pian… | NQR N2 | 1 | 0 |
| D12 | An email update confirms the daughter is enrolled, working at a bar, m… | NQR N3 (borderline) | 1 | 0 |
| D13 | Kate Beam and Carolyn Jacobs explore whether the mother must ultimatel… | WRONG W3 (borderline) | 1 | 0 |
| D14 | The speaker, presenting at a Kansas City Family Center webinar in Marc… | WRONG W1 (borderline) | 1 | 0 |
| D15 | He suggests that people who have not been heavily trained in the indiv… | WRONG W3 | 1 | 0 |
| D16, D19 | The client is a Vermont-based counseling psychologist in her late thir… (same sentence in both April drafts) | WRONG W1 | 2 | 0 |
| D17 | She lives with her partner, Sam, in her late grandmother's house. | WRONG W1 (borderline) | 1 | 0 |
| D18 | Her self-summary is precise: "I'm anxious and he's anxious too, and hi… | NQR N1 | 1 | 0 |
| D20 | In a June 2021 webcast, a speaker associated with the Kansas City Fami… | WRONG W1 (borderline) | 1 | 0 |
| D21 | Philosopher Karl Popper argued that developmental processes have goal-… | NQR N1 (borderline) | 1 | 0 |
| D22 | The speaker draws explicit parallels throughout: the identified patien… | WRONG W4 (borderline) | 1 | 0 |

- **WRONG-labelled flags downgraded: 0 of 10** (6 of the 10 are borderline). Ship
  criterion met.
- **NOT QUITE RIGHT flags downgraded: 0 of 12.** The judge kept every flag WRONG.
- **Drafts failing: old 9 of 12, new 9 of 12.** By my labels, 7 of the 9 contain a WRONG
  claim (Where Roots #1, Jan #1, Feb #1, Mar #2, April #1 and #2, Jun #2). 2 contain only
  NOT QUITE RIGHT flags (Where Roots #2, Jan #2): they should pass with a warning and
  still fail. If the borderline WRONG labels are read as NOT QUITE RIGHT, 4 drafts
  contain a WRONG claim.
- **Credential flags: none states the speaker's training or title.** Two flags expand
  the catalogue's "KCFC" into "Kansas City Family Center", which the source does not
  contain. D20 uses it as the speaker's affiliation ("a speaker associated with"). D14
  uses it as the event ("presenting at a Kansas City Family Center webinar"). The JS5
  prompt forbids a role from other knowledge; D20 breaks that, and the prompt says
  nothing about the event.

## e. Regression

10 gate checks of the current Kerr 2026-09-13 project files (hashes in `results.json`;
the CF.6 files were overwritten, see the plan's deviations). Old: FAIL in checks 2, 4
and 10. New: FAIL in 2 and 4, WARN in 10. No new FAIL.

- Checks 2 and 4 flag E5, "Michael Kerr … presents a webinar on Bowen theory…": the
  source is a conversation with an interviewer and listeners. My label: WRONG W2
  (borderline; could be N3, the talk described loosely). Judged WRONG both times.
- Check 10 flags E6 ("Kerr begins by contrasting Bowen's systems thinking with Freudian
  thinking", said at 00:01:23 after the opening about Billy) and E7 ("He ends with
  societal regression", the last main topic before the takeaway and thanks). My labels:
  NOT QUITE RIGHT N3. Both downgraded, so the check WARNs.

The 2026-10-11 CF.6 run had 0 FAILs in 10 checks on the earlier files. Here 3 of 10
fail before the step, on different files, so the counts are not comparable.

## f. Development set

The review's 43 claims, 3 runs each, against the policy labels (review labels with N4
counted WRONG, JS0.b): 13 WRONG claims, 30 NOT QUITE RIGHT.

- Policy WRONG judged WRONG: 39 of 39 runs.
- Policy NOT QUITE RIGHT judged NOT QUITE RIGHT: 3 of 90 runs (L1 in runs 2 and 3, L5
  in run 2).

Not a ship criterion: these claims shaped the policy.

## Other flags in the blind list (parts c and e)

| Flag | Claim (start) | My label | Judged | Downgraded |
|---|---|---|---|---|
| C1 | His mother, convinced Billy was fragile, had protected him intensely, … | NQR N2 (borderline) | 3 | 0 |
| C2 | This process is not malicious; it feels like love and protection to th… | NQR N2 | 3 | 0 |
| C3 | This connection operates at every scale: the individual body, the nucl… | NQR N2 | 2 | 0 |
| C4 | When Kerr considered leaving psychiatry to return home and care for hi… | WRONG W2 | 3 | 0 |
| E5 | Michael Kerr, a long-time student and successor of Murray Bowen, prese… | WRONG W2 (borderline) | 2 | 0 |
| E6 | Kerr begins by contrasting Bowen's systems thinking with Freudian thin… | NQR N3 | 1 | 1 |
| E7 | He ends with societal regression. | NQR N3 | 1 | 1 |

All 29 flags: WRONG-labelled downgraded 0 of 12; NOT QUITE RIGHT downgraded 2 of 17
(2 of 22 judgements).

## What the step does not do

The step blocks every WRONG claim measured, but it downgrades few NOT QUITE RIGHT
flags. The judge's own votes cause this, not the evidence check (`join.json`, vote
records in `results.json`):

- First severity vote WRONG: 22 of 22 draft flags, 23 of 23 part c judgements, 73 of 90
  policy-NOT-QUITE-RIGHT runs in part f, 69 of 70 gold judgements.
- When the first vote was NOT QUITE RIGHT (17 part f runs on NOT QUITE RIGHT claims),
  votes 2 and 3 were both WRONG in 14.
- Every NOT QUITE RIGHT vote's quote passed the evidence check.

The prompt says "If you are unsure, answer WRONG", and a first WRONG vote is final. The
judge treats most interpretive or loosely placed claims as WRONG (W4, W1, W2 on D8's
"any direction" for "one way or the other"). So the user's rule (fail only on WRONG
content) holds for WRONG claims, and the false failures on NOT QUITE RIGHT claims are
mostly still there: 2 of the 12 drafts fail on NOT QUITE RIGHT flags alone.

The drafts also show that most of the remaining failures are WRONG under the approved
policy. The summary stage still adds facts from outside the transcript (an age, "late",
a venue name, a first name) and credits remarks to the wrong person.

Loosening the step is a policy change with its own calibration, not part of this plan.
Options: drop "If you are unsure, answer WRONG"; let a first WRONG vote be checked by a
second, as a NOT QUITE RIGHT vote is; or tell the summary prompt not to expand
abbreviations or add ages or venues. Each needs the b, c and d checks again.

## Evidence rule re-score (learning-qa F4)

The JS6 runs started before the evidence check was made stricter (every "..."-part of
2+ words must be in the source, and the quote must share a significant word with the
claim). `rescore_evidence.py` re-checks every recorded vote under the new rule. One
outcome changes: gold run 2, k5 ("The practical stakes are significant."), whose two
NOT QUITE RIGHT quotes share no significant word with the claim, becomes WRONG. k5's
gold label is NOT QUITE RIGHT, so the new rule is slightly stricter. No pass rule
changes: b counts only downgraded WRONG cases. Parts c, d, e and f: no change.

## Cost

From `logs/token_usage.csv` (as recorded by the scripts): gold runs (a, b) $1.0832;
parts c, d and f $2.4801; part e $0.9339. Total $4.50 (plan estimate $5–8).

## Deviations

As listed in the plan ("Deviations while building"): a and b in one run; one judge run
per draft; Jun instead of Why Families for drafts; current files for part e. Also: the
measurement process loaded the code before the F1 and F4 fixes. F1 changes only what
the gate caches after a failed vote, and no vote failed here. F4 is re-scored above.
