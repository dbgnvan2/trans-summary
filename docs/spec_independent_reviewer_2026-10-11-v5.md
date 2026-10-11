# Spec — Independent Adversarial Reviewer (second-model critical validator)

Status: **v5 — ON HOLD (not built).** D6 decided 2026-10-11: public sources only. The
Step 0 experiment (`docs/calibration/independent_reviewer_experiment_2026-10-11/`) found
DeepSeek v4-pro caught none of the cases Sonnet 5.5 missed, at lower recall (0.69–0.77
vs 0.85–0.92) and with two false warnings per run on a clean abstract. Critical review:
`docs/review_independent_reviewer_2026-10-11.md`. Building waits on a decision.

Supersedes: `spec_independent_reviewer_2026-10-09-v4.md` (review trail: the three
`review_independent_reviewer_2026-10-09*.md` reports). Implementation plan:
`docs/plan_independent_reviewer_2026-10-11.md`.

## Changes from v4 (2026-10-11)

| # | v4 | v5 | Why |
|---|---|---|---|
| C1 | Model `deepseek-chat` | `deepseek-v4-pro` | The DeepSeek `/models` list for the configured key (checked 2026-10-11) offers only `deepseek-flash` and `deepseek-v4-pro`. Decision: v4-pro. |
| C2 | Problem: all three model constants hold `claude-sonnet-4-6` | Judges are `claude-sonnet-5-5` (re-calibrated 2026-10-10); generation is the GUI's choice | The cross-provider argument still holds: any Claude judge shares the Claude generator's family. |
| C3 | Accuracy scope: abstract, summary, overview, **blog** | abstract, summary, overview (`FAITHFULNESS_ARTIFACT_SUFFIXES` as it is now) | RF.N moved the blog to its own advisory `blog_faithfulness` check. Decision: leave the blog out. |
| C4 | Client: `openai` SDK or raw HTTP | `openai` SDK, pinned in `requirements.txt` | Decision. |
| C5 | Span check: `_quote_word_coverage >= QUOTE_MIN_WORD_COVERAGE` | `validation_pipeline.quote_is_verbatim_for_gate` | The gate's own verbatim rule since RF.K (disfluencies, curly quotes); the reviewer must not reject quotes the gate accepts. Decision. |
| C6 | — | **Per-project consent** before any text leaves for DeepSeek (I12) | Decision: transcripts can hold personal/clinical material. |
| C7 | — | Calibration sends only gold sources marked external-OK (D6) | The `dave_g` fixture is a clinical case presentation. |
| C8 | Read `keys.json` directly | Key through the shared `global-api-config` module (`llm_providers.get_provider("deepseek")`), loaded by file path | Decision 2026-10-11 ("get api keys via the attached folder"). Same pattern as AvsB-Finder's `shared_keys.py`. |

## Problem

The armed judges (faithfulness, theme grounding) run on `claude-sonnet-5-5`; the
generator runs on whatever Claude model the GUI selects. A judge from the same family
as the generator can share its blind spots (the original "Luciano Malorni" ship was a
fluent hallucination the same model could not see). A reviewer from a different
provider gives a second, independent opinion.

1. **Q1 — "is all the text there?"** — answered deterministically by
   `check_source_fidelity` + completeness checks. Residual: a semantic-coverage gap on
   the generative summary and abstract (material the `summary_coverage` checklist does
   not enumerate).
2. **Q2 — "are short outputs accurate?"** — answered by the faithfulness judge, on a
   Claude model.

## What this adds

One isolated module that runs a **second, provider-independent model** over the same
deterministic claim extraction the Claude judge uses, in two modes (accuracy,
coverage). It reports its own re-verified findings; agreement with the Claude judge is
read from the manifest, where both verdicts sit side by side. No coupling to the Claude
judge's cache, no prior-verdict injection. Advisory: a second opinion and coverage
pass, not a replacement judge, not a generator.

## Decisions

- **D1 — isolation.** New `independent_reviewer.py` owns its own OpenAI-compatible
  client (`openai` SDK). Do not import or modify `transcript_utils.call_claude_with_retry`,
  `get_anthropic_client`, or any Claude judge's judging function, prompt, threshold or
  blocking status. It may import the deterministic `faithfulness_judge.extract_claims` /
  `chunk_source` / `route_claims_to_chunks` and `_parse_judge_response` (pure parsing).
- **D2 — provider and key (C8).** DeepSeek `deepseek-v4-pro`. Key: `DEEPSEEK_API_KEY`
  env first, else the shared key store through `global-api-config/llm_providers.py`
  (`get_provider(INDEPENDENT_REVIEWER_PROVIDER)`), loaded by file path from
  `$GLOBAL_API_CONFIG_DIR` when set (and then only there), else
  `~/ProjectsLocal/global-api-config` (new `shared_keys.py`, modelled on AvsB-Finder's).
  Only the key and `base_url` come from the store; the provider must have dialect
  `openai`. The **model stays pinned** in `config.INDEPENDENT_REVIEWER_MODEL` (the store's
  `default_model` for deepseek is the retired `deepseek-chat`). Store missing, module
  unloadable, provider absent or empty key → None with a logged reason (never the key
  value). Another OpenAI-compatible provider is a config change. The Anthropic key path
  (`resolve_anthropic_key`) is not changed.
- **D3 — advisory, never a single point of failure.** `INDEPENDENT_REVIEWER_BLOCKING =
  False`; the check returns WARN on findings. Even if later promoted to
  `GATE_BLOCKING_CHECKS`, a reviewer failure returns WARN, never ERROR: the check wraps
  its whole body in `try/except Exception` (so `release_gate._safe` never converts a
  raise into a blocking ERROR). `SystemExit` / `KeyboardInterrupt` propagate.
- **D4 — scope (v1).** Accuracy: `config.FAITHFULNESS_ARTIFACT_SUFFIXES` (abstract,
  summary, overview). Coverage: summary + abstract. Not the blog, not
  `TOPIC_TERM_FAITHFULNESS_SUFFIXES` (uncalibrated sources), not headings.
- **D5 — calibration before arming.** Gold set `tests/fixtures/faithfulness_gold/`,
  bars `FAITHFULNESS_MIN_RECALL_UNFAITHFUL = 0.90` / `FAITHFULNESS_MIN_PRECISION_UNFAITHFUL
  = 0.70`. Arming needs a committed JSON artifact (precision/recall, model,
  `INDEPENDENT_REVIEWER_LOGIC_VERSION`, `JUDGE_LOGIC_VERSION`, date, sources used).
- **D6 — calibration data sent externally (DECIDED 2026-10-11: public only).** Gold sources: `dave_g` (clinical
  case presentation, 20 of 43 cases, 9 of 23 unfaithful), `where_roots`, `roots_bowen`,
  `kerr_families` (public talks, 23 cases, 13 unfaithful). `gold.json` gets a per-source
  `external_ok` flag; the calibration script sends only `external_ok` sources and records
  which ones it used. Proposed: public talks only (`dave_g` false). With 13 unfaithful
  cases, one miss = recall 0.92, two = 0.85, so the bar is coarse; say if `dave_g` may go.
- **D7 — per-project consent (I12).** No project text goes to the external provider
  unless that project has opted in. Consent lives in `<base> - external-review.json`
  (`{"allow_external_review": true, "provider": "deepseek", "set_at": <ISO>}`), written
  only by the GUI checkbox (or by hand). Absent, unreadable or false → not allowed. The
  check then returns PASS "not run: external review not allowed for this project"
  (the convention disabled judges already use). The consent check sits in
  `independent_reviewer` itself, before any client call, so no caller can skip it.

## Design

### `independent_reviewer.py`

- **Client:** `openai.OpenAI(base_url=…, api_key=…, timeout=…, max_retries=0)`; own
  retry with backoff on rate-limit / 5xx / timeout / connection errors
  (`INDEPENDENT_REVIEWER_MAX_RETRIES`, `INDEPENDENT_REVIEWER_TIMEOUT`); 4xx other than
  429 is not retried.
- **Truncation:** `finish_reason == "length"` → error, never a partial result.
- **Startup assertion:** `ENABLED=True` with an empty `MODEL` or no resolvable key →
  `IndependentReviewerConfigError` at first use, naming what is missing (never the key).
- **Claims:** the module calls `extract_claims(artifact_text, source=source)` itself;
  no read of the Claude judge's cache or verdicts.
- **Chunked parity:** mirrors `judge_claims_chunked`: chunk when the source exceeds
  `INDEPENDENT_REVIEWER_MIN_CHUNK_SOURCE_WORDS`; routed claims → their window, unrouted →
  full source; a routed claim the window does not entail → re-judged on the full source,
  on the reviewer's own window verdict.
- **Accuracy mode** `review_accuracy(claims, source)` → per claim `{index, label,
  rationale, source_quote}`; labels `entailed|contradicted|unsupported` (parsed with
  `_parse_judge_response`, `valid_labels` pinned; any other label is a parse error); a
  non-entailed verdict must carry `source_quote`.
- **Coverage mode** `review_coverage(artifact, source)` → `[{omitted, timestamp,
  materiality}]`; `timestamp` optional; a non-null timestamp must match a source
  `[HH:MM:SS]` marker after normalization (strip brackets, compare zero-padded
  `HH:MM:SS`), else the item is dropped and logged.
- **Span re-verification (C5):** a non-entailed `source_quote` or an `omitted` quote
  that fails `quote_is_verbatim_for_gate(quote, source)` is dropped and logged ("N of M
  dropped"); a reviewer that cannot anchor its objection is a reviewer error, not a
  finding.
- **Cache:** disk memo in `config.LOGS_DIR`, key = sha256 of (artifact sha, source sha,
  model, `INDEPENDENT_REVIEWER_LOGIC_VERSION`, `release_gate._judge_logic_version(<the
  reviewer's rendered prompt text>)`). Errors are never cached.

### `release_gate.py`

- `check_independent_reviewer(base_name, logger)` inserted in `DEFAULT_CHECKS` right
  after `("theme_grounding", check_theme_grounding)`.
- Order inside the check: global `ENABLED` off → PASS "disabled"; consent absent → PASS
  "not run: …"; else review, re-verify, return PASS (no findings) or WARN with findings in
  `items` and "N dropped (unanchored)" in the detail. Any exception → WARN.
- Not in `GATE_BLOCKING_CHECKS`; the `GATE_BLOCKING_CHECKS` comment records D3.
- `build_manifest`: `provenance.models` gains `faithfulness_judge`, `theme_judge`,
  `independent_reviewer` (the last only when it ran).

### `config.py` (new constants only; no existing constant changes)

```
INDEPENDENT_REVIEWER_ENABLED = False
INDEPENDENT_REVIEWER_BLOCKING = False
INDEPENDENT_REVIEWER_PROVIDER = "deepseek"            # keys.json providers.<name>
INDEPENDENT_REVIEWER_MODEL = "deepseek-v4-pro"
INDEPENDENT_REVIEWER_BASE_URL = "https://api.deepseek.com/v1"
INDEPENDENT_REVIEWER_API_KEY_ENV = "DEEPSEEK_API_KEY"
INDEPENDENT_REVIEWER_MAX_TOKENS = 8192
INDEPENDENT_REVIEWER_TIMEOUT = 120
INDEPENDENT_REVIEWER_MAX_RETRIES = 3
INDEPENDENT_REVIEWER_MIN_CHUNK_SOURCE_WORDS = 3000
INDEPENDENT_REVIEWER_LOGIC_VERSION = "2026-10-11a"
SUFFIX_EXTERNAL_REVIEW_CONSENT = " - external-review.json"
```

### GUI (`ts_gui.py`) — the one GUI change

A checkbox "Allow external review (DeepSeek) for this project", bound to the selected
project: reads the consent file when the selection changes, writes it on toggle. Off by
default. Follows `~/.claude/standards/ui-regression.md`.

### Prompts

`prompts/independent_reviewer_accuracy_v1.md`, `prompts/independent_reviewer_coverage_v1.md`:
adversarial stance; judge only against the source; no outside knowledge;
tentative→settled is unsupported; a fabricated name/place/date/quantity/study/attribution
is unsupported; a span citation on every non-entailed verdict and every omission.

## Acceptance criteria

- **I1 isolation** — own client from own config; `call_claude_with_retry` /
  `get_anthropic_client` are never imported or called.
- **I2 shared extractor** — the reviewer calls `extract_claims` itself and reads no
  Claude cache/verdict.
- **I3 fail-closed parse** — malformed JSON, missing label, label outside the set, or a
  non-entailed verdict without `source_quote` → error.
- **I4 span re-verification** — an unanchored non-entailed quote is dropped and logged,
  not counted; an anchored one with curly quotes / disfluencies is kept (C5).
- **I5 chunked parity** — unrouted → full source; window-not-entailed → re-judged on the
  full source on the reviewer's own verdict.
- **I6 coverage** — optional timestamp; non-matching normalized timestamp dropped;
  malformed → error; `finish_reason == "length"` → error.
- **I7 gate wiring** — WARN (never ERROR/BLOCK) on failure and on findings; findings in
  `items`.
- **I8 fail-open under `_safe`** — an exception inside the check returns WARN.
- **I9 cache/version** — logic-version bump, prompt-text change or claim-extraction
  change invalidates; errors not cached.
- **I10 key resolution** — env → shared store via `llm_providers` (file-path load,
  `$GLOBAL_API_CONFIG_DIR` honoured); non-`openai` dialect, missing store or empty key →
  None with a reason; no key, or an empty model, with `ENABLED=True` → loud config error.
  The model never comes from the store.
- **I11 scope** — never invoked on the blog or `TOPIC_TERM_FAITHFULNESS_SUFFIXES`.
- **I12 consent** — no client is constructed and no request is sent for a project
  without consent (absent / false / unreadable file); the GUI checkbox writes and reads
  the file for the selected project.
- **I13 isolation regression** — `tests/test_faithfulness_judge.py`,
  `tests/test_judge_routing_j.py`, `tests/test_release_gate.py` pass unchanged.
- **I14 calibration** — `scripts/calibrate_independent_reviewer.py` (live, not under
  `tests/`) sends only `external_ok` gold sources and commits
  `docs/calibration/independent_reviewer_<date>.json`.

## Not in this spec

No refactor of the Claude client path; no change to existing judges; no new artifact
type; no auto-fix loop; no blog or topic/term coverage; no claim-level diff against the
Claude judge.
