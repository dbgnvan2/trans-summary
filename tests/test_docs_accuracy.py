"""H6/H7 (review 2026-07-18): README must not contradict the code — model IDs must match
config.py, and the Run-All halt-list must not claim abstract-coverage halts the run (it's
advisory). These are regression guards for the documentation-drift finding class."""
from pathlib import Path

import config

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_h6_readme_lists_the_real_default_model():
    assert config.settings.DEFAULT_MODEL in README, (
        f"README does not mention the real DEFAULT_MODEL {config.settings.DEFAULT_MODEL!r}")


def test_h6_readme_has_no_stale_model_ids():
    for stale in [
        "claude-sonnet-4-20250514",
        "claude-3-5-haiku-20241022",
        "claude-3-7-sonnet-20250219",
    ]:
        assert stale not in README, f"README still lists a stale model id: {stale}"


def test_h7_readme_does_not_claim_abstract_coverage_halts():
    assert "abstract coverage validation fails, the workflow stops" not in README, (
        "README still claims abstract-coverage failure halts Run All (it is advisory)")


def test_l3_readme_html_generator_line_count_not_stale():
    assert "650 lines" not in README, (
        "README still cites the stale 650-line count for html_generator.py (now 822)")


def test_m4_architecture_documents_release_gate_layer():
    arch = (ROOT / "ARCHITECTURE_DESIGN.md").read_text(encoding="utf-8")
    assert "release_gate.py" in arch, "ARCHITECTURE_DESIGN omits the release-gate layer"
    assert "faithfulness" in arch.lower(), "ARCHITECTURE_DESIGN omits the faithfulness judge"



def test_r16_readme_install_and_key_setup_match_code():
    """G19 (review 2026-10-04): the install line must install the real deps, and the
    key setup must not claim a .env file the pipeline never reads."""
    assert "pip install -r requirements.txt" in README
    assert "pip install anthropic python-dotenv weasyprint beautifulsoup4" not in README
    assert "keys.json" in README


def test_r16_architecture_lists_every_blocking_check():
    arch = (ROOT / "ARCHITECTURE_DESIGN.md").read_text(encoding="utf-8")
    for check in config.GATE_BLOCKING_CHECKS:
        assert f"`{check}`" in arch, f"ARCHITECTURE_DESIGN omits blocking check {check}"
