# Task: Fix the failing nightly `mutation-gate` CI job in dbgnvan2/trans-summary

## Context

Repo: `dbgnvan2/trans-summary` (private). Work off the `validation-hardening`
branch (it is 63 commits ahead of `origin/main`; the failing code is identical
on both). Do NOT merge to main or push a PR without asking.

The nightly `mutation-gate` job (`.github/workflows/ci.yml`, cron `0 6 * * *`,
runs `python quality_gates.py mutation`) has failed 5 nights in a row. The
`quality-gates` and `build` jobs pass — this is mutation-testing-only.

The mutation harness is `mut_harness.py`. The gate config is the `MUTATION_GATE`
list in `quality_gates.py`. A target "passes" when its mutation score
(killed/total mutants) is >= its floor. Two targets are failing.

## Failure 1 — `load_bowen_references` scores None (0 mutants)

Root cause: this is a GATE-CONFIG BUG, not a code bug. `load_bowen_references`
(`transcript_utils.py:1410`) is a thin loader — it only does
`bowen_file.exists()`, `if deduped:`, and `return []`. The harness
(`mut_harness.count_ops`) finds ZERO mutation operators there, so
`mutants=0` → `score=None` → it fails the 0.4 floor every time.

The real logic (regex parse + dedupe loop — the F5 Bowen hardening) lives in
`parse_bowen_references_text` (`transcript_utils.py:1431`), which is NOT in the
gate. I verified locally it has **5 mutants**.

### Fix (required)
In `quality_gates.py`, change the gate entry:
```python
    ("transcript_utils.py",
     ["load_bowen_references"], 0.4),
```
to:
```python
    ("transcript_utils.py",
     ["parse_bowen_references_text"], 0.4),
```
Then verify `parse_bowen_references_text` clears 0.4 (needs >=2 of 5 mutants
killed). If it doesn't, add one focused unit test for the dedupe/merge branch
rather than lowering the floor.

### Fix (recommended hardening, small)
Make the gate resilient so a no-surface function can't silently re-break it:
- In `run_mutation_gate` (`quality_gates.py`), treat `score is None` (0 mutants)
  as a SKIP with a warning, not a FAIL.
- In `test_m6a1_mutation_gate_config_is_valid` (`tests/test_quality_gates.py`),
  also assert each listed function has >=1 mutation operator, e.g. via
  `len(mut_harness.count_ops(ast.parse(src), {fn})) >= 1`. Import `mut_harness`
  there. This pins the "target must actually be mutable" invariant.

## Failure 2 — grounding functions score 0.316 (floor 0.5)

Gate entry: `("validation_pipeline.py", ["_emphasis_quote_found_ratio",
"_best_local_grounding"], 0.5)`. Combined 19 mutants, 6 killed = 0.316.

IMPORTANT breakdown: the two functions are bundled, but only one is the problem:
- `_best_local_grounding` (`validation_pipeline.py:200`) → **2/12 = 0.167** (the real issue)
- `_emphasis_quote_found_ratio` (`validation_pipeline.py:538`) → 4/7 = 0.571 (fine on its own)

This is a TEST-STRENGTH gap, not a production bug. The code is correct (it is
the F1/F2 hardening from `tests/test_validator_gate_hardening.py`). You need to
add edge-case tests for `_best_local_grounding` that kill these 10 surviving
mutants (mapped to the exact code):

1. `] or [term]` fallback (line ~219) — flip `or`→`and` survives. Add a case
   where the term SPLITS into parts (non-empty list) AND a case where it falls
   back to `[term]`, asserting the returned grounding is computed from the
   correct parts.
2. `if len(p.strip()) > 3` (line 218) — `>3`→`>=`, `<=`, `4`, `0` all survive.
   Pin the boundary: a 4-char alias part (included) vs a 3-char part
   (excluded), and assert the threshold constant matters.
3. `aggressive=True` (lines 224 and 227, two sites) — flipping to False survives.
   Add a hyphenated/compound occurrence (e.g. "self-differentiation" vs
   "self differentiation") that only matches under aggressive normalization.
4. `range(len(norm_tokens) - span + 1)` (line 231) — the `+ 1` → 2 and → 0
   survive. Add a term occurring at the VERY END of the transcript so the final
   window boundary is exercised.
5. `max(0, i - window)` (line 233) — the `0` → 1 survives. Add a term occurring
   near the START (index < window) so the left clamp is exercised.

Existing real-artifact fixtures live in `tests/fixtures/where_roots/` and are
already exercised by `tests/test_validator_gate_hardening.py` (F1 covers
`_best_local_grounding`). Extend that file or add a focused unit test file
(e.g. `tests/test_local_grounding_edges.py`) — your call, but prefer extending
the existing contract tests where the case fits.

## Repo conventions (from AGENTS.md — follow these)

- Make MINIMAL, targeted changes. No broad refactors, no greenfield rewrites.
- Fix at the correct integration point (tests + the one gate-config line).
- Do NOT fix unrelated failing tests as part of this task.
- Run focused tests first, not the whole suite.
- Use the project venv: `.venv/bin/python` (there is no bare `python` on PATH).
- Update `CHANGELOG.md` only with a concise entry if you judge the behavior
  change warrants it (a test/gate fix — keep it short).

## Verification

1. `.venv/bin/python -m pytest tests/test_quality_gates.py tests/test_validator_gate_hardening.py -q`
   (fast)
2. Targeted mutant count check (fast, no suite run):
   `.venv/bin/python -c "import ast,mut_harness; from pathlib import Path; print(len(mut_harness.count_ops(ast.parse(Path('validation_pipeline.py').read_text()), {'_best_local_grounding'})))"`
   — should report 12, and your new tests should kill most of them.
3. Full gate (SLOW, ~30 min — runs the suite once per mutant):
   `.venv/bin/python quality_gates.py mutation`
   — must exit 0 with every target >= its floor.

## Acceptance criteria

- `quality_gates.py mutation` exits 0.
- Production logic in `validation_pipeline.py` / `transcript_utils.py` is
  UNCHANGED (test-only + gate-config-only), unless you find a genuine bug —
  if so, flag it and stop before changing behavior.
- New tests are assertion-bearing (the vacuity gate will reject empty ones).
- Do NOT lower any floor, do NOT remove a target, and do NOT touch anything
  outside this repo.

## Deliverable

A short summary of: (a) the gate-config change, (b) the tests added and which
surviving mutants each kills, (c) the final `quality_gates.py mutation` exit
code and per-target scores.
