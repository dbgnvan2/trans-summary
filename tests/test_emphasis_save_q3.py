"""Q3 — when the model's emphasis items all fail item validation, nothing is saved
and the step fails (it used to save the raw response, rejected items included).

Spec: docs/plan_todo_triage_2026-10-11.md#Q3
"""
from unittest.mock import MagicMock

import config
import extraction_pipeline as ep

SOURCE = "[00:00:01] Distance helps. Families settle down when anxiety drops, over time.\n"


def _setup(tmp_path, monkeypatch, quotes):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(ep, "_load_summary_prompt", lambda _n: "PROMPT")
    response = "\n\n".join(
        f'[Explicit - Clinical - Rank: 92%] Concept: Item {n}\n"{q}"' for n, q in enumerate(quotes, 1))
    monkeypatch.setattr(ep, "_generate_summary_with_claude", lambda *a, **k: response)


def test_q3_all_items_rejected_saves_nothing(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, ["Distance helps.", "Over time."])  # < 5 words each
    logger = MagicMock()
    assert ep.extract_scored_emphasis("Talk - A Person - 2021-01-01 - yaml.md", logger=logger,
                                      transcript_text=SOURCE) is False
    assert not list(tmp_path.rglob("* - emphasis-scored.md"))
    msg = logger.error.call_args.args[0] % logger.error.call_args.args[1:]
    assert "0 of 2" in msg


def test_q3_one_valid_item_still_saves(tmp_path, monkeypatch):
    good = "Families settle down when anxiety drops, over time."
    _setup(tmp_path, monkeypatch, ["Distance helps.", good])
    assert ep.extract_scored_emphasis("Talk - A Person - 2021-01-01 - yaml.md", logger=MagicMock(),
                                      transcript_text=SOURCE)
    saved = next(tmp_path.rglob("* - emphasis-scored.md")).read_text(encoding="utf-8")
    assert good in saved and "Distance helps." not in saved


def test_q3_failed_run_sets_aside_older_emphasis_file(tmp_path, monkeypatch):
    """Dirty state (P8, sweep finding 3): an emphasis file from an earlier run must
    not be published as this run's result. It is renamed to ".stale", not deleted."""
    _setup(tmp_path, monkeypatch, ["Distance helps.", "Over time."])
    proj = tmp_path / "Talk - A Person - 2021-01-01"
    proj.mkdir()
    old_md = proj / f"Talk - A Person - 2021-01-01{config.SUFFIX_EMPHASIS_SCORED}"
    old_md.write_text("old run", encoding="utf-8")
    old_md.with_suffix(".json").write_text("{}", encoding="utf-8")
    logger = MagicMock()
    assert ep.extract_scored_emphasis("Talk - A Person - 2021-01-01 - yaml.md", logger=logger,
                                      transcript_text=SOURCE) is False
    assert not old_md.exists() and not old_md.with_suffix(".json").exists()
    assert (proj / f"{old_md.name}.stale").read_text(encoding="utf-8") == "old run"
    warned = [c.args[0] % c.args[1:] for c in logger.warning.call_args_list]
    assert any("set aside" in w for w in warned)


def test_q3_api_failure_also_sets_aside_older_file(tmp_path, monkeypatch):
    """Re-check 3: the error path (API timeout, parse error) sets the old file aside too."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(ep, "_load_summary_prompt", lambda _n: "PROMPT")

    def boom(*a, **k):
        raise TimeoutError("API timeout")
    monkeypatch.setattr(ep, "_generate_summary_with_claude", boom)
    proj = tmp_path / "Talk - A Person - 2021-01-01"
    proj.mkdir()
    old_md = proj / f"Talk - A Person - 2021-01-01{config.SUFFIX_EMPHASIS_SCORED}"
    old_md.write_text("old run", encoding="utf-8")
    assert ep.extract_scored_emphasis("Talk - A Person - 2021-01-01 - yaml.md",
                                      logger=MagicMock(), transcript_text=SOURCE) is False
    assert not old_md.exists() and (proj / f"{old_md.name}.stale").exists()


def test_q3_pipeline_warns_when_emphasis_not_produced(monkeypatch):
    """Re-check 3: the main pipeline's emphasis step logs a warning on failure."""
    import inspect
    logger = MagicMock()
    monkeypatch.setattr(ep, "extract_scored_emphasis", lambda *a, **k: False)
    assert ep._run_emphasis_step("x - yaml.md", "m", logger, None) is False
    assert "no emphasis items" in logger.warning.call_args.args[0]
    monkeypatch.setattr(ep, "extract_scored_emphasis", lambda *a, **k: True)
    logger = MagicMock()
    assert ep._run_emphasis_step("x - yaml.md", "m", logger, None) is True
    logger.warning.assert_not_called()
    # summarize_transcript uses this step
    assert "_run_emphasis_step(" in inspect.getsource(ep.summarize_transcript)
