# Plan: the severity step downgrades NOT QUITE RIGHT flags (NQ0–NQ8) — 2026-10-19

Status: **superseded 2026-10-19, not built.** The user decided that faithfulness flags warn and never block (`docs/plan_warn_only_2026-10-19.md`), so the severity step no longer needs to be accurate enough to block on. Kept for the record.

Builds on `docs/plan_judge_severity_2026-10-19.md` (JS) and its calibration
`docs/calibration_judge_severity_2026-10-19.md` (JS6). Closes, if it passes, the two
"Open — found by the JS6 calibration" items in `TODO.md` (2026-10-19).

## Why

The user's rule (2026-10-18): a run fails only on WRONG content, never on content that
is merely not quite right. The JS severity step is safe: in JS6 no hand-labelled WRONG
claim was downgraded. It does almost nothing: 0 of 12 NOT QUITE RIGHT (NQR) flags in
fresh drafts were downgraded, 3 of 90 in the review set, and 9 of 12 drafts failed both
before and after. 2 of those 9 (Where Roots #2, Jan #2) failed on NQR flags alone.

The JS ship rules tested only safety. `LEARNINGS.md` ("The severity step passed every
ship test and changed no draft outcome") records the rule this plan follows: a change
that relaxes a gate needs a pass rule for the intended effect as well as for safety.

## What the JS6 votes show

From `docs/calibration/2026-10-19_judge_severity/join.json` and `results.json`:

- **The first vote is almost always WRONG.** 22 of 22 draft flags; 73 of 90 part f runs
  on policy-NQR claims; 69 of 70 gold judgements. A first WRONG vote is final, so these
  claims never get a second vote.
- **The judge reads interpretation as W4.** On the 12 NQR-labelled draft flags the one
  vote was W4 for 5 (D1, D2, D5, D7, D11, all N2 by label), W2 for 4 (D3, D8, D12, D18:
  a loose paraphrase or placement read as a contradiction), W1 for 2 (D6, D21), W3 for 1
  (D9). In part f the 73 WRONG first votes on NQR claims were W4 50, W1 11, W2 6, W3 6.
- **When the first vote was NQR (17 runs in part f), votes 2 and 3 were both WRONG in
  14.** The judge is unsure on these claims, and the policy line "If you are unsure,
  answer WRONG" settles each doubt as WRONG.
- **Every NQR vote's quote passed the evidence check in force at the time.** The
  evidence check is not the cause. (The stricter F4 rule rejects one: gold k5's quotes
  share no word with the claim.)
- **The WRONG labels are mostly facts and people.** Of the 10 WRONG-labelled draft flags,
  6 are W1 (an added age, venue, affiliation or description), 2 are W3 (wrong person) and
  2 are W4 (D4, D22). The NQR labels are mostly interpretation (W4 votes) and wording
  (W2 votes).
- **No margin is known on WRONG claims.** No WRONG-labelled claim has ever drawn an NQR
  vote, so the data does not show how close a WRONG claim is to being downgraded.

## Options

### Option 2: a second vote on a first WRONG vote

Today a claim whose votes are NQR with probability p is downgraded with probability
p²(2−p) (NQR, NQR; or NQR, WRONG, NQR). With a second vote on a first WRONG vote (best 2
of 3, a downgrade still needs two NQR votes with evidence found) it is p²(3−2p).

| p (one vote NQR) | today | option 2 |
|---|---|---|
| 0.19 (part f first votes on NQR claims) | 0.07 | 0.09 |
| 0.5 | 0.38 | 0.50 |
| 0.6 | 0.50 | 0.65 |

Option 2 multiplies the downgrade rate by at most 1.5. That applies to WRONG claims too.
On the draft flags, where p looks close to 0, it would change almost nothing. To reach
half of the NQR flags, a vote must be NQR on an NQR claim about 50–60% of the time, not
19% or less. That is the prompt's job (option 1 or 4). Option 2 is worth testing only
alongside a prompt change, where it lowers the p needed from about 0.6 to 0.5. It costs
one more severity call per flagged artifact, because one call judges all of an
artifact's flags.

### Option 1: drop or reword "If you are unsure, answer WRONG"

- **1a. Drop the line.** The smallest change. With no tie-break the model chooses by
  itself, and how far that moves is unknown.
- **1b. Reword it by kind of doubt.** Keep WRONG as the default where the WRONG labels
  are (a fact or a person), and make NQR the default where the NQR labels are
  (interpretation, emphasis, placement):

  > If you are unsure whether a fact, name, number, place, quote or the person who said
  > something is in the source, answer WRONG. If every fact is in the source and credited
  > to the right person, and you are unsure only whether the claim's framing, emphasis,
  > link or placement goes beyond what the speaker says, answer NOT QUITE RIGHT.

  Risk: the W4 and W2 WRONG claims (D4, D22, C4, E5; review R3, R11, R18, R22, R25, L4;
  gold us6, k3, sa3, sa5, us7, the c1–c6 group; injected W2 and W4). The safety checks
  contain all of these.

### Option 4 (from the data): restate the W4 / N2 line

Most WRONG votes on NQR claims are W4. The judge may not be unsure at all: W4 ("a
conclusion … that the speaker never states") reads as covering any sentence the speaker
did not say. Option 1 cannot fix that. Draft text, with 1b:

> - W4. It gives the speaker a conclusion, position, plan or future event whose content
>   is not in the source, or one that runs against a position the speaker states.
> - N2. It interprets, frames, connects or emphasizes what the speaker says without
>   adding a new fact, including naming the point of a passage, linking two things the
>   speaker discusses, or applying an idea the speaker states to material the speaker
>   discusses, in the writer's own words.

No new examples (the four unrelated-subject examples stay; JS4.b). This is the largest
policy change and the one most likely to downgrade a W4 WRONG claim. It is also the most
likely to meet the effect rule.

### Option 3: the summary prompt adds no outside facts

This is a separate change. It lowers the number of WRONG claims in drafts and does not
touch the severity step. In JS6, 6 of the 9 failing drafts contain an outside fact: an
age ("late thirties"), "late grandmother", "Kansas City Family Center" for KCFC (twice,
once as the speaker's affiliation), a first name. JS5 forbids an added role in the
opening only. Draft text, added to **Constraints** (so it covers the whole summary):

> *   Write names, titles, places and abbreviations as the transcript or recording title
>     gives them; do not expand an abbreviation. Describe a person (the speaker, a
>     client, a family member) only with facts the transcript states: add no name, age,
>     family status, place, occupation or affiliation from other knowledge or inference.

### Fitting risk

Options 1b and 4 were written after reading D1–D22 and their votes, so the replayed
draft flags are no longer held out. The 2026-10-11 framing rule scored 1.00 on gold and
failed more good writing on real files. So:

- The ship decision also needs a **new held-out set** (d-fresh): drafts of talks used
  in neither the review nor JS6, labelled blind. It is used once. If it fails, stop:
  do not tune the prompt against it.
- New policy text must share no 5-word run with any measured claim (the review's 43,
  the 29 hand-labelled JS6 flags) and no example may be fitted to them (JS4.b tests,
  extended).

## Items, criteria and tests

New test file `tests/test_severity_downgrade_nq.py` unless a row names another file.
All tests are offline with a mocked client, as in `tests/test_judge_severity_js.py`.

| ID | Criterion | Test |
|---|---|---|
| NQ0 | Decisions a–e below are answered and recorded in this plan. | Human (this document) |
| NQ1.a | New `config.FAITHFULNESS_SEVERITY_MODE` value `"both3"`: a first WRONG vote also gets a second vote; two WRONG votes keep the claim WRONG; a split goes to a third vote. A downgrade still needs two NQR votes whose evidence is found. | `test_nq1a_first_wrong_vote_gets_a_second`, `test_nq1a_two_wrong_votes_keep_wrong`, `test_nq1a_split_goes_to_third_vote` |
| NQ1.b | Adversarial (P7): in `"both3"`, votes WRONG, NQR with evidence not found, NQR with evidence found keep the claim WRONG (only one NQR vote counts). | `test_nq1b_unfound_evidence_counts_as_wrong_in_both3` |
| NQ1.c | Fails closed in `"both3"`: an API or parse error in any round keeps that round's claims WRONG and `undecided` (JS1.d, F1). | `test_nq1c_error_in_second_vote_keeps_wrong` |
| NQ1.d | `"majority3"` and `"off"` behave exactly as before; an unknown mode raises. | existing `tests/test_judge_severity_js.py::test_js1b_*`, `test_js1e_off_is_todays_behaviour` pass unchanged |
| NQ2.a | Screening variants are prompt files under `docs/calibration/<date>_severity_downgrade/variants/` (V1 = 1a, V3 = 1b, V4 = 1b + option 4). The chosen text becomes `prompts/Faithfulness Severity Prompt v2.md`; `config.PROMPT_FAITHFULNESS_SEVERITY_FILENAME` points to it; v2 is listed in `PROMPT_REGISTRY.md`. | `test_nq2a_v2_prompt_loaded_and_registered` |
| NQ2.b | Rollback: v1 stays in `prompts/` unchanged (sha `38d9fcf8c7bd`), so v1 + `"majority3"` gives the JS behaviour exactly. `test_js4a_prompt_file_loaded_and_registered`, which checks the v1 phrase "If you are unsure, answer WRONG.", is changed to read v1 by name. | `test_nq2b_v1_prompt_unchanged_for_rollback`, updated `test_js4a_*` |
| NQ2.c | Fitting (adversarial): each variant file and v2 shares no 5-word run with the review's 43 claims or the 29 claims in `hand_labels.json`; v2's examples pass the JS4.b overlap checks against those claims as well as the gold and prose_real sets. | `test_nq2c_no_five_word_run_with_measured_claims`, `test_nq2c_examples_not_fitted` (extends `test_js4b_*`) |
| NQ3.a | `config.JUDGE_LOGIC_VERSION` is bumped. A change of severity prompt or mode re-keys the gate cache (JS3.a already hashes both); a PASS cached under the old version is not served (P8). | `test_nq3a_logic_version_bumped`, `test_nq3a_both3_mode_rekeys_cache`; existing `test_js3b_old_cached_pass_not_served` passes |
| NQ4.a | Measurement script `docs/calibration/<date>_severity_downgrade/measure_downgrade.py`. Part r (replay): every claim in `hand_labels.json` (D1–D22, C1–C4, E5–E7) goes through `classify_severity` with the context the gate sent (`results.json`) and the source the gate builds (`_load_source_transcript` + `with_recording_metadata`), 3 runs. Parts b, c, d and f reuse `judge_recalibration.py --severity` and `measure_severity.py` (imported by path). Options: `--prompt-file`, `--mode`, `--talks`, `--holt-source`. Every setting is in-process; no production file is written. | `test_nq4a_replay_joins_every_hand_label` (29 of 29 found, each with context and source; a claim not found is reported by id, never dropped, P2) |
| NQ4.b | The replay refuses a source whose transcript sha differs from the one recorded in `results.json` (P6/P8), and records the sha of each source text it sends. If the Holt source for part f (`/private/tmp/.../scratchpad/src/holt.md`, another session's scratch) is gone, part f runs on the other 3 sources and the report says so. | `test_nq4b_replay_refuses_changed_transcript` |
| NQ4.c | The pass rules below (S3, S4, E1) are computed by one function from the recorded votes. Adversarial: a downgraded borderline WRONG label counts as a safety failure; a flag downgraded in 1 of 3 runs does not count toward E1. | `test_nq4c_pass_rules_scored`, `test_nq4c_borderline_wrong_downgrade_fails_safety` |
| NQ5.a | Summary prompt (`prompts/Summary Generation Prompt v1.md`, Constraints): the option 3 rule (no expanded abbreviation; no name, age, family status, place, occupation or affiliation the transcript does not state). | `test_nq5a_summary_prompt_forbids_outside_facts`, `test_nq5a_rule_is_in_the_prompt_sent` (as `test_js5a_opening_instruction_is_in_the_prompt_sent`) |
| NQ5.b | The rule shares no 5-word run with a JS6 hand-labelled claim. | `test_nq5b_rule_not_fitted_to_js6_flags` |
| NQ6 | Live calibration of the severity change, not in CI: below. Report `docs/calibration_severity_downgrade_<date>.md`, results under `docs/calibration/<date>_severity_downgrade/`. | Script + report |
| NQ7 | Live calibration of option 3, not in CI: below. Same report. | Script + report |
| NQ8 | Documents updated in the same commit as the code (below). | Review of the diff |

### NQ0 — decisions

- **NQ0.a Variants to screen.** Recommended: all of V1 (drop the line), V2 (option 2
  alone, prompt v1), V3 (1b), V4 (1b + option 4), and V5 (the best safe prompt variant +
  `"both3"`) only if that prompt is safe but short of E1. Approve or edit the 1b and
  option 4 texts above.
- **NQ0.b Pass rules** (below). Recommended as written: any WRONG-labelled downgrade,
  borderline or not, stops the ship. If the only downgraded WRONG claims are borderline,
  stop and report both readings for your decision.
- **NQ0.c Option 3.** Approve the summary prompt text. Recommended: the summary prompt
  only, since only summaries were measured. The abstract, overview and blog prompts are
  listed as adjacent, not changed.
- **NQ0.d Held-out set (d-fresh).** The only KCFC talks used in neither the review nor
  JS6 are 2021 Webcast Oct, 2021 Webinar Nov and 2021 Webinar Dec. Each has a formatted
  transcript and `topics.md` (checked 2026-10-19; they are on `/Volumes/CrucialX9`). 4
  drafts each = 12. "2021 Webcast Sep Part 1 - KCFC" is excluded as a likely copy of
  the review's Sep talk.
- **NQ0.e Selection rule.** Recommended: the smallest change that passes, in the order
  V1, V2, V3, V4, V5. The alternative is the variant with the largest effect that passes.

### NQ6 — live calibration of the severity change

Model and settings as in production (judge `claude-sonnet-5-5`, default effort,
`FAITHFULNESS_CONFIRM_MODE` majority of 3). Labels as in JS6 (`hand_labels.json`, policy
JS0.a): a label stays as written even if the policy text changes, because the labels
describe what the user calls WRONG.

**Step 1, screening (parts r and f, 3 runs each, per variant).** A variant is safe if
S3 and S4 hold. Choose by NQ0.e among safe variants that meet E1. If none does: stop,
report, and change nothing. The step stays as shipped.

**Step 2, ship checks for the chosen variant, with v2 and the config in place.** Parts
r and f from step 1 count if the prompt sha and code have not changed since; otherwise
they run again.

| Part | What | Pass rule |
|---|---|---|
| b. Gold severity | `judge_recalibration.py --repeats 3 --severity` | **S1.** No gold case labelled WRONG (JS0.c) is downgraded in any run. Report k5, k6. Detection metrics: within the JS6 range (recall 0.86–0.96, precision 0.96–1.00), since the finding step does not change. |
| c. Injected | `measure_severity.py --parts c` (the 4 injected claims W1–W4 in Why Families), 3 runs | **S2.** Each kept WRONG in 3 of 3 runs, and each run FAILs. |
| r. Replay of the JS6 flags | Part r, 3 runs | **S3.** 0 of the 12 WRONG-labelled flags (D4, D10, D13, D14, D15, D16, D17, D19, D20, D22, C4, E5) downgraded in any run. **E1.** At least 6 of the 12 NQR-labelled draft flags (D1, D2, D3, D5, D6, D7, D8, D9, D11, D12, D18, D21) downgraded in at least 2 of 3 runs. Report C1–C3, E6, E7, and per draft how many runs pass (JS6: Where Roots #2 and Jan #2 fail on NQR flags only). |
| f. Review set | `measure_severity.py --parts f`, 3 runs | **S4.** 0 of the 13 policy-WRONG claims downgraded in any run. Report NQR downgraded of 90 (JS6: 3). |
| d-fresh. Held-out drafts | 12 summary first drafts (NQ0.d), with the option 3 prompt if approved; one judge run per draft, as production does. I label every confirmed flag from a blind list (no severity decision shown) before reading any outcome, with source quotes that a script checks. | **S5.** No flag labelled WRONG is downgraded. **E2.** At least half of the NQR-labelled flags downgraded; this rule applies only if there are at least 6 such flags, otherwise it is reported. Report drafts failing old (any confirmed flag) vs new (a WRONG flag), and outside-fact flags. |

If any of S1–S5 or E2 fails: stop, report, don't ship. Part e (gate regression) is not
run: a looser step can only turn a FAIL into a WARN, so it cannot add a FAIL.

### NQ7 — live calibration of option 3

12 summary first drafts of the 6 JS6 talks (Where Roots, Jan, Feb, Mar, April, Jun; 2
each) with the new summary prompt. This uses the same talks so the 12 JS6 drafts are
the baseline.

- **Count, both sets by the same method.** A draft has an outside fact when it contains
  an expanded abbreviation, or a person's name, age, family status, place, occupation or
  affiliation that neither the transcript nor the recording title states. Found from
  (1) every confirmed flag, checked by hand with a source search, and (2) a script scan
  of each draft: expansions of the title's all-caps tokens, age phrases ("late
  thirties", "N-year-old"), and the names `release_gate.check_entity_grounding` reports.
  The baseline is that count on the 12 JS6 drafts (stored in `results.json`). JS6's
  flag-only count was 6 of 12.
- **O1.** Drafts with an outside fact are at most half the baseline count.
- **O2 (report).** Every opening still names the speaker as the transcript or title
  does. Drafts failing, old and new rule.

If O1 fails, the prompt change is not shipped. The severity change does not depend on
it.

### Cost

From `logs/token_usage.csv`: a severity call with about 10k cached source tokens and
about 600 output tokens costs $0.007–0.013. In JS6, parts c, d and f cost $2.48. Part d
made 212 of the 251 calls, so 12 drafts with judging cost about $2.0. Gold runs cost
$1.08.

| Item | Estimate |
|---|---|
| Screening, per variant: part r (8 sources × 3 runs × 1–3 rounds) + part f (4 × 3 × 1–3) | $0.6–1.2 |
| Screening, V1–V4 (+ V5 if needed) | $3–6 |
| b. Gold, 3 runs | $1.1 |
| c. Injected, 3 runs | $0.3 |
| d-fresh, 12 drafts | $2.0 |
| NQ7, 12 drafts | $2.0 |
| **Total** | **about $8.5–11.5** (JS6: $4.50) |

To cut cost: screen V3 and V4 only (−$1.5–2), or skip NQ7 if NQ0.c is no (−$2). In
production the change adds at most two severity calls per flagged artifact per run
(about $0.02).

### NQ8 — documents

CHANGELOG.md; TODO.md (the 2026-10-19 "Open — found by the JS6 calibration" items close
or update); `PROMPT_REGISTRY.md` (v2; v1 kept for rollback); `ARCHITECTURE_DESIGN.md`
and `PROJECT_STATUS.md` where they describe the severity step; the status line in
`docs/plan_judge_severity_2026-10-19.md` ("Loosening it is a separate decision") points
here; `LEARNINGS.md` if the calibration teaches something new; this plan's status; the
calibration report; the memory note on the judge (m2) with the new version, prompt and
mode.

## Order

1. NQ0: your decisions.
2. NQ5 tests (they fail), then the summary prompt. Full suite. NQ7 can run from here.
3. NQ1 tests, then `"both3"` in `classify_severity`.
4. NQ2.c tests on the variant files, then the variant files.
5. NQ4 tests, then `measure_downgrade.py`.
6. NQ6 step 1 (screening). Stop if no variant is safe and meets E1.
7. Promote the chosen variant: v2 prompt, config, registry, NQ2.a/b, NQ3. Full suite.
8. NQ6 step 2: b, c, d-fresh (blind labels before outcomes), score. Stop if a rule
   fails.
9. NQ8 documents; learning-qa review of the diff; fix findings; commit to main. No push
   until you say so.

## Not code-testable

- Whether the judge classifies real flags correctly. NQ6 measures it with hand labels.
  A mocked model would test nothing.
- Whether the 1b and option 4 texts say what you mean by WRONG. That is NQ0.a.
- The hand labels are one person's, as in JS6. Borderline labels are reported both ways;
  the safety rules count them as labelled.
- The sample is small. E1 has 12 flags, so one flag is 8 points, and the d-fresh drafts
  come from 3 talks.

## Risks

- **A WRONG claim is downgraded.** Guarded by two NQR votes with found evidence (kept in
  every variant), S1–S5 across about 150 judgements of WRONG-labelled claims, and the
  rollback (v1 prompt + `"majority3"`). The evidence check cannot catch an added fact
  when the judge quotes nearby source words, so W1 safety rests on the judge. S3 has 6
  W1 draft flags, S4 has 4 credential claims, and S1 has 7 gold absent-fact cases.
- **Fitting the policy to the replayed flags.** d-fresh is held out and used once;
  NQ2.c tests the text for overlap.
- **Choosing among variants on the same data** favours the variant that fits that data
  by chance. The selection rule takes the smallest change that passes, and d-fresh
  decides.
- **More warnings to read.** Each WARN lists the claim, type and evidence (JS2.b).

## Adjacent issues found, not fixed

- The abstract, overview and blog prompts have no outside-fact rule (if NQ0.c keeps
  option 3 to the summary). Not measured.
- `measure_severity.py` reads the Holt source for part f from another session's
  `/private/tmp` scratch folder (`SCRATCH_SRC`). That folder can be deleted at any time.
  NQ4 takes the path as an argument and checks its sha. The script itself is not changed.
- Already in `TODO.md`: the theme-grounding and key-terms judges have no severity step;
  gold claims have no preceding sentence; the summary prompt asks to "Weave in the
  Interpretive Themes", which the judge then flags.
