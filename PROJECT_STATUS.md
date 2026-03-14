# Project Status Report

**Last Updated:** 2026-03-10  
**Status:** Active maintenance / production workflow available

## Current Snapshot

- Core architecture is pipeline-driven and modular (`pipeline.py` facade with formatting/extraction/validation/rendering modules).
- GUI and CLI entry points are both present and functional:
  - GUI: `ts_gui.py`
  - Interactive CLI: `transcript_process.py`
  - Stage-specific CLIs: `transcript_*.py`
- Security and reliability controls introduced in the January quality initiative remain in place:
  - filename sanitization/path-traversal defense
  - API retry and response validation
  - config validation and directory checks
  - Jinja2 template-based HTML generation

## Effective Runtime Defaults (from `config.py`)

- `DEFAULT_MODEL`: `claude-sonnet-4-20250514`
- `AUX_MODEL`: `claude-3-5-haiku-20241022`
- `FORMATTING_MODEL`: `claude-3-7-sonnet-20250219`
- `DEFAULT_SUMMARY_WORD_COUNT`: `650`
- Data roots derived from `TRANSCRIPTS_BASE`:
  - `source/`
  - `projects/`
  - `processed/`

## Pipeline Artifact State

Current artifact naming is config-driven and centered on:

- ` - formatted.md`
- ` - yaml.md`
- ` - structural-themes.md`
- ` - interpretive-themes.md`
- ` - topics.md`
- ` - key-terms.md`
- ` - lenses-ranked.md`
- ` - bowen-references.md`
- ` - emphasis-items.md`
- ` - emphasis-scored.md`
- ` - summary-generated.md` + ` - summary-validation.txt`
- ` - abstract-generated.md` + ` - abstract-validation.txt`
- `.html`, ` - simple.html`, `.pdf`, `.zip`

See `DOCUMENT_REFERENCE.md` for the full matrix and stage mapping.

Structured summary/abstract generation now accepts either of the persisted transcript artifacts in a project folder:

- preferred: ` - formatted.md`
- fallback: ` - yaml.md`

Initial transcript validation also now has persistent review memory:

- rejected suggestion pairs can be promoted into `logs/validation_memory.json` and suppressed on future reruns
- approved terms/phrases are stored in `approve_terms.txt` under `TRANSCRIPTS_BASE`
- `approve_terms.txt` also supports `wrong = Correct` alias entries for deterministic validation findings and replacements
- validation scope is now transcription-only for this domain corpus: proper nouns, homophones, misspellings/non-words, and word-boundary issues
- the review UI is compact and approval-biased: approved items are checked by default and automatically enrich the dictionary

## Testing Status (2026-02-10)

- `pytest --collect-only -q` discovered 164 tests but ended with 3 collection errors caused by duplicate module names between root-level tests and `tests/` package files.
- This is a test-layout hygiene issue (import file mismatch), not a runtime pipeline crash.
- Recommended immediate cleanup:
  1. Eliminate duplicate test module basenames across root and `tests/`.
  2. Keep a single canonical location for each test module.
  3. Re-run `pytest --collect-only -q` and then full `pytest`.

## Known Documentation Alignment Notes

- Historical docs/changelog entries reference different model defaults across dates; the effective current defaults are those listed above from `config.py`.
- Historical metrics (for example fixed pass counts/coverage percentages) should be treated as point-in-time snapshots unless regenerated in current CI.
