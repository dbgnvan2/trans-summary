# Spec — Independent Adversarial Reviewer (second-model critical validator)

Status: **DRAFT — for review** (not built)

Base: local `main`. Do not push until reviewed + decisions below are settled.

## Problem

The pipeline already runs a critical reviewer, but it is **not independent of the generator**:

- `config.DEFAULT_MODEL = "claude-sonnet-4-6"` (generation)
- `config.FAITHFULNESS_JUDGE_MODEL = "claude-sonnet-4-6"` (accuracy judge)
- `config.THEME_JUDGE_MODEL = "claude-sonnet-4-6"` (theme judge)

A same-family reviewer shares the generator's blind spots — the original "Luciano Malorni"
ship was a fluent hallucination the same model could not see. The user's two open questions
map onto two reviewer modes:

1. **Q1 — "is all the text there?"** (large/full-file outputs) — already answered *deterministically*
   by `check_source_fidelity` (word-level diff vs raw) + `transcript_validate_completeness`. The
   only residual is a *semantic-coverage* gap on the **generative** large outputs (summary,
   abstract): material findings the fixed `summary_coverage` checklist does not enumerate.
2. **Q2 — "are short outputs accurate?"** (abstract, headings, summary, key-terms, themes, lenses,
   blog) — already answered by the faithfulness/theme judges, but on the *same model* as the generator.

## What this adds

One isolated module that runs a **second, provider-independent model** over the *same claims,
same source, same chunking* the Claude judge already uses, in two modes, and reports the
**disagreement** against the Claude verdicts. Disagreement is the deliverable: where a second
model independently concurs with a FAIL, confidence rises; where the two models split, that
artifact is flagged for human review.

Scope is deliberately narrow: this is a *second opinion + coverage pass*, not a replacement
for the existing judges and not a new artifact generator.

## Decisions needed

**D1 — provider adapter (recommended: a).**

| | (a) One OpenAI-compatible adapter | (b) Generalize `transcript_utils` |
|---|---|---|
| Change | New `independent_reviewer.py` owns its own client: base_url + model + key env var via the OpenAI-compatible wire protocol (works for DeepSeek, Nous Portal if it exposes an OpenAI-compatible endpoint, and OpenAI/"Fable" — zero extra code, config only). | Refactor `call_claude_with_retry` / `get_anthropic_client` into a multi-provider factory. |
| Isolation | ✓ does not touch the Claude path at all | ✗ touches the armed judge path |
| Risk | none to existing gates | regresses the calibrated Claude judges |

Pick (a). The Claude path is load-bearing and calibrated; do not modify it.

**D2 — which model/provider by default.** `INDEPENDENT_REVIEWER_MODEL` + `INDEPENDENT_REVIEWER_BASE_URL`
+ `INDEPENDENT_REVIEWER_API_KEY_ENV`, all config constants. Default = DeepSeek (`api.deepseek.com`,
key already in `.env` per project notes) as the cheap second opinion; the OpenAI top model ("Fable")
is a config swap, not a code change. See **Blocking inputs** below.

**D3 — is the reviewer a blocker?** No. Start `INDEPENDENT_REVIEWER_BLOCKING = False`: the check
returns WARN (advisory) and is *not* added to `config.GATE_BLOCKING_CHECKS`. Promote to blocking
only after D5 calibration clears. This is the same "arm after gold-set calibration" discipline the
existing judges followed.

**D4 — scope of artifacts.** Accuracy mode reuses the existing claim extraction over
`config.FAITHFULNESS_ARTIFACT_SUFFIXES` + `config.TOPIC_TERM_FAITHFULNESS_SUFFIXES` (same set the
Claude judge covers). Coverage mode targets the summary + abstract only (the generative large
outputs where Q1 is still open). Headings on the formatted file stay with the existing
`validate_headers` deterministic+Claude check — they are not re-covered here.

**D5 — calibration before arming.** Reuse `tests/fixtures/faithfulness_gold/`. Measure the
independent model's precision/recall on the unfaithful class; a promotion PR sets
`INDEPENDENT_REVIEWER_BLOCKING = True` only with a recorded precision ≥ 0.7 / recall ≥ 0.9 on that
set (mirror the J6.a threshold in `docs/plan_judge_routing_fix_2026-10-09.md`).

## Design (concrete touch points)

### New module `independent_reviewer.py`

- **Client**: OpenAI-compatible (`openai` SDK or raw HTTP to `base_url`), constructed from
  `INDEPENDENT_REVIEWER_BASE_URL` / `INDEPENDENT_REVIEWER_MODEL` / `INDEPENDENT_REVIEWER_API_KEY_ENV`.
  Do NOT import or reuse `call_claude_with_retry` (isolation invariant). Provide its own
  retry/timeout + truncation check; fail-closed: any API/parse error → ERROR.
- **Claims are shared, not re-derived.** Import `faithfulness_judge.extract_claims` and
  `chunk_source` / `route_claims_to_chunks`. Same claims, same source, same chunking as the Claude
  judge — otherwise the disagreement signal is noise.
- **Two modes** (prompts verbatim in `references/` — see below):
  - `review_accuracy(claims, source)` → per-claim `{index, label, rationale, source_quote}`.
    Labels `entailed|contradicted|unsupported`. **Mandatory**: a non-entailed verdict must carry a
    `source_quote` span.
  - `review_coverage(artifact, source)` → list of `{omitted, timestamp, materiality}` for the
    summary/abstract only.
- **Span re-verification (load-bearing).** After parsing, drop + log any `contradicted`/`unsupported`
  verdict whose `source_quote` is not verbatim in the source (reuse the repo's fuzzy
  `_quote_word_coverage` or a strict `in` check). A reviewer that cannot anchor its objection is a
  reviewer error, not a finding — this is what prevents a hallucinating reviewer from false-blocking.
- **Cache + logic-version** identical to `release_gate`: key the disk memo on
  `(artifact-sha, source-sha, INDEPENDENT_REVIEWER_MODEL, logic-version)`; hash the prompt text +
  extraction config into the version (reuse `release_gate._judge_logic_version` pattern, separate
  prompt constant). ERROR never cached.

### `release_gate.py`

- New check `check_independent_reviewer(base_name, logger)` registered in `DEFAULT_CHECKS` (position:
  after `check_faithfulness` / `check_theme_grounding`, so the Claude verdicts it diffs against are
  already computed/memoized).
- It runs the second model, then **diffs** against the Claude judge's cached verdicts per artifact:
  - concurrence on FAIL → note "second model concurs" (strengthens the existing BLOCK);
  - split (Claude PASS vs reviewer FAIL, or vice-versa) → WARN with the disagreement itemized.
- Status mapping: reviewer ERROR → WARN (advisory check, not in blocking set); WARN carries the
  disagreement list. Not added to `GATE_BLOCKING_CHECKS` while `INDEPENDENT_REVIEWER_BLOCKING = False`.
- Gate manifest: add the independent reviewer's model + verdicts under `provenance.models` (it is
  already enumerated in `build_manifest`) and a `disagreements` field.

### `config.py`

New constants (all defaulted so the feature is inert until wired):
`INDEPENDENT_REVIEWER_ENABLED`, `INDEPENDENT_REVIEWER_MODEL`, `INDEPENDENT_REVIEWER_BASE_URL`,
`INDEPENDENT_REVIEWER_API_KEY_ENV`, `INDEPENDENT_REVIEWER_BLOCKING`, `INDEPENDENT_REVIEWER_MAX_TOKENS`,
`INDEPENDENT_REVIEWER_MIN_CHUNK_SOURCE_WORDS`. No change to any existing constant.

### Prompts

Two prompt templates as markdown under `prompts/` (not hard-coded in the module, matching the repo's
prompt-file convention): `independent_reviewer_accuracy_v1.md` and `independent_reviewer_coverage_v1.md`.
Bodies per the workflow already reviewed with the user (adversarial stance; judge only against the
source; no outside knowledge; tentative→settled escalation is unsupported; interpretive themes judged
for grounding + fabricated-specific injection; span-citation required on every non-entailed verdict).

## Acceptance criteria → tests

New `tests/test_independent_reviewer.py` + fixtures:

- **I1 — isolation.** No import of / change to `call_claude_with_retry`, `get_anthropic_client`, or
  the Claude judge functions. Test: the module's client is constructed from its own config only
  (mock the OpenAI-compatible client).
- **I2 — shared claims.** `review_accuracy` receives the *identical* claim list the Claude judge
  produced for the same artifact (reuse a fixture artifact; assert claim equality, not re-extraction).
- **I3 — fail-closed parse.** Malformed JSON / missing label / missing `source_quote` on a non-entailed
  verdict → ERROR (never a silent pass); mirrored from `_parse_judge_response`.
- **I4 — span re-verification.** A `contradicted` verdict whose `source_quote` is not in the source is
  dropped and logged, not counted as a finding.
- **I5 — diff semantics.** Claude FAIL + reviewer FAIL → concurrence; Claude PASS + reviewer
  contradict/unsupported → WARN disagreement item; Claude FAIL + reviewer entailed → WARN disagreement
  item (the reviewer *disagrees with* the block).
- **I6 — coverage mode.** `review_coverage` returns only substance-level omissions (not restatements);
  malformed output → ERROR.
- **I7 — gate wiring.** `check_independent_reviewer` returns WARN (not BLOCK) while
  `INDEPENDENT_REVIEWER_BLOCKING = False`; ERROR → WARN; appears in the manifest with its model +
  disagreements.
- **I8 — cache/version.** Bumping the prompt text or extraction config invalidates the cached verdict
  (reuse the `_judge_logic_version` pattern); ERROR not cached.
- **I9 — calibration harness (live, not offline).** Script that runs `review_accuracy` over
  `tests/fixtures/faithfulness_gold/` and prints precision/recall — the gate that D3/D5 require before
  `INDEPENDENT_REVIEWER_BLOCKING = True`.

## Order

```
config constants → independent_reviewer.py (client + accuracy mode) → I1–I4
→ coverage mode + I6 → release_gate check + I5/I7 → cache/version + I8
→ prompts/*.md → offline suite green → I9 calibration run (recorded, not blocking)
→ hand to reviewer model → approve → build
```

## Risks

- **Reviewer hallucination** is the main failure mode; I4 (span re-verification) is the mitigation and
  must not be weakened.
- **Cost**: one extra model pass per artifact. Prompt caching is Claude-only; the second provider does
  not benefit, so budget the coverage pass separately (summary/abstract only, not every artifact).
- **Drift**: if the independent model's label vocabulary shifts, the diff becomes noise. Pin the prompt
  and the label set in `config` (as the existing judges do).

## What is deliberately NOT in this spec

- No refactor of `call_claude_with_retry` / the Claude client path.
- No change to the existing judges' prompts, thresholds, or their blocking status.
- No new artifact type, no GUI change, no re-plumbing of `validate_headers`.
- No auto-fix / regeneration loop — the reviewer only reports; a FAIL still routes to human or the
  existing regenerate path.

## Blocking inputs (verify before build)

1. **Which provider/model + credential.** Default DeepSeek (key in `.env`, OpenAI-compatible). Confirm
   the actual key env var name and that `base_url=https://api.deepseek.com` is reachable from the run
   environment. If the intent is OpenAI/"Fable", an OpenAI key + base_url must be supplied. This is a
   config decision, not code.
2. **Decision D1–D5 confirmation**, especially D3 (advisory-first) and D4 (artifact scope).
