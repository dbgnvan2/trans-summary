"""The end-to-end runner (scripts/e2e_run.py) runs the GUI's own stage runners, does
not stop at the first failure, skips a stage whose inputs are missing, and leaves the
GUI's saved settings alone. Fake stages only; no model calls."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import config
import ts_gui

ROOT = Path(__file__).resolve().parent.parent
BASE = "Talk - A Person - 2021-01-01"


@pytest.fixture
def e2e(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("e2e_run", ROOT / "scripts" / "e2e_run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(config.settings, "LOGS_DIR", tmp_path / "logs")
    (tmp_path / "logs").mkdir()
    settings_file = tmp_path / "logs" / "runtime_settings.json"
    settings_file.write_text('{"keep": "me"}', encoding="utf-8")
    monkeypatch.setattr(mod.transcript_cost_estimator, "CostEstimator",
                        lambda path, logger=None: SimpleNamespace(
                            run_full_estimation=lambda: None, costs=[{"cost": 1.25}]))
    monkeypatch.setattr(mod.analyze_token_usage, "generate_usage_report",
                        lambda since_timestamp=None: "usage")
    # restore paths and model after the run changes them
    for name in ("TRANSCRIPTS_BASE", "SOURCE_DIR", "PROCESSED_DIR", "PROJECTS_DIR",
                 "VALIDATION_APPROVED_TERMS_PATH", "DEFAULT_MODEL"):
        monkeypatch.setattr(config.settings, name, getattr(config.settings, name))
        if hasattr(config, name):
            monkeypatch.setattr(config, name, getattr(config, name))
    return mod, settings_file


def _fake_runners(calls, fail="core"):
    def make(key):
        def run(self=None):
            calls.append(key)
            if key == "format":  # write what later stages need
                proj = config.PROJECTS_DIR / BASE
                proj.mkdir(parents=True, exist_ok=True)
                for sfx in (config.SUFFIX_FORMATTED, config.SUFFIX_YAML, config.SUFFIX_TOPICS):
                    (proj / f"{BASE}{sfx}").write_text("x", encoding="utf-8")
            return key != fail
        return run
    return {k: make(k) for k, _l in ts_gui.STAGE_DEFINITIONS}


def test_e2e_runs_every_stage_and_keeps_going(e2e, monkeypatch, tmp_path):
    mod, settings_file = e2e
    calls = []
    runners = _fake_runners(calls)
    monkeypatch.setattr(ts_gui.TranscriptProcessorGUI, "stage_runners",
                        property(lambda self: runners))
    src = tmp_path / f"{BASE}_validated.txt"  # as Init Val leaves it; Format needs it
    src.write_text("Kerr said things.", encoding="utf-8")
    out = tmp_path / "out"
    assert mod.main(["--out", str(out), str(src)]) == 1  # one stage failed

    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    results = {r["stage"]: r for r in report["talks"][0]["results"]}
    labels = [l for _k, l in ts_gui.STAGE_DEFINITIONS]
    assert list(results) == labels  # every stage is reported, in GUI order
    assert results["4. Core (ST/IT/T/KT/L)"]["status"] == "FAIL"
    # stages after the failure still ran when their inputs exist ...
    assert results["Structured Summary"]["status"] == "PASS"
    assert results["8. Full Web/PDF"]["status"] == "PASS"
    # ... and are skipped, with the reason, when they do not (no themes were written)
    assert results["7. Blog (Lens #1)"]["status"] == "SKIPPED"
    assert "Structural Themes" in results["7. Blog (Lens #1)"]["detail"]
    assert "blog" not in calls
    assert report["talks"][0]["estimate"] == 1.25
    # it worked in its own folder and left the GUI's saved settings alone
    assert (out / "source" / src.name).exists()
    assert settings_file.read_text(encoding="utf-8") == '{"keep": "me"}'


def test_e2e_rejects_unknown_stage(e2e, tmp_path):
    mod, _ = e2e
    with pytest.raises(SystemExit):
        mod.main(["--out", str(tmp_path / "o"), "--stages", "nope", str(tmp_path / "x.txt")])


def test_e2e_records_format_review_instead_of_pausing(e2e, monkeypatch, tmp_path):
    mod, _ = e2e
    monkeypatch.setattr(mod.format_review, "pending_items", lambda base: [1, 2, 3])
    config.set_transcripts_base(tmp_path)
    src = tmp_path / f"{BASE}.txt"
    src.write_text("x", encoding="utf-8")
    run = mod.Run(src, tmp_path / "run.log")
    assert run.gui._open_review_if_needed() is False  # never opens a dialog or pauses
    assert run.review_items == 3
    assert any("3 difference(s) need a person's review" in t for _l, t in run.lines)


def test_e2e_format_needs_a_validated_transcript(e2e, monkeypatch, tmp_path):
    """E2E review (P13): the GUI refuses Format on an unvalidated transcript. When Init
    Val fails, Format and the stages that need its output are skipped, never PASS."""
    mod, _ = e2e
    calls = []
    runners = _fake_runners(calls, fail="init_val")
    monkeypatch.setattr(ts_gui.TranscriptProcessorGUI, "stage_runners",
                        property(lambda self: runners))
    src = tmp_path / f"{BASE}.txt"
    src.write_text("raw", encoding="utf-8")
    out = tmp_path / "out"
    assert mod.main(["--out", str(out), str(src)]) == 1
    results = {r["stage"]: r for r in json.loads(
        (out / "report.json").read_text(encoding="utf-8"))["talks"][0]["results"]}
    assert results["0. Init Val"]["status"] == "FAIL"
    assert results["1. Format"]["status"] == "SKIPPED"
    assert "validated transcript" in results["1. Format"]["detail"]
    assert "format" not in calls
    assert all(r["status"] in ("FAIL", "SKIPPED") for r in results.values())


def test_e2e_refuses_a_used_output_folder(e2e, tmp_path):
    """E2E review (P8): files from an earlier run must not make a stage pass."""
    mod, _ = e2e
    out = tmp_path / "out"
    (out / "projects").mkdir(parents=True)
    src = tmp_path / f"{BASE}.txt"
    src.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        mod.main(["--out", str(out), str(src)])


def test_e2e_removes_its_logging_hooks(e2e, monkeypatch, tmp_path):
    import logging
    mod, _ = e2e
    runners = _fake_runners([], fail=None)
    monkeypatch.setattr(ts_gui.TranscriptProcessorGUI, "stage_runners",
                        property(lambda self: runners))
    before = list(logging.getLogger().handlers)
    src = tmp_path / f"{BASE}_validated.txt"
    src.write_text("x", encoding="utf-8")
    mod.main(["--out", str(tmp_path / "out"), str(src)])
    assert logging.getLogger().handlers == before
    assert logging.getLogger("e2e.estimate").propagate is True
