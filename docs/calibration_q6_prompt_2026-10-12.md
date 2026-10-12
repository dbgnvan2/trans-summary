# Judge prompt examples no longer mirror gold cases (Q6 / C1) — 2026-10-12

Plan: `docs/plan_todo_triage_2026-10-11.md` (Q6, C1). Judge: claude-sonnet-5-5 with
confirmation (CF).

## Change

Two "unsupported" examples in the faithfulness judge prompt paraphrased gold cases. The
calibration could then measure recall of the example rather than of the rule
(LEARNINGS 2026-10-11). Only these two were replaced. Other examples still come from
measured material; see "Still open" below.
- "attributes recovery to medication" (twice) mirrored gold **us6** ("…attributes the
  client's recovery primarily to psychiatric medication"). It is now "blames the
  bridge's failure on a design flaw" when no design flaw is in the source.
- "definitively proven" / "conclusively established" (strength escalation) mirrored gold
  **us7** ("…Bowen theory has now been definitively proven…"). It is now
  "beyond any doubt" / "now settled".

No rule changed. `config.JUDGE_LOGIC_VERSION` is now 2026-10-12, so cached verdicts are
re-judged. Tests: `tests/test_judge_prompt_examples_q6.py`. They check that no example
quotes a gold claim, covers half its words, or uses the distinctive words of us6 or us7.

## Measurement (old and new prompt, same day)

The plan's bar: gold recall at least the current value, and 0 false fails on 10 fresh
checks of the Kerr 2026-09-13 project. Both prompts were run the same day, because the
judge varies from run to run. Data: `docs/calibration/2026-10-12_q6_prompt_examples/`.
Prompt fingerprints: old `96e5ab257296`, new `ff237a94655e`.

| | Old prompt | New prompt |
|---|---|---|
| Gold faithfulness recall (3 runs) | 0.91, 0.91, 0.91 (missed k4, k6) | 0.95, 0.95, 0.95 (missed k6) |
| Gold precision | 1.00 ×3 | 1.00 ×3 |
| us6, us7 | caught every run | caught every run |
| Themes recall / precision | 1.00 / 1.00, 0.93, 1.00 | 1.00 / 1.00 ×3 |
| Real abstracts, injected fabrication | 3/3, caught | 3/3, caught |
| Verdict changes across runs | 1 | 0 |
| Kerr project, 10 fresh checks | 1 FAIL | 0 FAIL |
| Cost | $1.12 + $0.90 | $0.99 + $0.89 |

- **Kerr FAIL on the old prompt:** in run 5, a majority confirmed a flag on "Finally, the
  conversation addresses societal regression, a concept Bowen…". The transcript supports
  that sentence, so it was a false fail (it was also overturned in run 9).
- **k4:** the whole 0.91 → 0.95 difference is this one case. The new prompt labels it
  "contradicted"; gold says "unsupported". k4 was judged ambiguous on 2026-10-11
  (`docs/calibration_framing_2026-10-11.md`), and nothing in the new examples relates to
  it. Read this as no loss, not as a gain.
- **us7** is caught as "contradicted" in all six runs, so the run does not test the new
  strength-escalation example. It shows only that removing "definitively proven" did
  not lose us7.
- **Kerr:** 1/10 vs 0/10 on one project meets the plan's bar. It is not evidence that the
  new prompt is better.
- **k6** (the writer's own framing) is still missed, as accepted.

Reproduce:
- Gold: `judge_recalibration.py --model claude-sonnet-5-5 --repeats 3 --out …`.
- Kerr: `docs/calibration/2026-10-11_confirm/cf6.py out.json logs_dir 10`, run from a
  checkout with the prompt being tested. The old prompt was HEAD `7c673b6`; the Kerr
  JSONs record the prompt fingerprint and file hashes. Model: claude-sonnet-5-5, CF
  majority3, run 2026-10-12.

## Conclusion

The new prompt meets the bar: recall no lower than before, and 0 of 10 false fails. us6
and us7 are still caught without examples that point at them. Shipped.

## Still open (found in review, not changed here)

- The "entailed" example "connects this history to Bowen theory by introducing the DOS
  equation" mirrors gold rb_e1/rb_e2. They were written the same day, 2026-07-15.
- Three "entailed" framing examples are copied word for word from the Systems Biology
  blog in `tests/fixtures/prose_real`, the `--prose-real` set:
  - "It was a logical approach, and it produced genuine discoveries.";
  - "The environment is not incidental.";
  - "…the explanation lives in the pattern."
- "That kind of reckoning is rare in science." is about the same subject as gold ef1/ef2.

Replacing these touches the framing behaviour that the 2026-10-11 work chose not to
change, so it is a user decision. It needs its own same-day old-vs-new measurement with
`--prose-real` and the Kerr checks. The archived test
`judge-framing:tests/test_judge_framing_tf.py::test_tf1_framing_examples_avoid_gold_subject`
would catch all four.
