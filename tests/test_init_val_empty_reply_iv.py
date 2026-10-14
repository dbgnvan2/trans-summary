"""IV — Init Val stopped a real run (2026-10-13, Why Families): for a chunk with
nothing to fix the model replied with a fenced empty list, "```json\\n[]\\n```" (14
characters), and call_claude_with_retry's 50-character default rejected it three
times. The older tests replaced call_claude_with_retry entirely, so the length check
never ran in them; these go through the real function with a fake client.
"""
import ast
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

import config
import transcript_utils as tu
from transcript_initial_validation import TranscriptValidator
from transcript_initial_validation_v2 import TranscriptValidatorV2

ROOT = Path(__file__).resolve().parent.parent
FENCED_EMPTY = "```json\n[]\n```"


def _msg(text):
    return SimpleNamespace(
        type="message", role="assistant", stop_reason="end_turn", stop_details=None,
        model="m", content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                              cache_creation_input_tokens=0, cache_read_input_tokens=0))


class _Client:
    """Fake Anthropic client: every call (streamed or not) returns ``text``."""

    def __init__(self, text):
        self.calls = 0
        outer = self

        class _Messages:
            def create(self, **kw):
                outer.calls += 1
                return _msg(text)

            def stream(self, **kw):
                outer.calls += 1

                class _Ctx:
                    def __enter__(self_inner):
                        return SimpleNamespace(get_final_message=lambda: _msg(text))

                    def __exit__(self_inner, *a):
                        return False
                return _Ctx()

        self.messages = _Messages()


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(type(config.settings), "EFFORT", property(lambda self: None))
    monkeypatch.setattr(tu, "log_token_usage", lambda *a, **k: None)
    monkeypatch.setattr("time.sleep", lambda s: None)


def _v2(text):
    v = TranscriptValidatorV2(api_key="unused", logger=logging.getLogger("iv"))
    v.client = _Client(text)
    return v


def _v1(text, tmp_path):
    v = TranscriptValidator(api_key="unused", logger=logging.getLogger("iv"))
    v.client = _Client(text)
    path = tmp_path / "Talk - A Person - 2021-01-01.txt"
    path.write_text("Kerr said the family is an emotional unit.", encoding="utf-8")
    return v, path


def test_iv_v2_fenced_empty_list_is_a_clean_chunk(quiet):
    v = _v2(FENCED_EMPTY)
    assert v._process_single_chunk({"id": 2, "text": "x"}, "claude-sonnet-5-5") == []
    assert v.client.calls == 1  # accepted first time, not retried


def test_iv_v2_short_non_list_still_stops(quiet):
    """Adversarial: a short reply that is not a list is still an error, not 'clean'."""
    for text in ("{}", "No issues.", "```json\n{}\n```"):
        with pytest.raises(ValueError, match="could not parse a JSON array"):
            _v2(text)._process_single_chunk({"id": 0, "text": "x"}, "claude-sonnet-5-5")


def test_iv_v2_error_names_the_chunk_as_the_progress_line_does(quiet, caplog):
    v = _v2("no list here")
    with caplog.at_level(logging.ERROR, logger="iv"), pytest.raises(ValueError):
        v._process_single_chunk({"id": 2, "text": "x"}, "claude-sonnet-5-5")
    assert "Error processing chunk 3:" in caplog.text


def test_iv_v1_fenced_empty_list_is_no_errors(quiet, tmp_path):
    v, path = _v1(FENCED_EMPTY, tmp_path)
    assert v.validate(path, model="claude-sonnet-5-5") == []


def test_iv_v1_reply_without_a_list_stops(quiet, tmp_path):
    """Before IV, v1 returned zero findings for a reply with no '['; the 50-char
    minimum hid that for short replies. Lowering the minimum must not expose it."""
    for text in ("No issues.", "[ unclosed",
                 # over 50 chars: before IV this returned zero findings (fail open)
                 "The transcript reads cleanly and I found no errors that need correcting."):
        v, path = _v1(text, tmp_path)
        with pytest.raises(json.JSONDecodeError):
            v.validate(path, model="claude-sonnet-5-5")


def test_iv_callers_on_the_default_minimum_are_listed():
    """Every DIRECT call that relies on call_claude_with_retry's 50-char default is one
    where a valid reply is always long. A new caller must be checked and added here.
    Not covered: wrappers that pass min_length through (e.g.
    extraction_pipeline._generate_summary_with_claude) and explicit minimums that are
    still too high for an empty answer (open in TODO, IV)."""
    reviewed = {
        ("formatting_pipeline.py", "call_claude_with_retry"),  # checks min_words instead
        ("transcript_validate_headers.py", "call_claude_with_retry"),  # a block per section
        ("summary_pipeline.py", "call_claude_with_retry"),  # min_words: >= 90% of the target (SL)
    }
    found = set()
    for p in ROOT.glob("*.py"):
        if p.name.startswith("test_"):
            continue
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call):
                name = getattr(n.func, "attr", None) or getattr(n.func, "id", None)
                if name == "call_claude_with_retry" and "min_length" not in {k.arg for k in n.keywords}:
                    found.add((p.name, name))
    assert found == reviewed
