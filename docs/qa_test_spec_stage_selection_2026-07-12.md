# QA Test Spec: Selectable Pipeline Stages with Dependency Pre-Flight Validation

Date: 2026-07-12
Author: Claude (independent QA pass — no prior design-discussion context, per
task instructions)
Input: `docs/spec_stage_selection_2026-07-12.md` (SS.1-SS.22), existing
pattern in `tests/test_ts_gui_run_all.py`, `~/.claude/standards/learnings.md`
(P1-P18)

Purpose: map every SS.N acceptance criterion to concrete tests, verify the
code spec's own proposed verification methods actually prove the criterion,
and add adversarial/dirty-state coverage the spec under-specifies —
especially around the pre-flight dependency validator (SS.14-SS.17), which
is the highest-risk part of this change (a false negative lets a doomed run
burn an API call; a false positive blocks a legitimate run).

This document specifies tests only. No implementation or test code was
written or modified as part of this pass.

---

## A. Traceability table

Proposed new test files (matching the spec's own naming in SS.22):
`tests/test_stage_selection_persistence.py` (config.py layer),
`tests/test_stage_dependencies.py` (pre-flight validator), and continued use
of `tests/test_ts_gui_run_all.py` for GUI-wiring/execution-order tests
(rewritten per SS.11).

| SS.N | Test function name(s) | Test file | Verdict on spec's own verification |
|---|---|---|---|
| SS.1 | `test_stage_selection_crud_roundtrip` (save → get → delete, asserting returned *values* not just key presence) | `tests/test_stage_selection_persistence.py` | **Insufficient.** `grep -n "def save_stage_selection\|..."` only proves the 5 methods exist with the right names — it proves nothing about signatures, default args (`include_bowen_core=True`), or that they actually write/read `runtime_settings["stage_selections"]` correctly. Add a behavioral round-trip test. |
| SS.2 | `test_module_level_stage_selection_proxies_delegate_to_settings` (call each module-level function, assert it mutates the same `settings` singleton the class methods do, using `unittest.mock.patch.object(config.settings, "save_stage_selection")` to assert delegation, not just re-implementation) | `tests/test_stage_selection_persistence.py` | **Insufficient.** Same grep-only problem as SS.1. A proxy that silently duplicates logic instead of delegating (common copy-paste bug) would still pass the grep but drift from the class method over time. Assert delegation via mock, not just presence. |
| SS.3 | `test_delete_default_selection_clears_default_pointer` (as specified) **+** `test_delete_non_default_selection_leaves_default_pointer_untouched` (new) | `tests/test_stage_selection_persistence.py` | **Sufficient for the happy path, but incomplete.** The spec's test only proves the clear-on-match case; it never proves the pointer survives deletion of an *unrelated* selection — a plausible off-by-one bug (clearing the pointer unconditionally on any delete) would pass the given test. |
| SS.4 | `test_stage_selection_save_reload_preserves_unrelated_keys` (as specified) **+** `test_stage_selection_save_reload_preserves_other_selections` (new — save two named selections, reload, assert both survive, not just the most-recently-saved one) | `tests/test_stage_selection_persistence.py` | **Sufficient as far as it goes**, but only exercises one selection. A dict-overwrite bug (`runtime_settings["stage_selections"] = {name: ...}` instead of `.update()`/keyed assignment) would silently drop prior selections and this test wouldn't catch it. |
| SS.5 | `test_stage_definitions_order` (as specified, **but see Gap E.1 — the literal count must be 13, not 12**) | `tests/test_ts_gui_run_all.py` (or a new `tests/test_stage_definitions.py`) | **Insufficient as written — the spec's own verification text is internally wrong.** §2's stage table has 13 rows (confirmed by direct count: `init_val, format, val_headers, yaml, core, structured_summary, gen_abstract, val_abstract, blog, overview, webpdf, bowen_emphasis, package`), not 12. A test asserting "12-row order" will either fail against a correct 13-stage implementation or silently validate an implementation that dropped `structured_summary`. See Gap E.1. |
| SS.6 | `test_stage_dependencies_matches_verified_graph` (as specified — literal-dict equality) **+** black-box tests in Section B (independent of the literal-dict comparison) | `tests/test_stage_dependencies.py` | **Strong but not self-sufficient.** A literal-equality test only catches drift between the code and the test's copy of the graph — if the *same* transcription error is made in both (plausible since a human/LLM would derive both from the same §2.1 text), it silently passes while the validator is still behaviorally wrong. Section B's black-box `(selection, disk-state) → block/proceed` tests are required as an independent check that doesn't share the transcription. |
| SS.7 | `test_stage_checkboxes_bound_to_stage_vars` (regex-per-key: assert each `STAGE_DEFINITIONS` key appears in a `ttk.Checkbutton(button_frame, ..., variable=self.stage_vars["<key>"])` construction, not just a bare count) **+ correct the literal `12` to `13`** | `tests/test_ts_gui_run_all.py` (source-inspection style, matching the repo's existing grep-based structural tests) | **Insufficient, two ways.** (1) `grep -c "ttk.Checkbutton(button_frame" ts_gui.py` == 12 is wrong per Gap E.1 (should be 13). (2) A bare count doesn't prove *which* checkbox is bound to *which* `stage_vars` key — a copy-paste bug that binds two checkboxes to the same `stage_vars["core"]` would still produce 13 matching lines. Assert the per-key binding explicitly. |
| SS.8 | `test_init_creates_stage_vars_for_every_stage` (as specified) | `tests/test_ts_gui_run_all.py` | **Sufficient** — the `set()` comparison against `STAGE_DEFINITIONS` is dynamic (not a hardcoded count), so it's immune to Gap E.1's 12-vs-13 drift and correctly self-corrects once `STAGE_DEFINITIONS` is fixed. |
| SS.9 | `test_run_frame_has_run_selected_and_manage_buttons` (as specified) | `tests/test_ts_gui_run_all.py` | **Sufficient** for presence; text-only grep, but this criterion is genuinely just about widget presence/wiring, and `command=` binding should additionally be asserted (`grep -n 'command=self.do_run_selected'`) rather than just the button text, in case the label exists but is wired to the wrong handler. |
| SS.10 | `test_do_run_selected_guard_order` (as specified, isolating each guard) **+** `test_do_run_selected_guard_precedence_when_multiple_conditions_true` (new) | `tests/test_ts_gui_run_all.py` | **Insufficient on its own for "order."** Testing each guard *in isolation* (only one condition true at a time) proves each guard works, but never proves *precedence* — e.g., if `self.processing=True` **and** nothing is checked simultaneously, does the "already running" log fire (correct, per guard order 2-before-3) or the "nothing checked" warning (wrong)? The isolation-only test would pass even if guards fired in the wrong order internally, as long as each guard works alone. Add a two-condition-true test that asserts which single message fires. |
| SS.11 | `test_run_selected_stages_order_and_halt` (as specified) **+** `test_run_selected_stages_skips_non_contiguous_unchecked_stages` (new — check `format` and `gen_abstract` but not `val_headers`/`yaml`/`core`, assert exactly those two wrapper calls fire and nothing between them) | `tests/test_ts_gui_run_all.py` | **Insufficient as scoped.** The spec's description covers ordering and halt-on-failure but doesn't explicitly require a *non-contiguous* selection test; a naive "run everything from stage[0] to the highest checked index" bug (instead of "run only checked stages") would pass a contiguous-selection test but silently run unchecked stages in between on a real, sparse selection. |
| SS.12 | `test_stage_runners_cover_all_keys` (as specified) **+** `test_stage_runner_forwards_correct_pipeline_args_per_stage` (new, table-driven — `blog` must call `summarize_transcript(..., skip_blog=False, skip_extracts_summary=True)`, `overview` must call it with `skip_overview=False, skip_extracts_summary=True`, `core` with `skip_extracts_summary=False`) | `tests/test_ts_gui_run_all.py` | **Insufficient.** `set(stage_runners.keys()) == {...}` only proves 9 wrapper methods exist and are registered under the right keys — it says nothing about whether each wrapper calls its underlying `pipeline.*` function with the correct flags. This is exactly the kind of "looks right, key present, but wrong behavior" case P7 warns about (proxy signal dominating a check it doesn't actually validate). The existing `test_run_all_includes_cost_estimation_and_separate_blog_step`'s flag-tuple assertions (lines 55-60 of the current file) are the right pattern to replicate per-wrapper. |
| SS.13 | `test_apply_stage_selection_clears_stale_ticks` (as specified) **+** `test_apply_stage_selection_preserves_overlapping_keys` (new — selections "A" and "B" share some keys; assert the overlap stays `True`, not toggled off-then-on) **+** `test_apply_stage_selection_defaults_bowen_emphasis_when_absent_from_saved_selection` (new, P8-relevant — see Section C) | `tests/test_ts_gui_run_all.py` | **Insufficient — only tests the disjoint case.** Disjoint-selection clearing is the easy case; it doesn't prove overlap is preserved without a flicker/bug, and it doesn't test what happens when an *older-format* saved selection lacks `include_bowen_core`/`include_emphasis_core` keys at all (a realistic post-upgrade scenario). |
| SS.14 | `test_preflight_blocks_full_run_on_any_unmet_dependency` (as specified) **+** all of Section B | `tests/test_stage_dependencies.py` | **Sufficient as a single example, insufficient as full coverage** — it's one scenario (mixed satisfiable/unsatisfiable) out of the many needed to trust a boolean-per-stage validator. Section B enumerates the required set. |
| SS.15 | `test_preflight_message_exact_format` (as specified — two *different* stages unmet) **+** `test_preflight_message_two_bullets_same_stage_multiple_unmet_groups` (new — see Gap E.6 / Section B.9) | `tests/test_stage_dependencies.py` | **Insufficient.** The spec's own test only covers two *different* stages each missing one group. It never exercises a single stage (e.g. `overview`) missing *two* of its own groups simultaneously — SS.14's own wording ("one bullet line per unmet requirement group") implies this should produce two bullets naming the *same* stage label, which is untested and ambiguous as written (see Gap E.6). |
| SS.16 | `test_preflight_never_mutates_selection` (as specified) | `tests/test_stage_dependencies.py` | **Sufficient** — a direct equality check on the captured `selected_keys` argument is the right test for a non-mutation guarantee. |
| SS.17 | Same test as SS.14/SS.16 (as specified) | `tests/test_stage_dependencies.py` | **Sufficient**, but strengthen by also asserting the specific `pipeline.*` mocks (not just `run_task_in_thread`) were never called, to rule out any code path that might invoke a `_run_stage_*` wrapper directly outside `run_task_in_thread`. |
| SS.18 | Manual script (Section D) | N/A (human-verify, as flagged in spec) | **Correctly flagged as non-automatable** by the spec. Manual script provided in Section D closes the gap on *what* to check, since the spec's own text ("confirm all six actions work") is too vague to execute repeatably. |
| SS.19 | `test_update_button_states_covers_checkboxes` (as specified) **+** `test_update_button_states_reenables_after_processing_completes` (new, P8-relevant — see Gap E.7) | `tests/test_ts_gui_run_all.py` | **Insufficient — only tests the disable direction.** `self.processing = True` → assert disabled is the easy half; never tests the reverse transition (`processing = False` after a prior `True`), which is the actual runtime scenario (post-run re-enable) and where a stale-disabled-forever bug would hide. |
| SS.20 | `test_apply_default_stage_selection_never_runs_pipeline` + `test_apply_default_stage_selection_noop_when_stale` (both as specified) **+** `test_apply_default_stage_selection_handles_selection_with_unknown_stage_keys` (new — see Section C) | `tests/test_ts_gui_run_all.py` | **Insufficient for the P8 "code changed between runs" case.** The spec's "stale" test only covers a default *name* pointing at a deleted selection — it doesn't cover a default whose *name* still resolves but whose *stage list* contains keys no longer in `STAGE_DEFINITIONS` (see Section C). |
| SS.21 | Manual script (Section D) | N/A (human-verify, as flagged in spec) | **Correctly flagged as non-automatable.** Manual script provided in Section D. |
| SS.22 | `pytest tests/test_ts_gui_run_all.py tests/test_stage_selection_persistence.py tests/test_stage_dependencies.py -q` (as specified) | N/A (CI gate) | **Sufficient as a gate**, but it is only as strong as the tests it runs — its "sufficiency" is entirely inherited from the fixes proposed above for SS.1-SS.20. |

---

## B. Adversarial test cases for the dependency pre-flight validator (SS.14-SS.17)

All tests live in `tests/test_stage_dependencies.py`. Convention: a fixture
`_gui_with_project(tmp_path, base_name)` creates a headless GUI object
(`ts_gui.TranscriptProcessorGUI.__new__(...)`) with `self.base_name` set and
`config.PROJECTS_DIR` monkeypatched to `tmp_path`; "on-disk artifact" means a
zero-byte file created at
`tmp_path / base_name / f"{base_name}{config.SUFFIX_X}"`.

| # | Scenario | Given | Expect | Test function name |
|---|---|---|---|---|
| B.1 | Dependency satisfied by an **on-disk artifact**, not by the producing stage being checked | Selection = `{val_headers}` only. `format` is **not** checked. On disk: `<base> - formatted.md` exists (from a prior run). | **Proceed** — `_validate_stage_dependencies` returns no unmet entries; `run_task_in_thread` is called. | `test_preflight_proceeds_when_dependency_satisfied_by_disk_artifact_only` |
| B.2 | Dependency satisfied by the **producing stage checked in this run**, no on-disk artifact yet | Selection = `{format, val_headers}`. Nothing on disk. | **Proceed** — `format` being checked satisfies `val_headers`'s group even though `SUFFIX_FORMATTED` doesn't exist yet (it will be produced mid-run). | `test_preflight_proceeds_when_dependency_satisfied_by_checked_producer_stage` |
| B.3 | **Two independent unmet dependencies** on two different stages, simultaneously | Selection = `{val_headers, core}`. Neither `format` nor `yaml` checked or on disk. | **Block**, single `messagebox.showwarning` call, message body contains **both** bullets (`val_headers` needs `format`... **and** `core` needs `yaml`...) — not just the first one encountered. | `test_preflight_message_exact_format` (spec's own test, reused — assert both bullets present, in `STAGE_DEFINITIONS` order: `val_headers` bullet precedes `core` bullet) |
| B.4 | One stage satisfiable, one not, in the **same** selection | Selection = `{format, val_abstract}`. `format` is trivially satisfiable (no deps). `val_abstract` unmet (no `gen_abstract` checked, none on disk). | **Block the whole run** — assert `run_task_in_thread` never called **and**, additionally, the `pipeline.format_transcript`/`pipeline.validate_format` mocks are never called either (proves `format` doesn't get partially run before the block). Unmet list names only `val_abstract`, not `format`. | `test_preflight_blocks_full_run_on_any_unmet_dependency` (spec's own test, strengthened per SS.14/SS.17 traceability note) |
| B.5a | `overview`'s OR-group satisfied via `SUFFIX_ABSTRACT_INIT` branch | Selection = `{core, overview}`. On disk (simulating `core` having run before in this same call graph is not needed since `core` is checked): none needed for abstract since `core` itself is checked and produces `SUFFIX_ABSTRACT_INIT`; `SUFFIX_STRUCTURAL_THEMES`/`SUFFIX_TOPICS`/`SUFFIX_KEY_TERMS` groups also satisfied by `core` being checked. | **Proceed.** | `test_preflight_overview_satisfied_by_abstract_init_branch` |
| B.5b | `overview`'s OR-group satisfied via `SUFFIX_ABSTRACT_GEN` branch, `core` **not** checked | Selection = `{overview}` only. On disk: `SUFFIX_ABSTRACT_GEN`, `SUFFIX_STRUCTURAL_THEMES`, `SUFFIX_TOPICS`, `SUFFIX_KEY_TERMS` all present (prior run completed `core` + `gen_abstract`). | **Proceed** — proves the OR-group's second branch (`gen_abstract`/`SUFFIX_ABSTRACT_GEN`) independently satisfies the requirement without `core` being checked or its own `SUFFIX_ABSTRACT_INIT` present. | `test_preflight_overview_satisfied_by_abstract_gen_branch` |
| B.5c | `overview`'s OR-group: **neither** branch satisfied | Selection = `{overview}` only. Nothing on disk, `core`/`gen_abstract` not checked. | **Block** — unmet list names `overview`'s abstract requirement specifically (distinguishable from its other three unmet groups if those are also unmet). | `test_preflight_overview_blocked_when_neither_abstract_branch_satisfied` |
| B.6 | No-dependency stages (`init_val`, `format`, `bowen_emphasis`) are **never** blocked | Selection = `{init_val, format, bowen_emphasis}` only, nothing else checked, nothing on disk. Parametrized/table-driven over all three keys individually and combined. | **Proceed** in every case — `STAGE_DEPENDENCIES[key] == []` for all three regardless of any other stage's state. | `test_preflight_never_blocks_dependency_free_stages` (parametrized) |
| B.7 | Empty selection | Selection = `{}` (nothing checked). | Pre-flight check is **never reached** — SS.10 guard (3) ("no stages checked" warning) fires first and returns before `_validate_stage_dependencies` is called at all. Assert `_validate_stage_dependencies` (mocked/spied) is not called, and separately assert that *if* it somehow were called with an empty set it returns no unmet entries (false-positive-proof at the unit level too, as defense in depth). | `test_preflight_not_reached_on_empty_selection` + `test_validate_stage_dependencies_returns_empty_for_empty_selection` |
| B.8 | **P6 — live ground truth, not cached from save time.** A selection was saved (and is satisfiable) when it was saved, but the on-disk artifact was deleted before this run | Selection = `{val_headers}`, saved via `save_stage_selection` at a time when `<base> - formatted.md` existed on disk. Before calling `do_run_selected` now, the test deletes that file from disk (simulating a user cleanup between sessions) without changing the saved selection. | **Block** — `_validate_stage_dependencies` re-checks the filesystem at run time, not a cached satisfiability bit from save time; `format`'s absence is now correctly flagged. This is the critical P6 case: nothing about `save_stage_selection`/`get_stage_selections` should record or trust a "was satisfiable when saved" bit. | `test_preflight_reevaluates_live_disk_state_not_cached_from_save_time` |
| B.9 | *(Gap-driven addition, not in the required list — see Gap E.6)* Single stage with **two** unmet dependency groups simultaneously | Selection = `{overview}` only, nothing checked or on disk (same setup as B.5c, but assertion targets the *message format* rather than block/proceed). | Message body contains **two separate bullets**, both naming `overview` (`Overview Post`) as `stage_label`, each with a *different* `missing_description`/`upstream_label` (one for the abstract OR-group, one for e.g. `SUFFIX_KEY_TERMS`) — proves SS.15's "one bullet per unmet group" (not "one bullet per unmet stage") is actually implemented, since SS.15's own given test never exercises a single stage with multiple unmet groups. | `test_preflight_message_two_bullets_same_stage_multiple_unmet_groups` |

---

## C. Dirty-state / persistence tests (P8) for `runtime_settings.json` selections

Beyond SS.4's clean round-trip, these simulate "the code changed which stages
exist since this file was last written" — a realistic second-run scenario
this repo's P8 pattern specifically targets, and one SS.6/SS.13/SS.20 do not
fully address as written.

1. **`test_get_stage_selections_survives_unknown_stage_key`**
   (`tests/test_stage_selection_persistence.py`) — Pre-seed
   `runtime_settings.json` with `"stage_selections": {"Old Combo":
   {"stages": ["val_headers", "retired_stage_key"], "include_bowen_core":
   true, "include_emphasis_core": true}}` (simulating a selection saved
   before a stage was renamed/removed). Call `config.get_stage_selections()`
   and assert it does **not** raise — it should return the raw persisted
   data (persistence layer has no knowledge of `STAGE_DEFINITIONS`, which
   lives in `ts_gui.py`, so filtering can't happen here).

2. **`test_apply_stage_selection_skips_stage_keys_not_in_stage_definitions`**
   (`tests/test_ts_gui_run_all.py`) — With the same "Old Combo" selection
   loaded, call `gui._apply_stage_selection("Old Combo")` against a real
   (current) `STAGE_DEFINITIONS`. Assert: (a) no `KeyError`/`AttributeError`
   from indexing `self.stage_vars["retired_stage_key"]`, (b)
   `stage_vars["val_headers"]` is set `True`, (c) the retired key is simply
   absent from `stage_vars` (never added), (d) a log line notes the skipped
   key (P2 — surface, don't silently drop; use `gui.log` as the mocked sink
   to assert on).

3. **`test_apply_default_stage_selection_handles_selection_reduced_to_empty_after_filtering`**
   (`tests/test_ts_gui_run_all.py`) — `default_stage_selection` points at a
   selection whose *entire* stage list is now-unknown keys (worse than
   SS.20's existing "stale name" test, which covers a deleted *selection*,
   not a selection whose *content* has fully rotted). Assert startup leaves
   all `stage_vars` `False` and does not crash — equivalent behavior to "no
   default set," not an exception.

4. **`test_default_stage_selection_pointer_survives_unrelated_stage_definition_change`**
   (`tests/test_stage_selection_persistence.py`) — `default_stage_selection
   = "Old Combo"` and `"Old Combo"` still exists in `stage_selections` (only
   its *contents* are partly stale, per case 1). Assert
   `get_default_stage_selection()` still returns `"Old Combo"` — the default
   pointer itself is a name-existence question, orthogonal to whether the
   named selection's stage list is fully valid; that validity question is
   `_apply_stage_selection`'s problem (case 2/3), not
   `get_default_stage_selection`'s.

**Flag back to the code spec:** SS.6 and SS.13 do not currently state what
`_apply_stage_selection` should do when a saved selection references a key
absent from the live `STAGE_DEFINITIONS`. Recommend an explicit addition:
*"`_apply_stage_selection` ignores any stage key in the saved selection that
is not present in `STAGE_DEFINITIONS`, logging one line per skipped key; it
never raises."* Without this sentence, an implementer could reasonably
choose to `KeyError` on `self.stage_vars[key] = ...` for an unknown key,
which — per this repo's P8 pattern — will only surface in production after a
future stage rename/removal, not in initial testing against a fresh
`runtime_settings.json`.

Also flag: SS.13's `_apply_stage_selection` restoring
`include_bowen_core`/`include_emphasis_core` should specify the fallback
when a saved selection predates those keys being added to the persisted
schema (test #3 in the SS.13 traceability row) — recommend defaulting to
`True`/`True` (matching SS.1's own default parameter values) rather than
`False`/`False` or leaving them unchanged, for consistency with what
`save_stage_selection`'s defaults would have produced had they been present.

---

## D. Manual/human-verify test scripts

### D.1 — SS.18: Selection Manager dialog

Precondition: app launched against a scratch `TRANSCRIPTS_DIR` (a temp
folder, not a real project directory) so `runtime_settings.json` writes are
disposable; a transcript file is selected in the file list.

1. Click **"Manage Selections..."**.
   *Expect:* a `Toplevel` window opens with an empty (or pre-existing)
   `Listbox`, and "Load"/"Set as Default"/"Delete" are disabled or no-op
   with nothing selected (verify no crash on clicking them with an empty
   list-selection).
2. Close the dialog. Back in the main window, check **Format** and **Val
   Headers** only. Reopen **Manage Selections...** → click **"Save Current
   As..."** → type `QA Test 1` → confirm.
   *Expect:* dialog closes/returns; `QA Test 1` now appears in the Listbox,
   unprefixed (not yet default).
3. Uncheck all checkboxes in the main window. Reopen the dialog, select `QA
   Test 1`, click **"Load"**.
   *Expect:* dialog may close or stay open per implementation; main window's
   **Format** and **Val Headers** checkboxes are re-ticked, all others
   remain unticked; the label bound to `active_selection_var` reads `QA Test
   1`.
4. With `QA Test 1` selected in the Listbox, click **"Set as Default"**.
   *Expect:* the Listbox entry re-renders as `★ QA Test 1`.
5. Click **"Save Current As..."** again, type `QA Test 1` (the existing
   name) with the same or different checkbox state.
   *Expect:* an overwrite-confirmation dialog (`messagebox.askyesno`)
   appears; confirm **No** first and verify the original selection's
   contents are unchanged (reload it and check); repeat and confirm **Yes**,
   verify the new checkbox state is now saved under the same name.
6. Click **"Clear Default"**.
   *Expect:* the `★ ` prefix disappears from `QA Test 1` in the Listbox.
7. Select `QA Test 1`, click **"Delete"**, confirm any prompt.
   *Expect:* entry removed from the Listbox; `active_selection_var` in the
   main window resets to `(none)` if it was still showing `QA Test 1`.
8. Click **"Close"**.
   *Expect:* dialog closes cleanly, no residual Toplevel window, main window
   remains responsive.

### D.2 — SS.21: End-to-end integration smoke test (spans two app restarts)

Precondition: scratch `TRANSCRIPTS_DIR`, a valid raw transcript file
selected, real (or throwaway-key) API access available for the one live
run in step 3.

1. Launch the app. Confirm no checkboxes are pre-ticked (no default set
   yet) and `active_selection_var` reads `(none)`.
2. Check **only** "Format" and "Gen Abstract". Click **"▶ Run Selected"**.
   *Expect:* a `messagebox.showwarning` titled `"Missing Prerequisites"`
   appears **before** any confirmation/cost dialog, naming `Gen Abstract`'s
   unmet dependency on `Core` (since `Core` isn't checked and no prior
   `Core` artifacts exist for this file). No processing indicator activates;
   no API call is made (verify via absence of new log lines / network
   activity if observable).
3. Additionally check **"Core"** (now `{Format, Core, Gen Abstract}`
   checked). Click **"▶ Run Selected"** again.
   *Expect:* pre-flight passes silently; the confirmation dialog appears
   listing all three stage labels; confirm; the run proceeds through all
   three stages and completes successfully (status/log shows completion,
   `processing` returns to `False`, checkboxes re-enable).
4. Open **"Manage Selections..."**, save the current 3-stage combo as `QA
   E2E`. Close the dialog.
5. **Quit the application entirely** (not just close the window if they
   differ — ensure the process exits).
6. **Relaunch the application** against the same scratch
   `TRANSCRIPTS_DIR`.
   *Expect:* no default is set yet, so all checkboxes are unticked on this
   launch (proves persistence of the *saved selection* without an implied
   default).
7. Open **"Manage Selections..."**, select `QA E2E`, click **"Set as
   Default"**. Close the dialog.
8. **Quit the application again.**
9. **Relaunch the application** a second time.
   *Expect:* `Format`, `Core`, and `Gen Abstract` checkboxes are pre-ticked
   automatically on startup, `active_selection_var` shows `QA E2E`, **and**
   no confirmation dialog, cost estimate, processing indicator, or log line
   indicating a pipeline call appears — the pipeline must **not**
   auto-run just because a default pre-ticked it. Manually verify by
   watching the log pane for at least a few seconds after launch with no
   stage-related log lines appearing.

---

## E. Gaps found in the code spec itself

1. **[Highest priority] SS.5 and SS.7's hardcoded "12" is arithmetically
   wrong against the spec's own §2 table, which has 13 rows.** Direct count
   of the stage table (`init_val, format, val_headers, yaml, core,
   structured_summary, gen_abstract, val_abstract, blog, overview, webpdf,
   bowen_emphasis, package`) = 13, and the §2.1 compact dependency graph
   independently lists the same 13 keys. `structured_summary` is a
   genuinely new 13th stage introduced by this plan (superseding
   `omit_summary_do_all`, per §2's closing note) — it is not a stray
   leftover. But SS.5 says *"defines module-level `STAGE_DEFINITIONS` =
   [...] in the 12-row order from §2"* and SS.7 says *"12 matches, one per
   `STAGE_DEFINITIONS` key"* — both should say 13. Cross-checking SS.12's
   count (9 new `_run_stage_*` wrappers for `yaml, core, structured_summary,
   gen_abstract, val_abstract, blog, overview, bowen_emphasis, package` +
   the 4 reused-method stages `init_val, format, val_headers, webpdf` = 13)
   confirms SS.12 already correctly assumes 13 stages — only SS.5 and SS.7's
   literal counts are stale, most likely because they were written before
   `structured_summary` was folded into the stage table. **Impact if
   unfixed:** an implementer following SS.7's literal grep count could
   "fix" a passing-count test by dropping `structured_summary`'s checkbox,
   silently reintroducing the exact `omit_summary_do_all` gap this plan
   claims to close (§2's closing note explicitly says `structured_summary`
   supersedes it). Recommend the fix be to make both tests derive their
   expected count from `len(STAGE_DEFINITIONS)` or a written-out list of the
   13 keys, never a bare literal `12`/`13`, so a future 14th-stage addition
   can't cause the same drift again (this is itself a P4-style "magic
   constant" bug, ironically inside a spec about avoiding hardcoded
   assumptions).

2. **SS.15's "one bullet line per unmet requirement group" is ambiguous
   about whether a single stage with multiple unmet groups produces
   multiple bullets naming the same stage, and the given test never
   exercises this case.** `overview` has four dependency groups (abstract
   OR-group + three single-artifact groups); a run that checks only
   `overview` with nothing else checked or on disk should — by SS.14's
   literal wording ("For each unmet group ... it records") — produce *four*
   `(stage_label, missing_description)` records, hence four bullets all
   reading `"Overview Post needs ..."` with different missing-artifact
   names. SS.15's own test only ever exercises two *different* stages each
   with one unmet group, so this multi-bullet-same-stage behavior is
   unverified and its exact wording (does "Overview Post" appear once with
   a combined description, or once per bullet?) is left to implementer
   discretion despite SS.15 claiming an exact, verbatim message format.
   Recommend resolving explicitly in the spec and adding the test proposed
   as B.9 above.

3. **No criterion tests that `self.base_name` (used to build the on-disk
   artifact path in SS.14: `config.PROJECTS_DIR / self.base_name /
   f"{self.base_name}{suffix}"`) matches the actual directory-naming
   convention the pipeline stages use to *write* those artifacts.** If
   `base_name` derivation differs even slightly between the pre-flight
   validator and the actual pipeline write path (e.g. one strips a
   `_validated` suffix or trailing whitespace and the other doesn't, or a
   filename containing the literal substring `" - "` — which is also the
   suffix separator used throughout `config.py`'s `SUFFIX_*` constants —
   causes ambiguous parsing), the validator would systematically false-block
   every run for that file, or worse, systematically false-negative (never
   detect a real missing artifact) if the path it checks is simply wrong in
   a way that never resolves to an existing path either way. This is a P6
   "trust the derived field, not the ground truth" risk sitting at the core
   of the new feature, and it has no explicit test anywhere in SS.1-SS.22.
   Recommend an explicit test asserting the pre-flight validator's artifact
   path construction is byte-identical to whatever helper the actual
   `_run_stage_*` wrappers/pipeline functions use to locate/write that same
   file (ideally by having both call one shared path-builder function,
   which itself would be worth promoting to `config.py` or
   `transcript_utils.py` rather than being reimplemented in the validator).

4. **Guard-order precedence (SS.10) is asserted only by isolated single-guard
   tests, never by a "two guards would both fire" case** — flagged already
   in the traceability table (SS.10 row) and Section A. Worth restating
   here because it's a P13-adjacent risk ("guard applied/ordered wrong"):
   the spec's own verification method for guard *order* doesn't actually
   test order.

5. **SS.13 and the persisted selection schema don't state a migration
   policy for `include_bowen_core`/`include_emphasis_core` on
   older-format saved selections** (elaborated in Section C's "flag back"
   note) — a real P8 second-run scenario once any user has saved a
   selection under a pre-upgrade schema.

6. **SS.20's "still present in `get_stage_selections()`" check for staleness
   only covers a deleted selection *name*, not a selection whose *contents*
   have partially rotted** (a subset of its stage keys no longer exist in
   `STAGE_DEFINITIONS`) — elaborated in Section C, items 2-3. This is the
   more realistic P8 scenario (a stage renamed/removed in a later release)
   than the full-deletion case SS.20 already tests.

7. **No acceptance criterion addresses what happens if two different
   `STAGE_DEPENDENCIES` groups for the *same stage* reference the *same*
   producing stage with different artifacts, and that producing stage
   partially fails** (e.g., in a real run, could `core` ever produce
   `SUFFIX_TOPICS` but not `SUFFIX_INTERPRETIVE_THEMES`, satisfying
   `structured_summary`'s pre-flight check but not `gen_abstract`'s, then
   have `gen_abstract` fail deep inside the pipeline anyway even though
   pre-flight said "core is checked, proceed")? SS.11's "halt on first
   `False`" behavior covers this at the *execution* level (gen_abstract
   simply won't run if core returns `False` first), but it's worth an
   explicit note in the spec that pre-flight satisfiability-by-"producer is
   checked" is inherently optimistic — it does not (and cannot) guarantee
   the producer *succeeds*, only that it will be attempted first. This is
   implied by SS.11 but never stated as an explicit limitation of the
   pre-flight validator's guarantee, and a user reading only SS.14-SS.17
   could reasonably believe "pre-flight passed" means "this run cannot
   fail," which is false. Recommend a one-line clarifying note in §2/SS.14.

---

## Summary of test counts

- Section A (traceability): 22 SS.N rows; ~34 distinct test function names
  across existing-and-sufficient, existing-and-strengthened, and net-new
  tests.
- Section B (pre-flight adversarial): 11 test functions across 9 scenario
  groups (required 8 + 1 gap-driven addition, B.9).
- Section C (dirty-state persistence): 4 test functions.
- Section D (manual): 2 numbered scripts (8 steps + 9 steps).
- Section E (spec gaps): 7 findings, headlined by the 12-vs-13 stage-count
  inconsistency (E.1).
