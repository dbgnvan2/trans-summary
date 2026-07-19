"""H4 (review 2026-07-18): pyproject.toml must declare the real runtime dependencies so
`pip install .` yields a working install (it previously listed only jsonschema)."""
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _dep_names(deps):
    return {re.split(r"[<>=!~ \[]", d, 1)[0].strip().lower() for d in deps}


def test_h4_pyproject_declares_runtime_deps():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    names = _dep_names(data["project"]["dependencies"])
    required = {
        "anthropic", "beautifulsoup4", "jsonschema", "jinja2", "markdown-it-py",
        "pdfminer.six", "python-dotenv", "tiktoken", "weasyprint",
    }
    missing = required - names
    assert not missing, f"pyproject.toml is missing runtime deps: {sorted(missing)}"


def test_h4_requirements_runtime_deps_are_in_pyproject():
    """Every non-test dep pinned in requirements.txt is declared in pyproject (no drift)."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    py_names = _dep_names(data["project"]["dependencies"])
    req_lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    req_names = _dep_names([ln for ln in req_lines if ln.strip() and not ln.startswith("#")])
    req_names -= {"pytest", "pyyaml"}  # test/dev deps, not runtime
    missing = req_names - py_names
    assert not missing, f"requirements.txt runtime deps absent from pyproject: {sorted(missing)}"


def test_test_only_imports_are_declared_pyyaml():
    """PyYAML is imported by tests/test_overview_post.py, so it must be declared in
    requirements.txt — else a clean CI runner fails at collection (sweep follow-up:
    H5's removal of `|| true` unmasked this)."""
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "pyyaml" in req, "PyYAML (imported by a test) is not declared in requirements.txt"
