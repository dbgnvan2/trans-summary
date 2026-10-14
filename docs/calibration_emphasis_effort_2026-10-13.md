# Calibration: scored emphasis thinking level (E2E6, 2026-10-13)

## Problem

Scored emphasis ran at the model's default thinking level ("high" on
claude-sonnet-5-5). Its saved answer is about 3,000–4,000 tokens, but the calls used
11,228–14,540 output tokens when they finished; the rest is thinking. On the 11–12k-word
talks the thinking ran past the ceiling: over 16,192 tokens (8,192 + headroom) in the
first end-to-end run, and over 24,000 (twice) after E2E3 raised it. The reply was cut off
and the Bowen + Emphasis stage failed: 3 of the 4 "high" calls on long talks (one finished
at 14,540). In the GUI the run stops there.

## Measurement

Three public talks (Why Families 4,182 words; Beautiful Boy 12,074; Systems Biology
11,570), the YAML transcripts from end-to-end run 3, claude-sonnet-5-5, the production
prompt and ceiling (24,000), two calls per level. Compared with the "high" outputs saved
by the end-to-end runs (Why Families: 2; Beautiful Boy: 1; Systems Biology: none, both
"high" calls were cut off).

- *verbatim*: share of quotes found word for word in the transcript (the pipeline needs
  verbatim quotes).
- *in_high*: share of this call's items that are also in a "high" output (token overlap
  ≥ 0.6 of the shorter quote). *high_found*: share of "high" items this call found.
- Reference: the two "high" Why Families outputs overlap 0.94 (both directions
  averaged). Averaged the same way, "medium" scores 0.91 and 0.78 against "high" on Why
  Families, and "low" 0.78 and 0.77.

| Talk | Level | Finished | Output tokens | Items | Verbatim | in_high | high_found |
|---|---|---|---|---|---|---|---|
| Beautiful Boy | low | 2/2 | 8,172 / 7,324 | 22 / 21 | 1.00 / 1.00 | 0.68 / 0.76 | 0.54 / 0.57 |
| Beautiful Boy | medium | 2/2 | 11,325 / 9,838 | 31 / 18 | 1.00 / 1.00 | 0.68 / 0.89 | 0.71 / 0.57 |
| Systems Biology | low | 2/2 | 8,283 / 5,411 | 32 / 44 | 1.00 / 1.00 | – | – |
| Systems Biology | medium | 2/2 | 13,071 / 11,429 | 46 / 39 | 1.00 / 1.00 | – | – |
| Why Families | low | 2/2 | 3,208 / 2,619 | 25 / 18 | 0.96 / 0.94 | 0.78 / 0.89 | 0.77 / 0.65 |
| Why Families | medium | 2/2 | 7,842 / 2,473 | 22 / 20 | 1.00 / 1.00 | 0.95 / 0.90 | 0.86 / 0.65 |

Cost of the measurement: about $1.

## Decision

`config.EMPHASIS_EFFORT = "medium"`. It finished every call, its largest reply at
13,071 tokens (55% of the ceiling), and every quote was verbatim. Its items are close to
"high" but not as close as two "high" runs are to each other: on Why Families 0.91 and
0.78 against 0.94, and the second call missed 35% of the "high" items. "Low" was cheaper;
on Why Families it gave one non-verbatim quote per call, and its overlap was similar to
"medium" on Why Families and lower on one Beautiful Boy call.

What "medium" trades: a reply that always finishes, for an item list that differs a
little more from "high". The item lists differ from run to run at every level, so the
emphasis items were never a fixed set.

The cost estimate for the emphasis step now uses the measured output at this level,
thinking included (`config.EMPHASIS_OUTPUT_PCT` 0.65, `EMPHASIS_OUTPUT_FLOOR` 5,000).

## Limits

- Two calls per level per talk. The item lists vary from run to run at every level
  (Beautiful Boy "medium": 31 and 18 items), so overlap figures are rough.
- Beautiful Boy has one "high" reference and Systems Biology none, so the quality
  comparison rests mostly on Why Families.
- "Medium" makes a cut-off much less likely, not impossible; the end-to-end runner
  will show if it recurs.

Script, printed results and the 12 replies: `docs/calibration/emphasis_effort_2026-10-13/`.
