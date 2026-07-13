# Implementation Plan: Selectable Pipeline Stages with Dependency Pre-Flight Validation

Date: 2026-07-12
Author: Claude (planning step per global workflow rule #1)
Scope: Replace `ts_gui.py`'s 12 per-stage pipeline buttons and the hardcoded
"▶ DO ALL STEPS" flow with per-stage checkboxes, a single data-driven
"▶ Run Selected" execution path, named/saved/default stage selections, and a
new synchronous pre-flight validator that blocks a run whenever a checked
stage's upstream artifact is neither produced earlier in the same run nor
already present on disk.

---

## 1. Background

### 1.1 Current state

`ts_gui.py`'s `button_frame` has one `ttk.Button` per pipeline stage (Init
Val, Format, Val Headers, YAML, Core, Gen Abstract, Val Abstract, Blog,
Overview Post, Full Web/PDF, Bowen+Emphasis, Package). Each button
independently triggers just that stage via its own `do_*` handler
(`ts_gui.py:1129-1653`). A separate "▶ DO ALL STEPS" button
(`do_all_steps` / `_run_all_steps`, `ts_gui.py:1717-1852`) runs a hardcoded
sequence gated by only two ad-hoc checkboxes
(`include_init_val_do_all`, `omit_summary_do_all`) plus the always-on
`include_bowen_core` / `include_emphasis_core` modifiers — not every stage is
individually selectable in that flow, and "Overview Post" and
"Bowen + Emphasis" are not part of the sequence at all.

### 1.2 What the user wants

The user wants to pick an arbitrary subset of stages for a single run (e.g.
"Validate, Format, and Abstract"), save that subset under a name for reuse,
and mark one saved subset as the default that pre-loads (pre-ticks only,
never auto-runs) on GUI startup. This requires generalizing "DO ALL STEPS"
into a data-driven "run whichever stages are checked, in fixed pipeline
order" flow, and adding named-selection persistence using the existing
`runtime_settings.json` mechanism already in `config.py`
(`set_default_source_dir` pattern, `config.py:136-142`).

### 1.3 Why dependency validation is now in scope

The prior plan (`~/.claude/plans/indexed-wobbling-candle.md`) explicitly
flagged "no per-stage prerequisite checking" as an **adjacent issue, not
fixed**: checking a downstream-only stage (e.g. "Val Abstract" without "Gen
Abstract") would "fail naturally when the underlying pipeline call can't
find its input file."

The user has now asked for this to be brought in scope: *"some functionality
have dependencies on earlier items in the pipeline - make sure this is
accounted for."* Free-form stage selection makes an invalid, dependency-
violating combination easy to create (e.g. ticking only "Val Headers", or
"Blog" without "Core"), and today that failure surfaces as an opaque
exception deep inside a pipeline function (`extraction_pipeline.py`,
`validation_pipeline.py`) after the confirmation dialog and after a
background thread has already started — wasting an API-key check, a cost
estimate, and the user's wait, for a run that could never have succeeded.
This plan adds a **pre-flight validator** that runs synchronously, before
the confirmation dialog, and blocks the entire run with one clear message
if any checked stage's prerequisites cannot be satisfied.

The dependency graph below was derived by reading the actual bodies of the
pipeline functions in `extraction_pipeline.py`, `formatting_pipeline.py`,
`html_generator.py`, `validation_pipeline.py`, and `packaging_pipeline.py`
(via the `pipeline.py` facade), not guessed from button order or labels. GUI
guards already present in `ts_gui.py`'s `do_*` methods (e.g.
`do_validate_headers`'s `self.formatted_file.exists()` check at
`ts_gui.py:1367`, `do_summaries`'s YAML-file check at `ts_gui.py:1447`) were
cross-referenced as hints, and in every case matched what the underlying
pipeline function actually requires to avoid returning `False` — except that
those GUI guards do not exist at all for 8 of the 12 stages, which is the
gap this plan closes.

---

## 2. Stage table (fixed execution order, with verified dependencies)

| key | label | execution reuses | verified upstream dependency (hard, code-enforced) |
|---|---|---|---|
| `init_val` | 0. Init Val | `_run_initial_validation_auto` (existing, non-interactive) | none — operates on `self.selected_file` (the raw source file) |
| `format` | 1. Format | `_run_format_and_validate` (existing) | none — operates on `self.selected_file` |
| `val_headers` | 2. Val Headers | `_run_header_validation` (existing) | `format` — `HeaderValidator.run(self.formatted_file, ...)` reads `SUFFIX_FORMATTED` directly; GUI already guards this at `ts_gui.py:1367` |
| `yaml` | 3. YAML | new thin wrapper around `pipeline.add_yaml` | `format` — `add_yaml()` calls `validate_input_file()` on `PROJECTS_DIR/<stem>/<formatted_filename>` (`formatting_pipeline.py:351-352`); raises → caught → returns `False` if `SUFFIX_FORMATTED` is missing |
| `core` | 4. Core (ST/IT/T/KT/L) | new wrapper around `pipeline.summarize_transcript` (`skip_extracts_summary=False`) | `yaml` — `_load_formatted_transcript()` is called with the exact `SUFFIX_YAML` filename and only checks `PROJECTS_DIR/<stem>/<filename>` or a legacy dir (`extraction_pipeline.py:48-64`); no fallback to the formatted file. Missing → `FileNotFoundError` → caught by the outer `try/except` in `summarize_transcript` → returns `False` |
| `structured_summary` | Structured Summary | new wrapper around `pipeline.generate_structured_summary` | `core` — hard-requires `SUFFIX_TOPICS` content (`extraction_pipeline.py:843-856`: `if not topics_section: return False`). `SUFFIX_INTERPRETIVE_THEMES` is read but **not** hard-enforced (soft; used if present) |
| `gen_abstract` | 5. Gen Abstract | new wrapper around `pipeline.generate_structured_abstract` | `core` — hard-requires **both** `SUFFIX_TOPICS` and `SUFFIX_INTERPRETIVE_THEMES` (`extraction_pipeline.py:934-938`: `if not topics_section or not themes_section: return False`) |
| `val_abstract` | 6. Val Abstract | new wrapper around `pipeline.validate_abstract_coverage` | `gen_abstract` — hard-requires `SUFFIX_ABSTRACT_GEN` to exist (`validation_pipeline.py:588-593`: else logs `"No generated abstract found to validate. (Step 6 likely failed)"` and returns `False`) |
| `blog` | 7. Blog (Lens #1) | new wrapper around `pipeline.summarize_transcript` (`skip_blog=False`, `skip_extracts_summary=True`) | `core` — standalone path loads `SUFFIX_STRUCTURAL_THEMES` and `SUFFIX_INTERPRETIVE_THEMES` from disk (`extraction_pipeline.py:1259-1266`); if both are absent, lens generation/validation cannot produce a `top_lens` and blog generation is "aborted by policy" (`extraction_pipeline.py:1350-1355`), returning `False` |
| `overview` | 7b. Overview Post | new wrapper around `pipeline.summarize_transcript` (`skip_overview=False`, `skip_extracts_summary=True`) | `core` — explicit `missing_inputs` check requires **all four** of abstract, `SUFFIX_STRUCTURAL_THEMES`, `SUFFIX_TOPICS`, `SUFFIX_KEY_TERMS` to be non-empty, else logs which are missing and returns `False` (`extraction_pipeline.py:1385-1400`). Abstract is satisfied by either `SUFFIX_ABSTRACT_GEN` (from `gen_abstract`) or `SUFFIX_ABSTRACT_INIT` (produced by `core` itself, `extraction_pipeline.py:1276-1285`) |
| `webpdf` | 8. Full Web/PDF | `_run_web_pdf_generation` (existing) | `format` (or `yaml`) — `generate_webpage`/`generate_pdf` both call `load_project_transcript()`, which requires `SUFFIX_FORMATTED` or, failing that, `SUFFIX_YAML` (`transcript_utils.py:108-130`); raises if neither exists → caught → returns `False`. Topics/themes/abstract/Bowen/emphasis enrichment is soft (each loader returns `""`/`[]` if its file is absent — verified in `html_generator.py:60-138`, `_load_abstract`, `_load_summary`) |
| `bowen_emphasis` | Bowen + Emphasis | new wrapper around `pipeline.extract_bowen_and_emphasis`, reusing `_resolve_individual_extraction_input` | none — `_resolve_individual_extraction_input()` (`ts_gui.py:1393-1409`) already degrades gracefully: YAML → formatted → raw `self.selected_file`. `_load_formatted_transcript()` reads an absolute path directly if given one (`extraction_pipeline.py:50-51`), so this stage always has a valid input as long as a file is selected |
| `package` | Package | new wrapper around `pipeline.package_transcript` | `format` (or `yaml`) — hard-requires **at least one** of webpage/simple-webpage/PDF/`SUFFIX_YAML`/`SUFFIX_FORMATTED` to exist, else `"No files found to package."` and returns `False` (`packaging_pipeline.py:19-54`). Since `format` always produces `SUFFIX_FORMATTED`, this is the code-enforced minimum; `webpdf` having run is a *quality* dependency (more files get packaged) but is not code-enforced |

`include_bowen_core` / `include_emphasis_core` checkboxes stay as-is next to
the Core row (modifiers of the Core stage, not stages themselves).
`include_init_val_do_all` and `omit_summary_do_all` are removed — superseded
by the `init_val` and `structured_summary` stage checkboxes.

### 2.1 Dependency graph (compact form)

```
init_val         → (none)
format           → (none)
val_headers      → format            [needs: SUFFIX_FORMATTED]
yaml             → format            [needs: SUFFIX_FORMATTED]
core             → yaml              [needs: SUFFIX_YAML]
structured_summary → core            [needs: SUFFIX_TOPICS]
gen_abstract     → core              [needs: SUFFIX_TOPICS + SUFFIX_INTERPRETIVE_THEMES]
val_abstract     → gen_abstract      [needs: SUFFIX_ABSTRACT_GEN]
blog             → core              [needs: SUFFIX_STRUCTURAL_THEMES + SUFFIX_INTERPRETIVE_THEMES]
overview         → core (+ optionally gen_abstract) [needs: (SUFFIX_ABSTRACT_GEN or SUFFIX_ABSTRACT_INIT) + SUFFIX_STRUCTURAL_THEMES + SUFFIX_TOPICS + SUFFIX_KEY_TERMS]
webpdf           → format or yaml    [needs: SUFFIX_FORMATTED or SUFFIX_YAML]
bowen_emphasis   → (none)
package          → format or yaml    [needs: SUFFIX_FORMATTED or SUFFIX_YAML (webpdf output optional/soft)]
```

A prerequisite is **satisfiable** for a given run if, for every required
artifact group, at least one of: (a) the producing stage is also checked in
this run, or (b) the artifact file already exists on disk from a prior run.

---

## 3. Acceptance Criteria

Each criterion has an ID (SS.N) and a specific verification method.

| ID | Criterion | Verification |
|----|-----------|--------------|
| SS.1 | `config.py`'s `ProjectSettings` gains `save_stage_selection(name, stages, include_bowen_core=True, include_emphasis_core=True)`, `delete_stage_selection(name)`, `get_stage_selections()`, `set_default_stage_selection(name_or_None)`, `get_default_stage_selection()`, following the exact pattern of `set_default_source_dir` (`config.py:136-142`) and writing into `runtime_settings["stage_selections"]` / `runtime_settings["default_stage_selection"]`. | `grep -n "def save_stage_selection\|def delete_stage_selection\|def get_stage_selections\|def set_default_stage_selection\|def get_default_stage_selection" config.py` — all 5 present on `ProjectSettings`. |
| SS.2 | Matching module-level proxy functions exist in `config.py` (mirroring `set_default_source_dir` at `config.py:267-272`) so `ts_gui.py` calls `config.save_stage_selection(...)` etc. | `grep -n "^def save_stage_selection\|^def delete_stage_selection\|^def get_stage_selections\|^def set_default_stage_selection\|^def get_default_stage_selection" config.py`. |
| SS.3 | `delete_stage_selection(name)` clears `runtime_settings["default_stage_selection"]` in the same call if `name` was the current default, so the default pointer never dangles. | pytest `test_delete_default_selection_clears_default_pointer`: save selection "A", set default "A", delete "A", assert `get_default_stage_selection() is None`. |
| SS.4 | Stage-selection persistence survives a dirty runtime-settings file (pre-existing unrelated keys are preserved across save/reload). | pytest `test_stage_selection_save_reload_preserves_unrelated_keys` (P8 dirty-state test): pre-seed `runtime_settings.json` with an unrelated key, save a selection, reload settings from disk, assert both the unrelated key and the new selection are present. Reuses the `monkeypatch.setattr(config.settings, "_runtime_settings_path", ...)` pattern from `test_validation_terms_file_selection_persists` (`tests/test_ts_gui_run_all.py:307`). |
| SS.5 | `ts_gui.py` defines module-level `STAGE_DEFINITIONS = [(key, label), ...]` in the 13-row order from §2 (12 stages carried over from the existing buttons plus the new `structured_summary` stage, which supersedes `omit_summary_do_all`), used both to build checkboxes and to drive execution order. | `grep -n "^STAGE_DEFINITIONS" ts_gui.py` + assert the tuple of keys equals the §2 order, length 13 (pytest `test_stage_definitions_order`). |
| SS.6 | `ts_gui.py` defines a `STAGE_DEPENDENCIES` map: `{stage_key: [group, ...]}` where each `group` is a list of `(producing_stage_key, artifact_suffix_attr)` pairs (a group is satisfied if *any* pair in it is satisfied; a stage's prerequisites are satisfied only if *every* group is satisfied), matching the graph in §2.1 exactly (`val_headers`→format/SUFFIX_FORMATTED, `yaml`→format/SUFFIX_FORMATTED, `core`→yaml/SUFFIX_YAML, `structured_summary`→core/SUFFIX_TOPICS, `gen_abstract`→core/SUFFIX_TOPICS+core/SUFFIX_INTERPRETIVE_THEMES as two groups, `val_abstract`→gen_abstract/SUFFIX_ABSTRACT_GEN, `blog`→core/SUFFIX_STRUCTURAL_THEMES+core/SUFFIX_INTERPRETIVE_THEMES as two groups, `overview`→ an abstract group `[(core, SUFFIX_ABSTRACT_INIT), (gen_abstract, SUFFIX_ABSTRACT_GEN)]` plus three single-pair groups for `SUFFIX_STRUCTURAL_THEMES`/`SUFFIX_TOPICS`/`SUFFIX_KEY_TERMS` all keyed to `core`, `webpdf`→ one group `[(format, SUFFIX_FORMATTED), (yaml, SUFFIX_YAML)]`, `package`→ same group as `webpdf`; `init_val`, `format`, `bowen_emphasis` map to `[]`). | pytest `test_stage_dependencies_matches_verified_graph`: assert `STAGE_DEPENDENCIES == EXPECTED` (the literal dict from §2.1, written out in the test) — a direct equality check, not just a key-presence check. |
| SS.7 | `setup_ui`'s `button_frame` replaces all 12 existing stage `ttk.Button`s, plus adds one new checkbox for `structured_summary` (13 checkboxes total, superseding `omit_summary_do_all`), with `ttk.Checkbutton(button_frame, text=label, variable=self.stage_vars[key])` at grid positions matching `STAGE_DEFINITIONS`; `do_all_btn` and the `include_init_val_do_all` / `omit_summary_do_all` checkboxes are removed. `include_bowen_core` / `include_emphasis_core` remain. | `grep -n "ttk.Checkbutton(button_frame" ts_gui.py` — 13 matches, one per `STAGE_DEFINITIONS` key; `grep -c "do_all_btn\|include_init_val_do_all\|omit_summary_do_all" ts_gui.py` — 0. |
| SS.8 | `__init__` replaces `include_init_val_do_all` / `omit_summary_do_all` with `self.stage_vars = {key: tk.BooleanVar(value=False) for key, _ in STAGE_DEFINITIONS}` and `self.active_selection_var = tk.StringVar(value="(none)")`, and calls `self._apply_default_stage_selection()` after `setup_ui()`/`update_button_states()`. | pytest `test_init_creates_stage_vars_for_every_stage`: instantiate headless GUI object, assert `set(gui.stage_vars.keys()) == {k for k, _ in STAGE_DEFINITIONS}` and all default to `False`. |
| SS.9 | A new `run_frame` contains `self.run_selected_btn` ("▶ Run Selected", `command=self.do_run_selected`), a "Manage Selections..." button (`command=self.open_selection_manager_dialog`), and a label bound to `active_selection_var`; `status_label`/`memory_label` shift from `main_frame` row 5 to row 6. | `grep -n 'text="▶ Run Selected"\|text="Manage Selections' ts_gui.py`. |
| SS.10 | `do_run_selected()` applies the same guard shape as the old `do_all_steps`, in order: (1) no `self.selected_file` → return; (2) `self.processing` → log + return; (3) no stages checked → `messagebox.showwarning` + return; (4) **new pre-flight dependency check (SS.14)**; (5) `init_val` unchecked and filename lacks `_validated` → `messagebox.showwarning` + return (matches today's enforcement at `ts_gui.py:1728-1731`); then a confirmation dialog listing selected stage labels, then `self.run_task_in_thread(self._run_selected_stages, selected_keys)`. | pytest `test_do_run_selected_guard_order`: table-driven test exercising each guard in isolation (no file selected; already processing; nothing checked; unmet dependency; not-validated filename) and asserting `run_task_in_thread` was never called for any of them. |
| SS.11 | `_run_selected_stages(selected_keys)` runs the unconditional cost estimate first, then iterates `STAGE_DEFINITIONS` in order, calling a `stage_runners` dict of wrapper methods (only for keys in `selected_keys`), stopping on first `False` return, then logs the token-usage report and returns `True`. | pytest `test_run_selected_stages_order_and_halt` (rewritten from the existing `_run_all_steps` tests at `tests/test_ts_gui_run_all.py:17-181`): assert only checked stages' pipeline calls fire, in `STAGE_DEFINITIONS` order; assert a mid-run failure (e.g. header validation) halts before later stages are called. |
| SS.12 | New thin `_run_stage_*` wrapper methods exist for `yaml`, `core`, `structured_summary`, `gen_abstract`, `val_abstract`, `blog`, `overview`, `bowen_emphasis`, `package` — each the same `pipeline.*` call already inlined in the current `_run_all_steps`/`do_*` methods, extracted to be independently callable and referenced from `stage_runners`. | `grep -n "def _run_stage_" ts_gui.py` — 9 matches; pytest `test_stage_runners_cover_all_keys`: assert `set(stage_runners.keys()) == {k for k, _ in STAGE_DEFINITIONS}`. |
| SS.13 | `_apply_stage_selection(name)` sets every `self.stage_vars[key]` to `True`/`False` per the saved selection (explicitly clearing keys not in the selection), restores `include_bowen_core`/`include_emphasis_core`, and updates `active_selection_var`. Any stage key present in a saved selection but absent from the current `STAGE_DEFINITIONS` (e.g. a stage renamed/removed in a later release) is silently ignored rather than raising `KeyError` — a partially-stale selection still loads whatever keys remain valid. | pytest `test_apply_stage_selection_clears_stale_ticks`: apply selection "A" (a subset), then apply selection "B" (a disjoint subset), assert every key from "A" not in "B" is `False`. Plus `test_apply_stage_selection_ignores_unknown_stage_keys` (P8): saved selection contains a stage key not in `STAGE_DEFINITIONS`; assert `_apply_stage_selection` does not raise and applies every still-valid key. |
| SS.14 | **Pre-flight dependency validation.** Before the confirmation dialog and before any background thread starts (same synchronous point in `do_run_selected` as the existing `_validated`-filename guard), a new `_validate_stage_dependencies(selected_keys)` method checks every selected stage's `STAGE_DEPENDENCIES` groups, resolving each group's artifact path via one shared path-builder helper (e.g. `self._stage_artifact_path(artifact_suffix_attr)` → `config.PROJECTS_DIR / self.base_name / f"{self.base_name}{getattr(config, artifact_suffix_attr)}"`) that the `_run_stage_*` wrappers reuse for their own file I/O, so the validator's notion of "does this artifact exist" can never drift from where the stage actually reads/writes it. For a given stage, ALL of its unmet groups are collected together into a single `(stage_label, [missing_description, ...])` record (not one record per group). If any stage has unmet groups, `do_run_selected` shows **one** `messagebox.showwarning` (SS.15) listing every affected stage and returns — no stage runs. The whole run is blocked; satisfiable stages are **not** partially run. Passing this check is **not a success guarantee** — it only confirms each producing stage will be *attempted* before its dependent (per SS.11's ordering), not that the producer will succeed; a producer that fails still halts the run at execution time via SS.11's existing halt-on-`False` behavior. | pytest `test_preflight_blocks_full_run_on_any_unmet_dependency`: select `{val_abstract, format}` (format satisfiable, val_abstract not — no `gen_abstract` checked or on disk), assert `run_task_in_thread` is never called and the reported unmet stages contain exactly `val_abstract` (not `format`). Plus `test_preflight_artifact_path_matches_stage_writer`: assert the validator's path-builder and a `_run_stage_*` wrapper's actual write-target resolve to the identical `Path` for the same `(base_name, artifact_suffix_attr)`. |
| SS.15 | **Exact blocking message.** Title: `"Missing Prerequisites"`. Body starts with the literal line `"The following selected stage(s) are missing required prior output:"`, followed by **one bullet per affected stage** (not one per unmet group) in the exact form `f"  • {stage_label} needs {joined_missing_descriptions} to have run first"` where `joined_missing_descriptions` joins that stage's missing artifacts with `" and "` (e.g. a stage with two unmet groups reads `needs "Topics" and "Interpretive Themes" to have run first`), bullets in `STAGE_DEFINITIONS` order, and body ends with the literal line `"Check the required stage(s) above, or run them in an earlier session, then retry."`. | pytest `test_preflight_message_exact_format`: monkeypatch `messagebox.showwarning` to capture `(title, message)`; select a combination with two independent unmet dependencies on two different stages (e.g. `val_headers` + `core`, with no `format`/`yaml` checked or on disk); assert `title == "Missing Prerequisites"` and `message` matches the literal template with both stage bullets present. Plus `test_preflight_message_combines_multi_group_stage`: select only `overview` (four unmet groups) and assert it produces exactly ONE bullet listing all four missing descriptions joined, not four separate bullets. |
| SS.16 | Pre-flight validation does **not** silently auto-add the missing prerequisite stage(s) to `selected_keys` — the set of stages actually run (when validation passes) is always exactly the set the user checked. | pytest `test_preflight_never_mutates_selection`: capture `selected_keys` passed into `run_task_in_thread` across a passing run; assert it equals the checked set exactly, with no keys added. (Covered jointly with SS.11's ordering test — same assertion point.) |
| SS.17 | Pre-flight validation does not let an unmet dependency fail deep inside a pipeline call: no `_run_stage_*` wrapper or `pipeline.*` function is invoked for *any* stage in a run that fails the pre-flight check (the earlier guard blocks execution before `run_task_in_thread` is reached at all). | Same test as SS.14/SS.16 — `run_task_in_thread` (and by extension every `_run_stage_*`) is asserted never called; no pipeline mock invocation recorded. |
| SS.18 | `open_selection_manager_dialog()` — new `tk.Toplevel` mirroring `open_folder_defaults_dialog` (`ts_gui.py:820+`): a `tk.Listbox` of saved selection names (default one prefixed `★ `), with "Load", "Save Current As..." (`simpledialog.askstring`, confirms overwrite via `messagebox.askyesno` if the name exists), "Set as Default", "Clear Default", "Delete", "Close". | `grep -n "def open_selection_manager_dialog" ts_gui.py` + manual/human-verify: launch the GUI, open the dialog, confirm all six actions work against a scratch `runtime_settings.json`. *(Flagged: dialog widget interaction is not practically unit-testable headless beyond mocking `tk.Toplevel`; the underlying persistence calls it makes are separately covered by SS.1-SS.4.)* |
| SS.19 | `update_button_states()` (`ts_gui.py:1926+`) extends the existing enable/disable loop to cover every stage `ttk.Checkbutton` and `run_selected_btn` (`state = tk.NORMAL if not self.processing and self.selected_file else tk.DISABLED`, same rule `do_all_btn` used); "Manage Selections..." stays always enabled. | pytest `test_update_button_states_covers_checkboxes`: set `self.processing = True`, call `update_button_states()`, assert every stage checkbox widget's `state` is `tk.DISABLED` and the Manage Selections button remains `tk.NORMAL`. |
| SS.20 | On GUI startup, `_apply_default_stage_selection()` pre-ticks the default selection's checkboxes if `config.get_default_stage_selection()` is set and still present in `get_stage_selections()` (a fully-deleted default name is a no-op per SS.13's staleness handling); it never triggers `do_run_selected` or any pipeline call. Absent/fully-deleted default → no-op (all unchecked); a default whose *contents* have partially rotted (some but not all stage keys still valid) applies the still-valid subset via SS.13, rather than being treated as entirely stale. | pytest `test_apply_default_stage_selection_never_runs_pipeline`: set a default selection, instantiate the GUI object, monkeypatch `run_task_in_thread` to fail the test if called, assert checkboxes are pre-ticked and the monkeypatched runner was never invoked. Second test `test_apply_default_stage_selection_noop_when_stale`: set a default pointing at a deleted selection name, assert startup leaves all `stage_vars` `False` (no exception). Third test `test_apply_default_stage_selection_partial_rot`: default selection contains one valid and one now-unknown stage key, assert only the valid one pre-ticks (no exception). |
| SS.21 | Manual GUI smoke test confirms the end-to-end flow: tick "Format" + "Gen Abstract" only → pre-flight blocks with a message naming `gen_abstract`'s unmet `core` dependency (since Core wasn't checked and no prior Core artifacts exist) → tick "Core" as well → run succeeds → save the 3-stage combo as a name → restart the app with no default set (all unchecked) → set the saved combo as default → restart again → checkboxes pre-tick without the pipeline auto-running. | Human-verify (not code-testable end-to-end across two process restarts and real Tk mainloop/file dialogs). Flagged explicitly per repo convention — automated coverage for each sub-behavior exists in SS.10/SS.14/SS.15/SS.20; this is the integration smoke test tying them together. |
| SS.22 | `pytest tests/test_ts_gui_run_all.py -q` (rewritten) and new persistence/dependency test modules all pass headless, with no Tk mainloop required — matching the existing `_Flag`/`__new__`/`patch.object` pattern already proven in that file. | `pytest tests/test_ts_gui_run_all.py tests/test_stage_selection_persistence.py tests/test_stage_dependencies.py -q` exits 0. |

SS.18 and SS.21 are the only criteria not fully automatable; both are flagged
explicitly above with what *is* automated around them, per this repo's rule
that no criterion is left unverifiable without saying so.

---

## 4. Order of Implementation

Dependencies between steps below (not to be confused with the pipeline
stage dependency graph in §2, which is a runtime data structure, not a
build-order constraint):

1. **`config.py` persistence (SS.1-SS.4).** No dependency on GUI code; can
   be built and unit-tested in isolation first, exactly like
   `set_default_source_dir` was. Must land before step 3 (GUI wiring calls
   these functions).
2. **`STAGE_DEFINITIONS` and `STAGE_DEPENDENCIES` data (SS.5, SS.6).**
   Pure data structures in `ts_gui.py`, derived directly from §2/§2.1 of
   this spec. No runtime dependency on step 1, but logically precedes step
   3 since the checkbox/execution/pre-flight code all consume these tables.
3. **`ts_gui.py` UI wiring (SS.7-SS.9, SS.18, SS.19).** Checkbox layout,
   `run_frame`, selection-manager dialog. Depends on steps 1 and 2 (calls
   `config.save_stage_selection` etc., iterates `STAGE_DEFINITIONS`).
4. **`ts_gui.py` execution + pre-flight (SS.10-SS.17, SS.20).** The
   `do_run_selected` / `_run_selected_stages` / `_run_stage_*` wrappers and
   `_validate_stage_dependencies`. Depends on step 2 (dependency map) and
   step 3 (checkbox state source `self.stage_vars`). This is the highest-
   risk step — implement the pre-flight validator (SS.14-SS.17) before or
   alongside the execution refactor (SS.10-SS.11), not after, since
   `do_run_selected`'s guard order in SS.10 places the pre-flight check
   ahead of the confirmation dialog.
5. **Tests (SS.4, SS.8, SS.11-SS.17, SS.19-SS.20, SS.22).** Write the
   pre-flight/dependency tests (SS.14-SS.17) first among the new tests —
   per the global rule that the highest-impact, most-likely-to-regress fix
   gets tested first, and an unenforced or silently-wrong dependency check
   is the highest-risk part of this change (a false negative lets a doomed
   run start; a false positive blocks a valid run). Persistence tests
   (SS.1-SS.4) and the rewritten `_run_all_steps`→`_run_selected_stages`
   tests (SS.11-SS.12) follow. The manual smoke test (SS.21) runs last,
   after all automated tests pass.
6. **Status report.** Generate a coverage report mapping every SS.N
   criterion to its verification artifact per the global "Completion
   standard" rule, once implementation is complete.

---

## 5. Adjacent Issues Found, Not Fixed

Per global rule #10, flagged but out of scope for this change:

1. **`overview`'s abstract source ambiguity** — like the existing
   `SUFFIX_ABSTRACT_INIT` vs `SUFFIX_ABSTRACT_GEN` ambiguity already flagged
   in `docs/implementation_plan_2026-05-13.md` §6.2, the pre-flight
   dependency map (SS.6) treats `overview`'s abstract requirement as
   satisfied by *either* file. This mirrors the pipeline's own runtime
   behavior (`extraction_pipeline.py:1276-1285`) rather than introducing a
   new resolution rule — not addressed further here.
2. **`package`'s soft dependency on `webpdf`** — `package_transcript` does
   not hard-fail without a webpage/PDF (only warns), so the pre-flight
   validator does not block a `package`-only run that would produce a
   transcript-only zip with no rendered output. Users may find that
   surprising. A future increment could add a *soft* pre-flight warning
   (not a block) for this case; out of scope here since it is not a
   code-enforced failure.
3. **No dependency-aware auto-suggestion in the selection manager UI** —
   SS.18's dialog does not proactively suggest adding a missing prerequisite
   stage when saving/loading a selection; it relies entirely on the
   pre-flight block at run time. A "this selection is missing X" indicator
   in the manager dialog itself would be a reasonable follow-up.

---

## 6. Open Questions for the User

None blocking. Soft questions the user can override during review:

- Q1: SS.15's exact wording is a design choice (bullet format, trailing
  guidance line). Say now if you want different phrasing — it's asserted
  verbatim in SS.15's test, so a later wording change is a one-line test
  edit, not a re-architecture.
- Q2: `overview`'s dependency group treats `SUFFIX_ABSTRACT_INIT` and
  `SUFFIX_ABSTRACT_GEN` as interchangeable (§Adjacent Issue 1). Flag if you
  want the pre-flight check to prefer/require the *generated* (validated)
  abstract specifically once `val_abstract` exists as a stage.
