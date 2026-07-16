"""Live-API integration harness for TranscriptValidator (skipped by default;
run with `--live-api` / `RUN_LIVE_API_TESTS=1`).

Previously print-only (vacuous). Now asserts real contracts: `validate` returns a
list of findings, each finding carries the required schema keys, and an applied
correction actually lands in the output file. Missing preconditions -> `pytest.skip`
(a real skip, not a silent `return`).
"""
import logging
import os
from pathlib import Path

import pytest

from transcript_initial_validation import TranscriptValidator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("HeadlessTest")

pytestmark = pytest.mark.live_api

_REQUIRED_KEYS = {"error_type", "original_text", "suggested_correction", "reasoning"}


def test_validation():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    test_file = Path("source/dummy_test_transcript.txt")
    if not test_file.exists():
        pytest.skip(f"test transcript not found: {test_file}")

    validator = TranscriptValidator(api_key, logger)
    findings = validator.validate(test_file)
    assert isinstance(findings, list)

    if findings:
        first = findings[0]
        assert _REQUIRED_KEYS <= set(first.keys())
        output_file = test_file.parent / f"test_validated_{test_file.stem}.txt"
        try:
            new_path = validator.apply_corrections(
                test_file, [first], output_path=output_file)
            content = Path(new_path).read_text(encoding="utf-8")
            # the applied correction must actually appear in the output
            assert first["suggested_correction"] in content
        finally:
            if output_file.exists():
                output_file.unlink()


def test_json_format_compliance(tmp_path):
    """The validator's LLM output parses to a list; each item matches the schema."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    temp_file = tmp_path / "temp_json_test_transcript.txt"
    temp_file.write_text(
        "This is a tezt transcript with some obvious erors to trigger JSON output.",
        encoding="utf-8")

    validator = TranscriptValidator(api_key, logger)
    findings = validator.validate(temp_file)
    assert isinstance(findings, list)  # JSON parsed to a list
    if findings:
        assert _REQUIRED_KEYS <= set(findings[0].keys())
