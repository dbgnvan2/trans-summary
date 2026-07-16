"""M6 — test-validity gates (spec_unattended_robustness_2026-07-15.md).

Two gates that keep the test suite honest — because a green suite is not a valid
suite (TEST_VALIDITY_REPORT.md):

  * M6.B vacuity checker — a test with no assertion can only fail by raising; it
    "guards" behaviour it never checks. ``find_vacuous_tests`` flags them.
  * M6.A mutation gate — coverage says a line ran; mutation says a fault in it
    would be caught. ``MUTATION_GATE`` lists the core functions and their score
    floors; ``run_mutation_gate`` runs the harness and fails below floor.

Run as a script (CI):
    python quality_gates.py vacuity     # fast; fails on any NEW vacuous test
    python quality_gates.py mutation    # slow; runs the mutation floors
"""
import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent


# --------------------------------------------------------------- M6.B vacuity
_ASSERT_CALL_NAMES = {"fail", "raises", "warns", "approx", "xfail", "skip"}


def _is_assertionish(node: ast.AST) -> bool:
    if isinstance(node, ast.Assert):
        return True
    if isinstance(node, ast.Call):
        func = node.func
        name = getattr(func, "attr", None) or getattr(func, "id", None) or ""
        if name.startswith("assert") or name in _ASSERT_CALL_NAMES:
            return True
    if isinstance(node, (ast.With, ast.AsyncWith)):
        for item in node.items:
            ctx = item.context_expr
            if isinstance(ctx, ast.Call):
                nm = getattr(ctx.func, "attr", None) or getattr(ctx.func, "id", None) or ""
                if nm in _ASSERT_CALL_NAMES:
                    return True
    return False


def find_vacuous_tests(source: str) -> list[str]:
    """Return the names of ``test_*`` functions in ``source`` that contain no
    assertion, ``pytest.raises``/``warns``/``fail``, or ``self.assert*`` call —
    they can only fail by raising, so they verify nothing they claim to guard."""
    tree = ast.parse(source)
    vacuous = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            if not any(_is_assertionish(child) for child in ast.walk(node)):
                vacuous.append(node.name)
    return vacuous


def scan_vacuous(test_files) -> list[tuple[str, str]]:
    """Scan test files, returning (relpath, test_name) for every vacuous test."""
    found = []
    for path in test_files:
        path = Path(path)
        rel = path.relative_to(REPO).as_posix() if path.is_absolute() else path.as_posix()
        for name in find_vacuous_tests(path.read_text(encoding="utf-8")):
            found.append((rel, name))
    return found


def _all_test_files():
    return sorted(
        set(REPO.glob("test_*.py")) | set((REPO / "tests").glob("test_*.py"))
    )


# --------------------------------------------------------------- M6.A mutation
# (module, [functions], min_score). Kept small and fast: the audit's bug-prone
# functions, not whole modules. Extend as new validator logic is added.
MUTATION_GATE = [
    ("validation_pipeline.py",
     ["_emphasis_quote_found_ratio", "_best_local_grounding"], 0.5),
    ("validation_pipeline.py",
     ["_keyword_grounding_ratio"], 0.5),
    ("transcript_utils.py",
     ["load_bowen_references"], 0.4),
]


def run_mutation_gate(stream=print) -> bool:
    """Run each MUTATION_GATE entry; return True iff all clear their floor."""
    import mut_harness

    ok = True
    for module, funcs, floor in MUTATION_GATE:
        res = mut_harness.run_campaign(
            REPO / module, set(funcs), mut_harness.run_suite, stream=stream
        )
        score = res["score"]
        status = "OK" if (score is not None and score >= floor) else "FAIL"
        if status == "FAIL":
            ok = False
        stream(f"[{status}] {module}:{','.join(funcs)} score={score} floor={floor}")
    return ok


def main(argv):
    if len(argv) < 2 or argv[1] not in ("vacuity", "mutation"):
        print("usage: python quality_gates.py {vacuity|mutation}")
        return 2
    if argv[1] == "vacuity":
        # The script form fails on ANY vacuous test; the allowlist for known
        # pre-existing debt lives in the test (test_quality_gates.py), not here.
        found = scan_vacuous(_all_test_files())
        for rel, name in found:
            print(f"VACUOUS: {rel}::{name}")
        return 1 if found else 0
    ok = run_mutation_gate()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
