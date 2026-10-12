"""HV — header validation: one implementation (the batched HeaderValidator), and a
per-batch output budget that holds a batch's full report.

The whole-transcript path in validation_pipeline.validate_headers asked for every
section's report in one 4096-token call and was cut off on a real 10k-word talk
(2026-10-12, Haiku 4.5). Spec: docs/plan_todo_triage_2026-10-11.md#HV
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import config
import transcript_validate_headers as tvh
import validation_pipeline as vp

BASE = "Talk - A Person - 2021-01-01"


def _project(tmp_path, monkeypatch):
    proj = tmp_path / BASE
    proj.mkdir()
    f = proj / f"{BASE}{config.SUFFIX_FORMATTED}"
    f.write_text("## Section 1 - Opening (00:00:00)\nHello there everyone.\n", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    return f


def test_hv1_validate_headers_uses_batched_validator(tmp_path, monkeypatch):
    path = _project(tmp_path, monkeypatch)
    seen = {}

    def fake_run(self, input_path, model=None):
        seen["path"], seen["model"] = Path(input_path), model
        return True

    with patch.object(tvh.HeaderValidator, "__init__", lambda self, key, logger: None), \
            patch.object(tvh.HeaderValidator, "run", fake_run), \
            patch("transcript_utils.resolve_anthropic_key", return_value="k"):
        assert vp.validate_headers(path.name, model="claude-haiku-5-5", logger=MagicMock()) is True
    assert seen == {"path": path, "model": "claude-haiku-5-5"}


def test_hv1_failed_batches_make_validate_headers_fail(tmp_path, monkeypatch):
    path = _project(tmp_path, monkeypatch)
    with patch.object(tvh.HeaderValidator, "__init__", lambda self, key, logger: None), \
            patch.object(tvh.HeaderValidator, "run", lambda self, p, model=None: False), \
            patch("transcript_utils.resolve_anthropic_key", return_value="k"):
        assert vp.validate_headers(path.name, model="m", logger=MagicMock()) is False


def test_hv1_no_key_fails_closed(tmp_path, monkeypatch):
    path = _project(tmp_path, monkeypatch)
    logger = MagicMock()
    with patch("transcript_utils.resolve_anthropic_key", return_value=None):
        assert vp.validate_headers(path.name, model="m", logger=logger) is False
    assert logger.error.called


def test_hv2_batch_budget_holds_a_full_batch():
    # A 5-section batch report is ~2-3k tokens on Haiku 4.5 (measured 2026-10-12);
    # 4096 left too little room. max_tokens is a ceiling, not a charge.
    assert config.MAX_TOKENS_HEADER_VALIDATION >= 8192
    v = tvh.HeaderValidator.__new__(tvh.HeaderValidator)
    v.logger = MagicMock()
    v.client = object()
    v.cached_system_message = [{"type": "text", "text": "cached"}]
    captured = {}

    def fake_call(*a, **k):
        captured["max_tokens"] = k["max_tokens"]
        from types import SimpleNamespace
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")])
    with patch.object(tvh, "call_claude_with_retry", fake_call):
        v.validate_batch([{"number": 1, "heading": "H", "content": "Body"}], model="claude-haiku-5-5")
    assert captured["max_tokens"] == config.MAX_TOKENS_HEADER_VALIDATION


def test_hv1_single_call_path_removed():
    assert not hasattr(vp, "_generate_validation_response")


def test_hv3_no_sections_rewrites_the_report(tmp_path, monkeypatch):
    """Sweep (P8): a transcript without sections must not leave an older report."""
    path = _project(tmp_path, monkeypatch)
    path.write_text("No headings here at all.\n", encoding="utf-8")
    report = path.parent / f"{BASE}{config.SUFFIX_HEADER_VAL_REPORT}"
    report.write_text("old report: PASS 54", encoding="utf-8")
    v = tvh.HeaderValidator.__new__(tvh.HeaderValidator)
    v.logger = MagicMock()
    v.problematic_terms = []
    assert v.run(path, model="m") is False
    text = report.read_text(encoding="utf-8")
    assert "old report" not in text and "No sections found" in text


def test_hv3_batches_use_strict_temperature():
    v = tvh.HeaderValidator.__new__(tvh.HeaderValidator)
    v.logger = MagicMock()
    v.client = object()
    v.cached_system_message = [{"type": "text", "text": "cached"}]
    captured = {}

    def fake_call(*a, **k):
        captured.update(k)
        from types import SimpleNamespace
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")])
    with patch.object(tvh, "call_claude_with_retry", fake_call):
        v.validate_batch([{"number": 1, "heading": "H", "content": "Body"}], model="claude-sonnet-4-6")
    assert captured["temperature"] == config.TEMP_STRICT


def test_u5_summary_coverage_key_follows_gui_aux_model(monkeypatch):
    """Sweep: the freshness key hashes the model the GUI runs the check with."""
    a = vp._summary_coverage_logic_version()
    monkeypatch.setattr(config.settings, "AUX_MODEL", "claude-sonnet-5-5")
    assert vp._summary_coverage_logic_version() != a


def test_u5_gate_path_runs_coverage_with_gui_aux_model(tmp_path, monkeypatch):
    """Re-check: a caller passing no model (the release gate) uses the GUI model,
    the same one the freshness key hashes."""
    import summary_validation
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config.settings, "AUX_MODEL", "claude-sonnet-5-5")
    proj = tmp_path / BASE
    proj.mkdir()
    (proj / f"{BASE}{config.SUFFIX_SUMMARY_GEN}").write_text("A summary.", encoding="utf-8")
    monkeypatch.setattr(vp, "load_project_transcript", lambda *a, **k: "transcript")
    monkeypatch.setattr(vp.summary_pipeline, "prepare_summary_input", lambda **k: object())
    monkeypatch.setattr(vp, "get_anthropic_client_or_none", lambda *a, **k: None)
    seen = {}

    def fake(summary, summary_input, api_client=None, model=None, logger=None):
        seen["model"] = model
        return "PASS", True, "PASS: ok"
    monkeypatch.setattr(summary_validation, "validate_and_report_status", fake)
    vp.validate_summary_coverage(BASE, logger=MagicMock())
    assert seen["model"] == "claude-sonnet-5-5"
