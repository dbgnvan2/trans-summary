"""MV.8: one short real call per Claude 5 model through call_claude_with_retry.

Opt-in only (costs a few cents): pytest --live-api tests/test_v5_models_live.py
Spec: docs/plan_v5_models_2026-10-10.md#MV.8
"""
import logging

import pytest

import config
import transcript_utils as tu

V5 = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1"]


@pytest.mark.live_api
@pytest.mark.parametrize("model", V5)
def test_mv8_live_call_each_v5_model(model, monkeypatch):
    monkeypatch.undo()  # this test needs the real key resolver (conftest blanks it)
    key = tu.resolve_anthropic_key()
    if not key:
        pytest.skip("no Anthropic API key available")
    client = tu.get_anthropic_client(key)
    message = tu.call_claude_with_retry(
        client, model,
        [{"role": "user", "content": "Reply with exactly one word: ready"}],
        max_tokens=64, temperature=config.TEMP_STRICT, min_length=3, max_retries=1,
        logger=logging.getLogger("mv8"),
    )
    assert "ready" in tu.response_text(message).lower()


@pytest.mark.live_api
def test_mv8_live_effort_level_accepted(monkeypatch):
    monkeypatch.undo()
    key = tu.resolve_anthropic_key()
    if not key:
        pytest.skip("no Anthropic API key available")
    monkeypatch.setattr(type(config.settings), "EFFORT", property(lambda self: "low"))
    message = tu.call_claude_with_retry(
        tu.get_anthropic_client(key), "claude-sonnet-5-5",
        [{"role": "user", "content": "Reply with exactly one word: ready"}],
        max_tokens=64, min_length=3, max_retries=1)
    assert "ready" in tu.response_text(message).lower()
