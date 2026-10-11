## Independent Review — Spec v3

---

### 1. RESIDUAL FACTUAL ERRORS

**RF-1 (NEW) — `QUOTE_MIN_WORD_COVERAGE` claim is wrong.**
The spec (Design, "Span re-verification") states: reuse `validation_pipeline._quote_word_coverage(quote, source) >= config.QUOTE_MIN_WORD_COVERAGE` and cites `config.py:1062`. The actual config shows `QUOTE_MIN_WORD_COVERAGE = 1.0` at line **1097**, not 1062. Line 1062 is `QA_SPEAKER_TITLES`. This is a wrong line citation — minor but a copy error that will cause confusion when a builder looks up the constant.

**RF-2 (NEW) — `build_manifest` / `provenance.models` claim is partially false.**
The spec states: "judge models are currently **absent** from the manifest — this PR adds them for the first time." The source shows `build_manifest` at `release_gate.py:1077`, and the `provenance.models` block at lines 1108–1111 already contains `default`, `aux`, `validation`. The spec's claim that *judge models* are absent is plausible (the excerpt cuts off after line 1111 and does not show `faithfulness_judge` or `theme_judge` keys). However, the spec also says this PR adds `faithfulness_judge` and `theme_judge` to the manifest for the first time. If the existing code already includes those keys (excerpt truncated), this is a false claim. **Risk: the excerpt is truncated; I cannot fully verify.** The builder must confirm lines 1111+ do not already carry those keys before writing the "adds them for the first time" commit message. This is a verification gap, not a confirmed error, but it must be checked.

**RF-3 (RESIDUAL from prior rounds) — `_judge_logic_version` signature vs. spec claim.**
The spec says: "Folding in `_judge_logic_version` (which already hashes `extract_claims`, the split/stem helpers, and the relevant config — `release_gate.py:594`)." The source shows `_judge_logic_version(instructions: str)` at line 594 — it takes an `instructions` string argument, not a zero-argument function. The spec implies it can be called without arguments or as a standalone cache component, but calling it requires passing the prompt/instructions text. This is a latent API confusion: the builder must know to pass the reviewer's own prompt text as `instructions`, not call it bare. The spec does not say what to pass. This is underspecified and could produce an incorrect cache key.

**RF-4 (NEW) — `DEFAULT_CHECKS` positioning claim.**
The spec says the new check is positioned "after `check_faithfulness` / `check_theme_grounding`" and cites `release_gate.py:997`. The actual `DEFAULT_CHECKS` list at line 997 runs: `source_fidelity, entity_grounding, artifact_contracts, faithfulness, topic_term_faithfulness, theme_grounding, required_artifacts, verbatim_quotes, topics_grounding, summary_coverage, timestamp_citations, entity_consistency, consistency`. The spec says to add `check_independent_reviewer` after `theme_grounding` — that would place it between `theme_grounding` and `required_artifacts`. This is a valid position but the spec does not give the exact insertion point in the list. Not a factual error per se, but the ordering claim needs to be explicit since the list already has 13 entries and the position affects log readability and manifest ordering. Low severity but should be pinned.

**RF-5 (CONFIRMED RESOLVED) — `api_key` snake_case field name.** Prior finding, explicitly resolved in v3. ✓

**RF-6 (CONFIRMED RESOLVED) — `dialect:"openai"` / `base_url` / `default_model` in keys.json.** Confirmed in verified facts. ✓

**RF-7 (CONFIRMED RESOLVED) — `FAITHFULNESS_JUDGE_MODEL` / `THEME_JUDGE_MODEL` separate constants.** v3 correctly cites lines 630 and 756. ✓

**RF-8 (CONFIRMED RESOLVED) — `GATE_ERROR_BLOCKS = True` at config.py:560.** Confirmed in source. ✓

**RF-9 (CONFIRMED RESOLVED) — `_safe` converts exception → ERROR.** Source lines 96–105 confirm. ✓

---

### 2. DESIGN RISKS

**DR-1 (NEW — HIGH) — `_judge_logic_version` is called with unknown arguments.**
As noted in RF-3, `_judge_logic_version(instructions: str)` requires a prompt string. The spec says to fold it into the cache key but never specifies what `instructions` to pass for the *reviewer's* cache key. If the builder passes the reviewer's own prompt template (correct), the key invalidates on reviewer prompt changes as intended. If the builder passes the Claude judge's prompt (wrong), the cache key couples the reviewer to the Claude judge's prompt changes — defeating D1 isolation. If the builder passes an empty string (wrong), the version folding is a no-op. **This must be pinned in the spec.**

**DR-2 (RESIDUAL — MEDIUM) — Fail-open enforcement vs. `GATE_ERROR_BLOCKS` interaction when promoted.**
The spec correctly notes: "even when armed a reviewer failure returns WARN, never ERROR-to-block." The mechanism is: `check_independent_reviewer` wraps its entire body in try/except and returns WARN on any exception. This is sound *if the except clause catches `BaseException` or at least `Exception`*. However, test I8 only simulates "a simulated exception raised inside `check_independent_reviewer` is caught." There is a gap: a `SystemExit` or `KeyboardInterrupt` raised inside the check would not be caught by `except Exception`. This is a theoretical edge case but worth noting for a check that calls an external API. Low probability; documenting is sufficient.

**DR-3 (NEW — MEDIUM) — `review_accuracy` receives claims but spec says "shared, not re-derived" yet test I2 asserts the reviewer "receives the *identical* claim list the Claude judge produced."**
This is a design ambiguity. If `check_independent_reviewer` calls `faithfulness_judge.extract_claims` itself (D1 allows importing it), it *re-derives* claims from the artifact — which should produce the same list deterministically. But test I2 says "receives the identical claim list the Claude judge produced (fixture artifact; assert equality, not re-extraction)." This implies the reviewer is passed the already-extracted claim list from the Claude judge run, which *would* create coupling to the Claude judge's execution order. The spec says "no coupling" and "no prior-verdict injection" but I2 implies reading Claude's intermediate output. **This is a contradiction**: either the reviewer re-extracts (independent, but I2 is testing the wrong thing) or it reads Claude's cache (coupled, violating D1). The spec must clarify.

**DR-4 (RESIDUAL — MEDIUM) — Coverage mode: `timestamp` validation against `[HH:MM:SS]` source markers.**
The spec says a non-null `timestamp` "must match a `[HH:MM:SS]` marker in the source, else dropped." No tolerance is specified — exact string match? The formatted transcript uses `[HH:MM:SS]` markers but the DeepSeek model may emit `HH:MM:SS` without brackets, or with slight format variation. The drop-on-mismatch policy is correct but without a normalized comparison (strip brackets, zero-pad), a well-intentioned timestamp that differs by `[` vs none will be silently dropped. This was flagged in round 2 and the spec has not added normalization detail.

**DR-5 (NEW — LOW) — `INDEPENDENT_REVIEWER_MAX_TOKENS = 8192` vs. DeepSeek API limit.**
DeepSeek-chat's default output limit varies by API version. `8192` output tokens is reasonable but if the artifact + source is large and the model returns verbose rationales, the response may be truncated mid-JSON. The spec has a "truncation check" ("Own retry/timeout + truncation check") but does not specify what constitutes a truncation signal for the OpenAI-compatible response (e.g., `finish_reason == "length"`). Test I3 covers malformed JSON but does not cover the truncation-mid-JSON path specifically. Should be explicit.

**DR-6 (CONFIRMED RESOLVED) — Advisory-only default with documented promotion path.** D3 is clean. ✓

**DR-7 (CONFIRMED RESOLVED) — `TOPIC_TERM_FAITHFULNESS_SUFFIXES` excluded from v1.** D4 is clean. ✓

**DR-8 (CONFIRMED RESOLVED) — Calibration artifact requirement before arming.** D5 is clean. ✓

**DR-9 (NEW — LOW) — `prompts/` directory existence not confirmed.**
The spec says templates go under `prompts/`, matching `config.PROMPTS_DIR`. The source excerpts do not include a `config.PROMPTS_DIR` definition or confirm the directory exists. If `PROMPTS_DIR` resolves differently (e.g., to a per-run temp path), the templates won't be found. Low risk but should be verified before build.

---

### 3. RECOMMENDATIONS — D1–D5

**D1** — As specified, with one addition: explicitly document that `_judge_logic_version` must be called with the reviewer's own prompt text as `instructions`, not the Claude judge's prompt. Without this pin, RF-3/DR-1 will be implemented incorrectly.

**D2** — As specified.

**D3** — As specified. The try/except-catches-`Exception` note (DR-2) is advisory; `BaseException` would be safer but is not strictly required.

**D4** — As specified.

**D5** — As specified.

---

### 4. MISSING (must be decided before build)

**M1 (BLOCKING) — `_judge_logic_version` call site.** What string is passed as `instructions` when computing the reviewer's cache key? Options: (a) the reviewer's own rendered prompt text, (b) a concatenation of reviewer prompt + `INDEPENDENT_REVIEWER_LOGIC_VERSION`, (c) just `INDEPENDENT_REVIEWER_LOGIC_VERSION`. Must be pinned; affects cache correctness and isolation guarantee.

**M2 (BLOCKING) — Claims: re-extracted or passed from Claude's run?** Resolve the DR-3 contradiction. If re-extracted: test I2 should assert `extract_claims(artifact_text) == fixture_claims`, not that the reviewer received Claude's list. If passed: document the coupling and explain why it doesn't violate D1.

**M3 (SHOULD-HAVE) — Timestamp normalization in coverage mode.** Specify whether timestamp matching strips brackets and zero-pads before comparison, or is exact-string. Without this, the drop policy has unpredictable behavior on real model output.

**M4 (SHOULD-HAVE) — Truncation signal definition.** Specify that `finish_reason == "length"` (or equivalent) triggers a parse-error path, not a silent partial result.

**M5 (LOW) — Confirm `build_manifest` lines 1111+ do not already include `faithfulness_judge` / `theme_judge` keys**, to validate the "adds them for the first time" claim and avoid a duplicate-key write.

**M6 (LOW) — Confirm `config.PROMPTS_DIR` resolves to a stable, pre-existing path** in the run environment.

---

### 5. VERDICT

**CHANGES REQUIRED**

Exact list:

1. **(BLOCKING — DR-1 / RF-3 / M1)** Pin what argument is passed to `_judge_logic_version` in the reviewer's cache key computation. Current spec leaves this undefined; a wrong choice breaks cache isolation or makes the version fold a no-op.

2. **(BLOCKING — DR-3 / M2)** Resolve the contradiction between "shared claims, not re-derived" (no coupling) and test I2's "identical claim list the Claude judge produced" (implies coupling). Choose one and make the spec internally consistent.

3. **(SHOULD-HAVE — DR-4 / M3)** Add timestamp normalization rule for coverage-mode timestamp matching (strip brackets, coerce format before comparison), or explicitly accept exact-match-only with the known false-drop risk.

4. **(SHOULD-HAVE — DR-5 / M4)** Add explicit truncation detection (`finish_reason == "length"`) to the client spec and a corresponding test case.

5. **(LOW — RF-1)** Correct the line citation for `QUOTE_MIN_WORD_COVERAGE` from `config.py:1062` to `config.py:1097`.