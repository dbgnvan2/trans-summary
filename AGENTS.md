# AGENTS.md

This file gives repo-specific guidance to coding agents working in this project.

## Scope

- Applies to the entire repository unless a deeper `AGENTS.md` overrides it.

## Primary Goal

- Make minimal, targeted changes.
- Prefer fixing the requested behavior at the correct integration point over broad refactors.
- Do not treat this repo as a greenfield rewrite.

## Where To Look First

For most feature and bug work, inspect these files before scanning the wider repo:

- `ts_gui.py` — Tkinter GUI and button wiring
- `pipeline.py` — public orchestration facade
- `extraction_pipeline.py` — summaries, Bowen, emphasis, abstract generation
- `formatting_pipeline.py` — formatting and YAML-related flow inputs
- `validation_pipeline.py` — validation entry points
- `config.py` — suffixes, directories, prompt filenames, model defaults
- `transcript_utils.py` — shared helpers for file resolution, naming, logging, API calls

Useful architecture references:

- `README.md`
- `DOCUMENT_REFERENCE.md`
- `ARCHITECTURE_DESIGN.md`

## Files Usually Not Worth Reading First

Avoid broad exploration unless the task clearly requires it:

- `oldfiles/`
- historical fix notes such as `*_FIX*.md`, `*_SUMMARY*.md`, `ISSUE_*.md`
- large review documents unless the task is documentation or architecture-oriented

## Repo Conventions

- The GUI is an orchestrator; keep business logic in pipeline modules where practical.
- `pipeline.py` is a facade layer; preserve public exports unless intentionally changing external behavior.
- Artifact names and locations are controlled by `config.py` suffix constants and `PROJECTS_DIR` / `SOURCE_DIR`.
- Prefer `clean_project_name()` and existing filename helpers instead of ad hoc stem parsing.
- For transcript-derived outputs, preserve existing file naming conventions.

## GUI Change Guidance

- For GUI requests, change `ts_gui.py` first and only touch backend modules needed to support the requested behavior.
- Keep UI changes small and consistent with existing button/checkbox patterns.
- If a GUI action maps to an existing pipeline function, reuse it instead of duplicating logic.

## Extraction Flow Notes

- Core extraction logic lives in `extraction_pipeline.summarize_transcript()`.
- Standalone extraction entry points exist for Bowen and emphasis:
  - `extract_bowen_references_from_transcript()`
  - `extract_scored_emphasis()`
- Artifact expectations are documented in `DOCUMENT_REFERENCE.md`.

## Testing Guidance

- Run focused tests first, not the entire suite.
- Prefer targeted commands such as:
  - `pytest tests/test_extraction_resilience.py -q`
  - `pytest tests/test_separate_extraction_steps.py -q`
- For syntax-only checks on touched files, use:
  - `python -m py_compile <files>`
- Do not fix unrelated failing tests as part of a narrow task.

## Documentation Guidance

- Only update docs when the user asks, or when behavior/user workflow has clearly changed.
- For user-facing behavior changes, update the minimum relevant docs first:
  - `README.md`
  - `ARCHITECTURE_DESIGN.md`
  - `CHANGELOG.md`

## Token / Exploration Discipline

- Do not “review the whole repo” unless the user explicitly asks for a broad audit.
- Prefer targeted `rg` searches and reading only the relevant functions/sections.
- Before making large doc or test sweeps, confirm they are necessary for the request.

## Refactoring Bias

- This repo includes some large files, especially `ts_gui.py`.
- Do not perform opportunistic refactors during narrow feature work.
- If a file is hard to modify cleanly, make the smallest safe change and optionally note refactor opportunities separately.
