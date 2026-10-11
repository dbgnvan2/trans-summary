# Spec — Independent Adversarial Reviewer (second-model critical validator)

Status: **DRAFT v4 — review-1 + review-2 + review-3 changes folded** (not built; final)

Supersedes: `spec_independent_reviewer_2026-10-09-v3.md`. Review trail:
`review_independent_reviewer_2026-10-09.md`, `review_independent_reviewer_2026-10-09-2.md`,
`review_independent_reviewer_2026-10-09-3.md`.

Base: local `main`.

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

Two open questions map onto two reviewer modes:

1. **Q1 — "is all the text there?"** (large/full-file outputs) — already answered *deterministically*
   by `check_source_fidelity` (word-level diff vs raw, `release_gate.py:237`) +
   `transcript_validate_completeness`. Residual: a *semantic-coverage* gap on the **generative** large
   outputs (summary, abstract) — material findings the fixed `summary_coverage` checklist does not
   enumerate.
2. **Q2 — "are short outputs accurate?"** (abstract, summary, overview, blog) — already answered by
   the faithfulness judge, but on the *same model value* as the generator.

## What this adds

One isolated module that runs a **second, provider-independent model** over the *same deterministic
claim extraction* the Claude judge uses, in two modes. It reports its **own** re-verified findings; the
disagreement signal is read from the manifest, where the `faithfulness` and `independent_reviewer`
verdicts sit side by side — the check does **not** diff against Claude's cache (no coupling, no
prior-verdict injection). Scope is narrow: a *second opinion + coverage pass*, not a replacement judge,
not a new artifact generator.

## Decisions needed

**D1 — provider adapter (a).** New `independent_reviewer.py` owns its own OpenAI-compatible client.
Do **not** import or modify `transcript_utils.call_claude_with_retry`, `get_anthropic_client`, or any
Claude-judge *judging* function. (It may import the deterministic `faithfulness_judge.extract_claims` /
`chunk_source` / `route_claims_to_chunks` — shared claim extraction, see Design.)

**D2 — model/provider default.** DeepSeek, resolved from `~/.config/llm/keys.json` `providers.deepseek`
(confirmed present: `dialect: "openai"`, `base_url: "https://api.deepseek.com/v1"`,
`default_model: "deepseek-chat"`, `api_key`), with `DEEPSEEK_API_KEY` env as the first fallback.
Config defaults reflect this; OpenAI/"Fable" is a config swap, not a code change.

**D3 — advisory-first, and *never* a single point of failure.** `INDEPENDENT_REVIEWER_BLOCKING = False`
at launch (check returns WARN). It may be promoted to a blocker by adding `independent_reviewer` to
`config.GATE_BLOCKING_CHECKS` after D5 calibration — **but even then a reviewer failure returns WARN,
never ERROR-to-block.** Rationale: `run_gate` runs each check via `_safe` (`release_gate.py:96-105`),
which converts an *unhandled raise* into an `ERROR` verdict, and `GATE_ERROR_BLOCKS = True`
(`config.py:560`) blocks on ERROR from a blocking check. Therefore `check_independent_reviewer` wraps
its **entire body** in `try/except Exception` and returns WARN on any exception (`SystemExit` /
`KeyboardInterrupt` are intentionally not caught — they should propagate). The fail-open posture is
enforced in code, not left to `_safe`. Document this in the `GATE_BLOCKING_CHECKS` comment.

**D4 — artifact scope (v1).** Accuracy mode: `config.FAITHFULNESS_ARTIFACT_SUFFIXES` only (abstract,
summary, overview, blog). **Exclude** `TOPIC_TERM_FAITHFULNESS_SUFFIXES` from v1 — those artifacts are
themselves uncalibrated (`config.py:734`), so a second model over them is noise-on-noise. Coverage mode:
summary + abstract only. Headings on the formatted file stay with the existing `validate_headers` check.

**D5 — calibration before arming.** Reuse `tests/fixtures/faithfulness_gold/`. Measure precision/recall
against `config.FAITHFULNESS_MIN_RECALL_UNFAITHFUL = 0.90` / `config.FAITHFULNESS_MIN_PRECISION_UNFAITHFUL
= 0.70` (`config.py:742-743`). Arming requires a committed JSON run artifact (precision/recall + model +
`JUDGE_LOGIC_VERSION` at calibration time + date), not a terminal printout.

## Design (concrete touch points)

### New module `independent_reviewer.py`

- **Client**: OpenAI-compatible (`openai` SDK or raw HTTP), from `INDEPENDENT_REVIEWER_MODEL` /
  `INDEPENDENT_REVIEWER_BASE_URL` / key resolution. Own retry/timeout.
- **Truncation detection (pinned).** After each call, treat `finish_reason == "length"` (OpenAI-
  compatible) as a hard failure → ERROR path, never a silent partial. Add a test for the
  truncated-mid-JSON case.
- **Key resolution**: `DEEPSEEK_API_KEY` env var first, else `~/.config/llm/keys.json`
  `providers.deepseek.api_key` (snake_case `api_key`, same file + shape `resolve_anthropic_key` reads at
  `transcript_utils.py:89-93`). Reuse that file's `base_url` / `default_model` when config leaves them
  at the DeepSeek default.
- **Startup assertion**: `ENABLED=True` requires a non-empty `MODEL` **and** a resolvable key; either
  absent → loud failure at first use (not a mid-run API error).
- **Claims — shared deterministic extractor, re-invoked independently.** The reviewer calls
  `faithfulness_judge.extract_claims(artifact_text, source=source)` itself. `extract_claims` is a pure
  regex function (no LLM call — see its docstring), so this is free and produces the identical list the
  Claude judge's path produced, by construction. "Shared" means *same function*, not shared runtime
  state: there is no read of Claude's cache or intermediate output, and no coupling to the Claude
  judge's execution order. This is what makes the disagreement signal meaningful.
- **Chunked parity (both buckets).** `route_claims_to_chunks` returns `(routed, unrouted)`. The reviewer
  mirrors `judge_claims_chunked` (`faithfulness_judge.py:392`): routed claims → their window; unrouted
  claims → the **full source**; a routed claim the window does not entail → re-judged on the full source.
  The re-judge decision is governed by the *reviewer's own* window verdict, not Claude's. The reviewer
  passes its own threshold explicitly: `chunk_source(source, chunk_words=INDEPENDENT_REVIEWER_MIN_CHUNK_SOURCE_WORDS)`
  and makes its own `_should_chunk`-equivalent decision on that constant (so the constant is live, not
  dead config).
- **Two modes** (prompt templates under `prompts/` — confirmed at `config.PROMPTS_DIR =
  Path(__file__).parent / "prompts"`, `config.py:134`/`:327`):
  - `review_accuracy(claims, source)` → per-claim `{index, label, rationale, source_quote}`. Labels
    `entailed|contradicted|unsupported`. A non-entailed verdict **must** carry a `source_quote`.
  - `review_coverage(artifact, source)` → list of `{omitted, timestamp, materiality}` for summary/abstract.
    `timestamp` is **optional** (null allowed); when non-null it must match a source timestamp after
    normalization (below), else dropped. No timestamps in the source → `timestamp` is null everywhere.
- **Span re-verification (pinned).** Reuse `validation_pipeline._quote_word_coverage(quote, source) >=
  config.QUOTE_MIN_WORD_COVERAGE` (`config.py:1097`, the existing whole-quote coverage that catches an
  altered middle). Any non-entailed `source_quote` (accuracy) or `omitted` quote (coverage) below that
  threshold is dropped + logged — a reviewer that cannot anchor its objection is a reviewer error, not a
  finding.
- **Timestamp normalization (coverage only, pinned).** Before comparing, strip surrounding `[` `]` and
  leading zeros from each `HH:MM:SS` segment on both the reviewer's value and the source's
  `[HH:MM:SS]` markers; compare as normalized `HH:MM:SS`. This avoids silently dropping a legitimate
  timestamp that merely differs by bracket or zero-padding.
- **Label vocabulary (pinned).** Reuse the `_parse_judge_response` pattern (`faithfulness_judge.py:544`)
  with `valid_labels={entailed,contradicted,unsupported}`; a verdict whose label is not in the set is a
  parse error, never a silent pass.
- **Cache + logic version (upstream-safe, pinned call site).** Disk memo keyed on the sha256 of
  `(artifact-sha, source-sha, INDEPENDENT_REVIEWER_MODEL, INDEPENDENT_REVIEWER_LOGIC_VERSION,
  release_gate._judge_logic_version(reviewer_prompt_text))` — i.e. the reviewer passes its **own rendered
  prompt text** as `instructions` to `_judge_logic_version`, so upstream claim-extraction/config changes
  (which `_judge_logic_version` already hashes at `release_gate.py:594`) invalidate the cache
  automatically, while reviewer prompt changes are captured by the `instructions` argument. New constant
  `INDEPENDENT_REVIEWER_LOGIC_VERSION` (manual bump on any reviewer *code* change not captured above).
  ERROR never cached.

### `release_gate.py`

- New check `check_independent_reviewer(base_name, logger)` in `DEFAULT_CHECKS` (`release_gate.py:997`),
  inserted **immediately after the `("theme_grounding", check_theme_grounding)` entry** (so it runs
  after the Claude judges, before `required_artifacts`).
- **It reports its own findings only.** It calls `review_accuracy` (over `FAITHFULNESS_ARTIFACT_SUFFIXES`)
  + `review_coverage` (summary/abstract), re-verifies spans, and returns WARN with the re-verified
  non-entailed claims in `items` (the free-form `Verdict.items` list — no `Verdict` schema change).
  No comparison to Claude's cache, no prior-verdict parameter. The `faithfulness` verdict is recorded by
  the gate separately, so a reader of the manifest sees both verdicts side by side and reads agreement/
  disagreement directly — an artifact-level "co-flag" (both flagged the artifact) is *not* claim-level
  confirmation, and nothing in the check implies it is.
- Status mapping: any exception → WARN (fail-open, enforced by the self-catch); re-verified non-entailed
  claims → WARN while `INDEPENDENT_REVIEWER_BLOCKING=False`; not in `GATE_BLOCKING_CHECKS` until D5.
- `build_manifest` (`release_gate.py:1077`): extend `provenance.models` to add `faithfulness_judge`,
  `theme_judge`, `independent_reviewer`. Verified: the current `provenance.models` (`release_gate.py:1108-1112`)
  holds only `default`/`aux`/`validation` — judge models are absent, so this PR adds them for the first
  time (no duplicate-key risk).

### `config.py`

New constants (defaults reflect the confirmed DeepSeek provider):

```
INDEPENDENT_REVIEWER_ENABLED = False
INDEPENDENT_REVIEWER_BLOCKING = False
INDEPENDENT_REVIEWER_MODEL = "deepseek-chat"
INDEPENDENT_REVIEWER_BASE_URL = "https://api.deepseek.com/v1"
INDEPENDENT_REVIEWER_API_KEY_ENV = "DEEPSEEK_API_KEY"
INDEPENDENT_REVIEWER_MAX_TOKENS = 8192
INDEPENDENT_REVIEWER_MIN_CHUNK_SOURCE_WORDS = 3000   # reviewer's own threshold, passed explicitly to chunk_source
INDEPENDENT_REVIEWER_LOGIC_VERSION = "2026-10-09a"
```

No change to any existing constant.

### Prompts

Two templates under `prompts/`: `independent_reviewer_accuracy_v1.md` and
`independent_reviewer_coverage_v1.md`. Bodies: adversarial stance; judge only against the source; no
outside knowledge; tentative→settled escalation is unsupported; a claim naming a fabricated
name/place/date/quantity/cited-study/attribution is unsupported even with no proper noun; span citation
required on every non-entailed verdict (accuracy) and every omission (coverage).

## Acceptance criteria → tests

New `tests/test_independent_reviewer.py` + fixtures:

- **I1 — isolation.** Module constructs its own client from its own config only; no import of
  `call_claude_with_retry` / `get_anthropic_client` (mock the OpenAI-compatible client).
- **I2 — shared deterministic extractor.** The reviewer invokes `extract_claims(artifact_text, source)`
  itself; assert `extract_claims(artifact, source) == fixture_claims` (deterministic equality), and that
  the reviewer reads **no** Claude cache/verdict object.
- **I3 — fail-closed parse.** Malformed JSON / missing label / label outside
  `{entailed,contradicted,unsupported}` / missing `source_quote` on a non-entailed verdict → ERROR.
- **I4 — span re-verification.** A `contradicted` verdict whose `source_quote` scores below
  `QUOTE_MIN_WORD_COVERAGE` is dropped + logged, not counted as a finding.
- **I5 — chunked parity.** `unrouted` claims judged against full source; a routed claim the window does
  not entail is re-judged on full source, on the *reviewer's own* verdict (mirror `judge_claims_chunked`).
- **I6 — coverage mode.** `review_coverage` returns only substance-level omissions; `timestamp` optional;
  a non-null `timestamp` that fails *normalized* matching against source `[HH:MM:SS]` markers is dropped;
  malformed output → ERROR; `finish_reason == "length"` → ERROR (truncation, not silent partial).
- **I7 — gate wiring.** `check_independent_reviewer` returns WARN (never ERROR/BLOCK) on reviewer
  failure AND while `INDEPENDENT_REVIEWER_BLOCKING=False`; its re-verified findings appear in `items`.
- **I8 — fail-open under `_safe`.** A simulated exception raised *inside* `check_independent_reviewer`
  is caught and returns WARN, so `_safe` never sees it (guards the promoted-to-blocker case).
- **I9 — cache/version.** Bumping `INDEPENDENT_REVIEWER_LOGIC_VERSION` OR changing the reviewer's prompt
  text (the `instructions` arg to `_judge_logic_version`) OR a change to the hashed claim-extraction
  material invalidates the cached verdict; ERROR not cached.
- **I10 — key resolution.** Env var absent → `keys.json` `providers.deepseek.api_key`; both absent +
  `ENABLED=True` → loud failure. Empty `INDEPENDENT_REVIEWER_MODEL` + `ENABLED=True` → loud failure.
- **I11 — scope.** The reviewer is not invoked on `TOPIC_TERM_FAITHFULNESS_SUFFIXES` artifacts in v1.

Calibration harness (not a unit test): `scripts/calibrate_independent_reviewer.py` runs `review_accuracy`
over `tests/fixtures/faithfulness_gold/`, writes a committed JSON artifact (precision/recall + model +
`JUDGE_LOGIC_VERSION` + date). Live-API; never under `tests/`.

## Order

```
config constants → independent_reviewer.py (client + key resolution + truncation + accuracy + chunked
parity) → I1–I5 → coverage mode + timestamp normalization + I6 → release_gate check + I7/I8
→ cache/version + I9 → key resolution + I10 → scope I11 → prompts/*.md → offline suite green
→ scripts/calibrate_independent_reviewer.py (recorded, not blocking) → hand to reviewer model → approve → build
```

## Risks

- **Reviewer hallucination** is the main failure mode; I4 (span re-verification) is the mitigation.
- **Cost**: one extra model pass over `FAITHFULNESS_ARTIFACT_SUFFIXES` (4 artifacts) + summary/abstract
  coverage (2). DeepSeek cost is negligible; token ceiling is `INDEPENDENT_REVIEWER_MAX_TOKENS`. No prompt
  caching on the second provider (Claude-only); bounded by artifact scope, not cache.
- **Provider drift**: pinned prompt + pinned label set + `INDEPENDENT_REVIEWER_LOGIC_VERSION` bump policy
  + upstream `_judge_logic_version` fold-in (I3/I9 enforce).
- **Sequential execution**: `run_gate` runs checks sequentially (`release_gate.py:1017`); the reviewer
  check introduces no parallelism, so the disk cache gains no new concurrency surface.

## What is deliberately NOT in this spec

- No refactor of `call_claude_with_retry` / the Claude client path.
- No change to existing judges' prompts, thresholds, or blocking status.
- No new artifact type, no GUI change, no re-plumbing of `validate_headers`.
- No auto-fix / regeneration loop — the reviewer only reports; a FAIL routes to human or the existing
  regenerate path.
- No `TOPIC_TERM_FAITHFULNESS_SUFFIXES` coverage in v1 (uncalibrated source artifacts).
- No claim-level diff against the Claude judge — the check reports its own findings; agreement is read
  from the manifest.

## Blocking inputs (verify before build)

1. **Provider/model + key** — confirmed: `providers.deepseek` in `~/.config/llm/keys.json`
   (`dialect:"openai"`, `base_url:"https://api.deepseek.com/v1"`, `default_model:"deepseek-chat"`,
   `api_key` present); `DEEPSEEK_API_KEY` also in `~/.hermes/.env` and `~/.zshrc`. Confirm
   `https://api.deepseek.com/v1` is reachable from the run environment.
2. **Decision D1–D5 confirmation**, especially D3 (fail-open even when armed) and D4 (artifact scope).
