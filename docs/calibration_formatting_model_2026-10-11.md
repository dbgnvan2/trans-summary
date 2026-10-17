# Formatting model: Haiku 4.5 vs Haiku 5.5 vs Sonnet 5.5 — 2026-10-11

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

## Round 2 — Haiku 5.5 at low effort, Sonnet 5.5 (default effort)

User chose option 2 (measure before deciding). Same 3 talks, 2 runs each, same method;
counts in `docs/calibration/2026-10-11_formatting_haiku/results_round2.json`.

Review items per run (Roots ×2, Societal ×2, Making ×2), all four configurations:

| Model | Review items | Other errors | Passed | Cost (6 runs) | Long-talk time |
|---|---|---|---|---|---|
| Haiku 4.5 | 0, 0, 3, 20, 1, 0 | 5 heading timestamps not in source (1 run) | 3 of 6 | $0.42 | 3.5–5 min |
| Haiku 5.5 (medium) | 0, 0, 9, 7, 2, 34 | 14-word repeat (1 run) | 2 of 6 | $0.12 | 2–3.5 min |
| Haiku 5.5 (low) | 1, 1, 9, 4, 3, 56 | heading timestamps wrong (2 runs) | 0 of 6 | $0.09 | 1.5–2.5 min |
| Sonnet 5.5 | 0, 0, 1, 2, 2, 1 | 1 heading timestamp off by a minute (1 run) | 1 of 6 | $3.38 | 6–8.5 min |

What the differences are:
- **Haiku 5.5 low** edits as much as medium. It changed "Cell" to "Self" and "Brahe" to
  "Bra", changed "Bertoloso" to "Bartoloso" again, deleted phrases, and wrote 45
  heading-timestamp errors in one run.
- **Sonnet 5.5** review items are only:
  - dropped single words ("that", "to,");
  - "[unintelligible]" removed;
  - one ASR double fixed ("Universityversity").

  It made no grammar edits and no name changes. It writes more section headings (54–77
  on the long talks vs 46–58 for Haiku 4.5). Its few "passed: no" results are 1–2
  one-word review items or one heading timestamp.

## Conclusion (round 2)

Sonnet 5.5 keeps the speaker's words best of the four, including Haiku 4.5. Its cost is
about $0.10 for a 2k-word talk and $0.67–1.00 for a 10–15k-word talk, versus about
$0.02 / $0.08–0.12 for Haiku 4.5. It also takes about twice as long. Haiku 5.5 at either
effort is not a fit for verbatim formatting. **Recommendation:** `FORMATTING_MODEL =
claude-sonnet-5-5`. `VALIDATION_MODEL` / `AUX_MODEL` (also Haiku 4.5) were not measured
here; they are not verbatim tasks, and U5 measures them separately.

## Decision (2026-10-12)

`FORMATTING_MODEL = claude-sonnet-5-5` (user approved). Sonnet thinks about 3.5 tokens
per transcript token while formatting (measured 2.0–5.0). `config.FORMATTING_THINKING_RATIO`
is used for the cost estimate and the single-pass length check, so a talk that would
not fit even at the typical ratio (about 20k words) is stopped before a paid call. Above
the measured maximum, 5.0 (`FORMATTING_THINKING_RATIO_MAX`, about 14.7k words), the step
runs but warns that the answer may be cut off. A cut-off answer fails loudly. The longest
of the 70 real transcripts on disk (14,609 words in the file; 14,314 after the validation
footer is removed) comes out at 124k of the 128k limit at
the maximum ratio; in the test runs it actually used 60–92k. The ratios above were measured at the model's default
effort (`FORMATTING_EFFORT = None`); since 2026-10-17 formatting runs at `"medium"`
(commit cc87ae1), so they are a conservative upper bound, not the live ratio.

## AUX model — Haiku 4.5 vs Haiku 5.5 (U5, 2026-10-12)

`AUX_MODEL` runs:
- header validation;
- the structured abstract (GUI "Gen Abstract" stage, with the gate's faithfulness
  pre-check and up to 3 attempts);
- stated-purpose extraction;
- the summary-coverage check, which blocks publication.

`VALIDATION_MODEL` is not read by any step: Initial Validation uses `DEFAULT_MODEL`.
Measured on the 3 public prose_real projects, 2 runs per model. Data:
`docs/calibration/2026-10-11_formatting_haiku/aux_results.json` and
`header_validation_results.json`.

| Task | Haiku 4.5 | Haiku 5.5 |
|---|---|---|
| Abstract: passes the faithfulness gate | 6 of 6 | 5 of 6 (Societal run 2 kept one unsupported Q&A claim after 3 attempts; the gate blocks it) |
| Abstract: attempts used | 9 | 11 |
| Abstract: words | 189–236 | 150–265 (one over the 250 limit; abstract validation flags it) |
| Stated purpose | the transcript's own sentences | the same, but one run tidied the sentence (not word for word) |
| Summary coverage (Systems Biology) | fails both runs | fails both runs (same result) |
| Header validation (batched), verdicts | 54/54, 77/77 | 54/54, 77/77 |
| Header validation, FAIL / WARN | 1/9 and 4/6 | 7/27 and 18/30 |
| Header validation, largest batch output | 2,410 tokens | 6,525 tokens (includes thinking) |

Haiku 5.5's extra header FAILs that I read were reasonable:
- a heading term that is not in the section;
- a "Speaker Transition" heading over Q&A logistics;
- a heading that leads with a minor topic.

Header validation is advisory.

**Decision:** `AUX_MODEL = claude-haiku-5-5` (Haiku 4.5 retires; Haiku 5.5 is close on
these tasks, and the gate catches the abstract it could not fix). If abstracts regress
in real use, move abstract generation to `DEFAULT_MODEL`. The main pipeline (Core)
already generates its abstract with `DEFAULT_MODEL`; only the GUI "Gen Abstract" stage
uses `AUX_MODEL`.

## Header validation fix (HV)

The 4096-token ceiling cut off `validation_pipeline.validate_headers` on the Societal
talk with both models. That function sent the whole transcript in one call. Nothing in
the app called it; it was reachable through `pipeline.validate_headers`. It now uses
the batched `HeaderValidator`, the GUI's step, 5 sections per call. The batched path
was never cut off: the largest batch measured 2,410 tokens on Haiku 4.5, and 6,525
including thinking on Haiku 5.5, which also gets the 8000-token thinking headroom. The
per-batch ceiling was raised from 4096 to 8192 as margin. That costs nothing unless it
is used.
