"""
Stage-selection persistence tests (config.py layer) + Section-C dirty-state
(P8) rot scenarios for saved stage selections.

Purpose: SS.1-SS.4 CRUD/round-trip coverage (behavioral, not grep-only --
         proves default args and actual read/write behavior, not just that
         the 5 methods exist), plus the "code changed which stages exist
         since this file was last written" scenarios from the QA test spec
         Section C.
Spec:    docs/spec_stage_selection_2026-07-12.md#SS.1-SS.4, #SS.13, #SS.20
Tests:   this file
"""
from unittest.mock import MagicMock, patch

import pytest

import config
import ts_gui


class _Flag:
    """Minimal tk.BooleanVar/StringVar stand-in (get + set)."""

    def __init__(self, value=False):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


@pytest.fixture
def scratch_settings(tmp_path, monkeypatch):
    """Redirect runtime_settings.json to a scratch file for the duration of
    the test, and restore the singleton's in-memory runtime_settings dict
    afterward -- config.settings is a process-wide singleton, so a test that
    mutates it must not leak state into later tests (repo's "restore
    patched state" rule)."""
    settings_path = tmp_path / "runtime_settings.json"
    monkeypatch.setattr(config.settings, "_runtime_settings_path", lambda: settings_path)
    original_runtime_settings = dict(config.settings.runtime_settings)
    try:
        yield settings_path
    finally:
        config.settings.runtime_settings = original_runtime_settings


def _make_gui_for_apply():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.stage_vars = {key: _Flag(False) for key, _ in ts_gui.STAGE_DEFINITIONS}
    gui.active_selection_var = _Flag("(none)")
    gui.include_bowen_core = _Flag(True)
    gui.include_emphasis_core = _Flag(True)
    gui.log = MagicMock()
    gui.run_task_in_thread = MagicMock()
    return gui


# ---------------------------------------------------------------------------
# SS.1 / SS.2 -- behavioral CRUD + delegation (grep-only would only prove
# the 5 methods/proxies exist, not that they read/write the right keys or
# that the module-level proxies actually delegate rather than re-implement).
# ---------------------------------------------------------------------------

def test_stage_selection_crud_roundtrip(scratch_settings):
    config.settings.runtime_settings = {}
    config.save_stage_selection(
        "Combo A", ["format", "val_headers"],
        include_bowen_core=False, include_emphasis_core=True,
    )

    selections = config.get_stage_selections()
    assert selections["Combo A"]["stages"] == ["format", "val_headers"]
    assert selections["Combo A"]["include_bowen_core"] is False
    assert selections["Combo A"]["include_emphasis_core"] is True

    config.delete_stage_selection("Combo A")
    assert "Combo A" not in config.get_stage_selections()


def test_module_level_stage_selection_proxies_delegate_to_settings(scratch_settings):
    """A proxy that silently re-implements the logic instead of delegating
    to config.settings would still pass a presence/grep check but drift
    from the class method over time -- assert delegation via mock."""
    with patch.object(config.settings, "save_stage_selection") as mock_save:
        config.save_stage_selection("X", ["format"])
    mock_save.assert_called_once_with("X", ["format"], True, True)

    with patch.object(config.settings, "delete_stage_selection") as mock_delete:
        config.delete_stage_selection("X")
    mock_delete.assert_called_once_with("X")

    with patch.object(config.settings, "get_stage_selections") as mock_get:
        config.get_stage_selections()
    mock_get.assert_called_once()

    with patch.object(config.settings, "set_default_stage_selection") as mock_setdef:
        config.set_default_stage_selection("X")
    mock_setdef.assert_called_once_with("X")

    with patch.object(config.settings, "get_default_stage_selection") as mock_getdef:
        config.get_default_stage_selection()
    mock_getdef.assert_called_once()


# ---------------------------------------------------------------------------
# SS.3 -- delete clears the default pointer only when it pointed at the
# deleted name.
# ---------------------------------------------------------------------------

def test_delete_default_selection_clears_default_pointer(scratch_settings):
    config.settings.runtime_settings = {}
    config.save_stage_selection("A", ["format"])
    config.set_default_stage_selection("A")
    config.delete_stage_selection("A")
    assert config.get_default_stage_selection() is None


def test_delete_non_default_selection_leaves_default_pointer_untouched(scratch_settings):
    """An off-by-one bug (clearing the pointer unconditionally on any
    delete) would pass the happy-path test above but fail this one."""
    config.settings.runtime_settings = {}
    config.save_stage_selection("A", ["format"])
    config.save_stage_selection("B", ["yaml"])
    config.set_default_stage_selection("A")

    config.delete_stage_selection("B")

    assert config.get_default_stage_selection() == "A"
    assert "A" in config.get_stage_selections()
    assert "B" not in config.get_stage_selections()


# ---------------------------------------------------------------------------
# SS.4 -- P8 dirty-state round trip: pre-existing unrelated keys AND
# multiple prior selections must survive a save + reload-from-disk.
# ---------------------------------------------------------------------------

def test_stage_selection_save_reload_preserves_unrelated_keys(scratch_settings):
    config.settings.runtime_settings = {"default_source_dir": "/some/unrelated/path"}
    config.save_stage_selection("Combo", ["format", "core"])

    # Simulate a fresh app start: reload from the persisted file.
    config.settings._load_runtime_settings()

    assert config.settings.runtime_settings.get("default_source_dir") == "/some/unrelated/path"
    assert "Combo" in config.settings.runtime_settings.get("stage_selections", {})


def test_stage_selection_save_reload_preserves_other_selections(scratch_settings):
    """A dict-overwrite bug (`runtime_settings["stage_selections"] =
    {name: ...}` instead of a keyed update) would silently drop prior
    selections; this test would catch it."""
    config.settings.runtime_settings = {}
    config.save_stage_selection("Combo A", ["format"])
    config.save_stage_selection("Combo B", ["yaml", "core"])

    config.settings._load_runtime_settings()

    selections = config.settings.runtime_settings.get("stage_selections", {})
    assert "Combo A" in selections
    assert "Combo B" in selections
    assert selections["Combo B"]["stages"] == ["yaml", "core"]


# ---------------------------------------------------------------------------
# Section C -- dirty-state rot scenarios (a stage renamed/removed since a
# selection was saved).
# ---------------------------------------------------------------------------

def test_get_stage_selections_survives_unknown_stage_key(scratch_settings):
    """The persistence layer has no knowledge of STAGE_DEFINITIONS (that
    lives in ts_gui.py) so it must return raw persisted data without
    raising, even if a stored stage key no longer exists."""
    config.settings.runtime_settings = {
        "stage_selections": {
            "Old Combo": {
                "stages": ["val_headers", "retired_stage_key"],
                "include_bowen_core": True,
                "include_emphasis_core": True,
            }
        }
    }
    selections = config.get_stage_selections()
    assert selections["Old Combo"]["stages"] == ["val_headers", "retired_stage_key"]


def test_default_stage_selection_pointer_survives_unrelated_stage_definition_change(scratch_settings):
    """The default pointer is a name-existence question, orthogonal to
    whether the named selection's stage list is fully valid; that validity
    question belongs to _apply_stage_selection, not get_default_stage_selection."""
    config.settings.runtime_settings = {
        "stage_selections": {
            "Old Combo": {
                "stages": ["val_headers", "retired_stage_key"],
                "include_bowen_core": True,
                "include_emphasis_core": True,
            }
        },
        "default_stage_selection": "Old Combo",
    }
    assert config.get_default_stage_selection() == "Old Combo"


def test_apply_stage_selection_skips_stage_keys_not_in_stage_definitions(scratch_settings):
    """_apply_stage_selection must ignore a stage key absent from the live
    STAGE_DEFINITIONS (renamed/removed stage) rather than raising, and log
    the skip (P2: surface, don't silently drop)."""
    config.settings.runtime_settings = {
        "stage_selections": {
            "Old Combo": {
                "stages": ["val_headers", "retired_stage_key"],
                "include_bowen_core": True,
                "include_emphasis_core": True,
            }
        }
    }
    gui = _make_gui_for_apply()

    gui._apply_stage_selection("Old Combo")  # must not raise

    assert gui.stage_vars["val_headers"].get() is True
    assert "retired_stage_key" not in gui.stage_vars
    gui.log.assert_called()


def test_apply_default_stage_selection_noop_when_default_name_missing(scratch_settings):
    """A default pointing at a fully-deleted selection name is a no-op, not
    a crash -- all checkboxes stay unticked."""
    config.settings.runtime_settings = {
        "stage_selections": {},
        "default_stage_selection": "Ghost Combo",
    }
    gui = _make_gui_for_apply()

    gui._apply_default_stage_selection()  # must not raise

    assert all(v.get() is False for v in gui.stage_vars.values())
    gui.run_task_in_thread.assert_not_called()


def test_apply_default_stage_selection_applies_valid_subset_of_partially_rotted_selection(scratch_settings):
    """Worse than a fully-deleted default (above): the selection NAME still
    resolves, but its stage LIST is partially rotted (one valid key, one
    unknown key). The still-valid subset must still apply -- equivalent to
    a full name-not-found staleness, this must not be treated as "nothing
    to apply"."""
    config.settings.runtime_settings = {
        "stage_selections": {
            "Partial Combo": {
                "stages": ["format", "retired_stage_key"],
                "include_bowen_core": True,
                "include_emphasis_core": True,
            }
        },
        "default_stage_selection": "Partial Combo",
    }
    gui = _make_gui_for_apply()

    gui._apply_default_stage_selection()

    assert gui.stage_vars["format"].get() is True
    assert all(
        v.get() is False for key, v in gui.stage_vars.items() if key != "format"
    )
    gui.run_task_in_thread.assert_not_called()


def test_apply_default_stage_selection_reduced_to_empty_after_filtering(scratch_settings):
    """The default selection's ENTIRE stage list is now-unknown keys --
    startup must leave all stage_vars False and not crash, equivalent to
    "no default set"."""
    config.settings.runtime_settings = {
        "stage_selections": {
            "Fully Rotted": {
                "stages": ["retired_stage_key_1", "retired_stage_key_2"],
                "include_bowen_core": True,
                "include_emphasis_core": True,
            }
        },
        "default_stage_selection": "Fully Rotted",
    }
    gui = _make_gui_for_apply()

    gui._apply_default_stage_selection()  # must not raise

    assert all(v.get() is False for v in gui.stage_vars.values())
    gui.run_task_in_thread.assert_not_called()


def test_duplicate_bowen_emphasis_detection():
    """Selecting Core (with Bowen/Emphasis included) AND the standalone Bowen+Emphasis
    stage runs the same extraction twice — the heads-up helper must flag it, and
    only when both are selected AND at least one of Bowen/Emphasis is included."""
    from ts_gui import _duplicate_bowen_emphasis
    # both selected + one extra included -> warn
    assert _duplicate_bowen_emphasis({"core", "bowen_emphasis"}, True, False) is True
    assert _duplicate_bowen_emphasis({"core", "bowen_emphasis"}, False, True) is True
    # both selected but neither included -> no duplicate
    assert _duplicate_bowen_emphasis({"core", "bowen_emphasis"}, False, False) is False
    # only one of the two stages selected -> never a duplicate
    assert _duplicate_bowen_emphasis({"core"}, True, True) is False
    assert _duplicate_bowen_emphasis({"bowen_emphasis"}, True, True) is False
    assert _duplicate_bowen_emphasis(set(), True, True) is False
