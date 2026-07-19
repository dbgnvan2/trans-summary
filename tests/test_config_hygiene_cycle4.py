"""Review 2026-07-18 batch 4 — config hygiene:
- M6: retry policy promoted from hard-coded literals to config.
- L5: VALIDATION_MODEL gets a setter like its siblings.
- L7: lens stopwords live in config, not embedded in source.
"""
import inspect

import pytest

import config
import extraction_pipeline
import model_specs
import transcript_utils


def test_m6_retry_constants_in_config():
    assert config.MAX_RETRIES == 3
    assert config.RETRY_BACKOFF_BASE == 2


def test_m6_call_claude_default_max_retries_is_config():
    sig = inspect.signature(transcript_utils.call_claude_with_retry)
    assert sig.parameters["max_retries"].default == config.MAX_RETRIES


def test_m6_backoff_uses_config_not_literal():
    """The exponential backoff must reference config.RETRY_BACKOFF_BASE, not the bare
    literal `2 ** attempt` (P10: verify the behavior, not just the constant's value)."""
    from pathlib import Path
    src = Path(transcript_utils.__file__).read_text(encoding="utf-8")
    assert "config.RETRY_BACKOFF_BASE ** attempt" in src
    assert "wait_time = 2 ** attempt" not in src


def test_l5_set_validation_model_valid_and_invalid():
    s = config.settings
    orig = s.VALIDATION_MODEL
    try:
        valid = next(iter(model_specs.PRICING))
        s.set_validation_model(valid)
        assert s.VALIDATION_MODEL == valid
        with pytest.raises(ValueError):
            s.set_validation_model("definitely-not-a-real-model-xyz")
    finally:
        s.VALIDATION_MODEL = orig


def test_l7_lens_stopwords_sourced_from_config():
    assert isinstance(config.LENS_STOPWORDS, frozenset)
    assert "the" in config.LENS_STOPWORDS
    assert extraction_pipeline._LENS_STOPWORDS is config.LENS_STOPWORDS
