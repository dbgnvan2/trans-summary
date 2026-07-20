"""C1 (review 2026-07-18): a valid-JSON NON-object in runtime_settings.json must not
crash config import.

Dirty-state test (P8): pre-populate the persisted settings file with null / [] / an int
and assert the loader resets to {} instead of raising AttributeError out of module
import. Before the fix, json.loads succeeded (no JSONDecodeError) and the subsequent
.get() call raised AttributeError, which escaped `import config`.

Note: ProjectSettings.__new__ returns the GLOBAL singleton (config.settings), so we must
NOT instantiate it here — that would leak our temp path / state onto the global object
and break other tests' isolation. Instead we exercise _load_runtime_settings unbound with
a throwaway `self` that carries only the one attribute the method reads.
"""
import json
from types import SimpleNamespace

import config


def _run_loader(path):
    fake = SimpleNamespace(_runtime_settings_path=lambda: path, runtime_settings=None)
    config.ProjectSettings._load_runtime_settings(fake)
    return fake.runtime_settings


def test_c1_non_dict_runtime_settings_resets_to_empty(tmp_path):
    path = tmp_path / "runtime_settings.json"
    for bad in ["null", "[]", "5", '"x"', "true"]:
        path.write_text(bad, encoding="utf-8")
        assert _run_loader(path) == {}, f"non-dict {bad!r} should reset to empty dict"


def test_c1_malformed_json_still_resets(tmp_path):
    path = tmp_path / "runtime_settings.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert _run_loader(path) == {}


def test_c1_missing_file_is_empty(tmp_path):
    path = tmp_path / "does_not_exist.json"
    assert _run_loader(path) == {}


def test_c1_valid_dict_still_loads(tmp_path):
    path = tmp_path / "runtime_settings.json"
    path.write_text(json.dumps({"unrelated_key": "v"}), encoding="utf-8")
    assert _run_loader(path) == {"unrelated_key": "v"}
