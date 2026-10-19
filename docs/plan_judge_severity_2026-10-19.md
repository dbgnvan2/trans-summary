# Plan: faithfulness flags fail only on WRONG content (JS0–JS7) — 2026-10-19

Status: **built 2026-10-19; JS6 passed, armed (`majority3`).** The user approved the
plan with every JS0 recommendation (see "JS0 — decisions", answers recorded there).
JS6 (`docs/calibration_judge_severity_2026-10-19.md`): b, c and d pass, no WRONG claim
was downgraded in any part. The step downgrades few NOT QUITE RIGHT flags (0 of 12 in
the held-out drafts; drafts failing 9 of 12 before and after), because the judge's own
votes are mostly WRONG. Loosening it is a separate decision (see the report).

## Why

The user's rule (2026-10-18): "The only fail is if something WRONG vs. not quite right."
The review `docs/judge_flag_review_2026-10-18.md` classified 43 flags the judge raised on
2026-10-18. **9 were WRONG and 34 NOT QUITE RIGHT** (17 of the 34 borderline; counting
those as WRONG still leaves 17 of 43, 40%, not quite right). The live run that day stopped
on a real remark placed under "closes by". Of 16 first drafts, 2 passed; if only WRONG
claims failed, 8 would have passed.

The judge also caught real errors that must keep failing: a participant's story credited
to Kerr, the stepdaughter put in the wrong marriage, a hedge turned into a claim the
speaker declines, an invented future plan, a meta-claim the transcript contradicts.

So the judge's job splits in two: **finding** claims the source does not state (it does
this well), and **deciding whether a found claim is wrong** (it does not do this; every
flag fails the run).

## Approach

Add a second step that runs only on flags that survive confirmation. It asks one
question, with the user's definitions: is this claim WRONG or only NOT QUITE RIGHT?

- WRONG claims fail, as today.
- NOT QUITE RIGHT claims pass with a warning. The gate's faithfulness check returns WARN,
  which the gate already treats as ALLOW_WITH_WARNINGS (`release_gate.decide`), and each
  claim is listed with its type and the source words it rests on.
- The finding step (judge prompt, extraction, confirmation) does not change, so the gold
  set's detection numbers should not move.

**Why not change the main judge prompt.** On 2026-10-11 a narrower writer-framing rule in
the main prompt scored 1.00 on the gold set but failed more good writing on real files
(Kerr 7 of 10 checks vs 5 of 10; `docs/calibration_framing_2026-10-11.md`). A change to
the main prompt changes the verdict on every claim. A second step only sees claims that
are already flagged, so it can only turn a FAIL into a WARN, and its effect is measured
on exactly those claims.

**Why not reuse the blog's second stage.** The blog check already re-judges UNSUPPORTED
claims with the theme grounding judge, which accepts "a fair interpretation of real
content" (`release_gate.blog_ungrounded_claims`, RF.N.1). That question has no test for
the wrong person (W3) or for an invented open question or plan (W4), and the theme gold
set has no such cases. The user named credit to the wrong person as WRONG, so the step
needs the user's own definitions.

**Why not make faithfulness advisory.** It would let the 9 WRONG claims through.

## The policy text (draft, for JS0.a)

Stored as a prompt file, `prompts/Faithfulness Severity Prompt v1.md` (editorial content in
a file, not in code; listed in `PROMPT_REGISTRY.md`). The examples below are placeholders
from unrelated subjects; the final examples must pass the overlap tests in JS4.

> You are given a SOURCE transcript and CLAIMS from a summary of it. A faithfulness check
> flagged each claim as not supported by the source. A summary written by a careful person
> is good, not perfect. For each claim, decide whether it is WRONG or only NOT QUITE
> RIGHT.
>
> A claim is WRONG when any part of it would give a reader a false idea of what the source
> says:
> - W1. It states a fact, name, date, number, place, event, quote, study, or description
>   of a person that the source does not contain, even if it may be true elsewhere.
> - W2. The source contradicts it: a different number, date, relationship or outcome; a
>   description of the talk that the source contradicts; or a hedged statement ("may",
>   "can contribute") made definite where the source hedges or declines it.
> - W3. It credits words, a story, a question or a view to the wrong person.
> - W4. It states a conclusion, position, plan or future event that the speaker never
>   states and that does not follow from what the speaker says, or that runs against a
>   position the speaker states.
>
> A claim is NOT QUITE RIGHT when every fact in it is in the source, each is credited to
> the right person, and it was flagged only because:
> - N1. It is a fair paraphrase or summary of the source.
> - N2. It interprets, frames, connects or emphasizes what the speaker says, including
>   applying ideas the speaker states to material the speaker discusses, without adding a
>   new fact.
> - N3. It places real content at the wrong point in the talk (for example "closes by" for
>   something said earlier), or describes the talk's order loosely.
>
> If any part of a claim is WRONG, the claim is WRONG. If you are unsure, answer WRONG.
>
> For NOT QUITE RIGHT, quote the source words that support the claim (up to 25 words,
> copied exactly). For WRONG, quote the source words it conflicts with, or write "absent".
>
> Examples. NOT QUITE RIGHT: "The conductor closes by thanking the volunteers", when she
> thanked them in her opening remarks (N3). WRONG: "The curator says the roof leaked
> twice", when a visitor said it (W3).
>
> Return ONLY a JSON array, one object per claim, in order:
> `[{"index": 1, "severity": "wrong|not_quite_right", "type": "W1|W2|W3|W4|N1|N2|N3", "evidence": "..."}]`

Checked against the review: under this text, the review's 9 WRONG claims are WRONG
(R3 W2, R11 W2, R18 W4, R22 W2, R25 W2, R34/R35/R37 W3, L4 W4), and its N1–N3 claims are
NOT QUITE RIGHT. The 4 speaker-credential claims (N4) fall under W1 and keep failing
(see JS0.b and JS5).

## Items, criteria and tests

New test file `tests/test_judge_severity_js.py` unless a row names another file. All
tests are offline with a mocked client, as in `tests/test_judge_confirm_cf.py`.

| ID | Criterion | Test |
|---|---|---|
| JS0 | Decisions a–e below are answered and recorded in this plan. | Human (this document) |
| JS1.a | `faithfulness_judge.classify_severity(claims, source, client)` sends the severity prompt with the source in the cached prefix (as `_cached_judge_content`) and returns, per claim, severity, type, evidence and the votes. | `test_js1a_severity_prompt_and_parse` |
| JS1.b | Votes: a first WRONG vote ends it (WRONG). A first NOT QUITE RIGHT vote gets a second; two NOT QUITE RIGHT votes downgrade; a split goes to a third vote. A downgrade needs two NOT QUITE RIGHT votes. | `test_js1b_wrong_first_vote_is_final`, `test_js1b_split_goes_to_third_vote` |
| JS1.c | Evidence check (P6): a NOT QUITE RIGHT vote counts only if its evidence is in the source (whitespace and case folded; a quote split by "…" counts when each part of 4+ words is present). Otherwise the vote counts as WRONG. | `test_js1c_invented_evidence_counts_as_wrong` (adversarial: a correct-looking quote that is not in the source) |
| JS1.d | Fails closed: a severity reply that cannot be parsed after `JUDGE_PARSE_ATTEMPTS`, an unknown severity or type, or an API error leaves the flag WRONG and records why. Never a pass on error. | `test_js1d_parse_error_keeps_wrong`, `test_js1d_api_error_keeps_wrong` |
| JS1.e | `config.FAITHFULNESS_SEVERITY_MODE` = `"majority3"` or `"off"`; `"off"` gives today's behaviour exactly (rollback switch). An unknown value raises. | `test_js1e_off_is_todays_behaviour` |
| JS2.a | `judge_artifact`: the step runs on confirmed flags only. The result is FAIL if any claim is WRONG, otherwise PASS with the NOT QUITE RIGHT claims recorded (type, evidence, votes), never dropped (P2). | `test_js2a_only_nqr_flags_pass_with_record`, `test_js2a_one_wrong_fails` |
| JS2.b | `release_gate.check_faithfulness`: WRONG → FAIL as today; only NOT QUITE RIGHT → WARN, detail "N claim(s) not quite right", items list each claim with type and evidence; the gate decision is ALLOW_WITH_WARNINGS. | `test_js2b_gate_warns_on_nqr_only` |
| JS2.c | Generation: `_faithfulness_precheck` returns only WRONG claims as issues, so revision and best-draft choice see WRONG claims only; NOT QUITE RIGHT claims are logged as a warning naming each claim. Covers the summary/overview/blog loop and the abstract loop (P5). | `test_js2c_precheck_ignores_nqr`, `tests/test_abstract_faithful_retry.py::test_js2c_abstract_nqr_only_passes` |
| JS2.d | (Adjacent fix in the same lines, if approved in JS0.d.) The "not faithful" warnings list every flagged claim in full, not `"; ".join(issues)[:300]` (`extraction_pipeline.py:1471`, and the abstract warning at `:1665` if it cuts too). | `test_js2d_warning_lists_every_claim` |
| JS2.e | Callers that read `unfaithful` or `contradicted` items keep working: the blog's two-stage check (advisory) now sees WRONG claims only; the topic/term check (advisory) inherits the step. Their existing tests pass unchanged. | existing `tests/test_run_fixes_rf.py`, topic/term tests |
| JS3.a | `config.JUDGE_LOGIC_VERSION` is bumped. `release_gate._judge_logic_version` also hashes the severity prompt text, `FAITHFULNESS_SEVERITY_MODE` and the evidence-check code, so a change to any of them re-keys the cache. | `test_js3a_logic_version_bumped`, `test_js3a_severity_prompt_change_rekeys_cache` |
| JS3.b | Dirty state (P8): a PASS cached before the bump is not served after it. A PASS with NOT QUITE RIGHT claims is cached with those claims and replayed with them (it is a pass); FAIL and ERROR stay uncached (D2). | `test_js3b_old_cached_pass_not_served`, `test_js3b_warn_replayed_with_claims` |
| JS4.a | The policy text is in the prompt file, loaded by code, and listed in `PROMPT_REGISTRY.md`. | `test_js4a_prompt_file_loaded_and_registered` |
| JS4.b | The examples come from unrelated subjects: none shares a rare word with a gold claim, a prose_real sentence, or a claim in the review (the 43), using the same checks as `tests/test_judge_prompt_examples_q6.py` (`test_fx_*`). | `test_js4b_examples_not_fitted_to_measured_claims` |
| JS5.a | Summary prompt, opening paragraph (`prompts/Summary Generation Prompt v1.md` line 17): describe the speaker only as the transcript and recording title do; give credentials only if the transcript states them; give a preview only if the speaker gives one. | `tests/test_summary_closing_sc.py`-style prompt-text test `test_js5a_opening_asks_only_for_what_the_transcript_gives`, and the prompt-sent test as in SC1.b |
| JS6 | Live calibration, not in CI: below. Report `docs/calibration_judge_severity_<date>.md`, results under `docs/calibration/<date>_judge_severity/`. | Script + report |
| JS7 | Documents updated in the same commit as the code (below). | Review of the diff |

### JS0 — decisions

**Answered 2026-10-19:** "Approve … with the recommended JS0 decisions: policy text as
drafted, credentials stay WRONG with the JS5 prompt fix, gold labels as proposed (k4
WRONG, k5 and k6 NOT QUITE RIGHT), NQR-only drafts pass without revision, JS2.d log fix
approved, contradicted flags…" (the message was cut at 300 characters; the reply button it
came from ends "go through the step", JS0.e as recommended). So: a yes, b keep WRONG +
JS5, c as proposed, d no revision + JS2.d yes, e yes.


- **JS0.a Policy text.** Approve, or edit, the definitions and the draft text above,
  including "If you are unsure, answer WRONG".
- **JS0.b Speaker credentials not in the transcript** (review N4: "psychiatrist and
  longtime exponent of Bowen family systems theory", 4 flags). They are true, but the judge
  cannot tell a true description from an invented one. **Recommended:** keep them WRONG
  (W1) and stop them at the source with JS5. Alternative: a config file of speaker
  descriptions, added to the judge's source like the recording title.
- **JS0.c Gold-set severity labels.** The gold set's 25 non-entailed cases need a
  severity label, so JS6 can check that none is downgraded. Proposed:
  - WRONG: c1–c6, rb_c1, k8 (wrong fact, W2); u1–u5, rb_u1, k9 (absent fact, W1); k2,
    sa4 (wrong person or role, W3); k3, sa3, sa5, us7 (contradicted or hedge made
    definite, W2); us6 (invented causal claim, W4).
  - **k4** ("Kerr, anxious about her speed, took over"; the source has her say "here, you
    take it in"): proposed WRONG (W2: changes who acted). It flipped in past runs.
  - **k5** ("The practical stakes are significant.") and **k6** ("This distinction is
    central to Bowen theory's explanation of how family dysfunction persists."): the
    2026-10-10 decision D1 made writer framing unsupported; under the 2026-10-18 rule they
    are NOT QUITE RIGHT (N2). Proposed: NOT QUITE RIGHT. Your call.
- **JS0.d NOT QUITE RIGHT at generation.** **Recommended:** a draft whose only flags are
  NOT QUITE RIGHT passes; the claims are logged, not revised. Alternative: revise them while
  attempts remain, but never fail on them. Also: approve JS2.d (stop cutting the log).
- **JS0.e "Contradicted" first-pass flags.** The review could not see the judge's labels,
  so a placement error might be labelled "contradicted". **Recommended:** both labels go
  through the step under the same rule, and JS6 lists every downgraded "contradicted" flag
  for hand review.

### JS6 — live calibration

Model and settings as in production (claude-sonnet-5-5, default effort, `majority3`). Old
= severity off; new = severity on. Same drafts and files for both.

| Part | What | Pass |
|---|---|---|
| a. Gold detection | `judge_recalibration.py --repeats 3` | Recall and precision within the range of the runs since confirmation was added (2026-10-11 to 2026-10-12: recall 0.86–0.96 per run, precision 0.96–1.00; the last, SA final, was 0.96 and 1.00 ×3). The finding step is unchanged, so a shift outside that range means a bug. |
| b. Gold severity | New `--severity` option: the step runs on every gold claim the judge flags; 3 runs | **No gold case labelled WRONG (JS0.c) is downgraded in any run.** |
| c. Injected | Into one held-out real summary, insert four WRONG claims: an invented study (W1), a swapped relationship (W2), a participant's story credited to the presenter (W3), an invented future plan (W4) | Each FAILs in 3 of 3 runs. |
| d. Held-out first drafts (≥10 fresh checks) | 12 summary first drafts (new summary prompt, JS5): 2 each from 6 talks not used in the review — Where Roots and Why Families Repeat (`tests/fixtures/prose_real`), and four KCFC talks with a formatted transcript (e.g. 2021 Webcast Jan Societal Regression, 2021 Webcast Feb, 2021 Webinar Mar, 2021 Webinar April). Each judged old and new. | I classify every flag from either path as WRONG or NOT QUITE RIGHT with a source quote, from a list that does not show which path downgraded it. **Ship only if no claim I classify as WRONG is downgraded.** Report: NOT QUITE RIGHT flags downgraded (n of m), drafts failing old vs new, credential flags (expected 0 after JS5). |
| e. Regression | 10 gate checks of the Kerr 2026-09-13 files used in CF.6 (`docs/calibration_confirm_2026-10-11.md`: 0 of 10 failed) | No new FAIL. |
| f. Development set | The review's 43 claims, 3 runs | Report agreement with the review's labels. Not a ship criterion: these claims shaped the policy. |

If b, c or d fails: stop, report, and don't ship. Options then: require three NOT QUITE
RIGHT votes, or narrow N2.

**Cost.** The step runs only on confirmed flags: 1 to 3 extra calls per flag, each with the
transcript in the cached prefix (in the 2026-10-18 log, confirmation calls were about
150–350 new input tokens and 150–330 output tokens each). For the calibration, past runs
give the scale: SC1.d cost $1.77 (16 drafts and a stage run); the framing gold runs were
$0.67–$1.53 per 3 runs. Estimate for JS6: about $5–8. The report gives the actual cost
from `logs/token_usage.csv`.

### JS7 — documents

CHANGELOG.md; TODO.md (the 2026-10-19 items close or update); `ARCHITECTURE_DESIGN.md`
and `PROJECT_STATUS.md` where they describe the faithfulness verdicts; `PROMPT_REGISTRY.md`
(new prompt); `LEARNINGS.md` if the calibration teaches something new; this plan's status;
the calibration report; the memory note on the judge (m2) with the new version, mode and
how to re-calibrate; `tests/fixtures/faithfulness_gold/gold.json` gains the severity
labels (JS0.c) with a note in its `_doc`.

## Deviations while building (2026-10-19)

- **Policy text, W2 and N3.** The prompt file drops the quoted words in W2 ("may", "can
  contribute") and in N3 ("closes by"). "can contribute" is the wording of review claim
  R25 and "closes by" that of L5; both claims are in the development set, so quoting them
  would fit the prompt to measured claims (JS4.b). N3 now reads "for example, says the
  speaker closes with something said earlier". The meaning is unchanged.
- **JS6.a and b in one run.** `judge_recalibration.py --repeats 3 --severity`: the
  finding step's metrics and the severity outcomes come from the same three runs.
- **JS6.d, one judge run per draft.** The step runs only on confirmed flags, so the old
  outcome (any confirmed flag fails) and the new one (only a WRONG flag fails) are read
  from the same run. Two separate runs would differ by judge noise, not by the change.
- **JS6.d talks.** Why Families Repeat has no `topics.md` (neither the fixture nor the
  project folder), and the summary stage needs one, so it cannot make drafts of that
  talk. A fifth KCFC talk, 2021 Webcast Jun, takes its place. Why Families is used in
  JS6.c (the injected claims go into its real summary) and JS6.e.
- **JS6.e files.** The Kerr 2026-09-13 files CF.6 judged were overwritten after
  2026-10-11: none of the three hashes in `docs/calibration/2026-10-11_confirm/cf6_r2.json`
  matches the project folder or the fixture now. The current project files are used; the
  results file records their hashes.

### learning-qa review fixes (2026-10-19)

The review found no path that lets a WRONG claim pass. It found six problems, all fixed
in the same change:

- **F1 (P1).** A FAIL that rests only on failed severity votes is transient: the claims
  are marked `severity_undecided`, and the gate neither caches that FAIL in memory nor
  leaves a "flagged" marker on disk, so the next run asks again. A FAIL with a WRONG
  decision keeps the D2 behaviour. The verdict detail says how many claims stayed WRONG
  because a vote failed.
- **F2 (P6).** Gate FAIL items gain a `wrong` list: claim, first-pass label, type,
  evidence, note and `undecided`, so a severity timeout is told apart from a W1 vote.
  `unfaithful` stays a list of strings for existing readers.
- **F3 (P2).** NOT QUITE RIGHT blog claims are logged by name
  (`release_gate.log_not_quite_right`, also used by the generation prechecks), and the
  advisory blog check returns WARN listing them instead of a PASS that only counted them.
- **F4 (P7).** The evidence check is stricter: every "..."-separated part of at least
  `FAITHFULNESS_SEVERITY_EVIDENCE_PART_MIN_WORDS` (2) words must be in the source, not
  only the parts of 4+ words, and the quote must share at least
  `FAITHFULNESS_SEVERITY_EVIDENCE_MIN_SHARED_WORDS` (1) significant word with the claim.
  The JS6 runs had started with the earlier rule; the stricter rule can only turn a
  downgrade back into WRONG, so it cannot break a JS6 pass criterion. The report
  re-scores the recorded votes under the new rule.
- **F5 (P8).** The cache key also hashes `FaithfulnessResult` (which claims fail), the
  severity types and the two new thresholds.
- **F6 (P20).** `judge_drift_monitor.py` runs the severity step on flagged gold claims; a
  gold WRONG case judged only NOT QUITE RIGHT is drift.

Adjacent issues found, not fixed: the theme-grounding judge (blocking) and the key-terms
judge do not have the severity step, so the user's rule is not applied there; gold claims
have no preceding sentence, so `judge_recalibration --severity` sends no context, while
the gate sends the sentence before each claim.

## Order

1. JS0: your decisions.
2. JS5 first (summary prompt only; the JS6 drafts use it). Tests, full suite.
3. JS4 tests, then the prompt file.
4. JS1 tests (they fail), then `classify_severity`.
5. JS2 tests, then the wiring in `judge_artifact`, `check_faithfulness` and the
   prechecks; JS2.d if approved.
6. JS3: version bump, cache key, tests. Full suite.
7. JS6: script, runs, report. Stop if a pass criterion fails.
8. JS7 documents; learning-qa review of the diff; fix findings; commit to main. Push only
   when you say so.

## Not code-testable

- Whether the step classifies real flags correctly. JS6 measures it on held-out drafts
  with hand classification; a mocked model would test nothing.
- Whether the policy text says what you mean by WRONG. That is JS0.a.
- My hand classifications in JS6 are one person's labels, as in the review; borderline
  claims are marked and reported both ways.

## Risks

- **A WRONG claim is downgraded.** Guarded by "if unsure, WRONG", two votes to downgrade,
  the evidence check, and JS6 b–d. The rollback is `FAITHFULNESS_SEVERITY_MODE = "off"`.
- **Fitting the policy to the measured claims** (the 2026-10-11 lesson). The examples come
  from unrelated subjects and are tested for overlap (JS4.b); the ship decision rests on
  talks that did not shape the policy (JS6 d).
- **More warnings to read.** Each WARN lists the claims, type and evidence, so a warning
  can be checked in a minute or ignored.

## Adjacent issues found, not fixed

- `extraction_pipeline.py:1471` cuts the flagged-claim list at 300 characters (JS2.d
  proposes the fix because it touches the same lines).
- Nothing reads the transcription tool's "Cloud transcription incomplete" warning; the
  Systems Biology project was summarised and judged from about 40 of its 88 minutes.
- The summary prompt says "Weave in the Interpretive Themes"; their interpretation is
  then judged by the faithfulness judge (8 Holt flags restate interpretive theme 3). With
  this plan such sentences become warnings, not failures.
- `measure_closing.py` saves flagged sentences but not the judge's labels or rationales;
  the JS6 script records both.
- The faithfulness judge prompt lives in `faithfulness_judge.py` as a string, not in a
  prompt file (rule 9). Not moved here: moving it changes the cache key and needs its own
  re-calibration.
