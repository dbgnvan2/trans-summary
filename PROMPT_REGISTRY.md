# Prompt Registry

Last updated: 2026-02-10

This registry maps prompt markdown files to the code paths that load them at runtime.

## Active Runtime Prompts

| Prompt File | Config Key | Used By |
| --- | --- | --- |
| `prompts/Transcript Formatting Prompt v12-Lite.md` | `PROMPT_FORMATTING_FILENAME` | `formatting_pipeline.py` |
| `prompts/Transcript Formatting Headers Validation Prompt 12.md` | `PROMPT_FORMATTING_HEADER_VALIDATION_FILENAME` | `validation_pipeline.py`, `transcript_validate_headers.py` |
| `prompts/problematic_header_terms_v2.md` | `PROMPT_PROBLEMATIC_HEADER_TERMS_FILENAME` | `transcript_validate_headers.py` |
| `prompts/Transcript Summary Key Items v1.md` | `PROMPT_EXTRACTS_FILENAME` | `extraction_pipeline.py` |
| `prompts/Transcript Summary Blog Post v1.md` | `PROMPT_BLOG_FILENAME` | `extraction_pipeline.py` |
| `prompts/emphasis_dedection_v3_production.md` | `PROMPT_EMPHASIS_SCORING_FILENAME` | `extraction_pipeline.py` |
| `prompts/bowen_reference_extraction_v1.md` | `PROMPT_BOWEN_EXTRACTION_FILENAME` | `extraction_pipeline.py`, `transcript_extract_bowen.py` |
| `prompts/bowen_reference_filter_v1.md` | `PROMPT_BOWEN_FILTER_FILENAME` | `extraction_pipeline.py` |
| `prompts/Summary Generation Prompt v1.md` | `PROMPT_STRUCTURED_SUMMARY_FILENAME` | `summary_pipeline.py` |
| `prompts/Abstract Generation Prompt v1.md` | `PROMPT_STRUCTURED_ABSTRACT_FILENAME` | `abstract_pipeline.py` |
| `prompts/Validation Coverage Prompt v1.md` | `PROMPT_VALIDATION_COVERAGE_FILENAME` | `summary_validation.py`, `abstract_validation.py` |
| `prompts/abstract_quality_assessment_prompt_v2.md` | `PROMPT_ABSTRACT_VALIDATION_FILENAME` | `validation_pipeline.py` (legacy abstract validation path) |
| `prompts/transcript_error_detection_prompt.md` | direct path | `transcript_initial_validation.py` |
| `prompts/transcript_error_detection_prompt_v2.md` | direct path | `transcript_initial_validation_v2.py` |

## Utility/Optional Prompts

| Prompt File | Config Key | Used By |
| --- | --- | --- |
| `prompts/Transcript Summary Key Terms v1.md` | `PROMPT_KEY_TERMS_FILENAME` | `transcript_extract_terms.py` |
| `prompts/Transcript Voice Audit Prompt v1.md` | `PROMPT_VOICE_AUDIT_FILENAME` | `transcript_audit_voice.py` |

## Archived (Unused) Prompts

These files are currently not referenced by runtime code and have been moved to:
`prompts/old prompts/`

- `emphasis_detection_master_criteria_v1.md`
- `emphasis_detection_prompt_condensed.md`
- `emphasis_detection_prompt_v3.md`
- `problematic_header_terms v1.md`

## Design Note

Prompt templates are loaded from disk at runtime (`read_text(...)`), so updates to active `.md` prompt files take effect without rebuilding the codebase.
