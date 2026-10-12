# Plan: confirm a faithfulness flag before it fails a run (CF.1–CF.6)

Status: **approved 2026-10-11, building.** CD1 = majority of 3 with early stop; CD2 =
faithfulness judge only; CD3 = on the current prompt (the framing change was not shipped).

## Problem

- The faithfulness judge (claude-sonnet-5-5, which takes no temperature) sometimes
  rejects a claim the source supports. On the Kerr 2026-09-13 project, with the files
  that passed the real run on 2026-10-10, 1 of 3 fresh checks with the **current**
  prompt failed (2026-10-11), on "Michael Kerr calls a multigenerational perspective
  the best entry point." (the interviewer asked for the best entry point; Kerr answered
  "extremely important"). With the option-B framing prompt, 2 of 3 failed, on other
  supported sentences: "It links chronic anxiety to chronic inflammation and physical
  illness." and "a concept Bowen introduced in 1975". The 10-run comparison in progress
  will give the rates.
- A flag fails the abstract, summary or overview, which starts a regeneration (RF.J, up
  to 3 attempts) and can block publication.
- **A false flag is sticky.** `release_gate._judge_cached` stores every non-ERROR verdict
  on disk keyed on (artifact, source, model, logic version) (`release_gate.py:806-815`),
  so re-running the gate on unchanged files replays the same false FAIL until the text
  is regenerated.

## The change

A first-pass flag is **confirmed** before it counts: the flagged claims (only those) are
judged again in fresh calls against the full source, and a claim stays unfaithful only
if the confirmation agrees.

- **CD1 — rule.** (a) *Majority of 3 with early stop* (proposed): flag in pass 1 →
  pass 2; both reject → unfaithful; pass 2 accepts → pass 3 decides. (b) *Both of 2*:
  unfaithful only if pass 1 and pass 2 both reject (cheaper; a real fabrication that one
  pass misses is lost).
- Extra calls happen only when pass 1 flags something, and they carry only the flagged
  claims (the source prefix is prompt-cached).
- The final verdict keeps pass 1's label and rationale and adds the later passes' labels
  and rationales and the vote count; each re-sent flagged claim is accompanied by the claim
  before it, for context only (sweep); overturned flags are logged and recorded ("2 of 3 first-pass flags not
  confirmed: …") so nothing is dropped silently (P2).
- A judge error in any confirmation call → ERROR (fail closed), as today.
- The cached verdict is the confirmed one; the confirmation settings are part of the
  judge logic version, so old unconfirmed verdicts are not reused.
- One function, `faithfulness_judge.judge_claims_confirmed`, does pass 1 (chunked or
  not) plus the confirmation; `judge_artifact`, `classify_claim`, the calibration tool
  (`judge_recalibration.faithfulness_gold`) and `judge_drift_monitor.py` all call it, so
  the calibration measures the behaviour that ships (P5).
- Setting `config.FAITHFULNESS_CONFIRM_MODE` = "majority3" (or "off"); it and the new
  function are part of the judge logic version.
- Through `judge_artifact`, every gate caller gets it: the faithfulness and topic/key-term
  checks, the blog's stage 1, and the generation pre-check
  (`extraction_pipeline._faithfulness_precheck`).

## Acceptance criteria → tests

- **CF.1 Confirmation logic** (offline, mocked judge returning fixed sequences):
  reject/reject → unfaithful; reject/accept/reject → unfaithful; reject/accept/accept →
  entailed and logged as overturned; accept → no extra call; an error in a
  confirmation call → ERROR.
  - Tests: `tests/test_judge_confirm_cf.py::test_cf1_*`.
- **CF.2 Overturned flags are surfaced** — the result's detail names how many
  first-pass flags were overturned and which; they are in the run manifest's verdict
  items. Test: `test_cf2_overturned_flags_recorded`.
- **CF.3 Every caller confirms** — the gate's faithfulness check, the topic/key-term
  check, blog stage 1 and the generation pre-check all go through `judge_artifact`.
  Tests: `test_cf3_all_callers_use_confirmed_judgement` (source scan: gate, calibration
  tool, drift monitor, live calibration test, `judge_artifact`, `classify_claim`);
  `test_cf2_topic_term_check_records_overturned` (mocked topic/key-term path). Blog stage 1
  and the generation pre-check call `check_faithfulness`, covered by the source scan.
- **CF.4 Cache** — the stored verdict is the confirmed one; changing
  `FAITHFULNESS_CONFIRM_MODE` changes the logic version. Test: `test_cf4_*`.
- **CF.5 Live: recall kept** — gold set (50 cases), 3 runs: recall ≥ 0.90 and precision
  ≥ 0.70 (current bars), every fabricated name/study/contradiction still caught;
  report recall before/after. Output: `docs/calibration/<date>_confirm.json`.
- **CF.6 Live: false fails reduced** — the Kerr project, 10 fresh checks: count failed
  runs and compare with the 10-run baseline (same files, same prompt). Bar: fewer failed
  runs than the baseline, and no supported sentence fails. Report the extra calls and
  cost per run.

## Decisions for you

- **CD1** — majority of 3 with early stop (proposed) or both of 2.
- **CD2** — scope: the faithfulness judge only (proposed), or also the theme-grounding
  judge (same random-flag risk; it uses its own call path, so it would be a second change).
- **CD3** — order: build this on top of whichever framing prompt you choose after the
  10-and-10 comparison (B or the current one), so CF.5/CF.6 measure the prompt that ships.

## Cost

Live checks: CF.5 ~$1.5–2 (3 gold runs), CF.6 ~$1.5–3 (10 Kerr checks, more calls when
flags occur). Per real run: extra calls only when a flag occurs, each one small (the
flagged claims) with the source cached.

## Not covered

- Making the judge itself deterministic (Sonnet 5.5 has no temperature control).
- The theme judge, unless CD2 says so.

## Adjacent issues found, not fixed

- A cached false FAIL is replayed on every gate re-run of unchanged files (sticky). CF
  reduces how often a false FAIL is stored; it does not add a way to clear one entry
  short of regenerating the artifact or deleting `logs/gate_judge_cache.json`.
