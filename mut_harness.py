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
import signal
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


def _sidecar_path(modpath: Path) -> Path:
    """On-disk backup of the target's original bytes, used for crash/kill recovery."""
    return Path(modpath).with_name(Path(modpath).name + ".mutbak")


def run_campaign(modpath, names, suite_fn, stream=print):
    """Run the mutation campaign against ``modpath``, restoring it byte-for-byte.

    The target is restored to its original bytes on normal completion, on an
    exception mid-run, and — via a sidecar backup — self-healed at the START of a
    later run if a previous run was killed (SIGKILL) before it could restore. This
    is why the harness can no longer leave an ``ast.unparse``-reformatted, mutated
    file on disk (the footgun that corrupted validation_pipeline.py twice).

    ``suite_fn() -> bool`` returns True when the suite is still green (mutant
    SURVIVED). It is injected so tests can run the campaign without pytest.
    """
    modpath = Path(modpath)
    bak = _sidecar_path(modpath)
    # Self-heal: a leftover sidecar means a prior run was killed mid-mutation and
    # the file on disk is a corrupt/reformatted mutant — restore the good bytes
    # BEFORE reading them as "original".
    if bak.exists():
        stream(f"self-heal: restoring {modpath.name} from leftover {bak.name}", flush=True)
        modpath.write_bytes(bak.read_bytes())
    orig = modpath.read_bytes()
    bak.write_bytes(orig)
    src = orig.decode("utf-8")
    n = len(count_ops(ast.parse(src), names))
    found = {fn.name for fn in _target_funcs(ast.parse(src), names)}
    missing = names - found
    stream(f"module={modpath.name} funcs_found={sorted(found)} "
           f"missing={sorted(missing)} mutants={n}", flush=True)
    survived = []
    killed = 0
    t0 = time.time()
    try:
        for k in range(n):
            tree = ast.parse(src)
            desc = apply_kth(tree, names, k)
            if desc is None:
                continue
            try:
                mutated = ast.unparse(tree)
            except Exception as e:
                stream(f"  [{k}] unparse-fail {e}", flush=True)
                continue
            modpath.write_text(mutated, encoding="utf-8")
            if suite_fn():
                survived.append(desc)
                stream(f"  SURVIVED [{k}/{n}] {desc}", flush=True)
            else:
                killed += 1
                stream(f"  killed   [{k}/{n}] {desc}", flush=True)
    finally:
        modpath.write_bytes(orig)
        bak.unlink(missing_ok=True)
    dt = time.time() - t0
    return {"module": modpath.name, "mutants": n, "killed": killed,
            "survived": survived, "score": round(killed / n, 3) if n else None,
            "seconds": round(dt, 1)}


def _stream(*args, flush=False, **kwargs):
    """print() that always flushes, so progress streams instead of buffering."""
    print(*args, flush=True, **kwargs)


def main():
    modpath = REPO / sys.argv[1]
    names = set(sys.argv[2].split(","))
    bak = _sidecar_path(modpath)

    def _restore_and_exit(signum, _frame):
        # Graceful SIGINT/SIGTERM: put the good bytes back before dying so a
        # Ctrl-C / timeout never leaves a mutated file on disk.
        if bak.exists():
            modpath.write_bytes(bak.read_bytes())
            bak.unlink(missing_ok=True)
        print(f"\n[mut_harness] signal {signum}: restored {modpath.name}, exiting",
              flush=True)
        sys.exit(130)

    signal.signal(signal.SIGINT, _restore_and_exit)
    signal.signal(signal.SIGTERM, _restore_and_exit)

    out = run_campaign(modpath, names, run_suite, stream=_stream)
    Path(f"/tmp/mut_{modpath.stem}.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2), flush=True)


if __name__ == "__main__":
    main()
