"""MV.1-MV.7: running the pipeline on the Claude 5 models
(docs/plan_v5_models_2026-10-10.md). No live calls here; see test_v5_models_live.py."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import config
import model_specs
import transcript_utils as tu

V5 = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1",
      "claude-opus-5", "claude-sonnet-5"]


# --- MV.1 -------------------------------------------------------------------------

def test_mv1_capabilities_known_models():
    for m in V5:
        cap = model_specs.capabilities(m)
        assert cap["temperature"] is False and cap["thinking"] == "always", m
        assert cap["max_output"] == 128000
    assert model_specs.capabilities("claude-opus-5-5")["default_effort"] == "medium"
    assert model_specs.capabilities("claude-sonnet-5-5")["default_effort"] == "high"
    s46 = model_specs.capabilities("claude-sonnet-4-6")
    assert s46["temperature"] is True and s46["thinking"] == "adaptive"
    assert "xhigh" not in s46["effort_levels"]
    h45 = model_specs.capabilities("claude-haiku-4-5-20251001")
    assert h45["temperature"] is True and h45["effort_levels"] == () and h45["max_output"] == 64000


def test_mv1_unknown_v5_name_uses_family_defaults():
    cap = model_specs.capabilities("claude-sonnet-5-7")
    assert cap["temperature"] is False and cap["thinking"] == "always"
    assert model_specs.capabilities("claude-3-5-haiku-20241022")["temperature"] is True


def test_mv1_pricing_present():
    assert model_specs.get_pricing("claude-opus-5-5")["input"] == 4.00
    assert model_specs.get_pricing("claude-sonnet-5-5")["output"] == 10.00
    assert model_specs.get_pricing("claude-haiku-5-5")["input"] == 0.10
    assert model_specs.get_pricing("claude-fable-5-1")["output"] == 50.00
    for m in V5:
        assert m in model_specs.PRICING


# --- MV.3 -------------------------------------------------------------------------

def _msg(blocks, stop="end_turn", out_tokens=50):
    return SimpleNamespace(type="message", role="assistant", stop_reason=stop, stop_details=None,
                           content=blocks, model="m",
                           usage=SimpleNamespace(input_tokens=10, output_tokens=out_tokens,
                                                 cache_creation_input_tokens=0, cache_read_input_tokens=0))


def _block(t, text=None, thinking=None):
    return SimpleNamespace(type=t, text=text, thinking=thinking)


def test_mv3_thinking_then_text_is_valid():
    m = _msg([_block("thinking", thinking=""), _block("text", text="The answer is " + "x " * 40)])
    tu.validate_api_response(m, "claude-opus-5-5", min_length=10)
    assert tu.response_text(m).startswith("The answer is")


def test_mv3_no_text_block_rejected():
    m = _msg([_block("thinking", thinking="...")])
    with pytest.raises(ValueError, match="no text content block"):
        tu.validate_api_response(m, "claude-opus-5-5")


def test_mv3_no_content0_text_left():
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parent.parent
    offenders = [p.name for p in root.glob("*.py")
                 if re.search(r"\.content\[0\]\.text", p.read_text(encoding="utf-8"))]
    assert offenders == []


# --- MV.2 / MV.4 / MV.5 -------------------------------------------------------------

class _FakeClient:
    """Records the kwargs of messages.create and returns a thinking+text reply."""

    def __init__(self, reply=None):
        self.sent = []
        self.reply = reply
        outer = self

        class _Messages:
            def create(self, **kw):
                outer.sent.append(kw)
                return outer.reply or _msg([_block("thinking", thinking=""),
                                            _block("text", text="ok " * 40)])

            def stream(self, **kw):
                outer.sent.append({**kw, "_stream": True})
                reply = outer.reply or _msg([_block("text", text="ok " * 40)])

                class _Ctx:
                    def __enter__(self_inner):
                        return SimpleNamespace(get_final_message=lambda: reply)

                    def __exit__(self_inner, *a):
                        return False
                return _Ctx()

        self.messages = _Messages()


@pytest.fixture
def no_effort(monkeypatch):
    monkeypatch.setattr(type(config.settings), "EFFORT", property(lambda self: None))


def _call(model, client, **kw):
    msgs = [{"role": "user", "content": "hi"}]
    return tu.call_claude_with_retry(client, model, msgs, max_tokens=kw.pop("max_tokens", 4096),
                                     temperature=0.0, min_length=5, max_retries=1, **kw)


def test_mv2_v5_request_has_no_temperature(no_effort):
    c = _FakeClient()
    _call("claude-opus-5-5", c)
    assert "temperature" not in c.sent[0] and "thinking" not in c.sent[0]


def test_mv2_v4_keeps_temperature(no_effort):
    c = _FakeClient()
    _call("claude-sonnet-4-6", c)
    assert c.sent[0]["temperature"] == 0.0
    assert c.sent[0]["max_tokens"] == 4096  # no thinking headroom on 4.6
    assert "extra_body" not in c.sent[0]


def test_mv2_effort_sent_only_when_supported(monkeypatch):
    monkeypatch.setattr(type(config.settings), "EFFORT", property(lambda self: "xhigh"))
    c = _FakeClient()
    _call("claude-opus-5-5", c)
    _call("claude-sonnet-4-6", c)        # 4.6 has no xhigh
    _call("claude-haiku-4-5-20251001", c)  # no effort at all
    assert c.sent[0]["extra_body"]["output_config"] == {"effort": "xhigh"}
    for sent in c.sent[1:]:
        assert "output_config" not in sent.get("extra_body", {})


def test_mv4_headroom_added_and_capped(no_effort):
    c = _FakeClient()
    _call("claude-sonnet-5-5", c, max_tokens=4096)
    assert c.sent[0]["max_tokens"] == 4096 + config.THINKING_TOKEN_HEADROOM
    _call("claude-sonnet-5-5", c, max_tokens=125000)
    assert c.sent[1]["max_tokens"] == 128000 and c.sent[1]["_stream"] is True  # long -> streamed


def test_mv5_refusal_raises_named_error(no_effort):
    reply = _msg([_block("text", text="")], stop="refusal")
    reply.stop_details = SimpleNamespace(category="cyber")
    c = _FakeClient(reply)
    with pytest.raises(tu.RefusalError) as e:
        _call("claude-opus-5-5", c, )
    assert e.value.category == "cyber" and len(c.sent) == 1  # not retried


def test_mv5_fallback_only_for_supported_models(no_effort):
    c = _FakeClient()
    _call("claude-sonnet-5-5", c)
    _call("claude-haiku-5-5", c)
    assert c.sent[0]["extra_body"] == {"fallbacks": "default"}
    assert config.REFUSAL_FALLBACK_BETA in c.sent[0]["extra_headers"]["anthropic-beta"]
    assert "extra_body" not in c.sent[1]
    assert config.REFUSAL_FALLBACK_BETA not in c.sent[1]["extra_headers"]["anthropic-beta"]


# --- MV.6 / MV.7 ----------------------------------------------------------------------

def test_mv6_effort_setting_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "runtime_settings", {})
    saved = []
    monkeypatch.setattr(config.settings, "_save_runtime_settings", lambda: saved.append(1))
    config.settings.set_effort("high")
    assert config.settings.EFFORT == "high" and saved
    config.settings.set_effort(None)
    assert config.settings.EFFORT is None
    with pytest.raises(ValueError):
        config.settings.set_effort("extreme")


def test_mv7_v5_in_model_list():
    names = config.settings.get_all_model_names()
    for m in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1"):
        assert m in names


def test_mv6_gui_effort_choices(monkeypatch):
    import ts_gui
    assert ts_gui.effort_choices() == ["model default", "low", "medium", "high", "xhigh", "max"]
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    logs = []
    gui.log = lambda *a, **k: logs.append(a)
    set_to = []
    monkeypatch.setattr(config.settings, "set_effort", lambda v: set_to.append(v))
    gui.effort_var = MagicMock(get=lambda: "model default")
    gui._on_effort_selected()
    gui.effort_var = MagicMock(get=lambda: "low")
    gui._on_effort_selected()
    assert set_to == [None, "low"]


def test_mv7_probe_has_no_temperature():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "find_available_models.py").read_text()
    assert "temperature=" not in src and '"claude-opus-5-5"' in src


# --- sweep findings ---------------------------------------------------------------------

def test_mv6_judges_ignore_effort_setting(monkeypatch):
    # P20: the GUI Effort setting must not change the calibrated judges.
    import faithfulness_judge as fj
    monkeypatch.setattr(type(config.settings), "EFFORT", property(lambda self: "low"))
    sent = []
    monkeypatch.setattr(fj, "call_claude_with_retry",
                        lambda **kw: sent.append(kw) or _msg([_block("text", text='[{"index": 1, "label": "entailed", "rationale": "r"}]')]),
                        raising=False)
    import transcript_utils
    monkeypatch.setattr(transcript_utils, "call_claude_with_retry",
                        lambda **kw: sent.append(kw) or _msg([_block("text", text='[{"index": 1, "label": "entailed", "rationale": "r"}]')]))
    fj.judge_claims(["Bowen studied families."], "Bowen studied families.", object())
    assert sent and sent[0]["effort"] is config.JUDGE_EFFORT
    params = tu.model_request_params("claude-sonnet-4-6", 0.0, 4096, effort=config.JUDGE_EFFORT)
    assert "output_config" not in params["extra_body"]


def test_mv6_judge_effort_in_cache_version(monkeypatch):
    import release_gate
    import faithfulness_judge as fj
    a = release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS)
    monkeypatch.setattr(config, "JUDGE_EFFORT", "low")
    assert release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS) != a


def test_mv3_no_content0_text_left_anywhere():
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parent.parent
    skip = ("tests", ".claude", ".venv", "venv", "node_modules", ".git")
    offenders = [str(p.relative_to(root)) for p in root.rglob("*.py")
                 if not any(part in skip for part in p.relative_to(root).parts)
                 and re.search(r"\.content\[0\]\.text", p.read_text(encoding="utf-8", errors="ignore"))]
    assert offenders == []


def test_mv4_formatting_budget_leaves_thinking_room():
    import formatting_pipeline as fp
    assert fp.formatting_max_tokens("claude-sonnet-5-5") == 128000 - config.THINKING_TOKEN_HEADROOM
    assert fp.formatting_max_tokens("claude-haiku-4-5-20251001") == 64000
    assert fp.formatting_max_tokens("unknown-model") == config.MAX_TOKENS_FORMATTING


def test_mv5_fallback_answer_priced_at_serving_model(monkeypatch, no_effort):
    logged = []
    monkeypatch.setattr(tu, "log_token_usage", lambda script, model, usage, stop: logged.append(model))
    reply = _msg([_block("text", text="ok " * 40)])
    reply.model = "claude-opus-4-8"
    logger = MagicMock()
    _call("claude-opus-5-5", _FakeClient(reply), logger=logger)
    assert logged == ["claude-opus-4-8"]
    assert any("fallback model claude-opus-4-8" in (c.args[0] % c.args[1:]) for c in logger.warning.call_args_list)


def test_mv_cost_estimate_includes_thinking(monkeypatch):
    import transcript_cost_estimator as tce
    monkeypatch.setattr(type(config.settings), "EFFORT", property(lambda self: None))
    assert tce.thinking_tokens_estimate("claude-sonnet-4-6") == 0
    assert tce.thinking_tokens_estimate("claude-opus-5-5") == config.THINKING_TOKENS_ESTIMATE["medium"]
    monkeypatch.setattr(type(config.settings), "EFFORT", property(lambda self: "max"))
    assert tce.thinking_tokens_estimate("claude-sonnet-5-5") == config.THINKING_TOKENS_ESTIMATE["max"]


def test_mv_log_once_without_logger_still_logs_later(caplog):
    tu._DROPPED_LOGGED.discard(("claude-haiku-5-5", "temperature"))
    tu.model_request_params("claude-haiku-5-5", 0.0, 100, logger=None)
    assert ("claude-haiku-5-5", "temperature") in tu._DROPPED_LOGGED  # logged via module logger
