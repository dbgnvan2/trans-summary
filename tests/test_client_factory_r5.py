"""R5 (review F12/F14 + B-11): one Anthropic client factory, one retry layer.

Spec: docs/plan_review_fixes_2026-10-04.md#R5
"""
import ast
import json
import logging
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx
import pytest

import config
import transcript_utils

ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-test-model"


def _response(stop_reason="end_turn", text="x" * 80):
    return SimpleNamespace(
        type="message", role="assistant", stop_reason=stop_reason, model=MODEL,
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1,
                              cache_creation_input_tokens=0, cache_read_input_tokens=0),
    )


def _call(client, **kw):
    return transcript_utils.call_claude_with_retry(
        client=client, model=MODEL, messages=[{"role": "user", "content": "hi"}],
        max_tokens=64, logger=None, script_name="r5_test", **kw)


@pytest.fixture
def real_key_resolution(monkeypatch, tmp_path):
    """Undo the conftest offline guard for this test only, with an isolated keys file
    and no env key, and capture the kwargs the SDK client is built with."""
    monkeypatch.undo()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    keys = tmp_path / "keys.json"
    monkeypatch.setenv("LLM_KEYS_FILE", str(keys))
    built = {}
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: built.update(kw) or object())
    return keys, built


def test_r5a_factory_uses_keys_json_when_env_unset(real_key_resolution):
    keys, built = real_key_resolution
    keys.write_text(json.dumps({"providers": {"anthropic": {"api_key": "sk-from-file"}}}))
    transcript_utils.get_anthropic_client()
    assert built["api_key"] == "sk-from-file"


def test_r5a_factory_raises_clear_error_without_key(real_key_resolution):
    with pytest.raises(ValueError, match="keys.json"):
        transcript_utils.get_anthropic_client()


def test_r5b_sdk_retries_disabled(real_key_resolution):
    _, built = real_key_resolution
    transcript_utils.get_anthropic_client("sk-explicit")
    assert built["max_retries"] == 0


def test_r5c_timeout_constants_in_config():
    assert config.TIMEOUT_FALLBACK == 600
    assert config.TIMEOUT_ESCALATION_FACTOR == 1.5
    src = (ROOT / "transcript_utils.py").read_text(encoding="utf-8")
    assert "900.0" not in src, "timeout fallback literal must live in config.py"


def test_r5c_default_timeout_applied_and_escalated(monkeypatch):
    monkeypatch.setattr(transcript_utils, "log_token_usage", lambda *a, **k: None)
    timeouts = []
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    def create(**kw):
        timeouts.append(kw.get("timeout"))
        if len(timeouts) == 1:
            raise anthropic.APITimeoutError(request=request)
        return _response()

    client = MagicMock()
    client.messages.create.side_effect = create
    _call(client)
    assert timeouts == [config.TIMEOUT_FALLBACK,
                        config.TIMEOUT_FALLBACK * config.TIMEOUT_ESCALATION_FACTOR]


def test_r5c_server_error_retried_by_wrapper(monkeypatch):
    """With SDK retries off, a 5xx must be retried here (the SDK used to do it)."""
    monkeypatch.setattr(transcript_utils.time, "sleep", lambda _s: None)
    monkeypatch.setattr(transcript_utils, "log_token_usage", lambda *a, **k: None)
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.InternalServerError(
        "boom", response=httpx.Response(500, request=request), body=None)
    client = MagicMock()
    client.messages.create.side_effect = [err, _response()]
    assert _call(client).stop_reason == "end_turn"
    assert client.messages.create.call_count == 2


def test_b11_max_tokens_not_retried_and_usage_logged(monkeypatch):
    logged = []
    monkeypatch.setattr(transcript_utils, "log_token_usage",
                        lambda script, model, usage, stop: logged.append(stop))
    client = MagicMock()
    client.messages.create.return_value = _response(stop_reason="max_tokens")
    with pytest.raises(transcript_utils.TruncatedResponseError):
        _call(client)
    assert client.messages.create.call_count == 1
    assert logged == ["rejected:max_tokens"]


def test_b11_short_response_still_retried(monkeypatch):
    """Non-deterministic validation failures keep their retry."""
    monkeypatch.setattr(transcript_utils, "log_token_usage", lambda *a, **k: None)
    client = MagicMock()
    client.messages.create.side_effect = [_response(text="short"), _response()]
    _call(client)
    assert client.messages.create.call_count == 2


# Scripts outside the pipeline that are not converted (dev/diagnostic tools).
_PERIPHERAL = {"find_available_models.py", "run_tests.py", "test_anthropic_models.py",
               "test_validation_headless.py", "transcript_utils.py"}


def _production_modules():
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.split()
    return [ROOT / p for p in out if "/" not in p and p not in _PERIPHERAL]


def test_r5d_single_client_construction_site():
    offenders = []
    for path in _production_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name == "Anthropic":
                offenders.append(f"{path.name}:{node.lineno} builds anthropic.Anthropic")
            if (name == "getenv" and node.args and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == "ANTHROPIC_API_KEY"):
                offenders.append(f"{path.name}:{node.lineno} reads the key with os.getenv")
    assert not offenders, "use transcript_utils.get_anthropic_client():\n" + "\n".join(offenders)


def test_r5e_conftest_blocks_factory_even_with_env_key(monkeypatch):
    """The offline guard reaches every client: an exported key can't make a unit
    test go live."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-exported")
    with pytest.raises(ValueError):
        transcript_utils.get_anthropic_client()


def test_r5f_no_client_logs_warning(caplog):
    with caplog.at_level(logging.WARNING):
        assert transcript_utils.get_anthropic_client_or_none() is None
    assert any("No Anthropic API key" in r.message for r in caplog.records)
