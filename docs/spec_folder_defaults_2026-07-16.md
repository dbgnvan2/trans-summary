# Spec: Source-directory "Make Default" persistence

**Date:** 2026-07-16
**Module:** `ts_gui.py` (directory row) · `config.py` (runtime settings)

## Problem

The "Make Default" checkbox next to "Set Directory" only persisted the default
when it happened to be checked at the moment the user picked a folder (its value
was read solely inside `select_transcripts_directory`). Checking it *after*
setting the directory did nothing, and the box always initialised to unchecked so
it never reflected an already-saved default. Persistence machinery itself works:
`config.set_default_source_dir` writes `default_source_dir` to
`logs/runtime_settings.json`, and startup loads it (`config._load_runtime_settings`).

## Acceptance criteria

| ID | Criterion | Test |
|---|---|---|
| FD.1 | Toggling "Make Default" ON persists the CURRENT source dir as `default_source_dir` (loads next start); toggling OFF clears it. Works regardless of order relative to Set Directory. | `tests/test_folder_defaults.py::test_fd1_toggle_on_persists_current_source_dir`, `::test_fd1_toggle_off_clears_default` |
| FD.2 | The checkbox reflects the real saved state: `_sync_make_default_checkbox` sets it True only when the current source dir equals the saved default; called from `update_dir_label` (startup + after any dir change). | `tests/test_folder_defaults.py::test_fd2_sync_reflects_saved_state` |
| FD.3 | Changing the session directory without "Make Default" checked no longer silently wipes an existing saved default (previously `select_transcripts_directory` called `set_default_source_dir(None)` on every non-default pick). | `tests/test_folder_defaults.py::test_fd3_non_default_pick_preserves_existing_default` |

| FD.4 | "Make Default" ON also adds the current source dir to a saved favorites list (`source_dir_favorites`), deduped. The auto-load default (`default_source_dir`) is the ★-marked entry. | `tests/test_folder_defaults.py::test_fd4_make_default_adds_to_favorites` |
| FD.5 | The "Folder Defaults…" dialog shows the favorites list; `_load_favorite_source_dir` switches the session to a chosen favorite (without changing which auto-loads); `_remove_favorite_source_dir` removes one (clearing the auto-load default if it was that one). | `tests/test_folder_defaults.py::test_fd5_config_favorites_crud`, `::test_fd5_remove_favorite_clears_default_if_it_was_default`, `::test_fd5_load_favorite_switches_session` |

## Model

- `default_source_dir` (single): the folder that auto-loads on start.
- `source_dir_favorites` (list): folders the user can quickly switch to from the
  Folder Defaults dialog. "Make Default" writes both; unchecking clears only the
  auto-load default (the favorite stays until removed in the dialog).
