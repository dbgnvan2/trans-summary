# Spec: Selective re-run (reuse existing outputs)

**Date:** 2026-07-16
**Builds on:** `docs/spec_stage_selection_2026-07-12.md` (SS.*) — the checkbox
stage-selection + pre-flight dependency system this feature extends.

## Motivation

The user wants to redo just particular outputs without re-running the whole
pipeline: check only the stages to (re)generate; unchecked stages are bypassed
and their existing outputs reused as inputs. Example: a run finished but Bowen +
Emphasis weren't checked; on the next run the user checks only those two, and the
pipeline generates them from the already-existing validated transcript.

Two things blocked this before: (a) the Init-Val guard blocked any run whose
selected file name lacked `_validated` unless `init_val` was checked — even for a
pure downstream re-run; and (b) there was no per-stage output map, so no way to
report/skip what already exists.

## Acceptance criteria

| ID | Criterion | Test |
|---|---|---|
| SR.1 | **`STAGE_OUTPUTS` producer map.** A module-level `{stage_key: [config-suffix-attr, ...]}` map naming the artifact(s) each stage WRITES, kept as data (attr names resolved via `_stage_artifact_path`) so status can't drift from the writer (P19). Covers every stage key except `init_val` (whose product is the `*_validated` source transcript, not a project-dir artifact). Every declared suffix attr resolves on `config`. | `tests/test_ts_gui_run_all.py::test_stage_outputs_cover_all_keys_except_init_val` |
| SR.2 | **"All present = exists" rule.** `_stage_outputs_status(key)` returns `(all_present, present, missing)`; `all_present` is True only when EVERY declared output exists (a partially-completed multi-file stage such as Core reads as not-done). A stage with no declared outputs returns `(False, [], [])` ("will generate"). | `tests/test_ts_gui_run_all.py::test_stage_outputs_status_requires_all_present`, `::test_stage_outputs_status_no_outputs_is_generate` |
| SR.3 | **Init-Val guard scoped to `format`.** The `do_run_selected` guard that requires a validated source fires ONLY when `format` (the stage consuming the raw transcript) is among the selected stages. A downstream-only selection is not blocked by it; those stages are governed by their own dependency pre-flight (SS.14). | `tests/test_ts_gui_run_all.py::test_selective_rerun_not_blocked_when_format_not_selected`, `::test_guard_still_blocks_format_even_alongside_other_stages` |
| SR.4 | **Bowen/Emphasis pre-flight.** `bowen_emphasis` requires a formatted/yaml artifact (`STAGE_DEPENDENCIES`), so a selective re-run can never run extraction on the raw unvalidated transcript (P13 — closes the hole opened by SR.3). | `tests/test_ts_gui_run_all.py::test_selective_rerun_bowen_blocked_without_derived_artifact`; graph in `tests/test_stage_dependencies.py::test_stage_dependencies_matches_verified_graph` |
| SR.5 | **Run-plan status log.** At run start (after cost estimate, before the stage loop) `_run_selected_stages` logs, per checked stage, `will generate` vs `will REGENERATE (overwrite)` (per SR.2), and one line naming which unchecked prerequisites are reused from disk. | `tests/test_ts_gui_run_all.py::test_run_plan_logs_regenerate_vs_generate` |
| SR.6 | **Extraction ordered before publish stages.** `bowen_emphasis` precedes `webpdf` and `package` in `STAGE_DEFINITIONS`. `webpdf`/`package` fail-closed on a release-gate BLOCK (return False → the runner halts), so placing the independent Bowen/Emphasis extraction earlier ensures a BLOCK can't skip it; it also means the rendered web/pdf (which highlight Bowen/Emphasis) reflect the current run. | `tests/test_ts_gui_run_all.py::test_bowen_emphasis_runs_before_webpdf_and_package` |

## Notes / adjacent

- `STAGE_OUTPUTS["webpdf"]` lists only `.html` + `.pdf` — the webpdf stage runner
  (`_run_web_pdf_generation`) does not write the simple webpage (that's a separate
  standalone tool), so declaring it would make a complete run read as incomplete
  (P19).
- Not built: an inverse "check many, skip those already present" toggle. The
  chosen model is "checked = redo (regenerate); unchecked-but-present = reused."
