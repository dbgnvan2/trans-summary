"""
Pre-flight dependency validator tests (SS.14-SS.17).

Purpose: Adversarial black-box coverage for the pre-flight dependency gate
         that runs synchronously inside `do_run_selected` before any
         background thread starts, per Section B of the QA test spec (the
         highest-risk area of this change: a false negative lets a doomed
         run burn an API call, a false positive blocks a valid run).
Spec:    docs/spec_stage_selection_2026-07-12.md#SS.14-SS.17 (see also
         #SS.5, #SS.6 for STAGE_DEFINITIONS / STAGE_DEPENDENCIES)
Tests:   this file
"""
from unittest.mock import MagicMock, patch

import pytest

import config
import ts_gui


class _Flag:
    """Minimal tk.BooleanVar/StringVar stand-in (get + set), matching the
    pattern in tests/test_ts_gui_run_all.py but extended with set() since
    the pre-flight/apply-selection code paths mutate these variables."""

    def __init__(self, value=False):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


BASE_NAME = "Sample Title - Author - 2025-01-01"


def _stage_vars(checked_keys):
    """Build a full stage_vars dict (one _Flag per STAGE_DEFINITIONS key)."""
    checked = set(checked_keys)
    return {key: _Flag(key in checked) for key, _ in ts_gui.STAGE_DEFINITIONS}


def _make_gui(tmp_path, base_name=BASE_NAME, validated=True, checked_keys=()):
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = base_name
    suffix = "_validated.txt" if validated else ".txt"
    gui.selected_file = tmp_path / f"{base_name}{suffix}"
    gui.logger = object()
    gui.log = MagicMock()
    gui.processing = False
    gui.stage_vars = _stage_vars(checked_keys)
    gui.active_selection_var = _Flag("(none)")
    return gui


def _write_artifact(tmp_path, base_name, suffix_attr):
    """Create a real zero-byte artifact file on disk under
    <tmp_path>/<base_name>/<base_name><suffix> -- the on-disk layout
    `_stage_artifact_path` is specified to resolve
    (config.PROJECTS_DIR / base_name / f"{base_name}{suffix}"). Real files
    are used (not a mocked Path.exists) so the P6 live-disk-state test is
    meaningful."""
    suffix = getattr(config, suffix_attr)
    project_dir = tmp_path / base_name
    project_dir.mkdir(parents=True, exist_ok=True)
    path = project_dir / f"{base_name}{suffix}"
    path.write_text("", encoding="utf-8")
    return path


def _label_for(stage_key):
    return dict(ts_gui.STAGE_DEFINITIONS)[stage_key]


@pytest.fixture(autouse=True)
def _scratch_projects_dir(tmp_path, monkeypatch):
    """Point config.PROJECTS_DIR at a scratch dir for every test in this
    module so artifact-existence checks touch real, disposable files
    instead of the real project tree."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config.settings, "PROJECTS_DIR", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# SS.6 -- literal dependency-graph equality (transcription-independent check;
# paired with the black-box scenarios below per the QA spec's warning that a
# literal-equality test alone can't catch a shared transcription error).
# ---------------------------------------------------------------------------

def test_stage_dependencies_matches_verified_graph():
    expected = {
        "init_val": [],
        "format": [],
        "val_headers": [[("format", "SUFFIX_FORMATTED")]],
        "yaml": [[("format", "SUFFIX_FORMATTED")]],
        "topics": [[("yaml", "SUFFIX_YAML")]],
        "core": [[("yaml", "SUFFIX_YAML")]],
        "structured_summary": [[("topics", "SUFFIX_TOPICS"), ("core", "SUFFIX_TOPICS")]],
        "gen_abstract": [
            [("topics", "SUFFIX_TOPICS"), ("core", "SUFFIX_TOPICS")],
        ],
        "val_abstract": [[("gen_abstract", "SUFFIX_ABSTRACT_GEN")]],
        "blog": [
            [("core", "SUFFIX_STRUCTURAL_THEMES")],
            [("core", "SUFFIX_INTERPRETIVE_THEMES")],
        ],
        "overview": [
            [("core", "SUFFIX_ABSTRACT_INIT"), ("gen_abstract", "SUFFIX_ABSTRACT_GEN")],
            [("core", "SUFFIX_STRUCTURAL_THEMES")],
            [("core", "SUFFIX_TOPICS")],
            [("core", "SUFFIX_KEY_TERMS")],
        ],
        "webpdf": [[("format", "SUFFIX_FORMATTED"), ("yaml", "SUFFIX_YAML")]],
        # bowen_emphasis extracts from the validated derived transcript, so it
        # requires formatted/yaml (P13: never read the raw source). Spec: SR.4
        "bowen_emphasis": [[("format", "SUFFIX_FORMATTED"), ("yaml", "SUFFIX_YAML")]],
        "package": [[("format", "SUFFIX_FORMATTED"), ("yaml", "SUFFIX_YAML")]],
    }
    assert ts_gui.STAGE_DEPENDENCIES == expected


# ---------------------------------------------------------------------------
# Section B -- adversarial pre-flight scenarios
# ---------------------------------------------------------------------------

def test_preflight_proceeds_when_dependency_satisfied_by_disk_artifact_only(tmp_path):
    """B.1: format wasn't checked this run, but SUFFIX_FORMATTED already
    exists on disk from a prior run -- val_headers must be allowed to run."""
    _write_artifact(tmp_path, BASE_NAME, "SUFFIX_FORMATTED")
    gui = _make_gui(tmp_path, checked_keys={"val_headers"})

    with patch("ts_gui.messagebox.showwarning") as mock_warn, \
         patch("ts_gui.messagebox.askyesno", return_value=True), \
         patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()

    mock_warn.assert_not_called()
    mock_run.assert_called_once()


def test_preflight_proceeds_when_dependency_satisfied_by_checked_producer_stage(tmp_path):
    """B.2: format is checked in this same run (nothing on disk yet) -- its
    output will be produced before val_headers runs, per SS.11 ordering."""
    gui = _make_gui(tmp_path, checked_keys={"format", "val_headers"})

    with patch("ts_gui.messagebox.showwarning") as mock_warn, \
         patch("ts_gui.messagebox.askyesno", return_value=True), \
         patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()

    mock_warn.assert_not_called()
    mock_run.assert_called_once()


def test_preflight_message_exact_format(tmp_path):
    """B.3 / SS.15: two independent unmet dependencies on two different
    stages produce ONE messagebox call whose body names both, in
    STAGE_DEFINITIONS order. Deliberately avoids hardcoding a full golden
    string with guessed artifact labels -- asserts structural invariants
    only (title, first/last line, bullet count, per-stage bullet mapping,
    STAGE_DEFINITIONS order, and the bullet template shape)."""
    gui = _make_gui(tmp_path, checked_keys={"val_headers", "core"})

    with patch("ts_gui.messagebox.showwarning") as mock_warn, \
         patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()

    mock_run.assert_not_called()
    mock_warn.assert_called_once()
    title, message = mock_warn.call_args.args[:2]
    assert title == "Missing Prerequisites"

    lines = message.split("\n")
    assert lines[0] == "The following selected stage(s) are missing required prior output:"
    assert lines[-1] == (
        "Check the required stage(s) above, or run them in an earlier session, then retry."
    )

    bullet_lines = [ln for ln in lines if ln.strip().startswith("•")]
    val_headers_label = _label_for("val_headers")
    core_label = _label_for("core")

    assert len(bullet_lines) == 2  # one bullet per affected STAGE, not per group
    for label in (val_headers_label, core_label):
        matches = [ln for ln in bullet_lines if label in ln]
        assert len(matches) == 1, f"expected exactly one bullet for {label!r}"

    val_headers_idx = next(i for i, ln in enumerate(bullet_lines) if val_headers_label in ln)
    core_idx = next(i for i, ln in enumerate(bullet_lines) if core_label in ln)
    order = [key for key, _ in ts_gui.STAGE_DEFINITIONS]
    assert order.index("val_headers") < order.index("core")
    assert val_headers_idx < core_idx  # bullets follow STAGE_DEFINITIONS order

    for ln in bullet_lines:
        stripped = ln.strip()
        assert stripped.startswith("• ")
        assert stripped.endswith("to have run first")
        assert " needs " in stripped


def test_preflight_message_combines_multi_group_stage(tmp_path):
    """SS.15's own resolved wording (per the code spec, superseding an
    earlier ambiguous draft): a single stage with multiple unmet groups
    produces exactly ONE bullet, with the missing descriptions joined by
    " and ". `overview` has four dependency groups and nothing satisfies
    any of them here."""
    gui = _make_gui(tmp_path, checked_keys={"overview"})

    with patch("ts_gui.messagebox.showwarning") as mock_warn, \
         patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()

    mock_run.assert_not_called()
    mock_warn.assert_called_once()
    _, message = mock_warn.call_args.args[:2]
    lines = message.split("\n")
    bullet_lines = [ln for ln in lines if ln.strip().startswith("•")]

    overview_label = _label_for("overview")
    matches = [ln for ln in bullet_lines if overview_label in ln]
    assert len(matches) == 1, "overview's 4 unmet groups must combine into ONE bullet"
    assert matches[0].count(" and ") >= 3


def test_preflight_blocks_full_run_on_any_unmet_dependency(tmp_path):
    """B.4 / SS.14 / SS.17: one satisfiable stage (format) + one unmet stage
    (val_abstract, no gen_abstract checked or on disk) in the same
    selection blocks the WHOLE run -- format must not partially execute."""
    gui = _make_gui(tmp_path, checked_keys={"format", "val_abstract"})

    with patch("ts_gui.messagebox.showwarning") as mock_warn, \
         patch.object(gui, "run_task_in_thread") as mock_run, \
         patch("ts_gui.pipeline.format_transcript") as mock_format, \
         patch("ts_gui.pipeline.validate_format") as mock_validate_format, \
         patch("ts_gui.pipeline.validate_abstract_coverage") as mock_val_abstract:
        gui.do_run_selected()

    mock_run.assert_not_called()
    mock_format.assert_not_called()
    mock_validate_format.assert_not_called()
    mock_val_abstract.assert_not_called()

    mock_warn.assert_called_once()
    _, message = mock_warn.call_args.args[:2]
    assert _label_for("val_abstract") in message
    assert _label_for("format") not in message  # only the unmet stage is named


def test_preflight_overview_satisfied_by_abstract_init_branch(tmp_path):
    """B.5a: overview's abstract OR-group is satisfied via the INIT branch
    because `core` (which produces SUFFIX_ABSTRACT_INIT) is checked in this
    same run; core also satisfies overview's other three groups. core's OWN
    chain (yaml <- format) is checked too so the whole selection is valid and
    the only behavior under test is 'checking core satisfies overview's
    abstract-init branch' (the disk-based branch is covered separately by
    test_preflight_overview_satisfied_by_abstract_gen_branch)."""
    gui = _make_gui(tmp_path, checked_keys={"format", "yaml", "core", "overview"})

    with patch("ts_gui.messagebox.showwarning") as mock_warn, \
         patch("ts_gui.messagebox.askyesno", return_value=True), \
         patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()

    mock_warn.assert_not_called()
    mock_run.assert_called_once()


def test_preflight_overview_satisfied_by_abstract_gen_branch(tmp_path):
    """B.5b: overview's abstract OR-group is satisfied via the OTHER branch
    (SUFFIX_ABSTRACT_GEN on disk from a prior gen_abstract run), with `core`
    neither checked nor its own abstract artifact present."""
    for suffix_attr in (
        "SUFFIX_ABSTRACT_GEN",
        "SUFFIX_STRUCTURAL_THEMES",
        "SUFFIX_TOPICS",
        "SUFFIX_KEY_TERMS",
    ):
        _write_artifact(tmp_path, BASE_NAME, suffix_attr)

    gui = _make_gui(tmp_path, checked_keys={"overview"})

    with patch("ts_gui.messagebox.showwarning") as mock_warn, \
         patch("ts_gui.messagebox.askyesno", return_value=True), \
         patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()

    mock_warn.assert_not_called()
    mock_run.assert_called_once()


def test_preflight_overview_blocked_when_neither_abstract_branch_satisfied(tmp_path):
    """B.5c: neither SUFFIX_ABSTRACT_INIT (via core) nor SUFFIX_ABSTRACT_GEN
    (via gen_abstract) is available -- overview must be blocked."""
    gui = _make_gui(tmp_path, checked_keys={"overview"})

    with patch("ts_gui.messagebox.showwarning") as mock_warn, \
         patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()

    mock_run.assert_not_called()
    mock_warn.assert_called_once()
    _, message = mock_warn.call_args.args[:2]
    assert _label_for("overview") in message


@pytest.mark.parametrize("key", ["init_val", "format"])
def test_stage_dependencies_empty_for_dependency_free_stages(key):
    # bowen_emphasis is no longer dependency-free: it requires formatted/yaml so
    # it can't extract from the raw transcript (P13). Its behavior is covered by
    # test_ts_gui_run_all.py::test_selective_rerun_bowen_blocked_without_derived_artifact.
    assert ts_gui.STAGE_DEPENDENCIES[key] == []


@pytest.mark.parametrize(
    "checked",
    [
        {"init_val"},
        {"format"},
        {"init_val", "format"},
    ],
)
def test_preflight_never_blocks_dependency_free_stages(tmp_path, checked):
    """B.6: init_val / format have no dependency groups and must never be
    blocked, individually or in combination, regardless of disk state."""
    gui = _make_gui(tmp_path, checked_keys=checked)

    with patch("ts_gui.messagebox.showwarning") as mock_warn, \
         patch("ts_gui.messagebox.askyesno", return_value=True), \
         patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()

    mock_warn.assert_not_called()
    mock_run.assert_called_once()


def test_preflight_not_reached_on_empty_selection(tmp_path):
    """B.7: the "nothing checked" guard (SS.10 guard 3) fires and returns
    before the pre-flight validator is ever invoked."""
    gui = _make_gui(tmp_path, checked_keys=set())

    with patch.object(gui, "_validate_stage_dependencies") as mock_validate, \
         patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()

    mock_validate.assert_not_called()
    mock_run.assert_not_called()


def test_validate_stage_dependencies_returns_empty_for_empty_selection(tmp_path):
    """B.7 defense-in-depth: even if the validator were somehow invoked
    with an empty selection, it must not false-positive."""
    gui = _make_gui(tmp_path, checked_keys=set())
    unmet = gui._validate_stage_dependencies(set())
    assert not unmet


def test_preflight_reevaluates_live_disk_state_not_cached_from_save_time(tmp_path, monkeypatch):
    """B.8 / P6: a selection that WAS satisfiable when saved (the artifact
    existed on disk at save time) must be re-checked LIVE at run time, not
    trusted from a cached "was satisfiable" bit -- deleting the artifact
    between the save and this run must now block."""
    settings_path = tmp_path / "runtime_settings.json"
    monkeypatch.setattr(config.settings, "_runtime_settings_path", lambda: settings_path)

    artifact_path = _write_artifact(tmp_path, BASE_NAME, "SUFFIX_FORMATTED")
    try:
        config.save_stage_selection("QA Combo", ["val_headers"])

        gui = _make_gui(tmp_path, checked_keys={"val_headers"})
        with patch("ts_gui.messagebox.showwarning") as mock_warn, \
             patch("ts_gui.messagebox.askyesno", return_value=True), \
             patch.object(gui, "run_task_in_thread") as mock_run:
            gui.do_run_selected()
        mock_warn.assert_not_called()
        mock_run.assert_called_once()

        # Simulate the artifact being deleted between sessions (user cleanup,
        # or a fresh checkout). The saved selection itself is untouched.
        artifact_path.unlink()

        gui2 = _make_gui(tmp_path, checked_keys={"val_headers"})
        with patch("ts_gui.messagebox.showwarning") as mock_warn2, \
             patch.object(gui2, "run_task_in_thread") as mock_run2:
            gui2.do_run_selected()
        mock_run2.assert_not_called()
        mock_warn2.assert_called_once()
    finally:
        config.delete_stage_selection("QA Combo")


def test_preflight_never_mutates_selection(tmp_path):
    """SS.16: the set of stages actually run (once pre-flight passes) is
    always exactly the set the user checked -- pre-flight never auto-adds
    the missing-prerequisite stage(s)."""
    checked = {"format", "val_headers"}
    gui = _make_gui(tmp_path, checked_keys=checked)

    with patch("ts_gui.messagebox.showwarning"), \
         patch("ts_gui.messagebox.askyesno", return_value=True), \
         patch.object(gui, "run_task_in_thread") as mock_run:
        gui.do_run_selected()

    mock_run.assert_called_once()
    call = mock_run.call_args
    passed_keys = None
    for arg in list(call.args) + list(call.kwargs.values()):
        if isinstance(arg, (set, frozenset, list, tuple)):
            passed_keys = set(arg)
    assert passed_keys == checked


def test_preflight_artifact_path_matches_stage_writer(tmp_path):
    """Gap E.3 / SS.14: the validator's artifact-path builder must resolve
    byte-identically to where the pipeline actually writes/reads that same
    artifact (config.PROJECTS_DIR / base_name / f"{base_name}{suffix}"),
    else the validator could systematically false-block or false-negative
    every run for a given file."""
    gui = _make_gui(tmp_path)
    expected = tmp_path / BASE_NAME / f"{BASE_NAME}{config.SUFFIX_FORMATTED}"
    assert gui._stage_artifact_path("SUFFIX_FORMATTED") == expected
