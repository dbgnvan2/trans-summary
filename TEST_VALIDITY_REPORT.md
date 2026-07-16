# trans-summary — Test-suite validity audit

**Question asked:** the app keeps surfacing critical bugs despite a green test suite of 300+ tests. Are those tests valid — i.e. would they actually catch bugs?

**Baseline:** commit `a50d72c` (branch `claude/nostalgic-tu`), the exact commit the previous P19 audit pushed. Working tree effectively clean.

**Method:** run in a Linux/Python-3.11 cloud copy of the repo (the on-device bridge is a Linux 3.10 VM with no network, so it can't run your macOS venv or install tooling). The parsers/validators under test are pure string/regex/logic, so results transfer. Four techniques: (1) mutation testing of the audit's bug-prone functions, (2) fixture-provenance classification of all 60 test files, (3) a vacuity scan, (4) a learnings→test enforcement map. Every finding below is either machine-verified (a mutant survived a real test run) or cited to `file:line`.

---

## Bottom line

**The suite is valid for one job and weak at another.** It is *good at preventing regressions of already-found bugs* — all 12 P19 findings (A1–A12) are pinned by strong real-artifact contract tests — and *poor at catching new faults in the validation logic*, which is exactly where new bugs keep appearing.

The single most decisive number: across the audited functions the suite catches **33% of injected faults (166 of 502)**, and the QA layer that is supposed to catch bad LLM output is the worst — **`summary_validation` detects 9%**, `validation_pipeline` 24%. Meanwhile the contract-tested parsers score 74–75%. So the green suite is dominated by tests that either re-assert a known-fixed bug, or feed idealized synthetic input, or (in several cases) assert nothing at all. That combination is precisely why 311 green tests coexist with recurring bugs.

On "will an AI reviewer just find stuff to find stuff": every claim here is falsifiable and was verified — a surviving mutant is a real test-run that stayed green with the code broken; a false-green test is quoted at its line. Model choice (Fable or otherwise) is second-order to that method.

---

## 1. Mutation testing — the empirical core

A mutant is a small deliberate fault (flip a comparison, swap `and`/`or`, change a constant, negate a boolean/return). If the full suite still passes with the fault in place, **no test detects that fault** — the mutant "survived." Kill-set = the 285-test green suite (minus 7 GUI modules that need tkinter/display, and the 10 known-red tests). Only the audit's bug-prone functions were mutated, not whole files.

| Module (audited functions) | Faults caught | Mutation score |
|---|---|---|
| `transcript_utils` (counters/parsers) | 30 / 40 | **75%** |
| `summary_pipeline` (theme/section/topic parsers) | 28 / 38 | **74%** |
| `extraction_pipeline` (`_is_valid_section_content`, `_top_lens_is_grounded`) | 16 / 25 | 64% |
| `abstract_validation` (coverage/keyword validators) | 33 / 91 | 36% |
| `abstract_pipeline` (theme/purpose/conclusion parsers) | 19 / 68 | 28% |
| `validation_pipeline` (key-terms/topics validators) | 29 / 120 | **24%** |
| `summary_validation` (coverage/keyword/proportionality) | 11 / 120 | **9%** |
| **Aggregate** | **166 / 502** | **33.1%** |

The split is not random: functions with dedicated **real-artifact contract tests** (theme parsers, verdict counters) score 64–75%; the **validators** score 9–36%. The validators are the part of the system whose whole purpose is to catch bad output, and they are the least protected.

### Concrete survivors (all left the suite fully green)

`summary_validation.py`
- `required=True` on coverage items → `False` **survives** at L179, L195, L233, L249. You can silently downgrade required coverage checks to optional — the A9 bug class — anywhere outside the one A9 contract test.
- `required=topic.percentage >= 10` → `< 10` **survives** (L215). The rule deciding which topics *must* be covered can be inverted undetected.
- `if match_count >= threshold or match_ratio >= 0.4` → `and`, and both threshold flips **survive** (L325). The keyword-coverage decision is unpinned.

`validation_pipeline.py`
- `return False` → `return True` **survives** (L238). A fail-closed path can be made to pass unconditionally.
- `if term_ratio < 0.50` → `1.0`, and the `0.90 / 0.50 / 0.80 / 0.35` grounding thresholds → all **survive** (L274–L280). LEARNINGS.md lists the 0.50 term-ratio rule as "covered by a test," but the *threshold value itself* is not pinned — the test passes at any value.

`abstract_validation.py`
- `required=i == 0` (first theme required) → `i != 0` **survives** (L226); the QA required/optional thresholds (L285, L296) **survive**.

`abstract_pipeline.py`
- `if not themes and "###" in themes_markdown` → `or` **survives** (L155) — the legacy `###` theme-fallback gate (the A1 neighborhood) is not pinned.

Full survivor lists: `mutation_results.json`.

---

## 2. Fixture provenance — where the false green comes from

Of 60 test files: **4 real-artifact, 35 synthetic, 14 mock-only, 3 GUI, 4 live-API.** Exactly **one** file (`tests/test_theme_parsing_contract.py`) reads the real KCFC theme artifacts. Every other theme/bowen/key-terms parser test uses hand-written idealized input.

The smoking gun for "green but wrong":

- **`test_summary_pipeline_parsing.py:119` `test_parse_themes_header_format`** asserts a bare `### Theme Header` parses to a valid theme and calls it "the new `### header format`." That is the **A1/A2 bug asserted as correct** — on the real artifact every `### X` is scaffolding and themes are `**N. Title**`. This test was green the whole time the pipeline returned 1-of-3 real themes.
- Same certification of the buggy shape in `tests/test_summary_pipeline.py:20`, `tests/test_abstract_pipeline_topics_parsing.py:45`, and `test_regex.py:68` (the abandoned `1. **Theme**:` numbering).
- A cluster (`test_bowen_cleaning.py`, `tests/test_bowen_references_integration.py:93`, `tests/test_bowen_header_cleanup.py:22`) certifies the **abandoned `> **Label:** "quote"` bowen format** (the A7 dead format); one of them even defines the regex inline in the test, so it validates a test-local copy rather than shipped code.

These pass only because production still carries the legacy shapes as fallback paths. They give confidence that theme/bowen parsing "works" while never touching the real format.

---

## 3. Vacuity — tests that assert nothing

Nine tests cannot fail on the behavior they claim to guard:

- **`test_validation_headless.py`** — `test_validation` and `test_json_format_compliance` have **no `assert` at all**; they `print("❌ FAILED…")` and `return`. They can only fail by raising, and they early-`return` to a no-op when no API key is set. They "guard" LLM-JSON parsing and correction-application and verify neither.
- **`test_exception_fix.py`** (×4) — assertion-free "did not raise" tests; a path that early-returns before reaching the risky code also passes.
- **`test_summary_word_count_fix.py:272`** — `assert not any("minimum 600" in w for w in length_warnings)` where `length_warnings` is pre-filtered to require *both* "Length check" and "Too short", so it is essentially always empty — the A9 vacuous-truth shape, in a test.
- **`test_validation_warnings.py::test_summary_proportionality_warning`** — **crashes** with `AttributeError: module 'unittest' has no attribute 'mock'` (missing `from unittest import mock`); it never reaches its assertions. This is the extra failure not in your ledger (see §4).
- **`test_validation_warnings.py:47` `test_summary_evaluative_warning`** — indented one level too deep, so it is defined *inside* the preceding test method and **pytest never collects or runs it**. A dead test masquerading as coverage.

---

## 4. Failure-ledger reconciliation (your 7-vs-9 drift)

Handoff said 7 pre-existing failures; `TODO.md` says 9; this run shows **10 failed, 285 passed, 12 skipped** (the 12 skipped are `live_api`; the 7 GUI modules are excluded here for tkinter). The 10th, not in any ledger, is `test_summary_proportionality_warning` — and it's failing because it's **broken** (the `unittest.mock` import bug above), not because of a product regression. It presumably "passed" on machines where some earlier import pulled in `unittest.mock` first: an order-dependent false green. A suite that carries a drifting count of known-red tests is where a genuine new failure hides; here it hid a broken test.

---

## 5. Learnings → test enforcement map

**Fully enforced (strong):** all of A1–A12 and all six concrete fix-log entries in LEARNINGS.md are pinned by real-format contract tests (`test_theme_parsing_contract.py`, `test_validator_pass_on_empty_contract.py`, `test_audit_medians_contract.py`, `test_validator_roundtrip_fixes.py`, `test_keyterms_bowen_fixes.py`). This part of the previous work is genuinely solid.

**Gaps (no enforcing test — can silently recur):**
- `unknown_script` cost-log rows on real runs (fix never tested; the conftest redirect only hides test pollution).
- Emphasis saver doesn't sanitize a nested `"` — no round-trip test uses a quote containing a quote.
- `_load_runtime_settings` `AttributeError` on valid non-dict JSON (`[]` or a string top-level).
- A4 residual: a real conclusion using none of `config.ABSTRACT_CONCLUSION_PATTERNS` (the KCFC "witching hour" sign-off) still drops the conclusion check — untested.

**Weak (a test exists but wouldn't catch the real regression):**
- **P9 token/size caps** — covered only by `test_header_validation_token_limits.py`, which is **currently red**, so it enforces nothing.
- **A5 producer wiring** — the counter `count_header_verdicts` is well-pinned, but nothing asserts the producers actually *call* it and surface a real FAIL; a refactor could unwire it and stay green.
- P12 token-usage-report survival; P8 "surface dropped keys" (tolerance tested, surfacing not); `verify_with_llm` positional YES/NO zip when the LLM returns fewer answers than items.

---

## 6. Prioritized remediation

1. **Raise the validator mutation score.** Add threshold/flag assertions targeting the concrete survivors in §1 — `summary_validation.generate_coverage_items` (the `required=` flags and the `>= 10` topic rule), `check_keyword_coverage`/`check_proportionality` thresholds, and `validation_pipeline.validate_key_terms_fidelity` grounding cutoffs (0.50/0.80/0.90). Re-run the harness until these mutants die. This is the highest-leverage work: it directly hardens the layer that keeps missing bugs.
2. **Fix the two broken/dead tests now** — add `from unittest import mock` to `test_validation_warnings.py`, and dedent `test_summary_evaluative_warning` so it actually runs. Then re-establish a *true* red baseline (your ledger should list the real count, and ideally be zero or all `xfail`-marked).
3. **Neutralize the false-green format tests.** The theme/bowen/key-terms synthetic tests that certify abandoned shapes (§2) should be repointed at `tests/fixtures/` real artifacts or deleted — at minimum they must stop asserting the buggy shape is canonical, because they will mask a re-drift.
4. **Give assertion-free tests real assertions** (`test_validation_headless.py`, `test_exception_fix.py`): assert the parsed JSON type/keys, the written CSV row, the emitted warning.
5. **Close the gap-learnings** with regression tests: nested-quote emphasis round-trip; `_load_runtime_settings` non-dict input; a named-logger assertion for the cost log; A5 producer-wiring; and repair/enable the red P9 token-cap tests.
6. **Institutionalize.** Add a mutation gate on the seven core modules to CI (even a coarse threshold), so this can't silently rot again. Coverage % will not tell you this — these modules are highly "covered" and still 9–36% mutation-killed.

---

## 7. Reproduce locally (your real macOS env) + caveats

The delivered `mut_harness.py` is self-contained (the ignore/deselect lists are baked in). In your repo venv:

```
cd /Users/davemini2/ProjectsLocal/Projects/trans-summary
source .venv/bin/activate
python mut_harness.py summary_validation.py check_keyword_coverage,validate_summary_coverage,generate_coverage_items,check_proportionality
```

It backs up and restores each module per mutant; if interrupted, restore from git (`git checkout -- <file>`) before trusting results — an interrupted run can leave a reformatted file (this is exactly the contamination I hit and corrected mid-audit). Cross-checking a module or two on your machine confirms the numbers transfer.

**Caveats / scope.** Mutation ran on the audit's bug-prone *functions*, not every line of all ~10k — the 33% figure characterizes those functions, and whole-module scores would differ. 7 GUI/orchestration modules were analyzed statically (§) but not executed in-cloud (no tkinter/display); their tests are not in the mutation kill-set, so a core-function survivor that one of them happens to cover could be a (rare) false survivor — none of the §1 examples plausibly are, since they live in pure validation logic those GUI tests don't exercise. This audit measured **test validity only**; it did not hunt for new product bugs (that was the deferred Track A).
