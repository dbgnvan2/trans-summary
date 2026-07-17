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

## Not built here (pending user decision)

- A **multi-folder "Folder Defaults" list** (favorites the user can pick from).
  Today's model is a single default each for source/processed/projects. Whether
  to add a favorites list, and how it relates to the single auto-load default, is
  an open design question raised with the user.
