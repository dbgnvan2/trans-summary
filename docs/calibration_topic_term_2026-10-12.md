# Topic / key-term faithfulness check on real projects (C2) — 2026-10-12

Plan: `docs/plan_todo_triage_2026-10-11.md` (C2). The check
`release_gate.check_topic_term_faithfulness` judges each topic description and key-term
definition against the transcript. It is advisory: not in `GATE_BLOCKING_CHECKS`. It
had not been measured on real output.

## Method

- Current code: faithfulness judge on claude-sonnet-5-5, with confirmation (CF).
- 5 real projects, 2 fresh runs each, no judge cache:
  - the 3 `tests/fixtures/prose_real` talks;
  - "Beautiful Boy Review" (Kathleen Kerr);
  - "Monika Baege and Michael Kerr interview".
- Script and results: `docs/calibration/2026-10-12_topic_term_c2/`.
- Earlier data from 2026-10-11 (before CF, 3 runs on the 3 fixtures):
  `docs/calibration/2026-10-11_framing_tf5_topicterm/tt_old_*.json`.

## Results

| Project | Run 1 | Run 2 | Earlier, pre-CF (3 runs) |
|---|---|---|---|
| Societal Emotional Process | PASS (1 first-pass flag not confirmed) | PASS | PASS ×3 |
| Systems Biology Meets Bowen Theory | PASS | PASS | PASS ×3 |
| Where Roots Bowen Theory Reside in the Brain | FAIL (topics) | FAIL (topics) | FAIL ×3, same claim |
| Beautiful Boy Review | PASS | PASS | — |
| Monika Baege and Michael Kerr interview | FAIL (key terms) | PASS (2 first-pass flags not confirmed) | — |

The two flags:
- **Where Roots, topic "Cancer as Blocked Ontogeny…" (every run): a real error.** The
  topic credits the idea to "Researchers Sonenschein, Soto, and Bertoloso". In the talk,
  "her key point is cancer as a disease of cell differentiation rather than
  multiplication", from one researcher. Sonenschein and Soto are named only as the
  editors of *The Society of Cells*.
- **Monika, key term "Societal Regression" (1 of 2 runs): borderline.** The definition
  ("a period in which systems thinking is resisted or suppressed in favor of
  reductionist… models") reads more into the term than the interview supports. Kerr only
  says "as long as we can get through this societal regression and come back to our
  sanity… it's going to move towards systems".

No flag was a clear false flag. The confirmation step overturned 3 first-pass flags
across the 10 runs.

## Conclusion

The check finds real errors and raised no clear false flags on these 5 projects. It
stays advisory (decision 2026-10-05: key terms are report-only). Making the **topics**
half blocking is a reasonable next step if wanted; on this sample it would have blocked
Where Roots for a real misattribution. Decision for the user.
