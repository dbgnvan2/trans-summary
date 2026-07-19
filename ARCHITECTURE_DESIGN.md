# Architecture and Design Overview

This document provides a high-level overview of the `trans-summary` project's architecture, its core components, data flow, and key design principles. It aims to serve as a central reference for understanding the system's internal workings, particularly for maintenance, extension, and analysis by AI models.

## 1. System Overview

The `trans-summary` project is a Python-based application designed to process academic and professional transcripts using AI (specifically Claude AI, with model-agnostic patterns for extensibility). It automates the formatting, summarization, validation, and generation of various output formats (Markdown, HTML, PDF) from raw transcript files.

The system emphasizes:
- **Automation**: Streamlined workflow from raw input to diverse outputs.
- **Quality Assurance**: Robust validation steps to ensure fidelity and completeness.
- **Modularity**: Separation of concerns into distinct scripts and modules.
- **User Experience**: Interactive GUI for ease of use, alongside CLI for automation.
- **AI Integration**: Model-agnostic patterns for flexible LLM integration with prompt caching.

## 2. Core Architecture

The architecture is primarily a **pipeline-driven system** orchestrated by a central `pipeline.py` module, which is invoked by either the GUI (`ts_gui.py`) or individual CLI scripts.

### 2.1. Major Components

- **GUI (`ts_gui.py`)**:
    - Provides an interactive user interface for executing pipeline stages.
    - Manages file selection, status display, and log output with vertical resizing support.
    - Orchestrates calls to the `pipeline.py` functions in a sequential workflow.
    - Utilizes `GuiLoggerAdapter` for integrated logging.
    - Features a **Model Selection** panel to dynamically configure models for Default, Auxiliary, and Formatting tasks.
    - Includes a dedicated standalone `Bowen + Emphasis` action in addition to the main `Core` workflow.
    - Allows Bowen and Emphasis to be included or excluded independently from `Core` and `Do All`.

- **Pipeline Core (`pipeline.py`)**:
    - The central module that defines and orchestrates the main workflow stages.
    - Contains high-level functions that call into specialized modules for specific tasks (e.g., formatting, summarization, validation, generation).
    - Ensures proper sequencing and error handling across stages.

- **Configuration (`config.py`)**:
    - Centralizes directory paths, constants, and prompt filenames.
    - Implements a Singleton pattern for runtime configuration management.
    - Ensures consistency across all scripts and facilitates easy environment setup.

- **Utilities (`transcript_utils.py`)**:
    - A shared module providing common functionalities used across the project.
    - **Key functionalities**:
        - API key and input file validation.
        - **Robust API Interaction**: Centralized `call_claude_with_retry` function that handles:
            - **7-Level Response Validation**: Checks message type, role, completion status (`stop_reason`), content existence, content format, text validity, and token usage.
            - **Truncation Detection**: Automatically detects and rejects responses cut off by token limits.
            - **Retry Logic**: Exponential backoff for rate limits and connection errors.
            - **Prompt Caching**: Supports `create_system_message_with_cache` for cost efficiency.
        - Structured logging (`setup_logging`) and CSV token usage tracking.
        - Markdown content extraction (`extract_section`, `extract_bowen_references`, `extract_emphasis_items`, `strip_yaml_frontmatter`).
        - Text normalization for validation.

- **Specialized Processing Modules**: Each primary task is encapsulated in its own module:
    - `transcript_initial_validation.py`: (Pre-process) Checks for phonetic errors and typos with interactive review.
    - `transcript_format.py`: Handles formatting of raw transcripts using LLMs.
    - `transcript_add_yaml.py`: Adds YAML front matter metadata.
    - `summary_pipeline.py`: Prepares input and generates structured summaries using LLMs.
    - `abstract_pipeline.py`: Prepares input and generates structured abstracts using LLMs.
    - `transcript_to_webpage.py`, `transcript_to_simple_webpage.py`, `transcript_to_pdf.py`: Generate various output formats.

- **Validation Modules**: Dedicated modules for ensuring data integrity and output quality:
    - `transcript_initial_validation.py`: Validates raw transcript quality before processing begins.
    - `transcript_validate_format.py`: Validates word preservation after formatting.
    - `transcript_validate_completeness.py`: High-level check for the presence and basic structure of all generated artifacts.
    - `summary_validation.py`: (Core) Deep validation of summary content. Distinguishes between **Coverage Failures** (missing topics) and **Structural Warnings** (length, proportionality, style).
    - `abstract_validation.py`: (Core) Deep validation of abstract content with similar Failure/Warning distinction.
    - `transcript_validate_emphasis.py`: Verifies emphasis items and quotes exist in the source text.
    - `transcript_validate_webpage.py`: Validates content in generated webpages.

## 3. Data Flow and Workflow

The system operates as a sequential pipeline, where the output of one stage often serves as the input for the next.

**High-Level Workflow:**

1.  **Input**: Raw transcript file (`.txt`) placed in `TRANSCRIPTS_BASE/source/`.
2.  **Initial Validation**: `transcript_initial_validation.py` checks for errors. User reviews and applies corrections via GUI dialog.
3.  **Formatting**: `transcript_format.py` (via `pipeline.py`) uses an LLM to format the raw transcript into a structured Markdown file.
4.  **Validation (Format)**: `transcript_validate_format.py` ensures no word loss during formatting.
5.  **Metadata Addition**: `transcript_add_yaml.py` adds YAML front matter to the formatted transcript.
6.  **Summarization & Extraction**: `summary_pipeline.py` extracts abstract, topics, themes, and key terms using LLMs. `abstract_pipeline.py` handles abstract generation. Bowen reference extraction and emphasis extraction can run either inside the main core flow or together as a standalone GUI step.
7.  **Validation (Summaries/Abstracts)**: `summary_validation.py` and `abstract_validation.py` ensure quality. Structural deviations (length, style) are reported as **warnings** but do not block progress.
8.  **Output Generation**: `transcript_to_webpage.py`, `transcript_to_simple_webpage.py`, `transcript_to_pdf.py` convert the processed Markdown into HTML and PDF documents.
9.  **Output Validation (Webpages)**: `transcript_validate_webpage.py` verifies the integrity of generated web content.
10. **Archiving**: The original source file is moved to `TRANSCRIPTS_BASE/processed/`.

### 3.1. Standalone Bowen / Emphasis Paths

- The GUI can run `Bowen + Emphasis` together without requiring the full core extraction step.
- The backend shares one cached transcript system message across both extraction calls in that standalone path.
- Standalone extraction resolves input in this order: project ` - yaml.md`, project ` - formatted.md`, then the selected source `.txt` file.
- The CLI wrappers `transcript_extract_bowen.py` and `transcript_extract_emphasis.py` support the same direct-file workflow.

### 3.2. Timestamp Association for References

To enhance usability and traceability, the pipeline now automatically associates a timestamp with each extracted **Bowen Reference** and **Emphasized Item**.

-   **Extraction Process**: During extraction, after an item's quote is identified by the LLM, a fuzzy search is performed against the full transcript text to locate the quote. The script then scans backwards from the quote's position to find the last preceding timestamp (e.g., `[00:12:34]`).
-   **Storage Format**: The found timestamp is stored directly in the intermediate artifact files:
    -   **Bowen References (`...-bowen-references.md`)**: The timestamp is appended to the concept header.
        ```markdown
        ### Concept Name [00:12:34]
        > "The quote text."
        ```
    -   **Scored Emphasis (`...-emphasis-scored.md`)**: The timestamp is added to the metadata block.
        ```markdown
        [Implicit - A3 - Rank: 88% | 00:12:34] Concept: The concept description
        "The quote text."
        ```
-   **Display**: The final PDF and HTML documents display this timestamp next to the item in the appendix sections and in the hover-over tooltip for highlighted text in the transcript body, allowing for quick reference.
-   **Robustness**: This process uses fuzzy matching to locate quotes, making it resilient to minor wording changes from the LLM. If a timestamp cannot be confidently determined, it is omitted for that item.

## 4. AI Integration Strategy (Model-Agnostic)

The system is designed with a model-agnostic approach for interacting with Large Language Models (LLMs), currently using Anthropic's Claude API.

### 4.1. Core Principles:

-   **Abstraction**: Aims to abstract away provider-specific API calls and response structures.
-   **Standardized Validation**: Uses a universal 7-step validation pattern for API responses (implemented in `transcript_utils.py`'s `validate_api_response`).
-   **Robust Error Handling**: Centralized retry logic, specific exception handling for common API errors.
-   **Prompt Caching**: Utilizes Anthropic's prompt caching to reduce latency and cost for large context windows.

### 4.2. Key Files for AI Interaction:

-   **`transcript_utils.py`**: Contains the `call_claude_with_retry` and `validate_api_response` functions.
-   **`model_specs.py`**: Defines model pricing and context window specifications.
-   **`config.py`**: Manages model selection constants (`DEFAULT_MODEL`, `AUX_MODEL`, `FORMATTING_MODEL`, `VALIDATION_MODEL`).

### 4.3. Release Gate & Faithfulness Verification (fail-closed publication)

Before any bundle (webpage / PDF / package) is written, `release_gate.py` runs a suite of publication checks and returns an aggregate `GateDecision` (`ALLOW` / `ALLOW_WITH_WARNINGS` / `BLOCK`). Publication is **fail-closed**: on `BLOCK` the generators refuse to write the bundle, and a check that raises or cannot verify becomes an `ERROR` verdict rather than a silent pass.

-   **Checks** (`DEFAULT_CHECKS`): `entity_grounding`, `artifact_contracts`, `faithfulness`, `theme_grounding`, `required_artifacts`, `verbatim_quotes`, `timestamp_citations`, `entity_consistency`. Which checks are hard blockers is config policy (`config.GATE_BLOCKING_CHECKS`, `config.GATE_ERROR_BLOCKS`); the rest are advisory `WARN`s.
-   **LLM judges** (`faithfulness_judge.py`, both Sonnet; forced OFF in the unit suite via a root-conftest fixture):
    -   **Faithfulness judge** — a claim-level entailment check on the PROSE artifacts (abstract / summary / overview / blog). Any unentailed claim, or a judge error, blocks publication.
    -   **Theme grounding judge** — asks whether an interpretive theme is a *reasonable grounding* in the source (not whether it is literally stated), passing legitimate interpretation while blocking themes built on fabricated subject matter.
    Both are ARMED as Hard BLOCKs after real-artifact calibration and pinned via `config.FAITHFULNESS_JUDGE_MODEL` / `config.THEME_JUDGE_MODEL`.
-   **Run manifest** (`build_manifest` / `write_manifest`): each gate run persists a machine-readable manifest recording the publish decision, per-check verdicts, artifact hashes, and provenance (source hash, code revision, gate policy, model IDs) so a decision is auditable.

## 5. Design Decisions and Patterns

-   **Separation of Concerns**: Each script or module has a single, well-defined responsibility.
-   **Fail-Fast Principle**: Early validation (API keys, input files, token budgets) prevents costly or time-consuming errors downstream.
-   **Warning vs. Error**: Validation logic distinguishes between fatal errors (semantic inaccuracy) and warnings (stylistic deviations), allowing for a smoother user experience without compromising core quality.
-   **File-based Intermediates**: Data is passed between pipeline stages primarily through files, making each stage somewhat independent and facilitating debugging.
-   **Metadata-driven Processing**: File naming conventions and YAML front matter are used to embed and extract metadata.

## 6. Future Considerations

-   **Parallelization**: Identify independent pipeline stages that can be run concurrently to speed up processing.
-   **Advanced Logging**: Centralized, persistent logging for better traceability and debugging.
-   **Extensibility**: Further generalize AI integration with a more complete `AIResponse` abstraction layer that can truly encapsulate responses from any LLM provider.

This document provides a foundational understanding of the project's architecture, which should assist both human developers and AI models in navigating and working with the codebase effectively.
