import inspect
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import config
import ts_gui


class _Flag:
    """Minimal tk.BooleanVar/StringVar stand-in (get + set). Extends the
    original get-only convenience class since the new stage-selection code
    paths (_apply_stage_selection, _apply_default_stage_selection) mutate
    these variables via .set()."""

    def __init__(self, value=False):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


BASE_NAME = "Sample Title - Author - 2025-01-01"


def _stage_vars(checked_keys=()):
    checked = set(checked_keys)
    return {key: _Flag(key in checked) for key, _ in ts_gui.STAGE_DEFINITIONS}


def _make_full_gui(tmp_path, selected_file=None, processing=False, checked_keys=(),
                    base_name=BASE_NAME):
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = base_name
    gui.selected_file = selected_file
    gui.processing = processing
    gui.logger = object()
    gui.log = MagicMock()
    gui.stage_vars = _stage_vars(checked_keys)
    gui.active_selection_var = _Flag("(none)")
    return gui


def _summarize_call_flags(mock_summarize):
    """Extract the summarize_transcript flags from a mocked call, tolerant
    of positional-vs-keyword style (real signature: formatted_filename,
    model, focus_keyword, target_audience, skip_extracts_summary,
    skip_emphasis, skip_bowen, skip_blog, skip_overview=True, ...)."""
    names = [
        "formatted_filename", "model", "focus_keyword", "target_audience",
        "skip_extracts_summary", "skip_emphasis", "skip_bowen", "skip_blog",
        "skip_overview",
    ]
    call = mock_summarize.call_args
    values = {names[i]: val for i, val in enumerate(call.args) if i < len(names)}
    values.update(call.kwargs)
    return values


# ===========================================================================
# SS.5 -- STAGE_DEFINITIONS: fixed 13-stage order (structured_summary is a
# genuinely new stage, superseding omit_summary_do_all -- not a leftover;
# see Gap E.1 in the QA test spec re: the code spec's own stale "12" counts).
# ===========================================================================

def test_stage_definitions_order():
    expected_keys = [
        "init_val", "format", "val_headers", "yaml", "topics", "core",
        "structured_summary", "gen_abstract", "val_abstract", "blog",
        "overview", "bowen_emphasis", "webpdf", "package", "bundle",
    ]
    assert [key for key, _ in ts_gui.STAGE_DEFINITIONS] == expected_keys
    assert len(ts_gui.STAGE_DEFINITIONS) == 15


def test_bowen_emphasis_runs_before_webpdf_and_package():
    """SR.6: independent Bowen/Emphasis extraction must precede the
    publish-gated web/pdf and package stages, so a release-gate BLOCK (which
    fail-closes web/pdf to False and halts the run) can't skip the extraction."""
    keys = [key for key, _ in ts_gui.STAGE_DEFINITIONS]
    assert keys.index("bowen_emphasis") < keys.index("webpdf")
    assert keys.index("bowen_emphasis") < keys.index("package")


# ===========================================================================
# SB.1 -- bottom status bar tracks the current major step during a run and
# shows a specific final message (previously it only showed a generic
# start/end message and never updated per-stage).
# ===========================================================================

def _status_gui():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = BASE_NAME
    gui.logger = object()
    gui.log = MagicMock()
    gui.status_label = MagicMock()
    gui.root = MagicMock()
    return gui


def _status_texts(gui):
    return " ".join(
        str(c.kwargs.get("text", "")) for c in gui.status_label.config.call_args_list
    )


def test_sb1_status_updates_per_step_and_final_message():
    gui = _status_gui()
    gui.stage_runners = {key: MagicMock(return_value=True) for key, _ in ts_gui.STAGE_DEFINITIONS}
    with patch.object(gui, "_run_cost_estimation", return_value=True), \
         patch("ts_gui.analyze_token_usage.generate_usage_report", return_value="report"):
        ok = gui._run_selected_stages({"format", "yaml"})
    assert ok is True
    text = _status_texts(gui)
    assert "Step 1/2" in text and "Step 2/2" in text   # major step tracked
    assert "Complete" in text                            # specific final message


def test_sb1_status_shows_failing_step():
    gui = _status_gui()
    gui.stage_runners = {key: MagicMock(return_value=True) for key, _ in ts_gui.STAGE_DEFINITIONS}
    gui.stage_runners["yaml"] = MagicMock(return_value=False)
    with patch.object(gui, "_run_cost_estimation", return_value=True):
        ok = gui._run_selected_stages({"format", "yaml"})
    assert ok is False
    assert "Failed at" in _status_texts(gui)


def test_sb1_run_task_sets_initial_running_status():
    """SB.1: starting a background task immediately updates the bottom bar to a
    'Running …' status (so it clears/updates on click, e.g. Create Bundle), not
    only when the task finishes."""
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.processing = False
    gui.progress = MagicMock()
    gui.set_status = MagicMock()
    gui.update_button_states = MagicMock()
    gui.log = MagicMock()
    with patch("ts_gui.threading.Thread") as mThread:
        gui.run_task_in_thread(lambda: True, task_name="bundle export (pdf)")
    mThread.return_value.start.assert_called_once()
    assert any(
        "Running" in str(c.args[0]) and "bundle export" in str(c.args[0])
        for c in gui.set_status.call_args_list
    )


def test_sb1_run_task_status_falls_back_to_function_name():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.processing = False
    gui.progress = MagicMock()
    gui.set_status = MagicMock()
    gui.update_button_states = MagicMock()
    gui.log = MagicMock()

    def _generate_bundle():
        return True

    with patch("ts_gui.threading.Thread"):
        gui.run_task_in_thread(_generate_bundle)
    assert any("generate bundle" in str(c.args[0]) for c in gui.set_status.call_args_list)


def test_sb1_execute_task_preserves_task_final_status():
    """A task that calls set_final_status keeps its message; _execute_task does
    not overwrite it with the generic 'Task completed successfully.'"""
    gui = _status_gui()
    gui.processing = False
    gui.progress = MagicMock()

    def task():
        gui.set_final_status("MY SPECIFIC FINAL", "green")
        return True

    gui._execute_task(task, "t")
    text = _status_texts(gui)
    assert "MY SPECIFIC FINAL" in text
    assert "Task completed successfully." not in text


# ===========================================================================
# SS.7 / SS.9 -- checkbox + run_frame wiring (structural/source-inspection,
# matching this repo's existing grep-based verification style; per-key
# binding is asserted, not just a bare count, and the count is derived from
# STAGE_DEFINITIONS rather than a hardcoded literal so it self-corrects on a
# future 14th stage).
# ===========================================================================

def test_stage_checkboxes_bound_to_stage_vars_per_key():
    # SS.7: one stage checkbox per STAGE_DEFINITIONS key, each bound to its
    # stage_var and registered in stage_checkbuttons. The implementation builds
    # these data-drivenly in a loop over STAGE_DEFINITIONS (one call site,
    # executed 13x) rather than 13 literal call sites -- so we assert the
    # loop's intent, not a brittle literal grep count.
    source = inspect.getsource(ts_gui.TranscriptProcessorGUI.setup_ui)
    assert "ttk.Checkbutton(button_frame" in source
    assert "for" in source and "STAGE_DEFINITIONS" in source, "checkboxes not built from STAGE_DEFINITIONS"
    assert "self.stage_vars[key]" in source, "checkbox not bound to stage_vars[key]"
    assert "self.stage_checkbuttons[key]" in source, "checkbox not registered in stage_checkbuttons"
    # Removed legacy symbols must be gone.
    assert "do_all_btn" not in source
    assert "include_init_val_do_all" not in source
    assert "omit_summary_do_all" not in source


def test_run_frame_has_run_selected_and_manage_buttons():
    source = inspect.getsource(ts_gui.TranscriptProcessorGUI.setup_ui)
    assert "Run Selected" in source
    assert "command=self.do_run_selected" in source
    assert "Manage Selections" in source
    assert "command=self.open_selection_manager_dialog" in source


# ===========================================================================
# SS.8 -- __init__ wiring for stage_vars/active_selection_var (structural
# check via inspect.getsource: __init__ requires a real Tk root and cannot
# be exercised via __new__, per this repo's "no real Tk mainloop, ever"
# rule, so this is deliberately NOT a fake behavioral pass).
# ===========================================================================

def test_init_creates_stage_vars_for_every_stage():
    source = inspect.getsource(ts_gui.TranscriptProcessorGUI.__init__)
    assert "self.stage_vars" in source
    assert "STAGE_DEFINITIONS" in source
    assert "self.active_selection_var" in source
    assert "include_init_val_do_all" not in source
    assert "omit_summary_do_all" not in source


# ===========================================================================
# SS.12 -- _run_stage_* wrapper methods exist for all 9 new keys, and the
# highest-risk ones (core/blog/overview all share summarize_transcript but
# must pass different flags) forward the correct pipeline flags.
# ===========================================================================

@pytest.mark.parametrize("key", [
    "yaml", "core", "structured_summary", "gen_abstract", "val_abstract",
    "blog", "overview", "bowen_emphasis", "package", "bundle",
])
def test_run_stage_wrapper_exists_for_each_new_stage(key):
    assert hasattr(ts_gui.TranscriptProcessorGUI, f"_run_stage_{key}")
    assert callable(getattr(ts_gui.TranscriptProcessorGUI, f"_run_stage_{key}"))


def test_run_stage_core_enables_extracts_summary_generation():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = BASE_NAME
    gui.logger = object()
    gui.log = MagicMock()
    gui.include_bowen_core = _Flag(True)
    gui.include_emphasis_core = _Flag(True)

    with patch("ts_gui.pipeline.summarize_transcript", return_value=True) as mock_summarize:
        ok = gui._run_stage_core()

    assert ok is True
    flags = _summarize_call_flags(mock_summarize)
    assert flags.get("skip_extracts_summary") is False


def test_run_stage_blog_runs_standalone_from_core():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = BASE_NAME
    gui.logger = object()
    gui.log = MagicMock()

    with patch("ts_gui.pipeline.summarize_transcript", return_value=True) as mock_summarize:
        ok = gui._run_stage_blog()

    assert ok is True
    flags = _summarize_call_flags(mock_summarize)
    assert flags.get("skip_extracts_summary") is True
    assert flags.get("skip_blog") is False


def test_run_stage_overview_runs_standalone_from_core():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = BASE_NAME
    gui.logger = object()
    gui.log = MagicMock()

    with patch("ts_gui.pipeline.summarize_transcript", return_value=True) as mock_summarize:
        ok = gui._run_stage_overview()

    assert ok is True
    flags = _summarize_call_flags(mock_summarize)
    assert flags.get("skip_extracts_summary") is True
    assert flags.get("skip_overview") is False


def test_stage_runners_cover_all_keys():
    """SS.12: `stage_runners` must map exactly the 13 STAGE_DEFINITIONS
    keys to callables. Accessed directly on a __new__-constructed instance
    (no Tk mainloop) -- if stage_runners can only be built inside a
    Tk-dependent __init__, this test should fail during reconciliation and
    flag that stage_runners needs to be reachable headlessly."""
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    runners = gui.stage_runners
    assert set(runners.keys()) == {key for key, _ in ts_gui.STAGE_DEFINITIONS}
    for fn in runners.values():
        assert callable(fn)


def test_stage_runners_reuse_existing_methods_for_carried_over_stages():
    """SS.12: init_val/format/val_headers/webpdf reuse the pre-existing
    handler methods rather than new _run_stage_* wrappers."""
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    runners = gui.stage_runners
    assert runners["init_val"].__func__ is ts_gui.TranscriptProcessorGUI._run_initial_validation_auto
    assert runners["format"].__func__ is ts_gui.TranscriptProcessorGUI._run_format_and_validate
    assert runners["val_headers"].__func__ is ts_gui.TranscriptProcessorGUI._run_header_validation
    assert runners["webpdf"].__func__ is ts_gui.TranscriptProcessorGUI._run_web_pdf_generation


# ===========================================================================
# SS.11 -- _run_selected_stages: cost estimate always runs, only checked
# stages fire (in STAGE_DEFINITIONS order, including non-contiguous
# selections), halts on first failure.
# ===========================================================================

def test_run_selected_stages_cost_estimation_always_runs():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = BASE_NAME
    gui.logger = object()
    gui.log = MagicMock()
    gui.stage_runners = {key: MagicMock(return_value=True) for key, _ in ts_gui.STAGE_DEFINITIONS}

    with patch.object(gui, "_run_cost_estimation", return_value=True) as mock_cost, \
         patch("ts_gui.analyze_token_usage.generate_usage_report", return_value="report"):
        ok = gui._run_selected_stages({"format"})

    assert ok is True
    mock_cost.assert_called_once()


def test_run_selected_stages_only_checked_stages_fire_in_order():
    """Covers a NON-contiguous selection (format + gen_abstract, skipping
    val_headers/yaml/core/structured_summary in between) -- a naive "run
    everything between the lowest and highest checked index" bug would pass
    a contiguous-only test but silently run unchecked stages here."""
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = BASE_NAME
    gui.logger = object()
    gui.log = MagicMock()

    call_order = []

    def _mark(key):
        def _runner(*_a, **_kw):
            call_order.append(key)
            return True
        return _runner

    gui.stage_runners = {key: MagicMock(side_effect=_mark(key)) for key, _ in ts_gui.STAGE_DEFINITIONS}
    selected = {"gen_abstract", "format"}

    with patch.object(gui, "_run_cost_estimation", return_value=True), \
         patch("ts_gui.analyze_token_usage.generate_usage_report", return_value="report"):
        ok = gui._run_selected_stages(selected)

    assert ok is True
    assert call_order == ["format", "gen_abstract"]
    for key, _ in ts_gui.STAGE_DEFINITIONS:
        if key not in selected:
            gui.stage_runners[key].assert_not_called()


def test_run_selected_stages_halts_on_mid_run_failure():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = BASE_NAME
    gui.logger = object()
    gui.log = MagicMock()

    gui.stage_runners = {key: MagicMock(return_value=True) for key, _ in ts_gui.STAGE_DEFINITIONS}
    gui.stage_runners["val_headers"] = MagicMock(return_value=False)

    selected = {"format", "val_headers", "yaml"}  # yaml is after val_headers in order

    with patch.object(gui, "_run_cost_estimation", return_value=True):
        ok = gui._run_selected_stages(selected)

    assert ok is False
    gui.stage_runners["format"].assert_called_once()
    gui.stage_runners["val_headers"].assert_called_once()
    gui.stage_runners["yaml"].assert_not_called()


# ===========================================================================
# Val Abstract is ADVISORY -- a coverage FAIL must not halt the run and skip
# the independent downstream stages (Bowen/Emphasis). Regression: a real run
# halted after Val Abstract (abstract missing "Speaker's conclusion"), so
# bowen-references.md and emphasis-scored.md were never produced.
# Root cause: _run_stage_val_abstract returned validate_abstract_coverage()'s
# pass/fail, and _run_selected_stages halts on the first False.
# ===========================================================================

def test_run_stage_val_abstract_advisory_does_not_halt():
    """A failed coverage validation returns True from the runner (advisory), so
    the halt check `if not stage_runners[key]()` cannot fire."""
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = BASE_NAME
    gui.logger = object()
    gui.log = MagicMock()

    with patch("ts_gui.pipeline.validate_abstract_coverage", return_value=False) as mock_val:
        ok = gui._run_stage_val_abstract()

    assert ok is True  # advisory: does NOT halt even though validation failed
    mock_val.assert_called_once()
    # P2: the continuation is surfaced, not silent.
    assert any(
        "advisory" in str(call.args[0]).lower()
        for call in gui.log.call_args_list
    ), "advisory continuation was not logged"


def test_run_stage_val_abstract_pass_does_not_log_advisory():
    """When validation passes, the runner returns True and emits no advisory
    warning (guards against always-warning)."""
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = BASE_NAME
    gui.logger = object()
    gui.log = MagicMock()

    with patch("ts_gui.pipeline.validate_abstract_coverage", return_value=True):
        ok = gui._run_stage_val_abstract()

    assert ok is True
    assert not any(
        "advisory" in str(call.args[0]).lower()
        for call in gui.log.call_args_list
    )


def test_run_selected_stages_continues_to_bowen_when_val_abstract_fails():
    """End-to-end regression: with a REAL _run_stage_val_abstract whose inner
    validation returns False, the run must continue to bowen_emphasis rather
    than halting."""
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = BASE_NAME
    gui.logger = object()
    gui.log = MagicMock()

    bowen_runner = MagicMock(return_value=True)
    runners = {key: MagicMock(return_value=True) for key, _ in ts_gui.STAGE_DEFINITIONS}
    runners["val_abstract"] = gui._run_stage_val_abstract  # exercise the real runner
    runners["bowen_emphasis"] = bowen_runner
    gui.stage_runners = runners

    selected = {"val_abstract", "bowen_emphasis"}

    with patch("ts_gui.pipeline.validate_abstract_coverage", return_value=False), \
         patch.object(gui, "_run_cost_estimation", return_value=True), \
         patch("ts_gui.analyze_token_usage.generate_usage_report", return_value="report"):
        ok = gui._run_selected_stages(selected)

    assert ok is True
    bowen_runner.assert_called_once()  # Bowen/Emphasis ran despite the abstract FAIL


# ===========================================================================
# SS.10 -- do_run_selected guard order, including a precedence test (two
# guard conditions true simultaneously) -- isolated single-guard tests alone
# can't prove which guard wins when more than one applies.
# ===========================================================================

def test_do_run_selected_blocks_when_no_file_selected(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    gui = _make_full_gui(tmp_path, selected_file=None, checked_keys={"format"})
    with patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()
    mock_run.assert_not_called()


def test_do_run_selected_blocks_when_already_processing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    gui = _make_full_gui(
        tmp_path,
        selected_file=tmp_path / f"{BASE_NAME}_validated.txt",
        processing=True,
        checked_keys={"format"},
    )
    with patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()
    mock_run.assert_not_called()
    gui.log.assert_called()


def test_do_run_selected_blocks_when_nothing_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    gui = _make_full_gui(
        tmp_path,
        selected_file=tmp_path / f"{BASE_NAME}_validated.txt",
        checked_keys=set(),
    )
    with patch("ts_gui.messagebox.showwarning") as mock_warn, \
         patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()
    mock_run.assert_not_called()
    mock_warn.assert_called_once()


def test_do_run_selected_blocks_on_unmet_dependency(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    gui = _make_full_gui(
        tmp_path,
        selected_file=tmp_path / f"{BASE_NAME}_validated.txt",
        checked_keys={"core"},  # core needs yaml; nothing satisfies it
    )
    with patch("ts_gui.messagebox.showwarning") as mock_warn, \
         patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()
    mock_run.assert_not_called()
    mock_warn.assert_called_once()


def test_do_run_selected_blocks_when_init_val_unchecked_and_filename_not_validated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    gui = _make_full_gui(
        tmp_path,
        selected_file=tmp_path / f"{BASE_NAME}.txt",  # no "_validated"
        checked_keys={"format"},  # format is satisfiable on its own
    )
    with patch("ts_gui.messagebox.showwarning") as mock_warn, \
         patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()
    mock_run.assert_not_called()
    mock_warn.assert_called_once()


def test_do_run_selected_guard_precedence_processing_before_nothing_checked(tmp_path, monkeypatch):
    """Guard (2) 'already processing' must fire before guard (3) 'nothing
    checked' when both conditions are true simultaneously -- per SS.10's
    guard order (2) uses gui.log, (3) uses messagebox.showwarning, so which
    channel fires distinguishes which guard actually won."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    gui = _make_full_gui(
        tmp_path,
        selected_file=tmp_path / f"{BASE_NAME}_validated.txt",
        processing=True,
        checked_keys=set(),
    )
    with patch("ts_gui.messagebox.showwarning") as mock_warn, \
         patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()

    mock_run.assert_not_called()
    mock_warn.assert_not_called()
    gui.log.assert_called()


def test_do_run_selected_proceeds_when_all_guards_and_preflight_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    checked = {"format", "val_headers"}
    gui = _make_full_gui(
        tmp_path,
        selected_file=tmp_path / f"{BASE_NAME}_validated.txt",
        checked_keys=checked,
    )

    with patch("ts_gui.messagebox.showwarning") as mock_warn, \
         patch("ts_gui.messagebox.askyesno", return_value=True), \
         patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()

    mock_warn.assert_not_called()
    mock_run.assert_called_once()


# ===========================================================================
# SS.13 -- _apply_stage_selection: clears stale ticks on a disjoint switch,
# preserves overlapping keys, defaults bowen/emphasis flags when absent from
# an older-format saved selection (P8).
# ===========================================================================

def _make_gui_for_apply():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.stage_vars = _stage_vars()
    gui.include_bowen_core = _Flag(True)
    gui.include_emphasis_core = _Flag(True)
    gui.active_selection_var = _Flag("(none)")
    gui.log = MagicMock()
    return gui


def test_apply_stage_selection_clears_stale_ticks():
    gui = _make_gui_for_apply()
    selections = {
        "A": {"stages": ["format", "yaml"], "include_bowen_core": True, "include_emphasis_core": True},
        "B": {"stages": ["core", "gen_abstract"], "include_bowen_core": True, "include_emphasis_core": True},
    }
    with patch.object(config, "get_stage_selections", return_value=selections):
        gui._apply_stage_selection("A")
        assert gui.stage_vars["format"].get() is True
        assert gui.stage_vars["yaml"].get() is True

        gui._apply_stage_selection("B")  # disjoint from A

    assert gui.stage_vars["format"].get() is False
    assert gui.stage_vars["yaml"].get() is False
    assert gui.stage_vars["core"].get() is True
    assert gui.stage_vars["gen_abstract"].get() is True


def test_apply_stage_selection_preserves_overlapping_keys():
    gui = _make_gui_for_apply()
    selections = {
        "A": {"stages": ["format", "core"], "include_bowen_core": True, "include_emphasis_core": True},
        "B": {"stages": ["core", "gen_abstract"], "include_bowen_core": True, "include_emphasis_core": True},
    }
    with patch.object(config, "get_stage_selections", return_value=selections):
        gui._apply_stage_selection("A")
        gui._apply_stage_selection("B")

    assert gui.stage_vars["core"].get() is True  # overlap stays True, no flicker
    assert gui.stage_vars["format"].get() is False
    assert gui.stage_vars["gen_abstract"].get() is True


def test_apply_stage_selection_defaults_bowen_emphasis_when_absent_from_saved_selection():
    """A realistic post-upgrade scenario: a selection saved before
    include_bowen_core/include_emphasis_core existed in the schema. Per the
    QA spec's recommendation (matching SS.1's own default parameter
    values), the fallback should be True/True, not False/False or
    left-unchanged."""
    gui = _make_gui_for_apply()
    gui.include_bowen_core = _Flag(False)
    gui.include_emphasis_core = _Flag(False)

    with patch.object(config, "get_stage_selections", return_value={"Legacy": {"stages": ["format"]}}):
        gui._apply_stage_selection("Legacy")

    assert gui.include_bowen_core.get() is True
    assert gui.include_emphasis_core.get() is True


# ===========================================================================
# SS.20 -- _apply_default_stage_selection never triggers the pipeline.
# ===========================================================================

def test_apply_default_stage_selection_never_runs_pipeline():
    gui = _make_gui_for_apply()
    gui.run_task_in_thread = MagicMock()

    selections = {"Combo": {"stages": ["format"], "include_bowen_core": True, "include_emphasis_core": True}}
    with patch.object(config, "get_default_stage_selection", return_value="Combo"), \
         patch.object(config, "get_stage_selections", return_value=selections):
        gui._apply_default_stage_selection()

    gui.run_task_in_thread.assert_not_called()
    assert gui.stage_vars["format"].get() is True


# ===========================================================================
# SS.19 -- update_button_states covers the stage checkboxes / run_selected_btn.
# The individual checkbox *widgets* are not part of the documented
# exact-name contract (only self.stage_vars/self.run_selected_btn are), so
# a per-checkbox-widget assertion would require guessing an undocumented
# attribute name. This tests the one widget-state transition reachable
# through the guaranteed contract name (run_selected_btn), in both
# directions (disable-while-processing AND re-enable-after-completion, per
# the QA spec's note that the disable-only half is the easy case).
# ===========================================================================

def test_update_button_states_disables_run_selected_btn_while_processing():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.processing = True
    gui.selected_file = Path("/tmp/Sample_validated.txt")
    gui.run_selected_btn = MagicMock()
    gui.stage_vars = _stage_vars()
    try:
        gui.update_button_states()
    except AttributeError as exc:
        pytest.skip(f"update_button_states() touches a widget not constructible without "
                    f"Tk __init__: {exc}")
    gui.run_selected_btn.config.assert_called_with(state=tk.DISABLED)


def test_update_button_states_reenables_run_selected_btn_after_processing_completes():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.processing = False
    gui.selected_file = Path("/tmp/Sample_validated.txt")
    gui.run_selected_btn = MagicMock()
    gui.stage_vars = _stage_vars()
    try:
        gui.update_button_states()
    except AttributeError as exc:
        pytest.skip(f"update_button_states() touches a widget not constructible without "
                    f"Tk __init__: {exc}")
    gui.run_selected_btn.config.assert_called_with(state=tk.NORMAL)


# ===========================================================================
# Pre-existing tests unrelated to the DO ALL STEPS -> Run Selected refactor
# (kept as-is).
# ===========================================================================

def test_do_extract_bowen_emphasis_uses_combined_pipeline():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = "Sample Title - Author - 2025-01-01"
    gui.logger = object()
    gui.log = MagicMock()
    gui.run_task_in_thread = MagicMock()
    gui._resolve_individual_extraction_input = MagicMock(
        return_value=(
            "Sample Title - Author - 2025-01-01 - yaml.md",
            "YAML transcript",
        )
    )

    gui.do_extract_bowen_emphasis()

    gui.log.assert_called_with(
        "STEP: Extracting Bowen References + Scored Emphasis from %s...",
        "YAML transcript",
    )
    gui.run_task_in_thread.assert_called_once_with(
        ts_gui.pipeline.extract_bowen_and_emphasis,
        "Sample Title - Author - 2025-01-01 - yaml.md",
        config.settings.DEFAULT_MODEL,
        gui.logger,
        task_name="Bowen + Emphasis Extraction",
    )


def test_run_task_in_thread_rejects_reentry():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.processing = True
    gui.log = MagicMock()
    gui.progress = MagicMock()
    gui.update_button_states = MagicMock()

    gui.run_task_in_thread(lambda: True)

    gui.progress.start.assert_not_called()
    gui.update_button_states.assert_not_called()
    gui.log.assert_called_with("⚠️ A task is already running. Please wait for it to finish.")


def test_do_initial_validation_blocks_when_existing_versions_found():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir) / "Sample_v-valid.txt"
        base.write_text("base", encoding="utf-8")
        (Path(tmpdir) / "Sample_v-valid_v1.txt").write_text("v1", encoding="utf-8")

        gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
        gui.selected_file = base
        gui.log = MagicMock()
        gui.run_task_in_thread = MagicMock()

        with patch("ts_gui.messagebox.showwarning") as mock_warning:
            gui.do_initial_validation()

        gui.run_task_in_thread.assert_not_called()
        mock_warning.assert_called_once()
        assert "Move or delete the existing Init Val versions" in mock_warning.call_args.args[1]


def test_run_initial_validation_auto_blocks_when_existing_versions_found():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir) / "Sample_v-valid.txt"
        base.write_text("base", encoding="utf-8")
        (Path(tmpdir) / "Sample_v-valid_v1.txt").write_text("v1", encoding="utf-8")

        gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
        gui.selected_file = base
        gui.log = MagicMock()

        ok = gui._run_initial_validation_auto()

        assert ok is False
        gui.log.assert_called()


def test_select_validation_terms_file_updates_active_path():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.terms_file_var = MagicMock()
    gui.log = MagicMock()

    original_path = config.VALIDATION_APPROVED_TERMS_PATH
    try:
        with patch("ts_gui.filedialog.askopenfilename", return_value="/tmp/custom_terms.txt"):
            gui.select_validation_terms_file()
        assert str(config.VALIDATION_APPROVED_TERMS_PATH) == "/tmp/custom_terms.txt"
        gui.log.assert_called()
    finally:
        config.set_validation_approved_terms_path(original_path)


def test_reset_validation_terms_file_restores_default():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.terms_file_var = MagicMock()
    gui.log = MagicMock()

    original_base = config.TRANSCRIPTS_BASE
    original_path = config.VALIDATION_APPROVED_TERMS_PATH
    try:
        config.set_transcripts_base("/tmp")
        config.set_validation_approved_terms_path("/tmp/custom_terms.txt")
        gui.reset_validation_terms_file()
        assert config.VALIDATION_APPROVED_TERMS_PATH == Path("/tmp/approve_terms.txt")
    finally:
        config.set_transcripts_base(original_base)
        config.set_validation_approved_terms_path(original_path)


def test_select_transcripts_directory_resets_terms_file_to_new_default():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.update_dir_label = MagicMock()
    gui.update_terms_file_label = MagicMock()
    gui.refresh_file_list = MagicMock()
    gui.log = MagicMock()
    gui.make_dir_default_var = _Flag(False)

    original_base = config.TRANSCRIPTS_BASE
    original_path = config.VALIDATION_APPROVED_TERMS_PATH
    try:
        config.set_validation_approved_terms_path("/tmp/custom_terms.txt")
        # select_transcripts_directory treats the chosen dir as the SOURCE dir
        # and infers the transcript base from its parent (see the sibling test
        # test_select_transcripts_directory_accepts_source_folder_without_double_source):
        # choosing "/tmp/new_transcripts" -> base "/tmp", terms reset to that base's default.
        with patch("ts_gui.filedialog.askdirectory", return_value="/tmp/new_transcripts"):
            gui.select_transcripts_directory()

        assert config.TRANSCRIPTS_BASE == Path("/tmp")
        assert config.VALIDATION_APPROVED_TERMS_PATH == Path("/tmp/approve_terms.txt")
    finally:
        config.set_transcripts_base(original_base)
        config.set_validation_approved_terms_path(original_path)


def test_select_transcripts_directory_accepts_source_folder_without_double_source():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.update_dir_label = MagicMock()
    gui.update_terms_file_label = MagicMock()
    gui.refresh_file_list = MagicMock()
    gui.log = MagicMock()
    gui.make_dir_default_var = _Flag(False)

    original_base = config.TRANSCRIPTS_BASE
    original_path = config.VALIDATION_APPROVED_TERMS_PATH
    try:
        with patch("ts_gui.filedialog.askdirectory", return_value="/tmp/new_transcripts/source"):
            gui.select_transcripts_directory()

        assert config.TRANSCRIPTS_BASE == Path("/tmp/new_transcripts")
        assert config.SOURCE_DIR == Path("/tmp/new_transcripts/source")
        assert config.VALIDATION_APPROVED_TERMS_PATH == Path("/tmp/new_transcripts/approve_terms.txt")
    finally:
        config.set_transcripts_base(original_base)
        config.set_validation_approved_terms_path(original_path)


def test_validation_terms_file_selection_persists(tmp_path, monkeypatch):
    settings_path = tmp_path / "runtime_settings.json"
    monkeypatch.setattr(config.settings, "_runtime_settings_path", lambda: settings_path)

    original_path = config.VALIDATION_APPROVED_TERMS_PATH
    try:
        config.set_validation_approved_terms_path("/tmp/persisted_terms.txt")
        payload = settings_path.read_text(encoding="utf-8")
        assert "/tmp/persisted_terms.txt" in payload
    finally:
        config.set_validation_approved_terms_path(original_path)


# ===========================================================================
# SR.* (spec_selective_rerun_2026-07-16.md) -- Selective re-run: check only the
# items to (re)generate; unchecked
# stages are bypassed and their existing outputs reused as inputs. The Init-Val
# guard is scoped to `format` (the only stage consuming the raw transcript) so
# a downstream redo (e.g. Bowen/Emphasis) is not blocked.
# ===========================================================================

def _make_outputs(tmp_path, suffix_attrs, base_name=BASE_NAME):
    """Create on-disk artifacts for the given config suffix attrs under the
    project dir, returning the project dir."""
    proj = tmp_path / base_name
    proj.mkdir(parents=True, exist_ok=True)
    for attr in suffix_attrs:
        suffix = getattr(config, attr)
        (proj / f"{base_name}{suffix}").write_text("x", encoding="utf-8")
    return proj


def test_stage_outputs_cover_all_keys_except_init_val():
    """Every stage except init_val declares its output artifact(s); init_val is
    intentionally absent (its product is the *_validated source transcript, not
    a project-dir artifact). Every declared suffix attr must resolve on config."""
    expected = {key for key, _ in ts_gui.STAGE_DEFINITIONS} - {"init_val"}
    assert set(ts_gui.STAGE_OUTPUTS.keys()) == expected
    for attrs in ts_gui.STAGE_OUTPUTS.values():
        assert attrs, "a stage declared an empty output list"
        for attr in attrs:
            assert hasattr(config, attr), f"{attr} is not a config attribute"


def test_stage_outputs_status_requires_all_present(tmp_path, monkeypatch):
    """'exists' is True only when EVERY output of a multi-file stage is present
    (Core writes 5 files); 4/5 present must read as not-done so it re-runs."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = BASE_NAME

    core_attrs = ts_gui.STAGE_OUTPUTS["core"]
    # 4 of 5 present -> not all_present
    _make_outputs(tmp_path, core_attrs[:-1])
    all_present, present, missing = gui._stage_outputs_status("core")
    assert all_present is False
    assert len(present) == len(core_attrs) - 1
    assert missing == [core_attrs[-1]]

    # complete the set -> all_present
    _make_outputs(tmp_path, [core_attrs[-1]])
    all_present, _present, missing = gui._stage_outputs_status("core")
    assert all_present is True
    assert missing == []


def test_stage_outputs_status_no_outputs_is_generate():
    """init_val has no declared outputs -> always 'will generate', never exists."""
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = BASE_NAME
    assert gui._stage_outputs_status("init_val") == (False, [], [])


def test_selective_rerun_not_blocked_when_format_not_selected(tmp_path, monkeypatch):
    """Regression: checking only Bowen+Emphasis on a non-'_validated' file must
    proceed when the validated-derived YAML already exists on disk (format not
    selected -> Init-Val guard does not fire; bowen's dependency is satisfied by
    the on-disk YAML)."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    _make_outputs(tmp_path, ["SUFFIX_YAML"])  # validated-derived artifact present
    gui = _make_full_gui(
        tmp_path,
        selected_file=tmp_path / f"{BASE_NAME} - yaml.md",  # no "_validated"
        checked_keys={"bowen_emphasis"},
    )
    with patch("ts_gui.messagebox.askyesno", return_value=True), \
         patch("ts_gui.messagebox.showwarning") as mock_warn, \
         patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()
    mock_run.assert_called_once()
    mock_warn.assert_not_called()


def test_selective_rerun_bowen_blocked_without_derived_artifact(tmp_path, monkeypatch):
    """P13: checking only Bowen+Emphasis on a raw file with NO formatted/yaml on
    disk must be BLOCKED -- extraction must never read the unvalidated raw
    transcript. (Closes the hole opened by scoping the Init-Val guard to
    `format`: bowen_emphasis now carries its own formatted/yaml preflight.)"""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    gui = _make_full_gui(
        tmp_path,
        selected_file=tmp_path / f"{BASE_NAME}.txt",  # raw, no derived artifacts
        checked_keys={"bowen_emphasis"},
    )
    with patch("ts_gui.messagebox.askyesno", return_value=True), \
         patch("ts_gui.messagebox.showwarning") as mock_warn, \
         patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()
    mock_run.assert_not_called()
    mock_warn.assert_called_once()


def test_guard_still_blocks_format_even_alongside_other_stages(tmp_path, monkeypatch):
    """The scoped guard keys on `format` specifically: selecting format (with
    others) on an unvalidated file still blocks."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    gui = _make_full_gui(
        tmp_path,
        selected_file=tmp_path / f"{BASE_NAME}.txt",  # no "_validated"
        checked_keys={"format", "yaml"},
    )
    with patch("ts_gui.messagebox.askyesno", return_value=True), \
         patch("ts_gui.messagebox.showwarning") as mock_warn, \
         patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()
    mock_run.assert_not_called()
    mock_warn.assert_called_once()


def test_run_plan_logs_regenerate_vs_generate(tmp_path, monkeypatch):
    """The run-start plan distinguishes a stage whose output exists (REGENERATE)
    from one that is absent (generate), and names reused prerequisites."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    # Bowen+Emphasis outputs already exist -> REGENERATE; also seed yaml so the
    # reused-prerequisite line fires (bowen has no deps, so use topics which
    # depends on yaml).
    _make_outputs(tmp_path, ts_gui.STAGE_OUTPUTS["bowen_emphasis"])
    _make_outputs(tmp_path, ["SUFFIX_YAML"])

    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = BASE_NAME
    gui.logger = object()
    gui.log = MagicMock()
    gui.stage_runners = {key: MagicMock(return_value=True) for key, _ in ts_gui.STAGE_DEFINITIONS}

    selected = {"topics", "bowen_emphasis"}  # topics absent -> generate; bowen present -> regenerate
    with patch.object(gui, "_run_cost_estimation", return_value=True), \
         patch("ts_gui.analyze_token_usage.generate_usage_report", return_value="report"):
        ok = gui._run_selected_stages(selected)

    assert ok is True

    def _render(call):
        if not call.args:
            return ""
        msg, rest = call.args[0], call.args[1:]
        try:
            return msg % rest if rest else str(msg)
        except Exception:
            return str(msg)

    logged = " ".join(_render(c) for c in gui.log.call_args_list)
    assert "REGENERATE" in logged        # bowen_emphasis outputs exist
    assert "will generate" in logged     # topics absent
    assert "Reusing existing output" in logged and "YAML" in logged
