"""M6 — enforce the test-validity gates in the suite itself.

  * M6.A: the mutation-gate config is well-formed (modules/functions exist,
    floors sane). The expensive mutation *run* is a scheduled CI job, not here.
  * M6.B: the vacuity checker catches an assertion-free test, and no NEW vacuous
    test is added beyond the known pre-existing debt (allowlisted, tracked in
    TODO for real assertions).
  * M6.C: the real-artifact fixtures the parser/validator contract tests depend
    on must exist (they can't be silently deleted, which would hollow out the
    contract tests).
"""
import ast
from pathlib import Path

import pytest

import mut_harness
import quality_gates

REPO = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------- M6.A
def test_m6a1_mutation_gate_config_is_valid():
    assert quality_gates.MUTATION_GATE, "mutation gate must list at least one target"
    for module, funcs, floor in quality_gates.MUTATION_GATE:
        path = REPO / module
        assert path.exists(), f"mutation-gate module missing: {module}"
        assert 0.0 < floor <= 1.0, f"floor out of range for {module}: {floor}"
        assert funcs, f"no functions listed for {module}"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        defined = {
            n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        missing = set(funcs) - defined
        assert not missing, f"mutation-gate functions not found in {module}: {missing}"
        for fn in funcs:
            assert len(mut_harness.count_ops(tree, {fn})) >= 1, (
                f"mutation-gate target has no mutation operators (would always "
                f"score None): {module}::{fn}"
            )


# --------------------------------------------------------------- M6.B
def test_m6b1_vacuity_checker_flags_assertionless_test():
    vacuous_src = (
        "def test_does_nothing():\n"
        "    x = compute()\n"
        "    print(x)\n"
        "def test_has_assert():\n"
        "    assert compute() == 1\n"
        "def test_uses_pytest_raises():\n"
        "    import pytest\n"
        "    with pytest.raises(ValueError):\n"
        "        boom()\n"
    )
    flagged = quality_gates.find_vacuous_tests(vacuous_src)
    assert flagged == ["test_does_nothing"]  # the other two assert / raises


# Allowlist of pre-existing vacuous tests. EMPTY as of 2026-07-15 — all six
# (test_exception_fix.py ×4, test_validation_headless.py ×2) were given real
# assertions (TEST_VALIDITY_REPORT §3 closed). The gate now blocks ANY new
# assertion-free test; keep this empty unless a genuinely-manual harness is added.
KNOWN_VACUOUS: set = set()


def test_m6b1_no_new_vacuous_tests():
    found = set(quality_gates.scan_vacuous(quality_gates._all_test_files()))
    new = found - KNOWN_VACUOUS
    assert not new, (
        "New assertion-free test(s) added — give them real assertions "
        f"(or pytest.raises): {sorted(new)}"
    )
    # Keep the allowlist honest: if a known-vacuous test was fixed, drop it here.
    stale = KNOWN_VACUOUS - found
    assert not stale, f"allowlisted tests are no longer vacuous — remove from allowlist: {sorted(stale)}"


# --------------------------------------------------------------- M6.C
def test_m6c1_real_format_fixtures_exist():
    """The real-artifact fixtures that back the parser/validator contract tests
    must exist — deleting them would leave those tests running on nothing."""
    fixtures = REPO / "tests" / "fixtures"
    assert (fixtures / "kcfc_structural-themes.md").exists()
    assert (fixtures / "kcfc_interpretive-themes.md").exists()
    where_roots = fixtures / "where_roots"
    assert where_roots.is_dir()
    md = list(where_roots.rglob("*formatted.md"))
    assert md, "where_roots real-artifact fixtures missing (formatted transcript)"



# --- sweep 2026-10-09: a gate target that tests nothing must FAIL, not pass ---

def _run_gate_with(monkeypatch, gate, campaign_result):
    from unittest.mock import patch

    monkeypatch.setattr(quality_gates, "MUTATION_GATE", gate)
    lines = []
    with patch.object(mut_harness, "run_campaign", return_value=campaign_result):
        ok = quality_gates.run_mutation_gate(stream=lines.append)
    return ok, lines


def test_m6a2_zero_mutants_fails(monkeypatch):
    ok, lines = _run_gate_with(
        monkeypatch, [("quality_gates.py", ["run_mutation_gate"], 0.5)],
        {"score": None, "mutants": 0})
    assert ok is False
    assert any("[FAIL]" in line and "0 mutation operators" in line for line in lines)


def test_m6a2_missing_target_fails_without_running(monkeypatch):
    ok, lines = _run_gate_with(
        monkeypatch, [("quality_gates.py", ["no_such_function"], 0.5)],
        {"score": 1.0, "mutants": 4})
    assert ok is False
    assert any("not found" in line for line in lines)


def test_m6a2_below_floor_fails_and_at_floor_passes(monkeypatch):
    gate = [("quality_gates.py", ["run_mutation_gate"], 0.5)]
    assert _run_gate_with(monkeypatch, gate, {"score": 0.4, "mutants": 5})[0] is False
    assert _run_gate_with(monkeypatch, gate, {"score": 0.5, "mutants": 4})[0] is True
