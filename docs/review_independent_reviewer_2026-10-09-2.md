# Independent Review — Spec v2 (`independent_reviewer`)

---

## 1. FACTUAL ERRORS

### F1 — `config.py` line references for judge constants are wrong (RESIDUAL)

The spec states:
> "Three *separate* constants (`config.py:46`, `:630`, `:756`) currently hold the same value `claude-sonnet-4-6`"

- `config.py:46` → `self.DEFAULT_MODEL = "claude-sonnet-4-6"` ✓
- `config.py:630` → `FAITHFULNESS_JUDGE_MODEL = "claude-sonnet-4-6"` ✓
- `config.py:756` → `THEME_JUDGE_MODEL = "claude-sonnet-4-6"` ✓

These are correct. **Not an error.**

### F2 — `config.py:621-624` mis-cited (RESIDUAL)

The spec states:
> "`config.py:621-624`: the judge model is a *named* constant so a `DEFAULT_MODEL` bump can't silently move the armed judge"

Source shows lines 621-624:
```
# Judge model: a SEPARATE named constant (NOT aliased to DEFAULT_MODEL) so a central
# DEFAULT_MODEL bump can't silently move the armed judge onto an un-recalibrated model
# (P6: the arming decision trusts a calibration artifact tied to this model). NOTE
# (H12): Anthropic publishes NO dated snapshot...
```
Correct. **Not an error.**

### F3 — `release_gate.py:237` cited for `check_source_fidelity` word-level diff (RESIDUAL)

The spec states:
> "already answered *deterministically* by `check_source_fidelity` (word-level diff vs raw, `release_gate.py:237`)"

The source excerpts do not include line 237 of `release_gate.py`. The function `check_source_fidelity` is not shown in the grep output (only signatures from line 540 onward are shown). **Cannot verify.** The line number claim is unverifiable from provided source. Mark as **UNVERIFIABLE / RESIDUAL RISK** — not confirmed resolved.

### F4 — `release_gate.py:997` cited as location of `DEFAULT_CHECKS` (NEW)

The spec states:
> "New check `check_independent_reviewer(base_name, logger)` in `DEFAULT_CHECKS` (`release_gate.py:997`)"

Source shows `DEFAULT_CHECKS` begins at **line 997**: `DEFAULT_CHECKS: list = [` ✓

The spec says the new check is "positioned **after** `check_faithfulness` and `check_theme_grounding`". In the actual `DEFAULT_CHECKS` at `release_gate.py:997–1011`, `check_theme_grounding` is at position 6 (index 5). The new check would be inserted after line 1003. This is a design statement, not a factual error, but the line number is close enough to verify: **no error here.**

### F5 — `release_gate.py:1077` cited for `build_manifest` (NEW)

The spec states:
> "`build_manifest` (`release_gate.py:1077`)"

Source shows `build_manifest` at line **1077**: ✓ matches.

### F6 — `INDEPENDENT_REVIEWER_MIN_CHUNK_SOURCE_WORDS` stated to "reuse the Claude judge's threshold value" of 3000 — value is correct but the comment is misleading (NEW)

The spec states:
> `INDEPENDENT_REVIEWER_MIN_CHUNK_SOURCE_WORDS = 3000   # reuse the Claude judge's threshold value`

Source confirms `FAITHFULNESS_JUDGE_MIN_CHUNK_SOURCE_WORDS = 3000` at `config.py:668`. The value is correct. However, the spec assigns this as a *separate constant* with the same default value — this is fine by design (D1 isolation) — but then the Design section says:

> "Claims are shared, not re-derived. Import `faithfulness_judge.extract_claims`, `chunk_source`, `route_claims_to_chunks`."

If the reviewer *imports and calls* `faithfulness_judge.chunk_source`, then `INDEPENDENT_REVIEWER_MIN_CHUNK_SOURCE_WORDS` is **not the threshold that actually controls chunking** — `faithfulness_judge.chunk_source` internally uses `FAITHFULNESS_JUDGE_MIN_CHUNK_SOURCE_WORDS` (via `_should_chunk`). The separate constant is therefore dead config unless `independent_reviewer.py` passes it explicitly to `chunk_source`. This is a **design ambiguity with factual consequences**: the constant either controls nothing, or requires a calling-convention change to `chunk_source`. **NEW FACTUAL ERROR / design gap.**

### F7 — `_quote_word_coverage` cited as `validation_pipeline._quote_word_coverage` but spec references `config.py:1062` for `QUOTE_MIN_WORD_COVERAGE` (verify)

The spec states:
> "Reuse `validation_pipeline._quote_word_coverage(quote, source) >= config.QUOTE_MIN_WORD_COVERAGE` (`config.py:1062`, the existing whole-quote coverage...)"

Source confirms:
- `validation_pipeline.py:675`: `def _quote_word_coverage(quote: str, transcript: str) -> float:` ✓
- `config.py:1062`: `QUOTE_MIN_WORD_COVERAGE = 1.0` ✓

Both correct. **Not an error.**

### F8 — `faithfulness_judge.py:544` cited for `_parse_judge_response` (verify)

The spec states:
> "Reuse the `_parse_judge_response` pattern (`faithfulness_judge.py:544`)"

Source shows: `544: def _parse_judge_response(response_text: str, claims: list,` ✓ **Not an error.**

### F9 — `release_gate.py:594` cited for `_judge_logic_version` (verify)

The spec states:
> "mirroring `release_gate._judge_logic_version` (`release_gate.py:594`)"

Source shows: `594: def _judge_logic_version(instructions: str) -> str:` ✓ **Not an error.**

### F10 — `transcript_utils.py:67` cited for `resolve_anthropic_key` (verify)

The spec states:
> "Key is resolved the same way `resolve_anthropic_key` works (`transcript_utils.py:67`)"

Source shows: `67: def resolve_anthropic_key() -> Optional[str]:` ✓

BUT: The actual `resolve_anthropic_key` reads `ANTHROPIC_API_KEY` env var, then falls back to `$LLM_KEYS_FILE` or `~/.config/llm/keys.json` under key path that is **not specified in the source excerpt for `providers.deepseek`**. The spec states the fallback reads `~/.config/llm/keys.json` `providers.deepseek`. The source shows the Anthropic key is read from the top-level JSON (`.get()` on `data`), not from `data["providers"]["deepseek"]`. The exact JSON path for the DeepSeek key is **unverified** — the spec asserts `providers.deepseek` as the key path but the source only shows the Anthropic resolution path. **NEW — unverifiable claim, potentially wrong key path.**

### F11 — Manifest currently lacks judge models — spec claims this PR adds them "for the first time" (verify)

The spec states:
> "judge models are currently **absent** from the manifest — this PR adds them for the first time"

Source `release_gate.py:1108-1111`:
```python
"models": {
    "default": config.DEFAULT_MODEL,
    "aux": getattr(config, "AUX_MODEL", None),
    "validation": getattr(config, "VALIDATION_MODEL", None),
```
The excerpt ends here. `FAITHFULNESS_JUDGE_MODEL` and `THEME_JUDGE_MODEL` are not shown in this `models` dict. The claim that judge models are absent is **consistent** with the source, but the excerpt is truncated — cannot fully confirm. Tentatively correct; not flagging as error.

### F12 — `config.py:560` cited for `GATE_ERROR_BLOCKS = True` (verify)

The spec states:
> "`GATE_ERROR_BLOCKS = True` (`config.py:560`)"

Source shows `config.py:560`: `GATE_ERROR_BLOCKS = True` ✓ **Not an error.**

---

## 2. DESIGN RISKS

### DR1 — Shared claims import creates hidden coupling to Claude judge state (HIGH)

The spec requires `independent_reviewer.py` to import `faithfulness_judge.extract_claims`, `chunk_source`, `route_claims_to_chunks`. This violates the spirit of D1 (isolation invariant) even if it doesn't touch `call_claude_with_retry`. If `extract_claims` is modified (e.g., its `source` parameter behavior changes, or heading-skip rules are updated), the independent reviewer silently inherits the change without a version bump to `INDEPENDENT_REVIEWER_LOGIC_VERSION`. The reviewer's "independence" is now dependent on a shared extraction pipeline. The spec does not address what happens when `faithfulness_judge.py` is modified — the `INDEPENDENT_REVIEWER_LOGIC_VERSION` bump policy covers reviewer prompt/code changes but **not upstream `faithfulness_judge` changes**.

Mitigation gap: `JUDGE_LOGIC_VERSION` (`config.py:641`) should be folded into the independent reviewer's cache key, but the spec does not say so.

### DR2 — Artifact-level diff has a false-concurrence failure mode (HIGH)

The spec's diff semantics (Design → `release_gate.py`):
> "reviewer flagged ≥1 re-verified non-entailed claim in artifact X" vs "the `faithfulness` verdict for artifact X is FAIL"

This is a **coarse binary comparison**. Consider: Claude FAILs artifact X on claim #3 (fabricated date). The independent reviewer flags claim #17 (different issue, also non-entailed). The spec records this as "concurrence" (both flagged the artifact). But the two models are flagging *different* claims — the reviewer has not independently confirmed the Claude finding on claim #3; it found a separate issue. This creates **false confidence**: the concurrence signal is presented as corroborating evidence but actually represents independent findings that may or may not overlap.

The spec explicitly chose artifact-level to avoid "cache coupling" but in doing so loses the diagnostic value it promises. The test I6 does not cover this case.

### DR3 — Fail-open ERROR semantics conflict with `GATE_ERROR_BLOCKS = True` is correct as designed but underdocumented for the promoted-to-blocker case (MEDIUM)

The spec states:
> "even then a reviewer ERROR is downgraded to WARN, never ERROR-to-block. `GATE_ERROR_BLOCKS = True` (`config.py:560`) would otherwise turn a DeepSeek outage into a hard publication stop. The `check_independent_reviewer` implementation catches its own failures and returns WARN"

This is correct *if* `check_independent_reviewer` is in `GATE_BLOCKING_CHECKS`. But if it is later promoted to blocking (post-D5), and `GATE_ERROR_BLOCKS = True`, the `decide()` function in `release_gate.py` will treat ERROR as blocking **unless** `check_independent_reviewer` actively returns WARN on its own failures rather than ERROR. The spec says it does, but:

1. Test I8 only tests the WARN-while-`BLOCKING=False` case, not the promoted-to-blocker + reviewer-raises-ERROR case.
2. The mechanism (catching exceptions inside `check_independent_reviewer`) is correct but fragile — if `_safe()` in `run_gate` catches the exception first (line 1017: `_safe(name, fn, base_name, logger)`), the status returned by `_safe` on an exception is unspecified in the provided source. If `_safe` returns ERROR on exception, the fail-open guarantee breaks regardless of the spec's intent.

The spec does not verify what `_safe()` returns on unhandled exception from a check function.

### DR4 — Chunked parity requirement (I5) is underspecified for the re-judge path (MEDIUM)

The spec states for I5:
> "a routed claim the window does not entail is re-judged on the full source (mirror `judge_claims_chunked`)"

`faithfulness_judge.judge_claims_chunked` at line 392 uses a specific re-judging strategy. The spec mandates the independent reviewer mirrors this, but:

1. The re-judge trigger in `judge_claims_chunked` depends on the Claude judge's window verdict (non-entailed from window → re-judge on full). The independent reviewer uses its *own* model — its window verdict may differ from Claude's. The spec does not clarify: does the reviewer re-judge on the full source based on its *own* window non-entailment, or based on Claude's? This should be its own (the reviewer's own verdict governs the re-judge decision), but it is not stated.

2. The `INDEPENDENT_REVIEWER_MIN_CHUNK_SOURCE_WORDS` constant (F6 above) may not actually control the `_should_chunk` decision if the reviewer calls `faithfulness_judge.chunk_source` directly, making the independent reviewer's chunking threshold silently identical to the Claude judge's regardless of the config constant.

### DR5 — `review_coverage` prompt constraint "substance-level omissions only" is unenforceable without calibration (MEDIUM)

The spec states:
> "`review_coverage(artifact, source)` → list of `{omitted, timestamp, materiality}` for summary/abstract only"

And in risks:
> "Coverage mode: summary + abstract only. Token ceiling is `INDEPENDENT_REVIEWER_MAX_TOKENS`."

The coverage prompt must return structured JSON with `{omitted, timestamp, materiality}`. The `timestamp` field implies the reviewer is expected to find and cite timestamps in the source for each omitted finding. DeepSeek (or any second model) may hallucinate timestamps or omit the field. The spec's I7 test only checks "malformed output → ERROR" — it does not test that `timestamp` values are actually present in the source (the same gap the spec is designed to close for the Claude judge). There is no span re-verification equivalent for coverage findings. **A hallucinated coverage finding with a plausible-looking timestamp would pass I7.**

### DR6 — Cache key includes `artifact-sha` but not `claims-sha` — claims can change without artifact changing (MEDIUM)

The cache key is:
> "`(artifact-sha, source-sha, INDEPENDENT_REVIEWER_MODEL, INDEPENDENT_REVIEWER_LOGIC_VERSION-hash)`"

If `faithfulness_judge.extract_claims` logic changes (e.g., a new heading is added to `FAITHFULNESS_GENERIC_HEADINGS` at `config.py:643`), the claims extracted from the same artifact will differ, but `artifact-sha` is unchanged. The cached verdict will be served against the old claim set. This is analogous to the `JUDGE_LOGIC_VERSION` problem for the Claude judge, but the spec's `INDEPENDENT_REVIEWER_LOGIC_VERSION` only covers "reviewer prompt/code/threshold change" — not upstream claim extraction changes. Since claims are shared (DR1), this cache invalidation gap is real.

### DR7 — `DEFAULT_CHECKS` positioning: reviewer runs before all advisory checks, creating a read-from-verdict-list race (LOW)

The spec states the check is positioned "after `check_faithfulness` and `check_theme_grounding`". In the actual `DEFAULT_CHECKS` (`release_gate.py:997`), `check_theme_grounding` is at index 5 (line 1003). The diff logic reads the "aggregate verdict list the gate already holds." Since `run_gate` runs checks sequentially and collects verdicts in order (line 1017), a check at position 7+ can read verdicts from positions 1-6. This works correctly for `check_faithfulness` (position 4) and `check_theme_grounding` (position 6), but the spec says "read from the aggregate verdict list" without specifying the mechanism. If the check receives only the pre-collected list up to its own position, this is fine. If it reads a global/shared structure, there is a state-mutation risk. Not verified from source.

### DR8 — `INDEPENDENT_REVIEWER_BLOCKING = False` at launch means the check can never produce a hard block, but ERROR also can't block — two separate suppression mechanisms are in play simultaneously (LOW)

When `INDEPENDENT_REVIEWER_BLOCKING = False`, the check is not in `GATE_BLOCKING_CHECKS`, so a FAIL won't block. Additionally, the check self-suppresses errors to WARN. These are independent. The spec says "not in `GATE_BLOCKING_CHECKS` until D5" which is correct, but the documentation conflates the two mechanisms. When D5 promotion happens, an operator must both add to `GATE_BLOCKING_CHECKS` AND verify the self-suppression behavior is intentional. This is a process risk, not a code defect, but could cause a misconfigured gate.

---

## 3. RECOMMENDATIONS FOR D1–D5

**D1 (provider adapter isolation):** Approve the no-import-of-Claude-client rule, but **add `JUDGE_LOGIC_VERSION` to the independent reviewer's cache key** to cover upstream claim-extraction changes — otherwise DR1 and DR6 cause stale cache hits.

**D2 (model/provider default):** Approve DeepSeek as default. **Verify and document the exact JSON key path in `~/.config/llm/keys.json` for DeepSeek** (e.g., `providers.deepseek.key` vs `deepseek`) — the current spec asserts `providers.deepseek` but this is unverified against the actual file schema (F10).

**D3 (fail-open ERROR semantics):** Approve the policy, but **verify what `_safe()` in `release_gate.py` returns when the check function raises an unhandled exception** — if `_safe` returns ERROR, the self-suppression guarantee inside `check_independent_reviewer` depends on no exception escaping, which is fragile. Add I8 variant: check function raises unexpectedly → `_safe` → still WARN.

**D4 (artifact scope):** Approve. Excluding `TOPIC_TERM_FAITHFULNESS_SUFFIXES` is correct given `config.py:734` "NOT YET CALIBRATED" note. **Add explicit test that the reviewer is not invoked on those suffixes.**

**D5 (calibration before arming):** Approve the threshold reuse (`FAITHFULNESS_MIN_RECALL_UNFAITHFUL = 0.90`, `config.py:742`). **Require the committed JSON artifact to include the `JUDGE_LOGIC_VERSION` value at calibration time** so a later claim-extraction change that invalidates the calibration is detectable.

---

## 4. MISSING — Undecided Before Build

**M1 — `_safe()` return value on unhandled exception not specified.**  
The fail-open guarantee depends on `check_independent_reviewer` never raising. The spec does not document what `_safe()` does, and the source excerpt does not show its body. This must be resolved before wiring the gate check.

**M2 — Exact JSON schema path for DeepSeek key in `~/.config/llm/keys.json`.**  
The spec says `providers.deepseek` but the `resolve_anthropic_key` source only shows a `.get()` on the top-level `data` object (for Anthropic). The DeepSeek resolver will be new code — its path into the JSON is unverified and must be confirmed against the actual file before I10 can be written correctly.

**M3 — Claim-level vs artifact-level concurrence documentation for operators.**  
The artifact-level diff (DR2) will produce false-concurrence signals. Operators reading the manifest need to understand that "concurrence" means "both flagged the artifact" not "both flagged the same claim." This must be documented in the check's `items` output or the manifest schema, otherwise operators will be misled.

**M4 — `timestamp` field in coverage output: source-grounding requirement.**  
`review_coverage` returns `{omitted, timestamp, materiality}`. No span re-verification is defined for `timestamp`. Is the timestamp field required? Optional? Verified against the source? This is unresolved and a hallucination vector (DR5).

**M5 — How the reviewer receives Claude's verdict for the diff.**  
The spec says "read from the aggregate verdict list the gate already holds — no per-claim cache read, no new accessor." The mechanism for passing the prior verdict list to `check_independent_reviewer` is not specified. Does `check_independent_reviewer` receive the prior verdicts as a parameter? Does it read from a shared gate state? This calling convention must be specified before implementation.

**M6 — `INDEPENDENT_REVIEWER_MODEL` default is empty string `""`.**  
The config block shows `INDEPENDENT_REVIEWER_MODEL = ""`. A startup assertion is promised when `ENABLED=True` and no key resolves, but there is no stated assertion for `ENABLED=True` and empty `MODEL`. A model-string of `""` passed to the OpenAI-compatible client will produce an API error, not a loud startup failure. This edge case must be handled.

**M7 — `review_coverage` output when source has no timestamps.**  
If the source transcript has no timestamps (or sparse ones), the `timestamp` field in coverage findings is meaningless or hallucinated. The spec does not handle this case.

---

## 5. VERDICT

**CHANGES REQUIRED**

Exact list of required changes before approval:

1. **(DR1 / DR6 / F6)** Either (a) fold `JUDGE_LOGIC_VERSION` into the independent reviewer cache key, or (b) document explicitly that upstream `extract_claims` changes require a manual `INDEPENDENT_REVIEWER_LOGIC_VERSION` bump — and add this to the bump policy comment. Resolve the `INDEPENDENT_REVIEWER_MIN_CHUNK_SOURCE_WORDS` dead-config ambiguity (does the reviewer pass it explicitly to `chunk_source`, or does it use `FAITHFULNESS_JUDGE_MIN_CHUNK_SOURCE_WORDS` implicitly?).

2. **(DR2 / M3)** Rename "concurrence" to "artifact-level co-flag" in the spec and in test I6 language. Add an explicit note that co-flag ≠ claim-level confirmation. Add a test variant for the false-concurrence case (Claude flags claim #3, reviewer flags claim #17, both on same artifact → recorded as co-flag, not claim-confirmed).

3. **(DR3 / M1)** Document `_safe()`'s behavior on unhandled exception. Add test I8-variant: exception escapes `check_independent_reviewer` → gate still WARN (not ERROR-to-block).

4. **(DR5 / M4)** Specify whether `timestamp` in `review_coverage` output is (a) required and source-verified, (b) optional, or (c) removed. If retained, add span-grounding for timestamp values analogous to I4.

5. **(F10 / M2)** Verify and hardcode the exact JSON key path for DeepSeek in `~/.config/llm/keys.json`. Update I10 fixture accordingly.

6. **(M5)** Specify the calling convention for passing prior gate verdicts to `check_independent_reviewer` (parameter injection vs shared state).

7. **(M6)** Add startup assertion: `INDEPENDENT_REVIEWER_ENABLED=True` and `INDEPENDENT_REVIEWER_MODEL=""` → loud failure, same class as missing-key assertion.