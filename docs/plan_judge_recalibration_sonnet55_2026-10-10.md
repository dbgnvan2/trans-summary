# Plan: re-calibrate the judges on claude-sonnet-5-5 (JC.0–JC.7)

Status: awaiting approval (and three decisions, below). Request 2026-10-10: "plan the
judge re-calibration for sonnet 5.5".

## Why

- The armed judges (faithfulness, theme grounding; the theme judge is also the blog's
  second stage) run on `claude-sonnet-4-6`, which will be deprecated.
- On the Kerr interview, Sonnet 4.6 misread the bold speaker labels (rejected a true
  "Kerr says…" claim and accepted the false "the interviewer says…"). All 5-family
  models read them correctly (spot test 2026-10-10, 5 claims).
- Sonnet 5.5 is cheaper ($2/$10 per MTok vs $3/$15) but cannot take `temperature`
  (it always runs its own sampling) and thinks before answering, so its verdicts may
  vary run to run and it spends output tokens on thinking.
- `tests/test_judge_model_pin.py` (H12) blocks any judge-model change until this
  calibration is run and recorded.

## What exists

- `tests/test_faithfulness_calibration.py` (live, opt-in): faithfulness gold
  (`tests/fixtures/faithfulness_gold/gold.json`, 33 cases, 3 sources), 3 real abstracts
  (roots_bowen PASS; where_roots FAIL naming "Malorni"; dave_g FAIL naming "nubbin"),
  an injected-fabrication check, and the theme gold (20 grounded / 13 ungrounded).
  Bars: recall ≥ 0.90, precision ≥ 0.70 for both judges. Last pass on 4.6: 1.0/1.0.
- `judge_drift_monitor.py`: runs the three gold sets live and reports per judge.
- `tests/fixtures/prose_real/`: 10 real prose artifacts (4 talks) with their transcripts.
- The key-terms judge is disabled (`KEY_TERMS_JUDGE_ENABLED = False`) — out of scope;
  its model constant moves with the others only if you say so.

## Acceptance criteria

- **JC.0 Calibration can target any model and effort** — the calibration tests and
  `judge_drift_monitor.py` take the model and effort from env
  (`CALIBRATION_JUDGE_MODEL`, `CALIBRATION_JUDGE_EFFORT`), defaulting to config, and
  print both in every report. No production change.
  - Test: `tests/test_judge_recalibration_jc.py::test_jc0_calibration_model_from_env` (offline).
- **JC.1 Gold cases for the failures seen in the 2026-10-08/09/10 runs** (P10: calibrate
  on the real failure modes) — added to the faithfulness gold with the Kerr interview
  transcript as a new source. Labels need your decision (D1):
  1. "Kerr states explicitly, 'You have to heal in the system.'"
  2. "The interviewer says, 'You have to heal in the system.'" → contradicted
  3. "Bowen told Kerr in a letter … 'You have to heal in the system.'" → contradicted
  4. "His wife was bringing the boat into moorage, and Kerr, anxious about her speed,
     took over." (she handed him the helm)
  5. "The practical stakes are significant." (filler, no content)
  6. "This distinction is central to Bowen theory's explanation of how family
     dysfunction persists." (overview's own framing)
  7. "Kerr is the youngest of five brothers." → entailed
  8. "Billy was the youngest brother." → contradicted
  9. "Kerr was Bowen's student in the 1950s." → contradicted/unsupported
  10. "Thirty-five years after Bowen's 1975 warning…" style routing case → entailed
  - Test: `test_jc1_gold_has_kerr_cases` (offline: cases present, source resolves).
- **JC.2 Baseline on 4.6** — run the full calibration on `claude-sonnet-4-6` with the
  new cases, so 4.6 and 5.5 are compared on the same set.
- **JC.3 Sonnet 5.5 meets the bars** — faithfulness gold recall ≥ 0.90 / precision
  ≥ 0.70; real abstracts give the expected PASS/FAIL and name Malorni / nubbin; the
  injected fabrication is caught; theme gold recall ≥ 0.90 / precision ≥ 0.70.
  Run at effort: model default (high) and medium (D2).
- **JC.4 Stability** — Sonnet 5.5 takes no temperature, so the gold sets are run 3
  times; bar: no case flips label between runs on the gold sets, and the real-artifact
  statuses never change. A flip is reported with the claim.
- **JC.5 No new false blocks on real prose** — every claim in the 10 `prose_real`
  artifacts is judged by both models; each verdict that differs is listed for your
  review in the report (not auto-passed).
- **JC.6 Switch** (only after JC.3–JC.5 pass and you approve the report) —
  `FAITHFULNESS_JUDGE_MODEL` and `THEME_JUDGE_MODEL` = `claude-sonnet-5-5`;
  `JUDGE_EFFORT` = the chosen level; `JUDGE_LOGIC_VERSION` bumped (cached 4.6 verdicts
  are not reused); `tests/test_judge_model_pin.py` pin updated with the date and
  numbers; the blog second stage follows (it uses the theme judge).
  - Tests: existing pin tests; `test_jc6_cache_version_bumped`.
- **JC.7 Record** — `docs/calibration_sonnet55_<date>.md` with the numbers for both
  models, flips, differing real verdicts and cost; memory note updated.

## Decisions for you

- **D1 — labels for the new gold cases.** My proposals:
  - Case 1 (speaker): **entailed**. The judge sees the formatted transcript, and its
    speaker labels are the record (the raw transcript is unlabeled and ambiguous).
  - Case 4 (boat "took over"): **unsupported**. She handed it over; "took over" adds a
    motive the source does not give.
  - Cases 5–6 (filler / the writer's own framing): **unsupported**, matching the current
    strict rule for summaries and overviews. All 5-family models called case 5
    "entailed" in the spot test, so this choice decides whether they pass.
- **D2 — effort to test.** Default (high) and medium. Low only if both pass and you
  want the cheaper run.
- **D3 — budget.** Estimate ~$5–10 for everything (two models, two effort levels,
  3× stability runs, 10 real artifacts). Each run is live, so I will show the total
  after JC.2 before running JC.3–JC.5.

## Order

JC.0 → JC.1 → JC.2 (report baseline + cost) → JC.3 → JC.4 → JC.5 → report to you →
JC.6 on your approval → JC.7 → push.

## Not covered

- The key-terms judge (disabled) and the summary-coverage / topic validators (Haiku,
  not calibrated judges).
- Whether 5.5 changes which blog claims are "accepted as interpretation": covered
  indirectly by the theme gold and JC.5's blog artifacts.
