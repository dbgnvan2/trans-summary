# User Request Log

This file tracks user requests and tasks to ensure they can be reviewed and revisited.

## 2026-01-11
- [x] Start tracking what I'm asking you to do - in a file - so you can review it or come back to it.
- [x] Investigate potential memory usage in GUI app (computer hung with OOM). Added memory monitor and log buffer truncation.
- [x] Fix GUI startup crash: "ImportError: cannot import name 'OverloadedError' from 'anthropic'".
- [x] Add explicit "Initial Validation" status indicator to the GUI file status list.
- [x] Fix summary generation being too short and missing Q&A/Conclusion. (Lowered Q&A threshold to 5%, added min_words constraint).
- [x] Update DEFAULT_SUMMARY_WORD_COUNT to 600 to target an ideal length of 600 words (min ~450).
- [x] Rewrite Summary Generation Prompt to use a "Narrative Synthesis" approach (ignoring rigid topic-per-paragraph constraints) and explicitly use the full transcript.
- [x] Write validation tests for the new summary prompt structure.
- [x] Add logging of Target Word Count to the 'Generating structured summary' step for visibility.
- [x] Refactor `generate_structured_summary` to use `None` as default for `summary_target_word_count` to ensure current config values are used at runtime.
- [x] Cleanup validation report: removed "Proportionality Issues" spam and relaxed length warnings.
- [ ] Create test `tests/test_summary_scaling.py` to verify inflation strategy and min_words logic.
