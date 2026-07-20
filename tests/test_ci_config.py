"""H5 (review 2026-07-18): the CI build matrix must match requires-python (>= 3.11) and
must not mask failures with `|| true`."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")


def test_h5_build_matrix_is_supported_versions_only():
    matrix_lines = [ln for ln in CI.splitlines() if "python-version:" in ln and "[" in ln]
    assert matrix_lines, "no build-matrix python-version line found"
    matrix = matrix_lines[0]
    for bad in ["3.8", "3.9", "3.10"]:
        assert bad not in matrix, f"build matrix still lists Python {bad} (< requires-python 3.11)"
    assert "3.11" in matrix and "3.12" in matrix, "build matrix should cover 3.11 and 3.12"


def test_h5_no_failure_masking():
    assert "|| true" not in CI, "CI still masks a step failure with '|| true'"
