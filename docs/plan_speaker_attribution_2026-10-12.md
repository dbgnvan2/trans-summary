# Plan: no speaker attribution in transcripts without speaker labels (SA) — 2026-10-12

Status: **plan, awaiting approval.** No code written.

## Problem

The source for "Why Families Repeat the Same Patterns - Michael Kerr - 2026-09-13" has
no speaker labels, so the formatted transcript has none either. The writing models still
write "The interviewer observes…", "The interviewer cites…". The transcript can't show
who said what, so the judge can't verify these sentences. They pass or fail by chance:
- 16:18 run: the summary passed at generation (attempt 2/3).
- 17:44 run: the same file was re-judged at publish and failed ("contradicted"), which
  blocked publication.
- 20:02 re-run: attempt 2 failed on "The interviewer describes self-differentiation as a
  scale…". Attempt 3 passed, but the saved summary still has three "The interviewer …"
  sentences.

Why the publish step re-judged a file that had passed: commit 1c0e98f added `_theme_body`
and `_is_theme_block` to the judge input functions. That changed the judge cache key, so
earlier PASS entries no longer matched and every claim was judged again. Most of the
time a borderline claim passes; this time the judge flagged it and 2 of 3 confirmation
runs agreed.

## Approach

When a transcript has no speaker labels, tell the writing prompts not to attribute
statements to anyone but the named presenter, and not to describe another speaker's
role ("interviewer", "host", "audience member"). They should describe such content
neutrally ("The conversation turns to…", "One question raised is…"). This is decided in
code, so it is testable. The wording lives in a prompt fragment file, not in Python
(rule 9).

The judge is not changed. This is a change to the writers only.

## Acceptance criteria and tests

| ID | Criterion | Test |
|---|---|---|
| SA1 | `transcript_utils.has_speaker_labels(text)` is True when any line starts with a `**Name:**` label (the formatting prompt's multi-speaker format), and False otherwise. | `tests/test_speaker_attribution_sa.py::test_sa1_detects_labels` (Where Roots and the older Why Families fixture: True; live-style unlabeled text: False) |
| SA1.a | Adversarial: a bold run-in label inside prose (`**Note:** …` mid-line), or a heading with a colon, is not a speaker label. | `test_sa1_bold_phrase_in_prose_is_not_a_label` |
| SA2 | The summary, abstract, blog and overview prompts include the unlabeled-speaker instruction when the transcript has no labels, and leave it out when it has labels. | `test_sa2_<artifact>_unlabeled_gets_instruction`, `test_sa2_<artifact>_labeled_has_no_instruction` (4 artifacts × 2) |
| SA3 | The instruction text is read from `prompts/fragments/unlabeled_speakers.md`; a missing file is an error, not a silent skip. | `test_sa3_fragment_loaded_from_file`, `test_sa3_missing_fragment_raises` |
| SA4 | The correction-feedback path (`_generate_until_faithful`) still adds the instruction on every attempt. | `test_sa4_instruction_present_on_regeneration` |
| SA5 | The cost estimator counts the extra prompt tokens. | `test_sa5_cost_estimate_includes_fragment` |
| SA6 | Real measurement, old vs new prompt, same day (see below). | Not code-testable; results doc `docs/calibration_speaker_attribution_2026-10-12.md` |

## SA6 measurement (needs real API calls, about $4–6)

- Kerr 2026-09-13 (unlabeled): generate summary, abstract, blog and overview 3 times each
  with the old prompt and 3 times with the new prompt.
- Record, for each run:
  - the first-attempt faithfulness result;
  - the number of attempts used;
  - how many sentences attribute a statement to an unnamed role (interviewer, host,
    questioner, audience).
- Control: Where Roots (labeled), summary and blog, 2 runs each with old and new.
  Attribution there must not get worse.

Pass bar:
- new prompt: zero role attributions in the Kerr outputs;
- first-attempt failures not higher than with the old prompt;
- no change on the control.

## Order

1. SA1 and SA1.a: tests, then the helper.
2. SA3: the fragment file and its loader.
3. SA2 and SA4: wire the instruction into the four builders.
4. SA5: cost estimator.
5. Full suite.
6. SA6 measurement.
7. learning-qa sweep, then fix its findings.
8. Docs, then commit and push.

## Docs to update in the same commit

- CHANGELOG
- TODO.md
- PROJECT_STATUS
- README (prompt section)
- this plan's results table

## Adjacent issues found, not fixed

- **Any change to the judge's input functions re-judges every saved artifact.**
  - When `_judge_input_functions` changes, the cache key changes and every saved
    artifact is judged again.
  - A borderline claim that passed before can then block an artifact that hasn't
    changed.
  - This is by design: a logic change must re-verify. The cost is that a borderline
    claim gets a fresh chance to fail.
  - Logged in TODO; no change proposed.
- **Generation-time attempts may still keep borderline sentences.**
  - The summary step accepts the first passing attempt.
  - That attempt can still contain sentences of the same kind as the one that failed
    (here, three "The interviewer …" sentences).
  - SA fixes this case only. Other borderline kinds are not covered.
- **Unattributed claims elsewhere.** Themes, lenses and key terms are not part of this
  change.
