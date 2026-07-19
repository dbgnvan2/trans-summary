"""H8 (review 2026-07-18): the DEFAULT "V2 (Safe)" initial validator must fail CLOSED.

Before the fix, a per-chunk API/parse failure was caught and returned [], so a dropped
chunk was indistinguishable from a clean one and a partially-validated transcript
shipped looking clean (P1/P2 fail-open — the exact pattern the v1 validator deliberately
raises on). A genuine "no findings" ([]) must still parse cleanly and NOT raise.
"""
import logging
import types

import pytest

import config
import transcript_utils
from transcript_initial_validation_v2 import TranscriptValidatorV2


def _validator():
    return TranscriptValidatorV2(api_key="test-key-unused", logger=logging.getLogger("h8-test"))


def _fake_msg(text):
    usage = types.SimpleNamespace(
        input_tokens=1, output_tokens=1,
        cache_creation_input_tokens=0, cache_read_input_tokens=0)
    return types.SimpleNamespace(usage=usage, content=[types.SimpleNamespace(text=text)])


def test_process_chunk_raises_on_api_failure(monkeypatch):
    v = _validator()

    def boom(*args, **kwargs):
        raise RuntimeError("simulated 429 after exhausted retries")

    monkeypatch.setattr(transcript_utils, "call_claude_with_retry", boom)
    with pytest.raises(Exception):
        v._process_single_chunk({"id": 0, "text": "some transcript chunk text"}, config.DEFAULT_MODEL)


def test_process_chunk_raises_on_unparseable_response(monkeypatch):
    v = _validator()
    monkeypatch.setattr(
        transcript_utils, "call_claude_with_retry",
        lambda *a, **k: _fake_msg("the model wrote prose and no JSON array at all"))
    with pytest.raises(Exception):
        v._process_single_chunk({"id": 1, "text": "x"}, config.DEFAULT_MODEL)


def test_process_chunk_accepts_valid_empty_findings(monkeypatch):
    """A legitimate 'no findings' response is a valid empty array and must parse to []
    — NOT raise. This is what keeps the fail-closed change from over-firing."""
    v = _validator()
    monkeypatch.setattr(
        transcript_utils, "call_claude_with_retry", lambda *a, **k: _fake_msg("[]"))
    assert v._process_single_chunk({"id": 2, "text": "x"}, config.DEFAULT_MODEL) == []


def test_process_chunk_raises_on_valid_non_list_json(monkeypatch):
    """A response that parses but is NOT a JSON array (the model returned an object)
    must fail closed, not be accepted as findings (P19; sweep follow-up)."""
    v = _validator()
    monkeypatch.setattr(
        transcript_utils, "call_claude_with_retry",
        lambda *a, **k: _fake_msg('{"note": "I could not find any errors"}'))
    with pytest.raises(Exception):
        v._process_single_chunk({"id": 3, "text": "x"}, config.DEFAULT_MODEL)
