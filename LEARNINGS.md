# trans-summary — failure-pattern playbook

This is the project's local failure-pattern log: how *this* pipeline tends to fail, and
the checks that stop it repeating a mistake. The generic pattern catalogue (P1–P18) lives
in `~/.claude/standards/learnings.md` and is authoritative for pattern definitions; this
file holds only the repo-specific instances, checklist items, and the fix log. Keep it lean.

## Patterns most load-bearing here

Pull from the global catalogue; the ones that bite this repo most:

- **P2 — Silent drop between pipeline stages.** A stage returns falsy on failure; a later
  stage or the caller can't tell "produced nothing" from "the call failed."
- **P5 — Sibling LLM/subprocess calls hardened inconsistently.** When one `summarize_transcript`
  / extraction call is fixed, fix every sibling wrapper and every standalone handler in the same change.
- **P6 — Trusting a status/derived path without the artifact.** Any code that decides "this stage
  already ran" must resolve the *exact* on-disk path the stage writes (`config.PROJECTS_DIR /
  base_name / f"{base_name}{SUFFIX}"`) and check it live, never a cached bit.
- **P8 — Dirty/second-run state.** `runtime_settings.json` persists between runs; loaders must
  survive unrelated keys, a stale default pointer, and stage keys removed in a later release.
- **P9 — Token/size caps in summarization** silently truncating real-scale transcripts.
- **P12 — Refactor-dropped side effect.** When collapsing an inlined pipeline into wrappers,
  every step (cost estimate, token-usage report, halt-on-failure, filename enforcement) must survive.
- **P13 — Guard at wrong scope.** A gate (e.g. the `_validated` filename check, or a pre-flight
  block) must guard exactly the steps it's meant to, and sit before `run_task_in_thread`.

## Review checklist (run before merging pipeline / GUI-run-path changes)

1. Each stage wrapper passes the *same* args/models/skip-flags as its standalone handler? (P5)
2. Any artifact-existence check resolved via the single shared path-builder, checked live? (P6)
3. Refactored run loop still does: cost estimate, halt-on-first-failure, token report, filename gate? (P12)
4. Guard chain ordered so no run can bypass the pre-flight block? (P13)
5. Persistence loaders tolerate a dirty file (unrelated keys, stale default, unknown stage keys), and *surface* dropped keys rather than silently ignoring? (P2/P8)
6. Dependency OR-groups match what the consuming stage actually reads (no false-negative that lets a doomed run start)? (P6)

## Open risks (found by review, not yet bitten)

- The `_validated` filename gate in `do_run_selected` blocks *any* selection whose source file
  lacks `_validated`, including late-only selections (package/webpdf/bowen_emphasis) that don't
  read the source file. Matches prior `do_all` behaviour and spec SS.10, so not a regression —
  but the gate is broader than the stages that actually consume the raw source file. Revisit if
  users hit spurious "run Init Val first" blocks when re-running only late stages.
- `_load_runtime_settings` resets to `{}` on corrupt JSON, but a *valid* non-dict top-level value
  (e.g. a hand-edited `[]` or string) would `AttributeError` on the first `.get`. Pre-existing,
  not introduced by the stage-selection change.

## Fix log

Newest first. Format: **Issue → Root cause (Pn) → What would have caught it → Fix → Rule.**

_(empty — no post-mortems captured yet)_
