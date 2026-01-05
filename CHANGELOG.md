# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2026-01-05

### Added

- **Dynamic Model Selection**: Added dropdown menus in the GUI to select specific Claude models for Default, Auxiliary, and Formatting tasks.
- **Test Runner**: Added `run_tests.py` script to execute all unit and integration tests.
- **Integration Tests**: Added `test_pipeline_integration.py` to simulate the full extraction and validation workflow.
- **Parsing Tests**: Added `test_summary_pipeline_parsing.py` and `test_extraction_model_passing.py` to verify parsing logic and model propagation.
- **Technical Documentation**: Added a "Technical Details" section to `README.md` explaining the robust regex logic for topic parsing.

### Changed

- **Topic Parsing Logic**: Updated regex patterns in `abstract_pipeline.py` and `summary_pipeline.py` to be non-greedy and robust against malformed metadata (e.g., missing semicolons).
- **Default Models**: Updated default models in `config.py` to `claude-opus-4-5-20251101` (Default) and `claude-haiku-4-5-20251001` (Aux/Formatting).
- **Configuration Management**: Refactored `config.py` to use a Singleton pattern for managing runtime settings while maintaining backward compatibility.
- **Test Suite**: Refactored multiple test files (`test_regex.py`, `test_timestamp_regex.py`, `test_formatting_helpers.py`, `test_emphasis_detector.py`) to use `pytest` style assertions and parametrization for better reporting.

### Fixed

- **Model Propagation**: Fixed issues where the selected model was not being passed down to `generate_structured_summary`, `generate_structured_abstract`, and validation functions.
- **Header Validation**: Fixed `HeaderValidator` to accept a dynamic model argument.
- **Deprecated Models**: Removed references to deprecated models (`claude-3-opus-20240229`, `claude-3-sonnet-20240229`, `claude-3-7-sonnet-20250219`) to prevent API errors.
- **Test Reliability**: Fixed `test_validation_headless.py` to correctly report failures to the test runner.
- **Bowen References**: Fixed parsing issue where list markers prevented references from being highlighted in the webpage; added robust cleaning logic.
