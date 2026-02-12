from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import config
import transcript_validate_headers


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


def test_validate_batch_caps_tokens_for_haiku(monkeypatch):
    validator = _build_validator()
    captured = {}

    def fake_call(*args, **kwargs):
        captured["max_tokens"] = kwargs["max_tokens"]
        return _fake_message()

    monkeypatch.setattr(transcript_validate_headers, "call_claude_with_retry", fake_call)

    batch = [{"number": 1, "heading": "H1", "content": "Body"}]
    validator.validate_batch(batch, model="claude-3-5-haiku-20241022")

    assert captured["max_tokens"] == 8192


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
