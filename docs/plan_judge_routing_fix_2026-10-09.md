# Plan — faithfulness judge routing fix (and heading claims)

Status: **PLAN — awaiting approval. No code changed.**
Base: local `main` at `9a21c9f` (merge of `validation-hardening`, not pushed).

## Problem

Run 2026-10-08, project `Why Families Repeat the Same Patterns - Michael Kerr - 2026-09-13`
(4,137-word transcript), was blocked by `faithfulness` on the summary (6 claims) and overview
(5 claims). Some flags were real errors, and at least two were false:

| Claim | Judge said | Transcript |
|---|---|---|
| "Now, thirty-five years later, chronic anxiety floods into living rooms nightly…" | unsupported ("fabricated timeframe") | "And now we are 35 years later… chronic anxiety is coming into your living room each evening" |
| "At the widest scale, Kerr applies the same logic to society." | unsupported | Kerr explains societal regression at length |

Cause: above `FAITHFULNESS_JUDGE_MIN_CHUNK_SOURCE_WORDS` (3000) the source is split into
windows and each claim is judged against ONE window (`route_claims_to_chunks`). A claim routes
to the window that contains all of its "anchored" significant words. Checked on this run:

- The "35 years" claim's anchored words (anxiety, chronic, years, living, news, through, trauma,
  focused, entirely, later) all occur, scattered, in window 0; the passage is in window 2, which
  lacks the summary's embellishments ("entirely", "focused", "trauma"). Routed to window 0.
- "society" occurs in window 1 next to "scale" and "same"; the discussion (window 2) says
  "societal" / "societies", which do not match "society" (no stemming). Routed to window 1.

So the judge answered correctly for the text it was given. The routing is wrong in two ways:
common words decide the window, and an embellished claim can fit a wrong window better than
the right one.

Why chunking exists (CHANGELOG 2026-08-21): a single call over a long transcript "degrades
attention (especially the middle) and can near the context limit". That was a design concern,
not a measurement.

## Decisions needed

**D1 — routing approach.**

| | (a) Confirm FAILs on the full source (recommended) | (b) Raise the chunk threshold |
|---|---|---|
| Change | Keep routing for speed; any routed claim the window judges NOT entailed is re-judged against the full source before it can FAIL. Plus: ambiguous routing (2+ windows hold the anchored words, or only common words anchor) goes to the full source; light stemming so society/societal/societies match. | `FAITHFULNESS_JUDGE_MIN_CHUNK_SOURCE_WORDS` 3000 → ~20,000 words, so ordinary talks (4–13k words) are never chunked. |
| False FAILs from routing | Removed by construction: no claim FAILs on a window alone | Removed for talks under the threshold |
| Recall (catching fabrications) | Window-entailed claims keep the window verdict; FAIL candidates get the full source — the long-context concern applies only to those few re-checks | Every claim judged on the full source — the August concern applies to all claims |
| Cost | Extra calls only for FAIL candidates (usually 0–10 claims per artifact) | One cached full-source call per batch (prompt caching already in place) |

**D2 — main's heading claims (from the merge; your 4a asked me to report before changing).**
`main` judges any heading ≥ 25 characters or containing a digit as a claim. On the 10 real
fixture artifacts it adds ~52 heading claims; judged live against the full transcripts, 8 came back
not entailed, and 7 of those are false flags: FAQ questions ("What is this transcript about?",
"What are the key topics discussed?"), section labels ("Key terms and definitions"), and blog
section titles ("What This Means in Practice", "What Crisis Actually Reveals: …"). They would
block Societal Emotional's overview and blog and Where Roots' blog — artifacts with no other
block. One looks real: the Where Roots abstract heading says "(June video)"; the recording is
dated February.

- **(a) Recommended:** judge a heading only when it states a concrete specific: a digit, a month
  name, or an ungrounded name (the branch's scaffolding-name check already covers names).
  Questions (ending "?") and the prompts' own section headings are never claims. This keeps
  "Bowen's 1954 Study at Harvard" and "(June video)" and drops the 7 false flags.
- (b) Drop main's heading rule; keep only the ungrounded-name check.
- (c) Keep main's rule as is.

Nothing is pushed until D1 and D2 are settled and the checks below pass.

## Acceptance criteria → tests (written for D1 = a, D2 = a)

Fixture first: copy the 2026-10-08 project's `- formatted.md`, `- summary-generated.md`,
`- overview.md` into `tests/fixtures/prose_real/Why Families Repeat the Same Patterns - Michael
Kerr - 2026-09-13/` (real artifacts; the run that exposed the bug).

**J1 — ambiguous routing goes to the full source.**
- J1.a A claim whose anchored words are all contained in 2+ windows is unrouted. →
  `tests/test_judge_routing_j.py::test_j1a_multiple_windows_unrouted`
- J1.b A claim anchored only by words present in every window is unrouted. →
  `::test_j1b_only_common_words_unrouted`
- J1.c A claim with distinctive words in exactly one window still routes there (no loss of the
  August behaviour). → `::test_j1c_distinctive_claim_still_routes`
- J1.d On the real fixture, the "35 years" and "society" claims are unrouted or routed to the
  window containing the passage. → `::test_j1d_real_oct8_claims_reach_their_passage`

**J2 — stemming.** `_significant_words` maps society / societal / societies (and -s, -es, -ies,
-al, -ing, -ed forms) to one stem; stop-word filtering unchanged. →
`::test_j2a_stem_variants_match`, `::test_j2b_adversarial_short_words_not_merged`
(e.g. "news" vs "new", "kerr" vs "ker").

**J3 — no claim FAILs on a window alone.** In `judge_claims_chunked`, a routed claim the window
judges unsupported/contradicted is re-judged against the full source; the full-source verdict
is final. Window-entailed claims keep their verdict. →
`::test_j3a_window_fail_is_rejudged_on_full_source` (mocked judge: window says unsupported,
full source says entailed → entailed), `::test_j3b_full_source_fail_stands`,
`::test_j3c_window_entailed_not_rejudged` (call count), `::test_j3d_rejudge_error_is_error`
(P1: a failed re-check is ERROR, not the window's FAIL).

**J4 — heading claims (D2 = a).** A heading is a claim only if it contains a digit, a month name
(`config.FAITHFULNESS_HEADING_MONTH_WORDS`), or an ungrounded name; never if it ends with "?" or
matches a prompt section heading (`config.FAITHFULNESS_GENERIC_HEADINGS`, extended with the
overview/blog prompts' fixed headings). → `tests/test_faithfulness_scaffolding_r6.py::test_j4a_*`
(digit, month, name kept; question, label, plain title dropped); real fixtures:
`::test_j4b_real_artifacts_heading_claims_pinned` (the observed list, reviewed).

**J5 — cache and version.** `JUDGE_LOGIC_VERSION` bumped; routing/stemming/heading code is
already in the hashed material (R9) — `tests/test_judge_disk_cache_h2.py::test_j5_*` pins the
new functions.

**J6 — live verification (API spend; not offline-testable).**
- J6.a Calibration suite: gold recall ≥ 0.9 / precision ≥ 0.7, real abstracts as expected, theme
  judge unchanged.
- J6.b Re-judge the 2026-10-08 summary and overview: the two false flags are entailed; the real
  errors (reversed Navy story, "led the Georgetown Family Center", "freedom runs through the
  source of constraint") still FAIL.
- J6.c Re-judge the 10 real prose fixtures' heading claims: no false heading flags; "(June
  video)" still flagged.
- Results recorded in CHANGELOG and the project memory note.

**J7 — sweep and push.** `learning-qa` over the diff; fix findings; then push `main` (includes the
merge) and `validation-hardening`.

## Order

```
fixture copy → J2 (stemming) → J1 (routing) → J3 (full-source confirmation) → J4 (headings)
→ J5 → offline suite → J6 (live) → J7
```

## Risks

- J3 adds full-source calls for FAIL candidates; on a bad artifact (many unsupported claims)
  that is one extra batched call per artifact, not per claim (batch the re-checks).
- Stemming can merge unrelated words; J2.b is the adversarial guard, and the suffix list stays
  short.
- J4 narrows what headings are judged. A fabricated claim written purely as a heading with no
  number, month or name ("Bowen Rejected Systems Thinking") is not judged — same as before
  main's rule. Flagged as a residual in the docstring and TODO.

## Also open (from the merge, not part of this plan)

- `verbatim_quotes` (100% word coverage) fails Societal Emotional on one quote that corrects a
  transcript typo ("birdd" → "bird"). Options: allow a 1-character difference in words of 4+
  letters, or regenerate. Needs your call.
