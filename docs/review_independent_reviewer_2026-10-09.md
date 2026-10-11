# Independent Review: Adversarial Reviewer Spec

---

## 1. FACTUAL ERRORS

### FE-1: Judge model constants are wrong
The spec states (Problem section):
> `config.FAITHFULNESS_JUDGE_MODEL = "claude-sonnet-4-6"` (accuracy judge)
> `config.THEME_JUDGE_MODEL = "claude-sonnet-4-6"` (theme judge)

Both are **correct** per source (`config.py:630`, `config.py:756`). ✓

However, the spec also implies all three roles (generation, faithfulness judge, theme judge) use the same constant or the same alias. The source explicitly refutes this: the comment at `config.py:621-624` states the judge model is a **SEPARATE named constant** precisely so a `DEFAULT_MODEL` bump cannot silently move the armed judge. The spec's framing ("same-family reviewer shares the generator's blind spots") is a valid concern but its claim that these are the same constant is misleading — they are three *separate* constants that happen to hold the same string value. This is not a code smell; it is documented as intentional. The spec should not imply they are aliased.

### FE-2: `route_claims_to_chunks` import name is wrong
The spec (Design section, "Claims are shared") says:
> Import `faithfulness_judge.extract_claims` and `chunk_source` / `route_claims_to_chunks`.

The actual function signature grep (`faithfulness_judge.py:340`) shows:
```
def route_claims_to_chunks(claims: list, chunks: list, min_overlap: float) -> tuple:
```
The name matches. However, `chunk_source` is at `faithfulness_judge.py:315`. Both names are confirmed. ✓ — but the spec omits that `route_claims_to_chunks` returns a **tuple of `(routed, unrouted)`** (`faithfulness_judge.py:340-341`), not a flat list. The spec's "same claims, same source, same chunking" framing implies the reviewer gets the same pre-routed per-chunk inputs — but the routing output is a two-element tuple, and the spec gives no instruction on how `unrouted` claims (those spread across windows, judged against the full source) are handed to the independent reviewer. This is a design gap, not merely a naming issue.

### FE-3: `_judge_logic_version` function attribution
The spec (Cache section) says:
> reuse `release_gate._judge_logic_version` pattern

The grep confirms this function exists at `release_gate.py:594`. ✓ However the spec also says "hash the prompt text + extraction config into the version" — the actual implementation at `release_gate.py:594-596` folds in `config.JUDGE_LOGIC_VERSION` (the manually-bumped constant) in addition to the prompt hash. The spec's independent reviewer would have its **own** logic version constant (not `JUDGE_LOGIC_VERSION`), but the spec never defines what constant name it would use or who is responsible for bumping it. This is underspecified, not merely a naming mismatch.

### FE-4: `build_manifest` / `provenance.models` claim
The spec says:
> add the independent reviewer's model + verdicts under `provenance.models` (it is already enumerated in `build_manifest`)

The source at `release_gate.py:1108-1111` shows `provenance.models` only contains `default`, `aux`, and `validation`. There is **no existing `provenance.models` field for judge models** — `FAITHFULNESS_JUDGE_MODEL` and `THEME_JUDGE_MODEL` are **not** currently in the manifest. The spec's claim that this location "already" enumerates models is false. Adding the independent reviewer model there would be the first time judge models appear in the manifest. This misrepresents the current state of `build_manifest`.

### FE-5: D5 calibration threshold attribution
The spec states:
> a promotion PR sets `INDEPENDENT_REVIEWER_BLOCKING = True` only with a recorded precision ≥ 0.7 / recall ≥ 0.9 on that set (mirror the J6.a threshold in `docs/plan_judge_routing_fix_2026-10-09.md`)

The thresholds `precision ≥ 0.7 / recall ≥ 0.9` are confirmed in the source at `config.py:742-743`:
```python
FAITHFULNESS_MIN_RECALL_UNFAITHFUL = 0.90
FAITHFULNESS_MIN_PRECISION_UNFAITHFUL = 0.70
```
These constants exist. However, the spec attributes them to `docs/plan_judge_routing_fix_2026-10-09.md` with label "J6.a" — there is no source excerpt provided to confirm that document or that label exist. This reference cannot be verified and may be hallucinated. The thresholds themselves match config; the citation is unverifiable.

### FE-6: `FAITHFULNESS_ARTIFACT_SUFFIXES` grep returned "not found"
The spec (D4) says:
> Accuracy mode reuses the existing claim extraction over `config.FAITHFULNESS_ARTIFACT_SUFFIXES` + `config.TOPIC_TERM_FAITHFULNESS_SUFFIXES`

The grep for both constants returns **not found**. Yet the config excerpt at `config.py:726-738` shows both constants defined. This is a grep tooling artifact, not a spec error, but it means the spec's claim that it "reuses the same set the Claude judge covers" cannot be mechanically confirmed from the provided excerpts. The constants do appear in the config body excerpt, so the claim is likely correct — but the discrepancy should be flagged.

### FE-7: `DEFAULT_CHECKS` position claim
The spec says the new check should be registered "after `check_faithfulness` / `check_theme_grounding`." The actual `DEFAULT_CHECKS` order (`release_gate.py:997-1011`) is:
```
source_fidelity → entity_grounding → artifact_contracts → faithfulness →
topic_term_faithfulness → theme_grounding → required_artifacts → verbatim_quotes →
topics_grounding → summary_coverage → timestamp_citations → entity_consistency → consistency
```
`check_theme_grounding` is position 6. The spec's "after both" is achievable, but the spec says "after `check_faithfulness` / `check_theme_grounding`, so the Claude verdicts it diffs against are **already computed/memoized**." This is only true if the independent reviewer runs after position 6 AND the faithfulness check at position 4 has its verdicts durably memoized before position 6. Given that `check_faithfulness` uses disk cache (`release_gate.py:542`), this holds — but the spec's statement implies the ordering itself provides the guarantee, when actually the guarantee comes from the disk cache, not the position. If the cache is cold (first run), the faithfulness verdict will have been computed earlier in the same `run_gate` call, so the diff logic must read from the in-memory or disk-cached result, not re-invoke. The spec doesn't specify how `check_independent_reviewer` retrieves the already-computed Claude verdict — this is a concrete design gap.

---

## 2. DESIGN RISKS

### DR-1: Span re-verification is under-specified and breakable
The spec calls span re-verification "load-bearing" and offers two options: "fuzzy `_quote_word_coverage` or a strict `in` check." These have very different false-positive suppression rates. `_quote_word_coverage` exists in the repo for a reason (verbatim quotes have filler words, stutters), but applying it here means a reviewer that returns a paraphrase as a `source_quote` passes the check. A strict `in` check will over-drop valid findings when the source has line-break normalization differences. The spec must pick one and specify the threshold. Leaving it open means the "load-bearing" mitigation is implemented differently by whoever codes it.

### DR-2: Retrieval of Claude verdicts inside `check_independent_reviewer` is unspecified
The diff logic requires knowing Claude's per-claim verdict for the same artifact. The spec says these are "already computed/memoized" but gives no concrete API for reading them. `check_faithfulness` returns a `Verdict` object (a pass/fail aggregate), not the per-claim breakdown. The per-claim data lives in the disk cache keyed by `(artifact-sha, source-sha, logic-version)`. The independent reviewer would need to either (a) re-read that cache directly (coupling it to the cache format), or (b) `check_faithfulness` would need to expose its per-claim output. Neither path is specified. This is a load-bearing design gap.

### DR-3: Cost is not bounded
The spec acknowledges "one extra model pass per artifact" but doesn't quantify it. `FAITHFULNESS_ARTIFACT_SUFFIXES` covers abstract, summary, overview, blog (4 artifacts). `TOPIC_TERM_FAITHFULNESS_SUFFIXES` adds topics and key-terms (2 more). Coverage mode adds summary + abstract again (overlapping). With no prompt caching on the second provider and potentially long source transcripts (the spec uses DeepSeek which has per-token cost), this could be 6+ full-source calls per run with no cache benefit on the provider side. The spec says "budget the coverage pass separately" but provides no actual budget, token ceiling per call, or cost estimate. `INDEPENDENT_REVIEWER_MAX_TOKENS` is listed as a config constant but never given a default value or rationale.

### DR-4: Fail-closed for the reviewer vs. fail-closed for the gate — conflation
The spec says "any API/parse error → ERROR" for the reviewer, and "reviewer ERROR → WARN" for the gate check (because `INDEPENDENT_REVIEWER_BLOCKING = False`). These are consistent now, but the spec also says "Promote to blocking only after D5 calibration clears." When `INDEPENDENT_REVIEWER_BLOCKING = True`, a reviewer API outage (network error, provider downtime) will produce ERROR → which maps to... what? The spec maps `GATE_ERROR_BLOCKS = True` (`config.py:560`), but `INDEPENDENT_REVIEWER_BLOCKING` is a separate flag. If ERROR is not in `GATE_BLOCKING_CHECKS` but `GATE_ERROR_BLOCKS` catches all ERRORs, then a DeepSeek outage would **block publication** after arming, even though the spec's intent is that the reviewer is a second opinion, not a single point of failure. This interaction is not addressed.

### DR-5: Provider drift is acknowledged but the mitigation is insufficient
The spec says "Pin the prompt and the label set in `config`." Label vocabulary drift (e.g., DeepSeek returning `"not_entailed"` instead of `"unsupported"`) would cause parse failures → ERROR → WARN (or BLOCK if armed). This is a latent silent failure: if the model returns a subtly different label that still looks like JSON, the parse succeeds but all verdicts are `entailed` (unknown labels treated as pass). The spec should require that any label not in `{entailed, contradicted, unsupported}` is treated as a parse error, not silently dropped. The existing `_parse_judge_response` at `faithfulness_judge.py:544` takes a `valid_labels` parameter for this purpose — the spec should mandate its equivalent.

### DR-6: `unrouted` claims not handled
As noted in FE-2: `route_claims_to_chunks` returns `(routed, unrouted)`. Routed claims go to specific windows; unrouted claims go to the full source. The spec says the independent reviewer uses "same claims, same source, same chunking" but doesn't specify whether it handles the `unrouted` bucket separately (full-source call) or collapses everything into one call. If it collapses, a claim that Claude judged against the full source is now being judged against a single window — a different context, producing noisy disagreement signal.

### DR-7: Cache invalidation race on first run (cold cache + concurrent checks)
If `check_faithfulness` and `check_independent_reviewer` run in the same `run_gate` call and both attempt to write/read the disk cache concurrently (e.g., if `run_gate` is ever parallelized), there is a race. The spec inherits the existing cache locking behavior (or lack thereof) from `release_gate` but doesn't mention it. If the existing gate has no locking (likely, as it's a sequential list comprehension at `release_gate.py:1017`), this is currently safe but becomes a latent issue if the gate is ever parallelized.

### DR-8: I9 is labeled "live, not offline" — this is a CI anti-pattern
The calibration harness (I9) makes live API calls to DeepSeek in what the spec calls a test. This means it cannot run in CI without credentials and incurs cost on every run. The spec says "not blocking" for the test itself, but placing a live-API test under `tests/` risks it being accidentally included in the test suite. It should be a script under `scripts/` or explicitly marked with a skip decorator and documented as manual-only.

### DR-9: The `disagreements` field in the manifest is not a standard `Verdict` field
The spec says to add a `disagreements` field to the manifest. The existing `build_manifest` at `release_gate.py:1077` takes a `GateDecision` and calls `decision.to_dict()`. The `Verdict` dataclass (not shown in excerpts but inferred from usage) presumably has `check`, `status`, `detail`, `items`. Adding a `disagreements` field requires either (a) extending the `Verdict` dataclass, which touches shared code, or (b) special-casing it in `build_manifest`. Both paths are unspecified and (a) contradicts the spec's "no change to any existing constant" isolation claim (the Verdict dataclass is not a constant, but the principle applies).

### DR-10: Prompt files in `prompts/` vs `references/` — inconsistency
The spec says prompts are "verbatim in `references/`" in the Design section, then later says "Two prompt templates as markdown under `prompts/`." These are different directories. The spec contradicts itself on where the prompt files live.

---

## 3. RECOMMENDATIONS (D1–D5)

**D1 — Provider adapter:** Use option (a), new `independent_reviewer.py` with its own OpenAI-compatible client. Do not touch `call_claude_with_retry`. ✓ Spec's recommendation is correct.

**D2 — Model/provider default:** Default to DeepSeek only if the key env var name and reachability from the CI/run environment are confirmed before the first merge; add a startup assertion that fails loudly if `INDEPENDENT_REVIEWER_ENABLED=True` and the key env var is absent.

**D3 — Blocking:** Keep `INDEPENDENT_REVIEWER_BLOCKING = False` at launch, but explicitly define the ERROR→WARN→BLOCK promotion path in the `GATE_BLOCKING_CHECKS` comment so a future engineer doesn't need to re-derive the policy.

**D4 — Artifact scope:** Exclude `TOPIC_TERM_FAITHFULNESS_SUFFIXES` from the initial accuracy-mode scope; those artifacts are themselves "NOT YET CALIBRATED" (`config.py:734`) and adding an uncalibrated reviewer on top of uncalibrated source verdicts produces noise-on-noise disagreement with no reference ground truth.

**D5 — Calibration:** Require the calibration script (I9) to be a standalone `scripts/` file, not under `tests/`, and require a recorded run artifact (JSON with precision/recall + model + date) committed to the repo as the arming evidence, not just a terminal printout.

---

## 4. MISSING (must be settled before build)

**M1 — How does `check_independent_reviewer` read Claude's per-claim verdicts?**
The `check_faithfulness` function returns an aggregate `Verdict`, not per-claim data. The diff logic needs claim-level Claude outputs. Either expose them from `check_faithfulness` (API change) or read from the disk cache directly (coupling). Must be specified.

**M2 — What happens to `unrouted` claims from `route_claims_to_chunks`?**
The spec says "same chunking" but `route_claims_to_chunks` returns `(routed, unrouted)`. The independent reviewer must handle both buckets or explicitly decide it only covers routed claims (and document that `unrouted` claims are not independently reviewed).

**M3 — ERROR behavior after `INDEPENDENT_REVIEWER_BLOCKING = True`.**
Once armed, a reviewer API outage → ERROR → does it block? `GATE_ERROR_BLOCKS = True` (`config.py:560`) catches all ERRORs from blocking checks. If `independent_reviewer` is added to `GATE_BLOCKING_CHECKS`, any provider outage blocks publication. A second-opinion tool should arguably have a "fail-open with loud warning" posture even when armed. This must be a conscious decision, not an implicit one.

**M4 — Span re-verification algorithm: fuzzy or strict, and at what threshold?**
The spec offers two options. Leaving it to the implementer means the "load-bearing" safety property has an undefined behavior. Must be pinned before build.

**M5 — Logic version constant name and bump ownership.**
The spec says "reuse `_judge_logic_version` pattern, separate prompt constant" but does not name the constant or specify who owns bumping it. Must be named (e.g., `INDEPENDENT_REVIEWER_LOGIC_VERSION`) and added to `config.py` with a bump policy.

**M6 — Where do prompt files live: `prompts/` or `references/`?**
The spec contradicts itself. Must be resolved before the file tree is created.

**M7 — Key env var name for DeepSeek.**
The spec says "key already in `.env` per project notes" but does not name the env var. `INDEPENDENT_REVIEWER_API_KEY_ENV` is a config constant whose *value* (the env var name string) is unspecified. Must be confirmed and documented in `config.py`.

**M8 — Default values for all new config constants.**
`INDEPENDENT_REVIEWER_MAX_TOKENS` has no default specified. `INDEPENDENT_REVIEWER_MIN_CHUNK_SOURCE_WORDS` has no default. `INDEPENDENT_REVIEWER_BASE_URL` has a stated default (`api.deepseek.com`) but no port/path. All defaults must be in the spec before `config.py` is modified.

**M9 — `disagreements` field in the manifest: Verdict extension or special-case?**
The mechanism for adding a non-standard field to the gate manifest must be specified to avoid ad-hoc implementation that breaks the `to_dict()` contract.

---

## 5. VERDICT

**CHANGES REQUIRED**

Required changes before build approval:

1. **Fix FE-4**: Remove the claim that `provenance.models` "already" enumerates judge models — it does not. Specify that this PR will be the first to add judge models to the manifest, and define the exact schema change to `build_manifest`.

2. **Fix FE-7 / M1**: Specify the concrete mechanism by which `check_independent_reviewer` retrieves Claude's per-claim verdicts (not just the aggregate `Verdict`). Either expose a per-claim accessor from `check_faithfulness` or document the disk-cache schema read path.

3. **Resolve DR-2 / M2**: Specify how `unrouted` claims (full-source claims from `route_claims_to_chunks`) are handled by the independent reviewer.

4. **Resolve DR-4 / M3**: Explicitly decide and document what happens to reviewer ERROR after `INDEPENDENT_REVIEWER_BLOCKING = True`, given that `GATE_ERROR_BLOCKS = True` will catch it.

5. **Pin DR-1 / M4**: Choose one span re-verification algorithm (strict `in` or fuzzy with a named threshold) and write it into the spec. Do not leave this to implementer discretion.

6. **Add M5**: Name the logic-version constant (`INDEPENDENT_REVIEWER_LOGIC_VERSION`) in `config.py` and state the bump policy.

7. **Fix DR-10 / M6**: Pick one directory for prompt files (`prompts/` or `references/`) and use it consistently throughout the spec.

8. **Add M7**: Name the DeepSeek key env var in the spec and in the config constant definition.

9. **Add M8**: Provide default values for all new config constants, including `INDEPENDENT_REVIEWER_MAX_TOKENS` and `INDEPENDENT_REVIEWER_MIN_CHUNK_SOURCE_WORDS`.

10. **Fix DR-8 / D5**: Move I9 calibration harness to `scripts/`, not `tests/`, and require a committed run artifact as arming evidence.

11. **Address DR-5**: Mandate that any label not in `{entailed, contradicted, unsupported}` is treated as a parse error, not silently dropped. This must appear in the acceptance criteria.

12. **Fix FE-5**: Either provide the source excerpt for "J6.a in `docs/plan_judge_routing_fix_2026-10-09.md`" or remove the citation and reference only the config constants directly.