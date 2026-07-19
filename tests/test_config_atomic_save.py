"""H3 (review 2026-07-18): _save_runtime_settings must write atomically so a partial
write can't corrupt the settings file (which the loader would then discard, zeroing the
user's settings). We call the method unbound with a throwaway `self` to avoid touching
the global config.settings singleton (see test_config_runtime_settings_dirty.py)."""
import json
import os
from types import SimpleNamespace

import pytest

import config


def _fake(path, settings):
    return SimpleNamespace(_runtime_settings_path=lambda: path, runtime_settings=settings)


def test_h3_atomic_save_roundtrips(tmp_path):
    path = tmp_path / "runtime_settings.json"
    config.ProjectSettings._save_runtime_settings(_fake(path, {"a": 1, "b": "two"}))
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1, "b": "two"}
    assert list(tmp_path.glob("*.tmp")) == [], "temp file left behind after a clean save"


def test_h3_failed_replace_preserves_prior_file(tmp_path, monkeypatch):
    path = tmp_path / "runtime_settings.json"
    path.write_text(json.dumps({"good": "original"}), encoding="utf-8")

    def boom(*args, **kwargs):
        raise OSError("simulated disk-full during replace")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        config.ProjectSettings._save_runtime_settings(_fake(path, {"new": "value"}))

    # the ORIGINAL file must be intact — os.replace never ran, so no half-write
    assert json.loads(path.read_text(encoding="utf-8")) == {"good": "original"}
    # and the temp file must be cleaned up, not left behind
    assert list(tmp_path.glob("*.tmp")) == []
