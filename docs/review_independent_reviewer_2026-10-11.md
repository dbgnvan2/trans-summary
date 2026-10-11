# Critical review — Independent Reviewer spec v5 (2026-10-11)

Question asked: are the proposed changes likely to do what is intended?
Reviewed: `docs/spec_independent_reviewer_2026-10-11-v5.md`, against the code at
`f628a75` and the 2026-10-10 Sonnet 5.5 calibration (`docs/calibration_sonnet55_2026-10-10.md`).

**Intent:** catch errors in the abstract, summary and overview that the Claude judge
misses because it shares the generator's model family (Q2), and find material the
summary/abstract left out (Q1 residual).

## Verdict

As written, it would run and produce output, but it is unlikely to deliver the intended
benefit. The accuracy mode is plausible, but one rule in it filters out the very errors
it is meant to catch. The coverage mode has no way to tell a real omission from noise.
Nothing shows the findings to you. The calibration does not measure whether a second
model adds anything. Each of these can be fixed; a cheap experiment should come before
the build.

## Findings

### F1 — The quote rule drops fabrications, the main target (high)
The spec requires a `source_quote` on every non-entailed verdict and drops any verdict
whose quote is not verbatim in the source (I4). That works for **contradicted**: the
reviewer can quote the passage that says otherwise. It does not work for
**unsupported**. A fabricated name ("Luciano Malorni") is unsupported because nothing
in the source mentions it; there is no passage to quote. The reviewer will either cite
an unrelated sentence (which passes the verbatim check and proves nothing) or cite
nothing (and the finding is dropped). So the rule both admits weak objections and
removes the strongest ones.
**Fix:** require a quote only for `contradicted`. For `unsupported`, require the
reviewer to name the unsupported element (the name, number, date or attribution) and
check deterministically that it is *absent* from the source; if it is present, drop
the verdict as a reviewer error.

### F2 — The calibration does not test the reason for the feature (high)
D5 checks DeepSeek alone against the 0.90 / 0.70 bars. The case for a second model is
that it catches what Claude misses. A DeepSeek that passes the bars but misses the same
cases as Sonnet 5.5 adds cost and nothing else; one that fails the bars could still
catch Claude's misses. The 2026-10-10 runs give the comparison point: Sonnet 5.5 missed
1–3 unfaithful gold cases per run.
**Fix:** the calibration runs both judges on the same cases and reports (a) unfaithful
cases Claude missed that DeepSeek caught, (b) DeepSeek false alarms on cases Claude got
right, (c) the recall of "either judge flags it". Go/no-go: if (a) is empty, stop.

### F3 — The gold set is too small to decide anything once `dave_g` is excluded (medium)
Without `dave_g` there are 23 cases with 13 unfaithful; one miss moves recall by about 0.08.
Several cases test a policy choice, not hallucination detection: k5 (filler, labelled
unsupported) and k6 (the writer's own framing). Sonnet 5.5 disagreed with k6 and every
Claude 5 model disagreed with k5; DeepSeek likely will too, and that would count against
it for reasons unrelated to catching fabrications.
**Fix:** report fabrication/contradiction cases separately from writer-framing cases;
add 10–15 public cases of the kind it should catch (invented names, numbers, wrong
speaker, wrong date) taken from real runs.

### F4 — The coverage mode has no ground truth (medium)
A summary leaves things out by design. An adversarial model asked for "material
omissions" will nearly always list some, so the check will warn on most runs. There is
no gold set for coverage and no calibration step for it. The verbatim-quote requirement
also fits poorly: the reviewer has to quote the omitted passage, which favours short
quotable lines over important arguments that span paragraphs.
**Fix:** leave coverage out of v1, or build a small labelled set first.

### F5 — Nobody will see the findings (medium)
The check only warns. Warnings reach you as a count in one log line ("… 2 warn(s)") and
as JSON in the run manifest; the findings themselves are not printed in the GUI. The
spec says agreement is "read from the manifest", which in practice means it is not
read. The RF.N blog warnings show the pattern.
**Fix:** print each finding in the GUI log under the gate line, marked as a
disagreement when the Claude judge passed the same artifact.

### F6 — Opt-in per project means it will rarely run (low; your decision)
Consent defaults to off for every project, so the reviewer runs only where you tick the
box. That is the right privacy default; it also means the "second opinion" is absent on
most runs unless you make ticking it a habit. Consider a global default in settings with
the per-project switch as the override.

### F7 — Failures look like findings (low)
Any exception becomes a WARN. A broken key or an outage then shows up the same way as a
real finding, on every run, which trains you to ignore the line.
**Fix:** a distinct detail ("reviewer did not run: <reason>") and a separate count.

### F8 — Shared claim extraction is a shared blind spot (low; accepted)
Both judges judge the same regex-extracted claims, so a claim the extractor drops or
merges is missed by both. The spec does this on purpose to make verdicts comparable;
it limits independence to the judging step.

## What is sound
- The isolation design (own client, no change to the Claude path) and the fail-open
  rule are correct for an advisory check.
- Using the gate's own verbatim rule (C5) and the shared key store (C8) avoids two
  sources of disagreement with the rest of the pipeline.
- Chunked parity mirrors the existing judge, so long transcripts are handled the same way.

## Recommended order
1. **Step 0 experiment** (throwaway script, a few cents; needs D6 = public sources):
   DeepSeek v4-pro with a draft accuracy prompt and the F1 rule, on the public gold cases
   and the three real abstracts; compare case by case with the 2026-10-10 Sonnet 5.5
   results (F2 report).
2. If DeepSeek catches cases Claude missed: build accuracy mode only, with F1, F5, F7.
3. Coverage mode later, only with a labelled set (F4).

## Step 0 result (2026-10-11)

Run with public sources only (D6). Details: `docs/calibration/independent_reviewer_experiment_2026-10-11/README.md`.
- DeepSeek v4-pro caught **none** of the cases Sonnet 5.5 missed (F2 go/no-go: no-go for
  this provider). Recall 0.69–0.77 raw vs Sonnet 5.5 0.85–0.92 on the same 23 cases; both
  1.00 precision; both caught every fabricated name, study and factual contradiction.
- Two false warnings per run on the clean roots_bowen / where_roots abstracts (a title line,
  "Mike Kerr presents a webinar").
- The F1 anchor rule as drafted dropped correct findings (a quote carrying the speaker label
  and an ellipsis; an "absent" element that appears elsewhere in the source). F1 stands as a
  problem; the fix needs more than a verbatim/absence test.
- v4-pro reasons heavily (up to 8,192+ tokens per call); the spec's `max_tokens` 8192 cut
  off 2 of 5 calls in one run.
