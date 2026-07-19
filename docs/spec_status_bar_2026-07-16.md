# Spec: Bottom status bar tracks major step + final message

**Date:** 2026-07-16
**Module:** `ts_gui.py`

## Problem

The bottom status label was updated only by `_execute_task` at task start/end
("Task completed successfully." / "Task failed."). During a multi-stage run it
never changed, so it didn't show which major step the app was on, and the final
message was always generic.

## Acceptance criteria

| ID | Criterion | Test |
|---|---|---|
| SB.1 | During a selected-stages run, the bottom status bar updates to the current major step (`Step i/N: <label>…`) as each stage starts, and shows a specific final message (`✅ Complete — N stage(s): <last>` on success, `❌ Failed at: <label>` on halt) instead of the generic text. `set_final_status` marks a terminal message so `_execute_task` won't overwrite it; `_apply_status` no-ops when the widget isn't built (headless test instances). | `tests/test_ts_gui_run_all.py::test_sb1_status_updates_per_step_and_final_message`, `::test_sb1_status_shows_failing_step`, `::test_sb1_execute_task_preserves_task_final_status` |
