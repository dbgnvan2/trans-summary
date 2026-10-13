"""U4 — formatting runs on Sonnet 5.5 (Haiku 4.5 retires no sooner than 2026-10-15;
measured in docs/calibration_formatting_model_2026-10-11.md). Sonnet 5.5 thinks before
it answers, about config.FORMATTING_THINKING_RATIO thinking tokens per transcript token
when formatting, so the cost estimate and the single-pass length check count it.

Spec: docs/plan_todo_triage_2026-10-11.md#U4
"""
import re
from pathlib import Path

import config
import formatting_pipeline as fp
import transcript_cost_estimator as tce
from transcript_utils import estimate_token_count

ROOT = Path(__file__).resolve().parent.parent


def test_u4_formatting_default_is_sonnet55():
    src = (ROOT / "config.py").read_text(encoding="utf-8")
    assert re.search(r'self\.FORMATTING_MODEL = "claude-sonnet-5-5"', src)


def test_u4_thinking_ratio_from_measurement():
    # measured 2.0-5.0 (median ~3.6) on 3 real talks, 2026-10-11
    assert 2.0 <= config.FORMATTING_THINKING_RATIO <= config.FORMATTING_THINKING_RATIO_MAX == 5.0


def _text_with_tokens(n):
    """Text whose estimate_token_count is about ``n``."""
    text = "family " * n
    while estimate_token_count(text) > n:
        text = text[: int(len(text) * n / estimate_token_count(text)) - 1]
    return text


def test_u4_length_check_counts_thinking():
    limit_tokens = 128000 / (config.FORMATTING_OUTPUT_EXPANSION + config.FORMATTING_THINKING_RATIO)
    needed, limit = fp.formatting_output_needed("claude-sonnet-5-5", _text_with_tokens(int(limit_tokens * 0.95)))
    assert needed <= limit == 128000
    needed, limit = fp.formatting_output_needed("claude-sonnet-5-5", _text_with_tokens(int(limit_tokens * 1.05)))
    assert needed > limit  # stopped before a paid call


def test_u4_length_check_no_thinking_for_legacy_model():
    text = _text_with_tokens(30000)
    needed, limit = fp.formatting_output_needed("claude-haiku-4-5-20251001", text)
    assert needed == int(estimate_token_count(text) * config.FORMATTING_OUTPUT_EXPANSION)
    assert limit == 64000


def test_u4_warns_between_typical_and_maximum(tmp_path, monkeypatch):
    """Fits at the typical ratio, not at the measured maximum -> runs, with a warning."""
    from unittest.mock import MagicMock
    t = int(128000 / (config.FORMATTING_OUTPUT_EXPANSION + 4.2))
    source = tmp_path / "source"
    source.mkdir()
    (source / "Talk - A Person - 2021-01-01.txt").write_text(_text_with_tokens(t), encoding="utf-8")
    monkeypatch.setattr(config, "SOURCE_DIR", source)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(fp, "format_transcript_with_claude", lambda *a, **k: "## Section 1 - A (00:00:00)\nfamily\n")
    logger = MagicMock()
    fp.format_transcript("Talk - A Person - 2021-01-01.txt", model="claude-sonnet-5-5", logger=logger)
    warned = [c.args[0] for c in logger.warning.call_args_list]
    assert any("may be cut off" in w for w in warned)
    assert not any("too long" in c.args[0] for c in logger.error.call_args_list)


def test_u4_formatting_runs_at_model_default_effort(monkeypatch):
    captured = {}
    monkeypatch.setattr(fp, "get_anthropic_client", lambda: object())
    monkeypatch.setattr(fp, "call_claude_with_retry", lambda *a, **k: captured.update(k) or "x")
    monkeypatch.setattr(fp.transcript_utils, "response_text", lambda m: "x")
    fp.format_transcript_with_claude("raw words here", "PROMPT", model="claude-sonnet-5-5")
    assert "effort" in captured and captured["effort"] is config.FORMATTING_EFFORT is None


def test_u4_cost_estimate_counts_formatting_thinking(tmp_path, monkeypatch):
    transcript = tmp_path / "t.txt"
    transcript.write_text(_text_with_tokens(13000), encoding="utf-8")
    monkeypatch.setattr(config.settings, "FORMATTING_MODEL", "claude-sonnet-5-5")
    est = tce.CostEstimator(transcript)
    est.estimate_formatting()
    row = est.costs[-1]
    t = est.transcript_tokens
    assert row["output_tokens"] == t + int(t * config.FORMATTING_THINKING_RATIO)  # no double count


def test_u4_cost_estimate_follows_gui_model(tmp_path, monkeypatch):
    """Sweep: the estimate prices the model selected in the GUI (config.settings)."""
    transcript = tmp_path / "t.txt"
    transcript.write_text(_text_with_tokens(13000), encoding="utf-8")
    monkeypatch.setattr(config.settings, "FORMATTING_MODEL", "claude-haiku-4-5-20251001")
    est = tce.CostEstimator(transcript)
    est.estimate_formatting()
    assert est.costs[-1]["model"] == "claude-haiku-4-5-20251001"
    assert est.costs[-1]["output_tokens"] == est.transcript_tokens


def test_u5_no_default_on_the_retiring_haiku_45():
    """U5: Haiku 4.5 retires no sooner than 2026-10-15; no default may use it."""
    src = (ROOT / "config.py").read_text(encoding="utf-8")
    for name in ("AUX_MODEL", "FORMATTING_MODEL", "VALIDATION_MODEL", "DEFAULT_MODEL"):
        m = re.search(rf'self\.{name} = "([^"]+)"', src)
        assert m and "haiku-4-5" not in m.group(1), name
    assert re.search(r'self\.AUX_MODEL = "claude-haiku-5-5"', src)


def test_t4_estimate_prices_the_gui_models(tmp_path, monkeypatch):
    """T4: every estimate row prices the model the GUI will run that step with,
    taken from config.settings (the GUI selection), not the import-time globals.
    Structured summary and abstract coverage run on the main model (ts_gui)."""
    transcript = tmp_path / "t.txt"
    transcript.write_text(_text_with_tokens(8000), encoding="utf-8")
    monkeypatch.setattr(config.settings, "DEFAULT_MODEL", "claude-opus-5-5")
    monkeypatch.setattr(config.settings, "AUX_MODEL", "claude-haiku-5-5")
    monkeypatch.setattr(config.settings, "FORMATTING_MODEL", "claude-sonnet-5-5")
    monkeypatch.setattr(config, "DEFAULT_MODEL", "claude-sonnet-4-6")  # stale global
    monkeypatch.setattr(config, "AUX_MODEL", "claude-haiku-4-5-20251001")
    est = tce.CostEstimator(transcript)
    est.run_full_estimation()
    by_step = {row["step"]: row["model"] for row in est.costs}
    assert by_step["1. Formatting"] == "claude-sonnet-5-5"
    assert by_step["3a. Structured Summary"] == "claude-opus-5-5"
    assert by_step["3b. Structured Abstract"] == "claude-haiku-5-5"
    assert by_step["6. Abstract Coverage Validation"] == "claude-opus-5-5"
    assert not any(m in ("claude-sonnet-4-6", "claude-haiku-4-5-20251001") for m in by_step.values())


def test_t5_gui_model_choice_reaches_module_values_and_manifest(monkeypatch):
    """T5 (review): choosing a model in the GUI (config.settings.set_*_model) also
    updates config.DEFAULT_MODEL etc., and the run manifest records the models the
    run used. The 2026-10-12 Opus run's manifest said claude-sonnet-4-6."""
    import release_gate
    s = config.settings
    saved = (s.DEFAULT_MODEL, s.AUX_MODEL, s.FORMATTING_MODEL, s.VALIDATION_MODEL,
             config.DEFAULT_MODEL, config.AUX_MODEL, config.FORMATTING_MODEL, config.VALIDATION_MODEL)
    try:
        s.set_default_model("claude-opus-5-5")
        s.set_aux_model("claude-haiku-5-5")
        s.set_formatting_model("claude-sonnet-5-5")
        assert config.DEFAULT_MODEL == "claude-opus-5-5"
        assert config.AUX_MODEL == "claude-haiku-5-5"
        assert config.FORMATTING_MODEL == "claude-sonnet-5-5"
        stamp = release_gate._models_stamp()
        assert stamp == {"default": "claude-opus-5-5", "aux": "claude-haiku-5-5",
                         "formatting": "claude-sonnet-5-5", "validation": s.VALIDATION_MODEL}
    finally:
        (s.DEFAULT_MODEL, s.AUX_MODEL, s.FORMATTING_MODEL, s.VALIDATION_MODEL,
         config.DEFAULT_MODEL, config.AUX_MODEL, config.FORMATTING_MODEL, config.VALIDATION_MODEL) = saved
