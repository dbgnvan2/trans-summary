# Plan: small open TODO items (N1–N5) — 2026-10-12

Status: **built 2026-10-12.** The user asked me to continue with my own
recommendations overnight. These items don't change what the faithfulness or theme
judge sees, so no calibration is needed.

Not taken, and why:
- **Theme judge meta label "nested under structural theme(s)"** needs a decision from
  the user and a theme calibration run.
- **Swapped-word quote gap (2 of 752)** changes a blocking gate check (verbatim
  quotes) and needs measuring on the 752 real quotes. Kept for a planned change.
- **Stated-purpose extraction and cost-estimator accuracy:** see TODO.

## Items, criteria and tests (`tests/test_small_fixes_n.py`)

| ID | Problem | Change | Test | Status |
|---|---|---|---|---|
| N1 | An emphasis reply of 500 characters or less with no scored items was saved raw and reported as success; the gate then returned ERROR on that file. | Nothing is saved, the step fails, an earlier run's file is set aside (as Q3), and the error shows the start of the reply. A longer zero-item reply is still saved raw on purpose (U4: the gate blocks publish on it). | `test_n1_short_response_with_no_items_saves_nothing`, `test_n1_short_reply_sets_aside_earlier_file`, `test_n1_error_shows_the_reply` | done |
| N2 | `_is_valid_section_content` accepted themes by a looser regex when the shared parser found none, so the stage could report valid themes that the format check rejects. | Themes and topics validity use the format checks' parsers (`parse_bold_numbered_theme_blocks`, `parse_topics_structure`). No result changed on 23 real theme files or 19 topics files. Review: a section failing the check was silently reused; it is now logged as an error (`_report_invalid_sections`). Both legacy theme-parser fallbacks warn when they produce themes (`summary_pipeline._warn_legacy_themes`). | `test_n2_themes_validity_uses_the_format_check_parser`, `test_n2_topics_validity_uses_the_format_check_parser`, `test_n2_invalid_section_is_reported`, `test_n2_legacy_theme_fallback_warns` | done |
| N3 | 24 functions had `model=config.AUX_MODEL` / `config.DEFAULT_MODEL` defaults, bound at import, so a caller passing no model ignored a model chosen later in the GUI. | Default `None`, resolved from `config.settings` when the function is called. | `test_n3_model_defaults_resolve_at_call_time`, `test_n3_default_follows_a_later_model_change`, `test_n3_no_function_default_binds_a_model_at_import` | done |
| N4 | `parse_topics_from_extraction` strategy 2 read the text before the first `###` header as a topic ("## Topics"). | That text is skipped and the skip is logged. No real topics file reaches this strategy (19 checked). | `test_n4_text_before_first_topic_header_is_not_a_topic` | done |
| N5 | The cost estimate leaves out the judges, the overview, coverage validation and regeneration loops, and doesn't say so. | The report lists what it does not price (`config.COST_ESTIMATE_NOT_COVERED`) under the total. Pricing those steps is still open. | `test_n5_cost_report_lists_what_it_does_not_estimate` | done |

## Adjacent issues found, not fixed

- `validation_pipeline.validate_abstract_coverage` defaults to the main model, while
  `validate_summary_coverage` defaults to the AUX model. The GUI always passes one.
- `summary_coverage_key` hashes `config.settings.AUX_MODEL`, not the model actually
  passed.
- Topics strategy 2 doesn't skip scaffolding headers ("### Key Topics (5 total)"). No
  real file reaches it.
- `transcript_audit_voice.py` and `transcript_extract_terms.py` read
  `config.DEFAULT_MODEL` at call time (the module value the GUI updates, T5). That is
  correct, but it reads a different name than `config.settings`.
