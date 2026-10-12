# Formatting model: Haiku 4.5 vs Haiku 5.5 — 2026-10-11

Plan: `docs/plan_todo_triage_2026-10-11.md` (U3). Haiku 4.5 (`claude-haiku-4-5-20251001`)
retires no sooner than 2026-10-15. Candidate chosen by the user: `claude-haiku-5-5`.

## Method

- 3 public Michael Kerr talks, each formatted twice per model (12 runs):
  "Roots of Bowen TEST" (1,989 words), "2021 Webcast Jan Societal Regression" (9,901),
  "Making a difference in Self and Family" (14,609).
- Prompt `Transcript Formatting Prompt v12-Lite.md`, no pattern set, default effort
  (Haiku 5.5 default: medium). Same post-processing as `format_transcript`.
- Checked with `formatting_pipeline.verify_source_fidelity` and no review approvals:
  "passed" means no review item and within the gross limits.
- Script and counts: `docs/calibration/2026-10-11_formatting_haiku/`. The formatted texts
  were not committed.

## Results

| Transcript | Model | Run | Passed | Review items | Mismatches | Max run | Headings | Seconds |
|---|---|---|---|---|---|---|---|---|
| Roots (2k) | 4.5 | 1 | yes | 0 | 0 | 0 | 20 | 36 |
| Roots (2k) | 4.5 | 2 | yes | 0 | 0 | 0 | 20 | 36 |
| Roots (2k) | 5.5 | 1 | yes | 0 | 1 | 1 | 18 | 83 |
| Roots (2k) | 5.5 | 2 | yes | 0 | 1 | 1 | 17 | 75 |
| Societal (10k) | 4.5 | 1 | no | 3 | 2 | 1 | 46 | 205 |
| Societal (10k) | 4.5 | 2 | no | 20 (+ 5 heading timestamps not in source, 99 errors) | 45 | 23 | 58 | 209 |
| Societal (10k) | 5.5 | 1 | no | 9 | 24 | **14** (limit 10) | 40 | 199 |
| Societal (10k) | 5.5 | 2 | no | 7 | 9 | 2 | 52 | 104 |
| Making (15k) | 4.5 | 1 | no | 1 | 0 | 0 | 53 | 292 |
| Making (15k) | 4.5 | 2 | yes | 0 | 0 | 0 | 49 | 291 |
| Making (15k) | 5.5 | 1 | no | 2 | 4 | 1 | 36 | 164 |
| Making (15k) | 5.5 | 2 | no | 34 | 43 | 3 | 45 | 130 |

Passed: Haiku 4.5 3 of 6, Haiku 5.5 2 of 6. Cost (token log): Haiku 4.5 $0.42 for 6
runs, Haiku 5.5 $0.12 (its output includes thinking: up to 54k output tokens for the
10k-word talk).

What the differences are:
- **Haiku 4.5** mostly fixes ASR doubles ("selff", "Universityversity"). Its bad run
  (Societal 2) dropped a sentence and wrote 5 heading timestamps that are not in the source.
- **Haiku 5.5** fixes the same ASR doubles, and also:
  - copy-edits: in Making 2 it deleted fillers, changed "there's" to "There are" and
    hyphenated words (34 review items);
  - changed a name: "Bertoloso" became "Bartoloso" (Societal 2);
  - repeated 14 words of transcript text a second time (Societal 1);
  - writes fewer section headings (17–45 vs 20–58).

The source check caught every one of these. None would publish unreviewed.

## Conclusion

Haiku 5.5 is not equal or better on fidelity. It edits the speaker's words more often,
which means more review items or re-runs. It is cheaper and faster on long transcripts.
Under the plan's rule (U4: switch only if equal or better) the defaults were **not**
switched. Decision for the user (below).

Not code-testable: formatting quality beyond these counts. A side-by-side read of one
formatted transcript per model is the human check.

## Options

1. Switch to Haiku 5.5 now and accept more review items. The format check stops bad output.
2. Measure Haiku 5.5 at `low` effort, and Sonnet 5.5 for formatting only, on the same 3
   talks (about $1–2), then decide.
3. Keep Haiku 4.5 until Anthropic retires it and switch then. Risk: formatting fails on
   the retirement day until the setting is changed (GUI model menu, or `config.py`).
