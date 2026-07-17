"""Tests for the source-directory 'Make Default' persistence.

Spec: docs/spec_folder_defaults_2026-07-16.md
"""

from unittest.mock import MagicMock

import pytest

import config
import ts_gui


class _Flag:
    def __init__(self, value=False):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


@pytest.fixture
def scratch_settings(tmp_path, monkeypatch):
    """Redirect runtime_settings.json to a scratch file and restore the
    process-wide singleton's in-memory dict afterward."""
    settings_path = tmp_path / "runtime_settings.json"
    monkeypatch.setattr(config.settings, "_runtime_settings_path", lambda: settings_path)
    original = dict(config.settings.runtime_settings)
    try:
        yield settings_path
    finally:
        config.settings.runtime_settings = original


def _gui():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.make_dir_default_var = _Flag(False)
    gui.log = MagicMock()
    return gui


def test_fd1_toggle_on_persists_current_source_dir(scratch_settings, tmp_path, monkeypatch):
    config.settings.runtime_settings = {}
    src = tmp_path / "my source"
    monkeypatch.setattr(config, "SOURCE_DIR", src)
    gui = _gui()
    gui.make_dir_default_var.set(True)

    gui._on_make_default_toggled()

    assert config.settings.runtime_settings.get("default_source_dir") == str(src)
    # persisted to disk
    assert scratch_settings.exists()
    assert str(src) in scratch_settings.read_text(encoding="utf-8")


def test_fd1_toggle_off_clears_default(scratch_settings, tmp_path, monkeypatch):
    src = tmp_path / "my source"
    config.settings.runtime_settings = {"default_source_dir": str(src)}
    monkeypatch.setattr(config, "SOURCE_DIR", src)
    gui = _gui()
    gui.make_dir_default_var.set(False)

    gui._on_make_default_toggled()

    assert "default_source_dir" not in config.settings.runtime_settings


def test_fd2_sync_reflects_saved_state(scratch_settings, tmp_path, monkeypatch):
    src = tmp_path / "my source"
    monkeypatch.setattr(config, "SOURCE_DIR", src)
    gui = _gui()

    # saved default matches current dir -> checked
    config.settings.runtime_settings = {"default_source_dir": str(src)}
    gui._sync_make_default_checkbox()
    assert gui.make_dir_default_var.get() is True

    # saved default is a different dir -> unchecked
    config.settings.runtime_settings = {"default_source_dir": str(tmp_path / "other")}
    gui._sync_make_default_checkbox()
    assert gui.make_dir_default_var.get() is False

    # no saved default -> unchecked
    config.settings.runtime_settings = {}
    gui._sync_make_default_checkbox()
    assert gui.make_dir_default_var.get() is False


def test_fd3_non_default_pick_preserves_existing_default(scratch_settings, tmp_path, monkeypatch):
    """Selecting a directory without 'Make Default' checked must not wipe an
    existing saved default (regression: the old code cleared it on every
    non-default pick)."""
    kept = tmp_path / "kept default"
    config.settings.runtime_settings = {"default_source_dir": str(kept)}

    gui = _gui()
    gui.make_dir_default_var.set(False)
    gui.update_dir_label = MagicMock()
    gui.update_terms_file_label = MagicMock()
    gui.refresh_file_list = MagicMock()

    new_dir = tmp_path / "temporary pick"
    new_dir.mkdir()
    monkeypatch.setattr(
        ts_gui.filedialog, "askdirectory", lambda **k: str(new_dir)
    )

    gui.select_transcripts_directory()

    # existing default untouched
    assert config.settings.runtime_settings.get("default_source_dir") == str(kept)
