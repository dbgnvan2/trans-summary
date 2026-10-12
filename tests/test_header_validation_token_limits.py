from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import config
import transcript_validate_headers
from transcript_utils import cap_max_tokens_for_model

# D5 (docs/plan_todo_triage_2026-10-11.md): the cap is the request, limited only by
# the model's own max output (model_specs.capabilities). It used to floor every
# model to config.MAX_TOKENS_SUMMARY (4096), which truncated larger requests (P9).


def _build_validator():
    """Create validator instance without running file-loading __init__."""
    validator = transcript_validate_headers.HeaderValidator.__new__(
        transcript_validate_headers.HeaderValidator
    )
    validator.logger = MagicMock()
    validator.client = object()
    validator.cached_system_message = [{"type": "text", "text": "cached"}]
    validator.problematic_terms = []
    return validator


def _fake_message(text: str = "ok"):
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def test_d5_validate_batch_sends_configured_limit_for_haiku(monkeypatch):
    validator = _build_validator()
    captured = {}

    def fake_call(*args, **kwargs):
        captured["max_tokens"] = kwargs["max_tokens"]
        return _fake_message()

    monkeypatch.setattr(transcript_validate_headers, "call_claude_with_retry", fake_call)

    batch = [{"number": 1, "heading": "H1", "content": "Body"}]
    validator.validate_batch(batch, model="claude-3-5-haiku-20241022")

    assert captured["max_tokens"] == config.MAX_TOKENS_HEADER_VALIDATION


def test_validate_batch_keeps_config_limit_for_non_haiku(monkeypatch):
    validator = _build_validator()
    captured = {}

    def fake_call(*args, **kwargs):
        captured["max_tokens"] = kwargs["max_tokens"]
        return _fake_message()

    monkeypatch.setattr(transcript_validate_headers, "call_claude_with_retry", fake_call)

    batch = [{"number": 1, "heading": "H1", "content": "Body"}]
    validator.validate_batch(batch, model="claude-sonnet-4-20250514")

    assert captured["max_tokens"] == config.MAX_TOKENS_HEADER_VALIDATION


def test_run_returns_false_when_batches_fail(monkeypatch):
    validator = _build_validator()
    sections = [
        {"number": 1, "heading": "A", "content": "x", "original_heading": "A"},
        {"number": 2, "heading": "B", "content": "y", "original_heading": "B"},
    ]

    monkeypatch.setattr(validator, "parse_transcript", lambda _path: sections)
    monkeypatch.setattr(validator, "check_problematic_terms", lambda _heading: [])
    monkeypatch.setattr(
        validator, "validate_batch", lambda _batch, model: (_ for _ in ()).throw(ValueError("bad request"))
    )
    save_mock = MagicMock()
    monkeypatch.setattr(validator, "_save_report", save_mock)

    result = validator.run(Path("dummy.md"), model="claude-3-5-haiku-20241022")

    assert result is False
    save_mock.assert_called_once()


def test_d5_cap_honors_request_above_old_4096_floor():
    assert config.MAX_TOKENS_SUMMARY < 12000
    assert cap_max_tokens_for_model("claude-haiku-5-5", 12000) == 12000
    assert cap_max_tokens_for_model("claude-sonnet-4-6", 12000) == 12000


def test_d5_cap_clamps_to_model_max_output():
    assert cap_max_tokens_for_model("claude-haiku-4-5-20251001", 100000) == 64000
    assert cap_max_tokens_for_model("claude-haiku-5-5", 500000) == 128000
    # an unknown legacy model gets model_specs' legacy limit
    assert cap_max_tokens_for_model("claude-3-5-haiku-20241022", 50000) == 8192


def test_d5_cap_never_raises_a_request():
    assert cap_max_tokens_for_model("claude-haiku-5-5", 300) == 300


def test_d5_limit_tables_agree():
    """Sweep: config.MODEL_OUTPUT_TOKEN_LIMITS and model_specs capabilities must give
    the same max output for every model config lists (two tables must not drift)."""
    import model_specs
    for name, limit in config.MODEL_OUTPUT_TOKEN_LIMITS.items():
        assert model_specs.capabilities(name)["max_output"] == limit, name
