"""
Tests for pattern sets and the review of formatting differences
(accept / reject / edit / save as pattern).
"""
import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import config
import format_review as fr
import formatting_pipeline as fp
import pattern_sets as ps
import transcript_review_format as cli

FX = Path(__file__).parent / "fixtures" / "where_roots"
BASE = "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid"


@pytest.fixture
def patterns(tmp_path, monkeypatch):
    folder = tmp_path / "patterns"
    monkeypatch.setattr(config, "PATTERNS_DIR", folder, raising=False)
    monkeypatch.setattr(config, "VALIDATION_APPROVED_TERMS_PATH", tmp_path / "none.txt", raising=False)
    return folder


@pytest.fixture
def project(tmp_path, monkeypatch, patterns):
    """A project with the fixture's formatted transcript and raw-source copy,
    and no review decisions yet."""
    projects = tmp_path / "projects"
    proj = projects / BASE
    proj.mkdir(parents=True)
    src = FX / BASE
    shutil.copy(src / f"{BASE}{config.SUFFIX_FORMATTED}", proj)
    raw = (src / f"{BASE}.txt").read_text(encoding="utf-8-sig")
    (proj / f"{BASE}{config.SUFFIX_RAW_SOURCE}").write_text(raw, encoding="utf-8")
    monkeypatch.setattr(config, "PROJECTS_DIR", projects)
    return proj


def _item(items, raw_text):
    return next(i for i in items if i["raw_text"] == raw_text)


# ------------------------------------------------------------------ pattern sets


def test_pattern_set_create_add_parse(patterns):
    ps.create_set("kerr lectures")
    assert ps.list_sets() == ["kerr lectures"]
    assert ps.add_fix("kerr lectures", "homostasis", "homeostasis", source="P1") is True
    assert ps.add_fix("kerr lectures", "homostasis", "homeostasis") is False  # duplicate
    text = (patterns / "kerr lectures.txt").read_text()
    assert "# added " in text and "from P1" in text
    loaded = ps.load_set("kerr lectures")
    assert loaded.fixes == [("homostasis", "homeostasis")]
    with pytest.raises(ValueError):
        ps.create_set("../escape")
    with pytest.raises(ValueError):
        ps.add_fix("kerr lectures", "a", "a")


def test_apply_fixes_whole_word_longest_first():
    text, applied = ps.apply_fixes(
        "The moon faces and faces. Homostasis!",
        [("faces", "FACES"), ("moon faces", "moon phases"), ("homostasis", "homeostasis")])
    assert text == "The moon phases and FACES. homeostasis!"
    assert {a["wrong"]: a["count"] for a in applied} == {
        "moon faces": 1, "faces": 1, "homostasis": 1}


def test_migrates_existing_approved_terms_file(tmp_path, monkeypatch):
    old = tmp_path / "approved_terms.txt"
    old.write_text("Bowen\nhomostasis = homeostasis\n")
    monkeypatch.setattr(config, "PATTERNS_DIR", tmp_path / "patterns", raising=False)
    monkeypatch.setattr(config, "VALIDATION_APPROVED_TERMS_PATH", old, raising=False)
    assert ps.list_sets() == ["approved_terms"]
    assert ps.load_set("approved_terms").terms == ["Bowen"]


def test_project_assignment_and_effective_raw(project):
    ps.create_set("grp")
    ps.add_fix("grp", "homostasis", "homeostasis")
    ps.assign_to_project(BASE, "grp")
    raw = "Speaker 1  0:01\nThe homostasis of cells.\n"
    fixed, record = ps.apply_to_raw_for_project(BASE, raw)
    assert "homeostasis" in fixed and record["applied"][0]["count"] == 1
    # re-applying the recorded fixes to the same raw reproduces the formatter input
    assert ps.effective_raw(BASE, raw) == fixed
    # a later edit to the set does not change what this project recorded
    ps.add_fix("grp", "cells", "CELLS")
    assert ps.effective_raw(BASE, raw) == fixed
    # different raw text -> unchanged (differences then surface for review)
    assert ps.effective_raw(BASE, "other text") == "other text"


def test_presenter_default(patterns):
    ps.create_set("grp")
    ps.remember_for_presenter("Michael Kerr", "grp")
    assert ps.default_for_presenter("Michael Kerr") == "grp"
    assert ps.default_for_presenter("Someone Else") is None


def test_format_transcript_applies_pattern_set_before_llm(tmp_path, monkeypatch, patterns):
    src = tmp_path / "source"
    src.mkdir()
    name = "Talk - A Person - 2021-01-01.txt"
    (src / name).write_text("Speaker 1  0:01\nThe homostasis of cells.\n", encoding="utf-8")
    monkeypatch.setattr(config, "SOURCE_DIR", src)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    ps.create_set("grp")
    ps.add_fix("grp", "homostasis", "homeostasis")
    sent = {}

    def _fake_llm(raw, prompt, model=None, logger=None):
        sent["raw"] = raw
        return "## Section 1 – The Homeostasis of Cells ([00:00:01]).\n\nThe homeostasis of cells."

    monkeypatch.setattr(fp, "format_transcript_with_claude", _fake_llm)
    monkeypatch.setattr(fp, "load_prompt", lambda: "PROMPT")
    assert fp.format_transcript(name, model="claude-haiku-4-5-20251001", pattern_set="grp")
    assert "homeostasis" in sent["raw"] and "homostasis" not in sent["raw"]
    assert fp.validate_format(name) is True  # compared against the fixed raw


# ------------------------------------------------------------------ review


def test_unreviewed_differences_block_and_list(project):
    items = fr.pending_items(BASE)
    assert len(items) == 6
    assert {i["kind"] for i in items} == {"changed", "correction", "deleted"}
    item = _item(items, "was")
    assert item["formatted_text"] == "were" and item["section"] == 70


def test_accept_approves_without_changing_text(project):
    before = fr.formatted_path(BASE).read_text()
    key = _item(fr.pending_items(BASE), "was")["key"]
    result = fr.apply_decisions(BASE, [{"key": key, "action": "accept"}])
    assert result == {"changed_text": False, "errors": [], "patterns_saved": []}
    assert fr.formatted_path(BASE).read_text() == before
    assert len(fr.pending_items(BASE)) == 5


def test_reject_restores_raw_wording(project):
    items = fr.pending_items(BASE)
    result = fr.apply_decisions(BASE, [{"key": _item(items, "was")["key"], "action": "reject"}])
    assert result["changed_text"] and not result["errors"]
    remaining = {i["raw_text"] for i in fr.pending_items(BASE)}
    assert "was" not in remaining and len(remaining) == 5


def test_reject_of_deletion_at_section_boundary_is_refused_on_real_fixture(project):
    # In the fixture the formatter dropped "Amy Post." where it starts a new
    # section ("## Section 45 – Q&A: Amy Post on ..."); restoring it
    # automatically could put it in the wrong section, so it is refused.
    before = fr.formatted_path(BASE).read_text()
    key = _item(fr.pending_items(BASE), "Amy Post.")["key"]
    result = fr.apply_decisions(BASE, [{"key": key, "action": "reject"}])
    assert result["changed_text"] is False and result["errors"]
    assert fr.formatted_path(BASE).read_text() == before


def test_reject_restores_deleted_words_mid_paragraph(tmp_path, monkeypatch, patterns):
    projects = tmp_path / "projects"
    stem = "Talk - A Person - 2021-01-01"
    (projects / stem).mkdir(parents=True)
    monkeypatch.setattr(config, "PROJECTS_DIR", projects)
    raw = "Speaker 1  0:01\nWe do not accept that idea here.\n"
    fmt = "## Section 1 – Accepting That Idea Here ([00:00:01]).\n\nWe do accept that idea here.\n"
    (projects / stem / f"{stem}{config.SUFFIX_FORMATTED}").write_text(fmt)
    (projects / stem / f"{stem}{config.SUFFIX_RAW_SOURCE}").write_text(raw)
    item = fr.pending_items(stem)[0]
    assert item["raw_text"] == "not" and item["kind"] == "deleted"
    result = fr.apply_decisions(stem, [{"key": item["key"], "action": "reject"}])
    assert result["changed_text"] and not result["errors"]
    assert "We do not accept that idea here." in fr.formatted_path(stem).read_text()
    assert fr.pending_items(stem) == []


def test_edit_is_applied_and_approved(project):
    key = _item(fr.pending_items(BASE), "faces")["key"]
    result = fr.apply_decisions(BASE, [{"key": key, "action": "edit",
                                        "edit_text": "phases [sic: faces]"}])
    assert result["changed_text"]
    assert "phases [sic: faces]" in fr.formatted_path(BASE).read_text()
    assert not any("faces" in i["raw_text"] for i in fr.pending_items(BASE))
    assert fr.review_counts(BASE)["edit"] == 1


def test_all_resolved_passes_validation(project):
    items = fr.pending_items(BASE)
    fr.apply_decisions(BASE, [{"key": i["key"], "action": "accept"} for i in items])
    assert fr.pending_items(BASE) == []
    raw = fr.project_raw(BASE)
    outcome = fp.verify_source_fidelity(raw, fr.formatted_path(BASE).read_text(),
                                        approvals=fr.load_approvals(BASE, raw))
    assert outcome["passed"], outcome["errors"]


def test_approvals_ignored_for_different_raw(project):
    items = fr.pending_items(BASE)
    fr.apply_decisions(BASE, [{"key": i["key"], "action": "accept"} for i in items])
    assert fr.load_approvals(BASE, fr.project_raw(BASE))
    assert fr.load_approvals(BASE, "a different raw text") == set()


def test_save_as_pattern(project):
    ps.create_set("grp")
    ps.assign_to_project(BASE, "grp")
    items = fr.pending_items(BASE)
    result = fr.apply_decisions(BASE, [
        {"key": _item(items, "homostasis")["key"], "action": "accept", "save_pattern": True},
        {"key": _item(items, "Amy Post.")["key"], "action": "accept", "save_pattern": True},
    ])
    assert result["patterns_saved"] == ["homostasis = homeostasis"]
    assert any("deletion or insertion" in e for e in result["errors"])
    assert ("homostasis", "homeostasis") in ps.load_set("grp").fixes


def test_save_as_pattern_without_assigned_set_reports(project):
    key = _item(fr.pending_items(BASE), "homostasis")["key"]
    result = fr.apply_decisions(BASE, [{"key": key, "action": "accept", "save_pattern": True}])
    assert any("no pattern set assigned" in e for e in result["errors"])


def test_unknown_key_and_bad_action_reported(project):
    key = fr.pending_items(BASE)[0]["key"]
    result = fr.apply_decisions(BASE, [{"key": "nope", "action": "accept"},
                                       {"key": key, "action": "delete"}])
    assert len(result["errors"]) == 2


def test_stutter_is_auto_allowed():
    raw = "Speaker 1  0:01\nI I went to the the store today.\n"
    fmt = "## Section 1 – Going to the Store Today ([00:00:01]).\n\nI went to the store today.\n"
    outcome = fp.verify_source_fidelity(raw, fmt)
    assert outcome["passed"], outcome["errors"]
    assert outcome["comparison"]["auto_allowed"] == 2


def test_formatted_tokens_skip_headings_and_labels():
    text = "## Section 1 – Title Words Here ([00:00:01]).\n\n**Kerr:** Hello there.\n"
    tokens = fp.formatted_tokens(text)
    assert [t[0] for t in tokens] == ["Hello", "there."]
    assert text[tokens[0][1]:tokens[0][2]] == "Hello"


# ------------------------------------------------------------------ CLI


def test_cli_review_flow(project):
    ps.create_set("grp")
    ps.assign_to_project(BASE, "grp")
    answers = iter(["a", "y", "a", "n", "r", "a", "a", "n", "e", "were [sic]", "n"])
    out = []
    code = cli.review(BASE, input_fn=lambda prompt: next(answers), output=out.append)
    text = "\n".join(out)
    assert "need a decision" in text
    assert fr.pending_items(BASE) == []
    assert code == 0 and "Validation PASSES" in text


def test_cli_assign_and_list(project, capsys):
    ps.create_set("grp")
    assert cli.main(["--list-sets"]) == 0
    assert "grp" in capsys.readouterr().out
    assert cli.main([BASE, "--assign", "grp"]) == 0
    assert ps.load_project_record(BASE)["name"] == "grp"
    assert cli.main([BASE, "--assign", "missing"]) == 1


# ------------------------------------------------------------------ GUI wiring


def _headless_gui():
    import ts_gui
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.logger = MagicMock()
    gui.log = MagicMock()
    gui.root = MagicMock()
    return gui


def test_gui_format_stage_passes_selected_pattern_set(project):
    import ts_gui
    gui = _headless_gui()
    gui.selected_file = Path(f"{BASE}.txt")
    gui.base_name = BASE
    gui.pattern_set_var = MagicMock(get=MagicMock(return_value="grp"))
    with patch.object(ts_gui.pipeline, "format_transcript", return_value=True) as fmt, \
         patch.object(ts_gui.pipeline, "validate_format", return_value=True):
        assert gui._run_format_and_validate() is True
    assert fmt.call_args.kwargs["pattern_set"] == "grp"


def test_gui_format_stage_opens_review_when_needed(project):
    import ts_gui
    gui = _headless_gui()
    gui.selected_file = Path(f"{BASE}.txt")
    gui.base_name = BASE
    gui.pattern_set_var = MagicMock(get=MagicMock(return_value=ts_gui.PATTERN_SET_NONE))
    with patch.object(ts_gui.pipeline, "format_transcript", return_value=True) as fmt, \
         patch.object(ts_gui.pipeline, "validate_format", return_value=False):
        assert gui._run_format_and_validate() is False
    assert fmt.call_args.kwargs["pattern_set"] == ""
    gui.root.after.assert_called_once()


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="needs a display (run under xvfb-run)")
def test_gui_review_dialog_collects_decisions(project):
    import tkinter as tk

    import ts_gui
    root = tk.Tk()
    root.withdraw()
    try:
        items = fr.pending_items(BASE)
        got = []
        dlg = ts_gui.FormatReviewDialog(root, BASE, items, "grp", got.append)
        # 'changed' items have no default; applying now must warn, not apply
        with patch.object(ts_gui.messagebox, "showwarning") as warn:
            dlg.on_apply()
        warn.assert_called_once()
        for item, action, edit_text, save in dlg.rows:
            if not action.get():
                action.set("accept")
        with patch.object(ts_gui.messagebox, "askyesno", return_value=True):
            dlg.on_apply()
        assert len(got) == 1 and len(got[0]) == len(items)
        kinds = {d["key"]: d["action"] for d in got[0]}
        deleted = next(i for i in items if i["kind"] == "deleted")
        assert kinds[deleted["key"]] == "reject"  # suggested default
    finally:
        root.destroy()


# ------------------------------------------------------------------ sweep fixes


def test_corrupt_review_file_is_loud_not_ignored(project):
    fr.review_path(BASE).write_text("{not json")
    with pytest.raises(ps.CorruptRecordError):
        fr.pending_items(BASE)
    with pytest.raises(ps.CorruptRecordError):
        fr.apply_decisions(BASE, [])
    assert fr.review_path(BASE).read_text() == "{not json"  # not overwritten


def test_corrupt_pattern_record_is_loud(project):
    ps.project_record_path(BASE).write_text("[]")
    with pytest.raises(ps.CorruptRecordError):
        ps.load_project_record(BASE)
    with pytest.raises(ps.CorruptRecordError):
        ps.effective_raw(BASE, "text")


def test_grammatical_double_goes_to_review():
    raw = "Speaker 1  0:01\nHe had had enough, and that that was it.\n"
    fmt = "## Section 1 – He Had Had Enough Then ([00:00:01]).\n\nHe had enough, and that was it.\n"
    result, items = fp.difference_items(raw, fmt)
    assert len(items) == 2 and all(i["auto"] is None for i in items)
    ok_raw = "Speaker 1  0:01\nI I went home.\n"
    ok_fmt = "## Section 1 – Going Home Right Now ([00:00:01]).\n\nI went home.\n"
    assert fp.difference_items(ok_raw, ok_fmt)[1][0]["auto"] == "stutter"


def test_restore_across_section_boundary_is_refused(tmp_path, monkeypatch, patterns):
    projects = tmp_path / "projects"
    stem = "Talk - A Person - 2021-01-01"
    (projects / stem).mkdir(parents=True)
    monkeypatch.setattr(config, "PROJECTS_DIR", projects)
    raw = "Speaker 1  0:01\nFirst part ends here. Dropped words. Second part starts.\n"
    fmt = ("## Section 1 – The First Part Ends Here ([00:00:01]).\n\nFirst part ends here.\n\n"
           "## Section 2 – The Second Part Starts Now ([00:00:01]).\n\nSecond part starts.\n")
    (projects / stem / f"{stem}{config.SUFFIX_FORMATTED}").write_text(fmt)
    (projects / stem / f"{stem}{config.SUFFIX_RAW_SOURCE}").write_text(raw)
    item = fr.pending_items(stem)[0]
    assert item["raw_text"] == "Dropped words."
    result = fr.apply_decisions(stem, [{"key": item["key"], "action": "reject"}])
    assert result["changed_text"] is False
    assert any("section heading or speaker-label boundary" in e for e in result["errors"])


def test_gui_apply_while_busy_keeps_decisions(project):
    import ts_gui
    gui = _headless_gui()
    gui.processing = True
    gui.run_task_in_thread = MagicMock()
    with patch.object(ts_gui.messagebox, "showwarning") as warn:
        assert gui._apply_review_decisions([{"key": "k", "action": "accept"}]) is False
    warn.assert_called_once()
    gui.run_task_in_thread.assert_not_called()
    gui.processing = False
    assert gui._apply_review_decisions([{"key": "k", "action": "accept"}]) is True
    gui.run_task_in_thread.assert_called_once()
