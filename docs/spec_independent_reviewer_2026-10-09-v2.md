# Spec — Independent Adversarial Reviewer (second-model critical validator)

Status: **DRAFT v2 — review-1 changes folded** (not built)

Supersedes: `spec_independent_reviewer_2026-10-09.md` (v1). Review trail: `review_independent_reviewer_2026-10-09.md`.

Base: local `main`. Do not push until this v2 is reviewed + approved.

## Problem

The pipeline already runs a critical reviewer, but it is not **independent of the generator**.
Three *separate* constants (`config.py:46`, `:630`, `:756`) currently hold the same value
`claude-sonnet-4-6`:

- `config.DEFAULT_MODEL = "claude-sonnet-4-6"` (generation)
- `config.FAITHFULNESS_JUDGE_MODEL = "claude-sonnet-4-6"` (accuracy judge)
- `config.THEME_JUDGE_MODEL = "claude-sonnet-4-6"` (theme judge)

The separation is intentional (`config.py:621-624`: the judge model is a *named* constant so a
`DEFAULT_MODEL` bump can't silently move the armed judge). The gap is that all three currently hold
the *same value* — a same-family reviewer shares the generator's blind spots (the original
"Luciano Malorni" ship was a fluent hallucination the same model could not see).

The user's two open questions map onto two reviewer modes:

1. **Q1 — "is all the text there?"** (large/full-file outputs) — already answered *deterministically*
   by `check_source_fidelity` (word-level diff vs raw, `release_gate.py:237`) +
   `transcript_validate_completeness`. Residual: a *semantic-coverage* gap on the **generative** large
   outputs (summary, abstract) — material findings the fixed `summary_coverage` checklist does not
   enumerate.
2. **Q2 — "are short outputs accurate?"** (abstract, summary, overview, blog) — already answered by
   the faithfulness judge, but on the *same model value* as the generator.

## What this adds

One isolated module that runs a **second, provider-independent model** over the *same claims, same
source, same chunking* the Claude judge already uses, in two modes, and reports agreement/disagreement
against the Claude verdicts **at the artifact level** (not claim-level cache coupling — see Design).
Disagreement is the deliverable: where a second model independently concurs with a FAIL, confidence
rises; where the two models split, that artifact is flagged for review.

Scope is deliberately narrow: a *second opinion + coverage pass*, not a replacement judge and not a
new artifact generator.

## Decisions needed

**D1 — provider adapter (a).** New `independent_reviewer.py` owns its own OpenAI-compatible client
(base_url + model + key). Do **not** import or modify `transcript_utils.call_claude_with_retry`,
`get_anthropic_client`, or any Claude-judge function (isolation invariant; the Claude path is
load-bearing and calibrated).

**D2 — model/provider default.** `INDEPENDENT_REVIEWER_MODEL`, `INDEPENDENT_REVIEWER_BASE_URL`,
`INDEPENDENT_REVIEWER_API_KEY_ENV`. Default = DeepSeek (`base_url="https://api.deepseek.com"`,
`INDEPENDENT_REVIEWER_API_KEY_ENV="DEEPSEEK_API_KEY"`). Key is resolved the same way
`resolve_anthropic_key` works (`transcript_utils.py:67`): env var first, then
`~/.config/llm/keys.json` `providers.deepseek` (both confirmed present). A startup assertion fails
loudly when `INDEPENDENT_REVIEWER_ENABLED=True` and no key resolves. OpenAI/"Fable" is a config swap,
not a code change.

**D3 — the reviewer is advisory; and never a single point of failure.** `INDEPENDENT_REVIEWER_BLOCKING
= False` at launch (check returns WARN). It may later be promoted to a blocker by adding
`independent_reviewer` to `config.GATE_BLOCKING_CHECKS` after D5 calibration — **but even then a
reviewer ERROR is downgraded to WARN, never ERROR-to-block.** `GATE_ERROR_BLOCKS = True`
(`config.py:560`) would otherwise turn a DeepSeek outage into a hard publication stop. The
`check_independent_reviewer` implementation catches its own failures and returns WARN, so the
fail-open posture is enforced in code, not by policy review. Document this in the `GATE_BLOCKING_CHECKS`
comment.

**D4 — artifact scope (v1).** Accuracy mode: `config.FAITHFULNESS_ARTIFACT_SUFFIXES` only (abstract,
summary, overview, blog). **Exclude** `TOPIC_TERM_FAITHFULNESS_SUFFIXES` from v1 — those artifacts
are themselves uncalibrated (`config.py:734` note), so a second model over them is noise-on-noise.
Coverage mode: summary + abstract only. Headings on the formatted file stay with the existing
`validate_headers` check and are not re-covered here.

**D5 — calibration before arming.** Reuse `tests/fixtures/faithfulness_gold/`. Measure the independent
model's precision/recall against `config.FAITHFULNESS_MIN_RECALL_UNFAITHFUL = 0.90` /
`FAITHFULNESS_MIN_PRECISION_UNFAITHFUL = 0.70` (`config.py:742-743`). Arming requires a committed
run artifact (JSON: precision/recall + model + date), not a terminal printout.

## Design (concrete touch points)

### New module `independent_reviewer.py`

- **Client**: OpenAI-compatible (`openai` SDK or raw HTTP to `base_url`). Own retry/timeout +
  truncation check. Fail-closed internally: API/parse error raises (the *gate* downgrades to WARN).
- **Claims are shared, not re-derived.** Import `faithfulness_judge.extract_claims`,
  `chunk_source`, `route_claims_to_chunks`. Same claims, same source, same chunking — otherwise the
  disagreement signal is noise.
- **Chunking mirrors the Claude judge exactly** (`faithfulness_judge.py:392` `judge_claims_chunked`):
  `route_claims_to_chunks` returns `(routed, unrouted)`; routed claims are judged against their
  window, **unrouted claims against the full source**, and a routed claim the window does not entail
  is re-judged against the full source. The reviewer implements the same flow with its own model;
  both buckets are handled.
- **Two modes** (prompts as files under `prompts/`, matching `config.PROMPTS_DIR`):
  - `review_accuracy(claims, source)` → per-claim `{index, label, rationale, source_quote}`. Labels
    `entailed|contradicted|unsupported`. A non-entailed verdict **must** carry a `source_quote`.
  - `review_coverage(artifact, source)` → list of `{omitted, timestamp, materiality}` for
    summary/abstract only.
- **Span re-verification (pinned).** Reuse `validation_pipeline._quote_word_coverage(quote, source)
  >= config.QUOTE_MIN_WORD_COVERAGE` (`config.py:1062`, the existing whole-quote coverage that catches
  an altered middle). A `contradicted`/`unsupported` verdict whose `source_quote` scores below that
  threshold is dropped and logged — a reviewer that cannot anchor its objection is a reviewer error,
  not a finding.
- **Label vocabulary (pinned).** Reuse the `_parse_judge_response` pattern (`faithfulness_judge.py:544`)
  with an explicit `valid_labels={entailed,contradicted,unsupported}`; any verdict whose label is not
  in the set is a parse error, never a silent pass.
- **Cache + logic version.** Disk memo keyed on `(artifact-sha, source-sha, INDEPENDENT_REVIEWER_MODEL,
  INDEPENDENT_REVIEWER_LOGIC_VERSION-hash)`, mirroring `release_gate._judge_logic_version`
  (`release_gate.py:594`). New config constant `INDEPENDENT_REVIEWER_LOGIC_VERSION` (bumped on any
  reviewer prompt/code/threshold change). ERROR never cached.

### `release_gate.py`

- New check `check_independent_reviewer(base_name, logger)` in `DEFAULT_CHECKS` (`release_gate.py:997`),
  positioned **after** `check_faithfulness` and `check_theme_grounding` so the Claude verdicts it
  compares against are already in the gate's verdict list.
- **Diff is at the artifact level, no cache coupling.** The check calls `review_accuracy`/`review_coverage`
  independently and compares: "reviewer flagged ≥1 re-verified non-entailed claim in artifact X" vs
  "the `faithfulness` verdict for artifact X is FAIL" (read from the aggregate verdict list the gate
  already holds — no per-claim cache read, no new accessor). Concurrence vs split is recorded in the
  check's `items` (the `Verdict.items` list is already free-form; no `Verdict` schema change).
- Status mapping: reviewer failure → WARN (fail-open, enforced here); reviewer found a re-verified
  non-entailed claim → WARN while `INDEPENDENT_REVIEWER_BLOCKING=False`; not in `GATE_BLOCKING_CHECKS`
  until D5. No new manifest field beyond the existing per-check verdict record.
- `build_manifest` (`release_gate.py:1077`): extend `provenance.models` to add `faithfulness_judge`,
  `theme_judge`, `independent_reviewer` (judge models are currently **absent** from the manifest —
  this PR adds them for the first time).

### `config.py`

New constants, all defaulted so the feature is inert until wired:

```
INDEPENDENT_REVIEWER_ENABLED = False
INDEPENDENT_REVIEWER_BLOCKING = False
INDEPENDENT_REVIEWER_MODEL = ""            # e.g. "deepseek-chat"
INDEPENDENT_REVIEWER_BASE_URL = "https://api.deepseek.com"
INDEPENDENT_REVIEWER_API_KEY_ENV = "DEEPSEEK_API_KEY"
INDEPENDENT_REVIEWER_MAX_TOKENS = 8192
INDEPENDENT_REVIEWER_MIN_CHUNK_SOURCE_WORDS = 3000   # reuse the Claude judge's threshold value
INDEPENDENT_REVIEWER_LOGIC_VERSION = "2026-10-09a"
```

No change to any existing constant.

### Prompts

Two templates under `prompts/`: `independent_reviewer_accuracy_v1.md` and
`independent_reviewer_coverage_v1.md`. Bodies: adversarial stance; judge only against the source; no
outside knowledge; tentative→settled escalation is unsupported; a claim naming a fabricated
name/place/date/quantity/cited-study/attribution is unsupported even with no proper noun; span
citation required on every non-entailed verdict.

## Acceptance criteria → tests

New `tests/test_independent_reviewer.py` + fixtures:

- **I1 — isolation.** Module constructs its own client from its own config only; no import of
  `call_claude_with_retry` / `get_anthropic_client` (mock the OpenAI-compatible client).
- **I2 — shared claims.** `review_accuracy` receives the *identical* claim list the Claude judge
  produced (fixture artifact; assert equality, not re-extraction).
- **I3 — fail-closed parse.** Malformed JSON / missing label / label outside
  `{entailed,contradicted,unsupported}` / missing `source_quote` on a non-entailed verdict → ERROR.
- **I4 — span re-verification.** A `contradicted` verdict whose `source_quote` scores below
  `QUOTE_MIN_WORD_COVERAGE` is dropped + logged, not counted as a finding.
- **I5 — chunked parity.** `unrouted` claims are judged against the full source; a routed claim the
  window does not entail is re-judged on the full source (mirror `judge_claims_chunked`).
- **I6 — diff semantics.** Claude FAIL + reviewer non-entailed → concurrence; Claude PASS + reviewer
  non-entailed → split; Claude FAIL + reviewer all-entailed → split. All recorded in `items`.
- **I7 — coverage mode.** `review_coverage` returns only substance-level omissions; malformed output
  → ERROR.
- **I8 — gate wiring.** `check_independent_reviewer` returns WARN (never BLOCK) on reviewer failure
  AND while `INDEPENDENT_REVIEWER_BLOCKING=False`; appears in the manifest with its model.
- **I9 — cache/version.** Bumping `INDEPENDENT_REVIEWER_LOGIC_VERSION` or the prompt text invalidates
  the cached verdict; ERROR not cached.
- **I10 — key resolution.** Env var absent → falls back to `~/.config/llm/keys.json` `providers.deepseek`;
  both absent + `ENABLED=True` → loud failure.

Calibration harness (not a unit test): `scripts/calibrate_independent_reviewer.py` runs
`review_accuracy` over `tests/fixtures/faithfulness_gold/`, writes a committed JSON artifact
(precision/recall + model + date). Live-API; never under `tests/`.

## Order

```
config constants → independent_reviewer.py (client + accuracy + chunked parity) → I1–I5
→ coverage mode + I7 → release_gate check + I6/I8 → cache/version + I9 → key resolution + I10
→ prompts/*.md → offline suite green → scripts/calibrate_independent_reviewer.py (recorded, not blocking)
→ hand to reviewer model → approve → build
```

## Risks

- **Reviewer hallucination** is the main failure mode; I4 (span re-verification) is the mitigation.
- **Cost**: one extra model pass over `FAITHFULNESS_ARTIFACT_SUFFIXES` (4 artifacts) + summary/abstract
  coverage. DeepSeek cost is negligible; the coverage pass is bounded to 2 artifacts; token ceiling
  is `INDEPENDENT_REVIEWER_MAX_TOKENS`. No prompt caching on the second provider (Claude-only) — budgeted
  by the artifact scope, not by cache.
- **Provider drift**: pinned prompt + pinned label set + `INDEPENDENT_REVIEWER_LOGIC_VERSION` bump policy
  (I3/I9 enforce).
- **Sequential execution**: `run_gate` runs checks sequentially (`release_gate.py:1017`); the reviewer
  check introduces no parallelism, so the existing disk-cache has no new concurrency surface.

## What is deliberately NOT in this spec

- No refactor of `call_claude_with_retry` / the Claude client path.
- No change to existing judges' prompts, thresholds, or blocking status.
- No new artifact type, no GUI change, no re-plumbing of `validate_headers`.
- No auto-fix / regeneration loop — the reviewer only reports; a FAIL routes to human or the existing
  regenerate path.
- No `TOPIC_TERM_FAITHFULNESS_SUFFIXES` coverage in v1 (uncalibrated source artifacts).
- No claim-level cache coupling between the reviewer and the Claude judge.

## Blocking inputs (verify before build)

1. **Provider/model + key** — confirmed: `DEEPSEEK_API_KEY` in `~/.hermes/.env` and `~/.zshrc`;
   `deepseek` provider in `~/.config/llm/keys.json`. Confirm the DeepSeek model id to use
   (e.g. `deepseek-chat`) and that `https://api.deepseek.com` is reachable from the run environment.
2. **Decision D1–D5 confirmation**, especially D3 (fail-open even when armed) and D4 (artifact scope).
