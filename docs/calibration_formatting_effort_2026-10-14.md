# Format: lower thinking level (Sonnet 5.5 "medium") and DeepSeek V4 Pro — 2026-10-14

Question (user): can Format cost less? It is the largest cost of a run (31% of the
end-to-end run of 2026-10-13), and most of its output tokens are thinking.

## Method

- Three public talks (the end-to-end runner's set): Why Families (4,055 words),
  Beautiful Boy (11,274), Systems Biology (10,732). Input: the `_validated` sources of
  end-to-end run 4. Prompt `Transcript Formatting Prompt v12-Lite.md`, no pattern set.
- Each output gets format_transcript's post-processing and
  `formatting_pipeline.verify_source_fidelity` with no review approvals. "Passed" = no
  review item and within the gross limits, the same check the pipeline runs.
- **Sonnet 5.5, default ("high")**: the 9 Format runs of end-to-end runs 1–4
  (2026-10-13/14), from their logs.
- **Sonnet 5.5, "medium"**: 2 runs per talk, `compare_formatting_effort.py` (sets
  `config.FORMATTING_EFFORT` in-process).
- **DeepSeek V4 Pro** (`deepseek-v4-pro`, thinking mode, its default): 2 runs per talk,
  the identical prompt text through the OpenAI-compatible API with the shared key module
  (`deepseek_call.py`, max_tokens 64,000), then the same check
  (`deepseek_prepare_and_check.py`). Prices from api-docs.deepseek.com/quick_start/pricing
  (2026-10-14): $0.66 / 1M input (cache miss), $1.98 / 1M output off-peak; double at
  peak (01:00–04:00 and 06:00–10:00 UTC weekdays).

## Results

| Model / level | Passed | Review items per run | Other errors | Cost per run (WF / long talks) |
|---|---|---|---|---|
| Sonnet "high" (9 runs) | 8 of 9 | 0 ×8, 1 | — | $0.25–0.43 / $0.49–0.89 |
| Sonnet "medium" (6 runs) | 4 of 6 | 0, 0, 0, 0, 1, 1 | 1 heading timestamp | $0.11–0.17 / $0.33–0.44 |
| DeepSeek V4 Pro (6 runs) | 0 of 6 | 1, 2, 3, 0, 2*, 15 | 1 invented timestamp; 1 reply cut off | $0.05–0.08 / $0.09–0.14 off-peak |

\* cut off at 64,000 output tokens (52,978 of them reasoning): the last 2,312 words of
Systems Biology are missing.

What the differences are:
- **Sonnet "medium"**: both Systems Biology runs deleted the same word ("How does Bowen
  theory **look** or the concept of…"), a small grammar tidy that "high" did not make
  in its 3 runs of that talk. Otherwise as "high". About 45–60% cheaper per run.
- **DeepSeek V4 Pro** deletes filler words ("uh" ×3), stray letters ("S"), a phrase
  ("to revert or transcend the cancer state, meaning"), slide cues ("Next one,
  please."), changes words ("that's" → "that"), invents a heading timestamp, and on one
  run thought until it ran out of room. It is 3–6× cheaper than "medium" and slower
  (4–9 minutes per long talk vs about 3).

## Conclusion

- DeepSeek V4 Pro does not keep the speaker's words: 0 of 6 passed, and using it would
  also need a second provider in the pipeline. Not a fit for Format.
- Sonnet "medium" roughly halves Format's cost (about $0.15–0.45 per talk, ~15% of a
  full run) at the price of more one-word review stops (2 of 6 runs vs 1 of 9). Small
  samples; the repeated "look" deletion suggests "medium" tidies grammar slightly more.
- No change made; `config.FORMATTING_EFFORT` stays at the model default pending the
  user's decision.

> **2026-10-17 update:** later adopted — `config.FORMATTING_EFFORT` is now `"medium"`
> (commit cc87ae1). The Sonnet "medium" row above is the current production behavior.

Files: `docs/calibration/2026-10-14_formatting_effort/` (scripts, per-run results,
DeepSeek usage). The formatted texts are not committed.
