"""M8.A / M6.B — structural code-health guards.

These are cheap AST-level guards that keep the whole-file footguns from creeping
back: a shadowed top-level definition (Python silently keeps the last one, so a
"fix" to the wrong copy is invisible — the two `_generate_simple_html_page`
copies were exactly this), and assertion-free "vacuous" tests that pass without
verifying anything (the test-validity audit found nine).
"""
import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

CORE_MODULES = [
    "html_generator.py",
    "validation_pipeline.py",
    "transcript_utils.py",
    "abstract_validation.py",
    "abstract_pipeline.py",
    "summary_pipeline.py",
    "summary_validation.py",
    "config.py",
    "extraction_pipeline.py",
    "formatting_pipeline.py",
]


# M8.B — the pre-existing red tests must stay explained: each carries an xfail
# marker with a reason. This guards against silently un-xfailing one (which would
# turn the suite red again and let a real regression hide in the noise) OR leaving
# it failing unannotated.
KNOWN_REDS = [
    ("test_config_validation.py", "test_runtime_settings_persistence"),
    ("tests/test_header_validation_token_limits.py", "test_validate_batch_caps_tokens_for_haiku"),
    ("tests/test_header_validation_token_limits.py", "test_cap_max_tokens_defaults_to_32000_when_model_limit_unknown"),
    ("tests/test_bowen_references_integration.py", "test_bowen_references_generation_and_extraction"),
    ("tests/test_bowen_references_integration.py", "test_bowen_references_fallback_to_primary_when_filter_invalid"),
]


@pytest.mark.parametrize("relpath,func", KNOWN_REDS)
def test_m8b1_known_reds_are_xfail_annotated(relpath, func):
    tree = ast.parse((REPO / relpath).read_text(encoding="utf-8"))
    fn = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.FunctionDef) and n.name == func),
        None,
    )
    assert fn is not None, f"{func} not found in {relpath}"
    decorators = " ".join(ast.unparse(d) for d in fn.decorator_list).lower()
    assert "xfail" in decorators, (
        f"{relpath}::{func} is a known pre-existing failure but is not xfail-"
        f"annotated — fix it or mark it xfail with a reason (M8.B)."
    )


@pytest.mark.parametrize("module", CORE_MODULES)
def test_m8a1_no_shadowed_defs(module):
    """No core module may define the same top-level function/class name twice —
    the later one silently shadows the earlier, hiding dead code and mis-targeted
    edits."""
    tree = ast.parse((REPO / module).read_text(encoding="utf-8"))
    names = [
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"{module} has shadowed top-level definitions: {dupes}"
