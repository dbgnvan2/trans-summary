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

