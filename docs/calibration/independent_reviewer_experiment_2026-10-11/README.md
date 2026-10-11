# Independent reviewer experiment — DeepSeek v4-pro vs Sonnet 5.5 (2026-10-11)

Step 0 of `docs/review_independent_reviewer_2026-10-11.md`: does a second-provider
judge catch what the Claude judge misses? Not a calibration for arming.

**Setup**
- Model: `deepseek-v4-pro`, key from the shared store (`global-api-config/llm_providers.py`).
- Prompt: the Claude judge's label rules verbatim (`faithfulness_judge._JUDGE_INSTRUCTIONS`), plus
  anchor fields (`instructions.txt`).
- Inputs: public gold sources only (D6: `where_roots`, `roots_bowen`, `kerr_families`; 23 cases,
  13 unfaithful) and the roots_bowen and where_roots real abstracts (18 claims).
- Three complete runs: `raw_8k.json` run 0, `raw_32k.json` runs 0 and 1. (`raw_8k.json` run 1 has
  two batches cut off at `max_tokens` 8192, all of it reasoning; not scored.)
- Comparison: Sonnet 5.5 default effort, `docs/calibration/2026-10-10_sonnet55_default.json` (3 runs).
- Re-run: `build_inputs.py <dir>` → `call_deepseek.py <dir> deepseek-v4-pro 2` (system python3,
  needs `requests`) → `score.py <dir>` (repo venv, `PYTHONPATH=.`).

**Results**

| | Recall | Precision |
|---|---|---|
| Sonnet 5.5 (same 23 public cases) | 0.85–0.92 | 1.00 |
| DeepSeek raw | 0.69–0.77 | 1.00 |
| DeepSeek with the F1 anchor rule | 0.62–0.69 | 1.00 |

- **Claude misses that DeepSeek caught: none.** Sonnet 5.5 missed k4 (1 of 3 runs) and k6 (3 of 3);
  DeepSeek missed both in every run, plus k5 (3 of 3) and k2 (1 of 3).
- Both caught every fabricated name, study and factual contradiction (u1 Malorni, u5, rb_u1,
  us7, c6, rb_c1, k3, k8, k9).
- Real abstracts: both flag "Luciano Malorni" in where_roots. DeepSeek also flagged, in every
  run, the abstract's title line ("Abstract - … (June video)") and "Mike Kerr presents a
  webinar" in roots_bowen, which Sonnet 5.5 passed: two false warnings per run.
- The F1 anchor rule dropped correct findings: k2's quote carried the speaker label and an
  ellipsis ("Michael Kerr: ... You have to heal in the system.") and failed the verbatim test;
  k9's named element "in the 1950s" appears in the source in another context, so the absence
  test dropped it.
- Reasoning load: 718–8192+ reasoning tokens per call, 27–103 s per call; at the spec's
  `max_tokens` 8192, 2 of 5 calls in one run returned no answer. 290,591 tokens in all
  (15 calls).
