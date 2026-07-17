# Spec: MD-collection bundle export (DOCX / PDF)

**Date:** 2026-07-16
**Plan:** `docs/bundle_export_plan.md` (approved)
**Module:** `bundle_export.py` · **CLI:** `transcript_bundle.py`

## Summary

Package a run's per-stage Markdown artifacts into a single **DOCX** and/or **PDF**
as a plain concatenation with section headers. DOCX is rendered with pandoc
(external binary); PDF reuses the project's `markdown_to_html` + WeasyPrint, so
both formats derive from the same combined Markdown. Google Doc export deferred.

## Acceptance criteria

| ID | Criterion | Test |
|---|---|---|
| BE.1 | `export_bundle(base_name, fmt="docx"\|"pdf"\|"both", logger=None) -> bool` returns True only if every requested format was produced. An invalid `fmt` returns False before any work (and before the gate). | `tests/test_bundle_export.py::test_be_invalid_fmt_rejected_before_gate` |
| BE.2 | `_build_combined_markdown` concatenates the `config.BUNDLE_SECTIONS` in configured order, each under its heading. Each section names a `key`, `heading`, and `suffix_attrs` (an ordered candidate list — the first artifact that exists AND is non-empty is used, so the transcript is the Formatted **or** YAML file, whichever is present). Sections/order/headings live in config (editorial data, not code). | `::test_be2_combines_sections_in_config_order` |
| BE.3 | A missing OPTIONAL section is skipped and surfaced, not silently dropped: `export_bundle` logs "N of M included" and names the skipped section (P2). A section artifact that exists but strips to empty is content drift (P19): excluded (not shipped blank) and surfaced via `empty_present`; an empty REQUIRED section is fatal. Frontmatter is stripped only where declared (`strip_frontmatter`), so a `---…---` divider in another section body is preserved. | `::test_be3_missing_optional_surfaced_not_silent`, `::test_be3_export_logs_n_of_m`, `::test_be3_present_but_empty_section_excluded_not_shipped_blank`, `::test_be3_present_but_empty_required_is_fatal` |
| BE.4 | A missing REQUIRED section (or no sections found at all) is an honest failure: returns False and renders nothing. | `::test_be4_missing_required_aborts_before_render`, `::test_be4_all_missing_returns_false` |
| BE.5 | Fails closed on a release-gate BLOCK — no bundle produced (parity with `generate_pdf`/`package_transcript`). Bundle artifacts are in `PUBLISHED_BUNDLE_SUFFIXES`, so a later BLOCK quarantines a stale bundle (F4). | `::test_be5_fails_closed_on_block` |
| BE.6 | DOCX via pandoc, hardened (P5): bounded `timeout`; a missing pandoc binary, a timeout, and a non-zero exit each return False with a clear error and leave no partial file. | `::test_be6_docx_invokes_pandoc`, `::test_be6_pandoc_missing_reports_error_no_partial_file`, `::test_be6_pandoc_nonzero_exit_cleans_partial` |
| BE.7 | PDF via WeasyPrint from the same combined Markdown. | `::test_be7_pdf_written_via_weasyprint` |
| BE.8 | CLI `transcript_bundle.py` resolves a base name by stripping known extensions/suffixes (mirrors `transcript_to_pdf.py`). | `::test_be8_cli_resolve_base_name_strips_suffixes` |
| BE.9 | **Post-run dialog.** A "Create Bundle (DOC/PDF)…" button opens a dialog with a checkbox per section and a PDF/DOCX/both format choice; `export_bundle`/`_build_combined_markdown` accept a `sections` subset so only the ticked sections are included. `_run_bundle_export` runs it on a background thread; empty selection warns and does nothing. Default format `config.BUNDLE_DEFAULT_FORMAT` = "pdf". | `::test_be9_build_markdown_honors_section_subset`, `::test_be9_run_bundle_export_builds_subset_and_threads`, `::test_be9_run_bundle_export_no_sections_warns`, `::test_be9_dialog_builds_section_and_format_controls` |
| BE.10 | **Run-stage.** A `bundle` pipeline stage (`STAGE_DEFINITIONS`, deps on formatted/yaml) runs the bundle during a run using the default format + all configured sections. `STAGE_OUTPUTS["bundle"]` is derived from `BUNDLE_DEFAULT_FORMAT` (not a second literal) so the "exists" status can't drift (P4/P19). | `::test_be10_run_stage_bundle_uses_default_format`, `::test_be10_stage_outputs_bundle_tracks_default_format`, `tests/test_ts_gui_run_all.py::test_stage_definitions_order` |

**Note on `required` in the dialog (BE.9):** `required` (the YAML transcript) is
enforced for the full-run stage and whenever a section is *selected but missing on
disk*. The post-run dialog honors explicit user selection: unchecking the
Transcript is allowed (the user may want e.g. Topics + Summary only), so `required`
does not force-include it there.

## Not code-tested (flagged)

- The **real pandoc invocation** is an external-binary integration path. Unit
  tests mock `subprocess.run`; the live pandoc call is integration-only, not
  implied-covered. pandoc **is installed** on this machine (pandoc 3.10, via
  `brew install pandoc`) and a real `fmt="both"` export was smoke-tested to
  produce both ` - bundle.pdf` and ` - bundle.docx` (2026-07-16).

## Config (single source)

- `SUFFIX_BUNDLE_DOCX = " - bundle.docx"`, `SUFFIX_BUNDLE_PDF = " - bundle.pdf"`
  (distinct from the designed `.pdf`/`.html` so the plain-concat bundle never
  clobbers them); both added to `PUBLISHED_BUNDLE_SUFFIXES`.
- `BUNDLE_SECTIONS`: ordered `[{key, heading, suffix_attrs, required, strip_frontmatter?}]`.
  Default: Transcript (Format **or** YAML, required) → Topics → Emphasis →
  Bowen References → Abstract.

## Adjacent (not fixed, per rule #10)

- `package_transcript` zips the rendered web/pdf + transcript, not the new
  bundle or the individual MD files. Whether the zip should include the bundle
  is a separate decision — flagged, not changed.
