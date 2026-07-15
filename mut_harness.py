#!/usr/bin/env python3
"""Targeted AST mutation harness.

Mutates a curated set of functions in one module, one mutation at a time, then
runs the GREEN kill-set (full suite minus 7 GUI modules and 10 known-red tests).
A mutant that leaves the suite green = SURVIVED (no test detects the fault).

Usage: python mut_harness.py <module.py> <func1,func2,...>
"""
import ast
import copy
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent

IGNORE = [
    "tests/test_lean_abstract.py", "tests/test_overview_post.py",
    "tests/test_stage_dependencies.py", "tests/test_stage_selection_persistence.py",
    "tests/test_ts_gui_run_all.py", "tests/test_ts_gui_web_generation.py",
    "tests/test_validation_learning.py",
]
DESELECT = [
    "test_config_validation.py::test_runtime_settings_persistence",
    "test_html_generation.py::test_highlighting_logic",
    "test_validation_warnings.py::TestValidationWarnings::test_summary_proportionality_warning",
    "tests/test_bowen_references_integration.py::test_bowen_references_generation_and_extraction",
    "tests/test_bowen_references_integration.py::test_bowen_references_fallback_to_primary_when_filter_invalid",
    "tests/test_header_validation_token_limits.py::test_validate_batch_caps_tokens_for_haiku",
    "tests/test_header_validation_token_limits.py::test_cap_max_tokens_defaults_to_32000_when_model_limit_unknown",
    "tests/test_html_generator.py::TestHtmlGenerator::test_generate_simple_html_page_structure",
    "tests/test_html_generator.py::TestHtmlGenerator::test_highlight_html_content_basic",
    "tests/test_html_generator.py::TestHtmlGenerator::test_highlight_html_content_exact_word_match",
]

CMP_SWAP = {
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE, ast.LtE: ast.Gt,
    ast.Is: ast.IsNot, ast.IsNot: ast.Is, ast.In: ast.NotIn, ast.NotIn: ast.In,
}
CMP_BOUNDARY = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt}


def _target_funcs(tree, names):
    out = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names:
            out.append(n)
    return out


def count_ops(tree, names):
    """Return a list of (kind, sub) op-recipes in deterministic walk order."""
    recipes = []
    for fn in _target_funcs(tree, names):
        for node in ast.walk(fn):
            if isinstance(node, ast.Compare) and node.ops:
                op = type(node.ops[0])
                if op in CMP_SWAP:
                    recipes.append(("cmp_swap", None))
                if op in CMP_BOUNDARY:
                    recipes.append(("cmp_bound", None))
            elif isinstance(node, ast.BoolOp):
                recipes.append(("bool", None))
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in ("all", "any"):
                recipes.append(("allany", None))
            elif isinstance(node, ast.Constant):
                v = node.value
                if isinstance(v, bool):
                    recipes.append(("const", "boolneg"))
                elif isinstance(v, int):
                    recipes.append(("const", "plus1"))
                    if v != 0:
                        recipes.append(("const", "zero"))
                elif isinstance(v, float):
                    recipes.append(("const", "zero"))
                    if v != 1.0:
                        recipes.append(("const", "one"))
    return recipes


def apply_kth(tree, names, k):
    """Walk fresh tree, apply the k-th recipe in place, return description."""
    idx = 0
    for fn in _target_funcs(tree, names):
        for node in ast.walk(fn):
            if isinstance(node, ast.Compare) and node.ops:
                op = type(node.ops[0])
                if op in CMP_SWAP:
                    if idx == k:
                        new = CMP_SWAP[op]
                        node.ops[0] = new()
                        return f"L{node.lineno}: {op.__name__}->{new.__name__}"
                    idx += 1
                if op in CMP_BOUNDARY:
                    if idx == k:
                        new = CMP_BOUNDARY[op]
                        node.ops[0] = new()
                        return f"L{node.lineno}: boundary {op.__name__}->{new.__name__}"
                    idx += 1
            elif isinstance(node, ast.BoolOp):
                if idx == k:
                    new = ast.Or if isinstance(node.op, ast.And) else ast.And
                    node.op = new()
                    return f"L{node.lineno}: {type(node.op).__name__} (and<->or)"
                idx += 1
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in ("all", "any"):
                if idx == k:
                    old = node.func.id
                    node.func.id = "any" if old == "all" else "all"
                    return f"L{node.lineno}: {old}()->{node.func.id}()"
                idx += 1
            elif isinstance(node, ast.Constant):
                v = node.value
                if isinstance(v, bool):
                    if idx == k:
                        node.value = not v
                        return f"L{node.lineno}: {v}->{not v}"
                    idx += 1
                elif isinstance(v, int):
                    if idx == k:
                        node.value = v + 1
                        return f"L{node.lineno}: int {v}->{v+1}"
                    idx += 1
                    if v != 0:
                        if idx == k:
                            node.value = 0
                            return f"L{node.lineno}: int {v}->0"
                        idx += 1
                elif isinstance(v, float):
                    if idx == k:
                        node.value = 0.0
                        return f"L{node.lineno}: float {v}->0.0"
                    idx += 1
                    if v != 1.0:
                        if idx == k:
                            node.value = 1.0
                            return f"L{node.lineno}: float {v}->1.0"
                        idx += 1
    return None


def run_suite():
    cmd = ["python", "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
           "--no-header", "-o", "addopts="]
    for ig in IGNORE:
        cmd.append(f"--ignore={ig}")
    for de in DESELECT:
        cmd += ["--deselect", de]
    try:
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, timeout=120)
        return r.returncode == 0  # True == still green == SURVIVED
    except subprocess.TimeoutExpired:
        return False  # timeout == killed (mutant broke something)


def main():
    modpath = REPO / sys.argv[1]
    names = set(sys.argv[2].split(","))
    src = modpath.read_text()
    orig = src
    n = len(count_ops(ast.parse(src), names))
    found = {fn.name for fn in _target_funcs(ast.parse(src), names)}
    missing = names - found
    print(f"module={sys.argv[1]} funcs_found={sorted(found)} missing={sorted(missing)} mutants={n}")
    survived = []
    killed = 0
    t0 = time.time()
    try:
        for k in range(n):
            tree = ast.parse(orig)
            desc = apply_kth(tree, names, k)
            if desc is None:
                continue
            try:
                mutated = ast.unparse(tree)
            except Exception as e:
                print(f"  [{k}] unparse-fail {e}")
                continue
            modpath.write_text(mutated)
            still_green = run_suite()
            if still_green:
                survived.append(desc)
                print(f"  SURVIVED [{k}/{n}] {desc}")
            else:
                killed += 1
    finally:
        modpath.write_text(orig)
    dt = time.time() - t0
    out = {"module": sys.argv[1], "mutants": n, "killed": killed,
           "survived": survived, "score": round(killed / n, 3) if n else None,
           "seconds": round(dt, 1)}
    Path(f"/tmp/mut_{modpath.stem}.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
