# Plan: MD-collection export to DOCX / PDF (bundle export)

**Status:** BUILT (2026-07-16). See `docs/spec_bundle_export_2026-07-16.md` for the
implemented acceptance criteria → tests. Module: `bundle_export.py`; CLI:
`transcript_bundle.py`.

## Goal

Add an option to package the Markdown artifacts produced for a run into a single
**DOCX** and/or **PDF** document (Google Doc deferred). Content model chosen by the
user: **plain concatenation of the raw MD files** with section-header dividers
(not the existing designed/highlighted PDF layout). DOCX engine: **Pandoc**.

## Decisions (locked)

- Content model: **plain MD concatenation** (section headers between files).
- DOCX engine: **Pandoc** (external binary). PDF stays on WeasyPrint (already a dep).
- Google Doc export: **deferred** (get later for free by uploading the .docx to Drive).

## Design

One new module `bundle_export.py` exposing:

    export_bundle(base_name, fmt="pdf" | "docx" | "both", logger=None) -> bool

It builds **one combined Markdown string** from a config-driven, ordered section
list, then renders:

- **DOCX** -> pandoc via subprocess (hardened: timeout, check, captured stderr,
  explicit "pandoc not installed" message mirroring the existing WeasyPrint guard).
- **PDF**  -> reuse existing `markdown_to_html` + WeasyPrint (no new dep; keeps the
  plain-concat PDF consistent with the DOCX from the same source).

Both formats derive from the **same combined-MD builder**, so they never drift.

## Files to change

| File | Change |
|---|---|
| `config.py` | Add `BUNDLE_SECTIONS` (ordered list of `{suffix, heading, required}` — editorial content in config), plus `SUFFIX_BUNDLE_DOCX = " - bundle.docx"` and `SUFFIX_BUNDLE_PDF = " - bundle.pdf"` (distinct from the existing designed `.pdf` so they do not clobber it). |
| `bundle_export.py` *(new)* | `export_bundle(...)`, `_build_combined_markdown(...)`, `_render_docx_pandoc(...)`, `_render_pdf_weasyprint(...)`. Reuses `strip_yaml_frontmatter`, `load_project_transcript`, `markdown_to_html`. Gated by `release_gate.publish_allowed` (fail-closed, like the other exporters). |
| `transcript_bundle.py` *(new CLI)* | `python transcript_bundle.py "<base>" --format docx\|pdf\|both`; reuses the `resolve_base_name` suffix-stripping pattern. |
| `pipeline.py` | Import/export `export_bundle` in `__all__`, consistent with `generate_pdf` / `package_transcript`. |

## Default sections (from user's example; adjustable in config)

1. YAML transcript (`SUFFIX_YAML`) — heading "Transcript"
2. Topics (`SUFFIX_TOPICS`) — heading "Topics"
3. Emphasis, scored (`SUFFIX_EMPHASIS_SCORED`) — heading "Emphasis"
4. Bowen References (`SUFFIX_BOWEN`) — heading "Bowen References"
5. Summary (`SUFFIX_SUMMARY_GEN`) — heading "Summary"

Themes / key terms / abstract available as opt-in config entries. Order mirrors the
existing run-manifest ordering (`_MANIFEST_SUFFIXES`, release_gate.py).

## Robustness (project standards)

- **P2 — surface, never silently drop:** log "N of M sections included"; missing
  files counted, not silent. All-missing -> honest `False`.
- **P5 / external-api:** pandoc subprocess with `timeout`, `check`, captured
  stderr; explicit "pandoc not installed" message. No partial file left on failure.
- Fail-closed on a publish BLOCK, same as `generate_pdf` / `package_transcript`.

## Acceptance criteria -> tests (`test_bundle_export.py`)

| Criterion | Test |
|---|---|
| Sections combined in configured order | `test_bundle_combines_sections_in_config_order` (real fixture: `tests/fixtures/where_roots/...`) |
| Missing section surfaced, not silent (P2) | `test_bundle_missing_section_surfaced_not_silent` — asserts "N of M" log + builds from the rest |
| All sections missing -> honest failure | `test_bundle_all_missing_returns_false` |
| Fails closed on publish BLOCK | `test_bundle_blocked_publish_fails_closed` |
| DOCX invokes pandoc correctly | `test_bundle_docx_invokes_pandoc` (monkeypatch `subprocess.run`; **restore patch**) |
| pandoc missing -> clean error, no partial file | `test_bundle_pandoc_missing_reports_error` |
| PDF written from combined HTML | `test_bundle_pdf_written` (monkeypatch WeasyPrint `write_pdf`) |
| CLI strips suffixes | `test_resolve_base_name_strips_suffixes` |

**Cannot be unit-tested (flagged):** the *real* pandoc invocation is an
external-binary integration path — mock it in unit tests and mark the live call as
integration-only, not implied-covered.

## Setup note

DOCX requires the pandoc binary: `brew install pandoc` (system binary, not pip; not
currently installed on this machine). WeasyPrint already present.

## Adjacent issue found, not fixed (global rule #10)

`package_transcript` (packaging_pipeline.py) zips rendered artifacts but not the
individual MD files or this new bundle. Whether the zip should include the bundle is
a separate decision — flagged, not silently changed.
