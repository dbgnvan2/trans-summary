# Document Reference Guide

This guide reflects the current artifact set produced by the transcript processing pipeline as of 2026-02-10.

## Base Path and Naming

- All data paths are derived from `config.TRANSCRIPTS_BASE` (default: current project directory, overridable with `TRANSCRIPTS_DIR` or GUI directory selection).
- Source inputs live in `TRANSCRIPTS_BASE/source/`.
- Per-transcript artifacts live in `TRANSCRIPTS_BASE/projects/<Base Name>/`.
- `<Base Name>` follows `Title - Presenter - Date`.

## Artifact Matrix

| Artifact | Filename Pattern | Contains | Producer |
| --- | --- | --- | --- |
| Source transcript | `<Base Name>.txt` | Raw transcript text | external transcription input |
| Formatted transcript | `<Base Name> - formatted.md` | Cleaned/structured transcript | `formatting_pipeline.format_transcript` |
| YAML transcript | `<Base Name> - yaml.md` | Formatted transcript + YAML front matter | `formatting_pipeline.add_yaml` |
| Structural Themes | `<Base Name> - structural-themes.md` | Overarching structural themes grounded in transcript | `extraction_pipeline.summarize_transcript` |
| Interpretive Themes | `<Base Name> - interpretive-themes.md` | Interpretive themes grounded in transcript | `extraction_pipeline.summarize_transcript` |
| Topics | `<Base Name> - topics.md` | Topic objects with coverage metadata | `extraction_pipeline.summarize_transcript` |
| Ranked Lenses | `<Base Name> - lenses-ranked.md` | Ranked lenses (top lens used for blog generation) | `extraction_pipeline.summarize_transcript` |
| Key Terms | `<Base Name> - key-terms.md` | Term-focused extract (if generated in flow) | `extraction_pipeline` |
| Bowen references | `<Base Name> - bowen-references.md` | Filtered explicit Bowen references | `extraction_pipeline.extract_bowen_references_from_transcript` |
| Emphasis items | `<Base Name> - emphasis-items.md` | Emphasis quotes and labels | `extraction_pipeline.extract_scored_emphasis` |
| Emphasis (scored) | `<Base Name> - emphasis-scored.md` | Scored emphasis items | `extraction_pipeline.extract_scored_emphasis` |
| Blog post | `<Base Name> - blog.md` | Blog-style adaptation | `extraction_pipeline.summarize_transcript` |
| Structured summary | `<Base Name> - summary-generated.md` | Long-form structured summary | `extraction_pipeline.generate_structured_summary` |
| Summary validation report | `<Base Name> - summary-validation.txt` | Coverage/structure validation report | `validation_pipeline.validate_summary_coverage` |
| Structured abstract | `<Base Name> - abstract-generated.md` | Structured abstract | `extraction_pipeline.generate_structured_abstract` |
| Abstract validation report | `<Base Name> - abstract-validation.txt` | Coverage/structure validation report | `validation_pipeline.validate_abstract_coverage` |
| Header validation report | `<Base Name> - header-validation.md` | Header quality report | `validation_pipeline.validate_headers` |
| Full webpage | `<Base Name>.html` | Sidebar layout with transcript + extracted content | `html_generator.generate_webpage` |
| Simple webpage | `<Base Name> - simple.html` | Single-column webpage | `html_generator.generate_simple_webpage` |
| PDF | `<Base Name>.pdf` | Print-ready PDF | `html_generator.generate_pdf` |
| Package | `<Base Name>.zip` | Bundled final artifacts | `packaging_pipeline.package_transcript` |

## Current Pipeline Stages

1. Initial transcript validation (optional/manual stage in GUI/CLI workflows).
2. Formatting (`format_transcript`) -> ` - formatted.md`
3. Format validation (`validate_format`) checks word-preservation fidelity.
4. Header validation (`validate_headers`) -> ` - header-validation.md`
5. YAML front matter (`add_yaml`) -> ` - yaml.md`
6. Core extraction (`summarize_transcript`) -> structural themes, interpretive themes, topics, key terms, ranked lenses, Bowen, emphasis, blog outputs.
7. Structured generation (optional flag/GUI flow):
   - `generate_structured_summary` -> ` - summary-generated.md`
   - `generate_structured_abstract` -> ` - abstract-generated.md`
8. Structured validation:
   - `validate_summary_coverage` -> ` - summary-validation.txt`
   - `validate_abstract_coverage` -> ` - abstract-validation.txt`
9. Rendering:
   - `generate_webpage` -> `.html`
   - `generate_simple_webpage` -> ` - simple.html`
   - `generate_pdf` -> `.pdf`
10. Packaging (`package_transcript`) -> `.zip`

## Notes

- Webpage/PDF generation loads generated artifacts directly from dedicated one-artifact-per-output files.
- Bowen and emphasis items are both used for transcript highlighting in HTML/PDF.
- Legacy paths like `~/transcripts/...` are no longer the canonical default; use `config.TRANSCRIPTS_BASE`-derived directories.
