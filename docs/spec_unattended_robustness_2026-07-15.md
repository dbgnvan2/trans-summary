# Spec + Plan — "Trust Unattended" Robustness

**Status:** Approved scope, 2026-07-15 — awaiting go-ahead to start Phase 0 code.
**Author:** run-log robustness track, 2026-07-15
**Depends on / supersedes:** builds on the Step-1/Step-2 validator hardening
(`CHANGELOG.md`), the P19 contract audit (A1–A12), and `TEST_VALIDITY_REPORT.md`.

### Selected scope (2026-07-15)

**Build now — the "fail-closed net" (Phases 0–1):** `M8`, `M6`, `M1`, `M4`, `M7`.
**Deferred (revisit after the net is in):** `M3` (JSON contracts) and `M2`
(semantic judge). Consequence to state plainly: deferring M2 means **U2 is only
met for its machine-checkable subset** (verbatim quotes, entity grounding) — a
fluent hallucination in *prose* can still ship until M2 lands. Deferring M3 means
**U4 is not met** — producer/consumer drift remains a latent risk, mitigated (not
eliminated) by M1's loud zero-from-non-empty checks.

**Blocking policy decision (M1.B):** the single elected hard blocker is a
**fabricated/ungrounded entity** (M4.C). Per the note in M1.B, ERROR is *also*
kept blocking-by-default (recommended, vetoable) so a transient failure can't ship
unverified — otherwise U1/U3 are unmet. All other checks (non-verbatim quote,
missing artifact, proportionality, consistency) default to **WARN** and are
flippable to block via the `config` policy table. This is a deliberately
conservative net: it stops the confirmed real failure (the Luciano Malorni class)
and outages, and leaves the rest advisory until proven necessary.

---

## 0. Goal and definition of "unattended"

Today the pipeline is **trustworthy only with a human reviewer in the loop**: the
validators are *advisory* (they write a report; nothing blocks on them), the
generation layer can emit fluent hallucinations with no hard stop, and the
producer→consumer boundaries are markdown-parsed so drift fails silent.

**"Trust unattended" = the pipeline can run end-to-end with no human review and
still guarantee: it either publishes a correct, source-faithful artifact, or it
fails closed with a specific, actionable status — it NEVER silently publishes
wrong, fabricated, or unverifiable content.**

This is achieved when all seven exit criteria hold. They are the acceptance
criteria for the whole effort; every module below traces to one.

| ID | Exit criterion (measurable) | Verified by |
|----|------------------------------|-------------|
| **U1** | No run publishes an artifact that failed a hard gate. | `M1` + fault-injection suite `M5` |
| **U2** | Every quote, timestamp, section-citation, and named entity in a published artifact is machine-verified against the source, or the artifact is blocked. | `M4` |
| **U3** | A transient/tooling failure never produces the same result as a genuine pass or a genuine "absent" (P1). It yields a distinct, retryable ERROR that blocks publish. | `M1.C` + `M5.D` |
| **U4** | Every producer→consumer boundary is schema-validated; format drift is a hard error, not a silent zero (P19). | `M3` |
| **U5** | Every run emits one machine-readable manifest carrying an authoritative publish decision + provenance; an operator (or a cron) can act on that single file. | `M7` |
| **U6** | Mutation score on the core modules ≥ threshold in CI; zero assertion-free tests; parser/validator tests run against real formats. | `M6` |
| **U7** | The full edge-case/fault matrix (empty / short / long / malformed / API-fail / dirty re-run / partial artifacts) each fails closed or degrades with a distinct signal. | `M5` |

**Non-goals (explicitly out of scope):** improving *summary quality* or prose
style; changing the editorial content of prompts beyond what a contract requires;
a UI redesign; multi-user/auth concerns. This spec is about *safety of the
automated output*, not its eloquence.

**Design principles**
1. **Fail closed.** Absence of proof of correctness blocks publication.
2. **Verify against the artifact, now** (P6) — never trust a status flag.
3. **Transient ≠ terminal** (P1) — a check that couldn't run is ERROR, not PASS/FAIL.
4. **Contracts are code** (P19) — a boundary format is a schema, enforced both sides.
5. **Every drop is surfaced** (P2) — zero-from-non-empty is always loud.
6. **The judge is judged** — any LLM-based check has its own gold-set eval + threshold.

---

## M1 — Fail-closed release gate

**Purpose:** introduce a single gating layer between generation and publication.
No artifact reaches the published bundle (HTML/PDF/blog/zip) unless the gate
returns ALLOW. This is the highest-leverage change and delivers most of U1 on
its own.

- **M1.A — Structured verdict contract.** Every validator returns a typed
  `Verdict{status: PASS|WARN|FAIL|ERROR, checks: [...], detail}` instead of a
  bare bool / advisory report. `WARN` = ship-with-note; `FAIL` = content wrong;
  `ERROR` = could-not-verify (transient/tooling).
  - *AC M1.A.1:* each of the seven core validators returns a `Verdict`;
    the legacy bool is derived from it. **Test:** `test_m1a1_validators_return_verdict.py` (one param case per validator, asserting the dataclass shape and that `PASS`/`FAIL` map to the old bool).
- **M1.B — Aggregating gate.** `release_gate(base_name) -> GateDecision` collects
  all verdicts and decides ALLOW / BLOCK / ALLOW_WITH_WARNINGS per a policy table
  in `config` (which checks are publish-blocking).
  - *AC M1.B.1:* any `FAIL` in a blocking check → `BLOCK`. **Test:** `test_m1b1_fail_blocks_publish` (inject one FAIL, assert BLOCK and that `generate_pdf`/HTML publish is not called).
  - *AC M1.B.2:* the publish step (`html_generator`, `packaging_pipeline`) is guarded by the gate; a BLOCK prevents the bundle from being written. **Test:** `test_m1b2_blocked_run_writes_no_bundle` (assert no `.html/.pdf/.zip` on BLOCK; a `*.BLOCKED` marker written instead).
- **M1.C — ERROR ≠ FAIL ≠ absent.** An ERROR verdict (no API key, timeout, parse
  crash) blocks publish AND is marked retryable; it is never collapsed into PASS
  or "genuinely absent" (P1, the A10 class).
  - *AC M1.C.1:* a validator whose dependency is unavailable returns ERROR and the gate BLOCKs (not ALLOW). **Test:** `test_m1c1_transient_error_blocks_not_passes` (monkeypatch a check to raise; assert ERROR→BLOCK, retryable=True).

**Dependencies:** none (foundational). **Risk:** medium — touches the publish
path; must preserve existing outputs on ALLOW. **Effort:** L.

---

## M2 — Semantic faithfulness verification

**Purpose:** lexical grounding cannot catch a fluent hallucination (F1/F4 proved
this — a wrong-but-on-topic definition and a fabricated name both passed keyword
checks). Add a claim-level entailment check for the narrative artifacts
(abstract, summary, overview, blog, themes).

- **M2.A — Claim extraction + entailment.** For each narrative artifact, extract
  atomic claims and verify each is *entailed by* the source transcript (LLM-judge
  or NLI). Unentailed claim → `FAIL` with the offending sentence.
  - *AC M2.A.1:* on a fixture where one sentence is a known fabrication, the check returns FAIL naming that sentence. **Test:** `test_m2a1_fabricated_claim_flagged` (real artifact + one injected fabricated sentence).
  - *AC M2.A.2:* on the clean real artifact, the check returns PASS (no false FAIL). **Test:** `test_m2a2_faithful_artifact_passes` (real `where_roots` abstract vs source).
- **M2.B — The judge is judged (gold set).** A curated `tests/fixtures/faithfulness_gold/`
  of (artifact-sentence, source, label∈{entailed,contradicted,unsupported}) pins
  the judge's decision threshold; the check ships only if it clears precision/recall
  targets on that set.
  - *AC M2.B.1:* judge accuracy on the gold set ≥ agreed threshold (e.g. recall ≥ 0.9 on contradicted/unsupported). **Test:** `test_m2b1_judge_meets_gold_thresholds`.
- **M2.C — The judge fails closed.** If the judge call errors/times out, the
  artifact is ERROR (blocked), never PASS (P1 + M1.C).
  - *AC M2.C.1:* judge exception → ERROR verdict. **Test:** `test_m2c1_judge_error_is_error_not_pass`.

**Not fully code-testable — flagged for human review:** the judge's *semantic
correctness* is bounded by the gold set. **Proposal:** maintain the gold set as a
living artifact (add every real hallucination found in production to it), and
require a human sign-off on any threshold change. AC M2.B.1 makes the *threshold*
testable; the underlying judgment quality is a curated-eval concern, not a unit test.

**Dependencies:** M1 (emits Verdict), M4 (verbatim layer runs first — cheap exact
checks before the expensive judge). **Risk:** high (LLM cost, calibration, false
positives). **Effort:** XL.

---

## M3 — Structured intermediates + schema contracts

**Purpose:** kill the P19 drift *class*, not instances. The producer→consumer
boundary becomes schema-validated JSON; markdown becomes a *rendering* of the
validated structure, not the interface.

- **M3.A — Boundary schemas.** JSON Schema for each structured artifact (themes,
  topics, key-terms, bowen, emphasis, abstract-input). Stored in
  `schemas/` and versioned.
- **M3.B — Producer emits + self-validates.** Each generation step emits JSON
  conforming to its schema and validates before save; a non-conforming model
  output is a retryable ERROR (not a silently-saved bad file).
  - *AC M3.B.1:* a producer whose model output violates the schema raises/records ERROR, does not save a malformed artifact. **Test:** `test_m3b1_nonconforming_output_errors`.
- **M3.C — Consumer validates on read; drift is loud.** Parsers read JSON and
  validate; a schema mismatch is a hard error with the diff, never a zero-count
  pass (P19). Markdown is generated from the validated object for display.
  - *AC M3.C.1:* a round-trip test on a real sample: `parse(save(obj)) == obj` for every boundary. **Test:** `test_m3c1_roundtrip_real_samples` (per artifact).
  - *AC M3.C.2:* a corrupted/old-format artifact yields a schema error, not empty. **Test:** `test_m3c2_drift_is_error_not_silent_zero`.
- **M3.D — Migration/back-compat.** A shim reads the legacy markdown artifacts
  (existing runs on disk) into the new schema so old projects still validate.
  - *AC M3.D.1:* the real `where_roots` markdown artifacts load into the schema. **Test:** `test_m3d1_legacy_markdown_migrates`.

**Dependencies:** none hard, but pairs with M1. **Risk:** high (touches every
generation step + prompts must be told to emit JSON; largest blast radius).
**Effort:** XL. **Note:** can be staged artifact-by-artifact behind the shim.

---

## M4 — Provenance & citation enforcement (make F4/F6/verbatim gating)

**Purpose:** every verbatim-quoted or cited element in a *published* artifact must
be machine-verifiable against the source, and the check must *block* (not advise).

- **M4.A — Verbatim quote enforcement.** Bowen quotes + emphasis quotes must match
  the source verbatim (extend the Step-2 head/tail check to full-span exactness at
  publish time); a non-locatable quote → FAIL.
  - *AC M4.A.1:* a fabricated-tail quote → FAIL and BLOCK. **Test:** `test_m4a1_fabricated_quote_blocks` (extends the existing emphasis test to the gate).
- **M4.B — Timestamp & section-citation correctness.** A quote's timestamp / a
  topic's section range must resolve to the span the quote actually occupies
  (closes F6). Mismatch → FAIL (or auto-corrected from the matched span, policy TBD).
  - *AC M4.B.1:* a quote whose stored timestamp points to the wrong block is flagged. **Test:** `test_m4b1_timestamp_drift_flagged` (real `where_roots` emphasis has known drift — a natural fixture).
- **M4.C — Entity grounding, gating + all-artifact.** Promote the Step-2 advisory
  `find_ungrounded_names` to a blocking check applied to *every* artifact, not
  just the abstract; an ungrounded entity → FAIL.
  - *AC M4.C.1:* the `Luciano Malorni` fixture → FAIL/BLOCK, not a warning. **Test:** `test_m4c1_ungrounded_name_blocks`.
- **M4.D — Cross-artifact consistency (F7).** The same entity must be spelled
  identically across artifacts (or all map to one canonical form); divergence → WARN.
  - *AC M4.D.1:* Bertoloso/Bertolaso/Malorni divergence is reported. **Test:** `test_m4d1_entity_consistency_reported`.

**Dependencies:** M1 (verdicts + gate). **Risk:** medium. **Effort:** L.

---

## M5 — Fault-injection & edge-case harness

**Purpose:** *prove* fail-closed behaviour under the adverse conditions an
unattended run will actually hit. This is what converts "we think it fails closed"
into "we tested that it does" (U7/U1/U3).

- **M5.A — Input edge matrix.** empty / whitespace-only / very short / very long
  (real-scale) / missing-sections / malformed-headers transcript.
  - *AC M5.A.1:* each input either produces a valid gated bundle or BLOCKs with a distinct status; none crashes or ships silently. **Test:** `test_m5a1_input_edge_matrix` (parametrized).
- **M5.B — Partial-artifact matrix.** each artifact missing / truncated / empty
  in turn.
  - *AC M5.B.1:* a missing required artifact → BLOCK naming it. **Test:** `test_m5b1_missing_artifact_blocks`.
- **M5.C — Dirty re-run (P8).** re-run over a project dir already containing prior
  outputs (incl. a prior BLOCKED marker, stale reports).
  - *AC M5.C.1:* re-run is idempotent and reads only current inputs; a prior FAIL does not leak into a now-clean run, and vice versa. **Test:** `test_m5c1_dirty_rerun_idempotent`.
- **M5.D — API/tooling fault injection.** timeout / 429 / 5xx / no-key / partial
  stream mid-run at each LLM call.
  - *AC M5.D.1:* every injected fault yields ERROR→BLOCK (retryable), never a partial published bundle. **Test:** `test_m5d1_api_fault_blocks` (monkeypatched client raising at each call site).

**Dependencies:** M1 (gate exists), M3/M4 (checks to exercise). **Risk:** low.
**Effort:** M. **This module is the acceptance test for the whole spec.**

---

## M6 — Test-validity gate in CI

**Purpose:** the meta-gate that keeps every other module honest — mutation, not
coverage, is the measure (per `TEST_VALIDITY_REPORT.md`).

- **M6.A — Mutation gate.** `mut_harness` (fixed per M8.C) runs on the core
  modules in CI; a per-module mutation score below threshold fails the build.
  - *AC M6.A.1:* CI job exists and fails when a core module drops below its floor. **Test:** the CI config + a self-test `test_m6a1_mutation_gate_config`.
- **M6.B — No vacuous tests.** a lint/CI check rejects assertion-free test
  functions and `assert`-on-possibly-empty patterns (the §3 vacuity class).
  - *AC M6.B.1:* the checker flags a known vacuous test. **Test:** `test_m6b1_vacuity_checker`.
- **M6.C — Real-format fixture requirement.** parser/validator tests must reference
  a `tests/fixtures/` real artifact (policy + review checklist item).
  - *AC M6.C.1:* documented + enforced by review checklist; spot-checked by `test_m6c1_no_synthetic_only_parser_tests` where feasible.

**Dependencies:** M8.C (mut_harness fix). **Risk:** low. **Effort:** M.

---

## M7 — Run manifest & observability

**Purpose:** for unattended operation an operator/cron must be able to read ONE
file and know the run is safe (U5).

- **M7.A — Manifest.** each run writes `<base> - run-manifest.json`: per-artifact
  status + verdicts, the `GateDecision`, provenance (source hash, model IDs,
  prompt versions, timestamps), token usage, and a single top-level
  `publish_decision`.
  - *AC M7.A.1:* a run produces a manifest whose `publish_decision` matches the gate and lists every artifact status. **Test:** `test_m7a1_manifest_matches_gate`.
- **M7.B — Exit code / signal.** the pipeline entrypoint returns a nonzero exit on
  BLOCK so a cron/CI can detect it without parsing logs.
  - *AC M7.B.1:* BLOCK → nonzero exit; ALLOW → zero. **Test:** `test_m7b1_exit_code_reflects_decision`.
- **M7.C — Alert hook (optional).** a pluggable notifier (email/webhook) on BLOCK,
  off by default.
  - *AC M7.C.1:* on BLOCK the configured hook is invoked with the manifest. **Test:** `test_m7c1_alert_on_block` (mock hook).

**Dependencies:** M1. **Risk:** low. **Effort:** M.

---

## M8 — Code-health hardening (prerequisite cleanup)

**Purpose:** remove the footguns that made this session harder and that undermine
confidence in unattended operation.

- **M8.A — Remove duplicate/dead code.** the two `_generate_simple_html_page`
  definitions; other dead shadows surfaced by review.
  - *AC M8.A.1:* one definition remains; grep + `test_m8a1_no_shadowed_defs`.
- **M8.B — Resolve the pre-existing red tests.** the 5 documented failures
  (config-singleton reload, 2× header token-cap, 2× bowen integration): fix or
  `xfail` with a reason so a red suite can't hide a real regression (the 7-vs-9-vs-10
  drift in the validity report).
  - *AC M8.B.1:* `pytest` is green or every red is an annotated `xfail`. **Test:** the suite itself + `test_m8b1_no_unexplained_failures`.
- **M8.C — Fix `mut_harness` footgun.** it rewrites the target via `ast.unparse`
  (reformats the whole file on restore) and buffers output; restore byte-exactly
  and stream progress. (Bit this session twice.)
  - *AC M8.C.1:* running the harness leaves the target file byte-identical. **Test:** `test_m8c1_mut_harness_preserves_bytes`.
- **M8.D — Single source of truth for naming/paths** — audit that all artifact
  path building goes through the `config` suffix helpers (supports M1/M7).

**Dependencies:** none (do first). **Risk:** low. **Effort:** M.

---

## Implementation order & dependency graph

```
Phase 0 (foundation, low risk):      M8  →  M6 (needs M8.C)
Phase 1 (the big robustness jump):   M1  →  M4, M7
Phase 2 (kill the drift class):      M3  (behind a per-artifact shim)
Phase 3 (kill hallucination-ships):  M2  (needs M1, M4)
Phase 4 (prove it):                  M5  (needs M1, M3, M4)
Phase 5 (sign-off):                  measure U1–U7; close.
```

Rationale: **M8/M6 first** so the ground is stable and measurable. **M1 next** —
it alone moves the needle most (fail-closed publish). **M4+M7** ride on M1 cheaply.
**M3** is the largest architectural change and can be staged artifact-by-artifact.
**M2** is highest-risk/cost and comes once the cheap exact checks (M4) already
filter most problems. **M5** is the final acceptance gate.

## Effort / risk summary

| Module | Effort | Risk | Moves which U |
|--------|--------|------|---------------|
| M8 | M | low | enables all |
| M6 | M | low | U6 |
| M1 | L | med | U1, U3 |
| M4 | L | med | U2 |
| M7 | M | low | U5 |
| M3 | XL | high | U4 |
| M2 | XL | high | U2 (semantic) |
| M5 | M | low | U7, U1, U3 |

## Criteria that cannot be fully code-tested (flagged per planning rules)

1. **M2 judge semantic quality** — bounded by the gold set, not a unit test.
   *Proposal:* living gold set + human sign-off on threshold changes; AC M2.B.1
   pins the threshold.
2. **"No hallucination ever ships"** is not provable in the absolute; it is
   *reduced to* U2's machine-checkable subset (verbatim + entailment-over-gold).
   Residual risk is documented, not eliminated. *Proposal:* track escaped
   hallucinations as production incidents that each add a gold-set case.

## Decisions (resolved 2026-07-15)

- **Scope:** fail-closed net first — `M8, M6, M1, M4, M7`. `M3`, `M2` deferred
  (see *Selected scope* above for the U-criteria consequences).
- **Blocking policy (M1.B):** hard-block on **ungrounded/fabricated entity**;
  **ERROR blocks by default** (recommended, vetoable); everything else defaults to
  **WARN**, flippable via the `config` policy table.
- **M2 cost appetite:** deferred, so moot for now; when built, gate the entailment
  judge behind a "strict" mode by default.
