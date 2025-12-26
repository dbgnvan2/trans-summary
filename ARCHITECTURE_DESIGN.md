# Architecture and Design Overview

This document provides a high-level overview of the `trans-summary` project's architecture, its core components, data flow, and key design principles. It aims to serve as a central reference for understanding the system's internal workings, particularly for maintenance, extension, and analysis by AI models.

## 1. System Overview

The `trans-summary` project is a Python-based application designed to process academic and professional transcripts using AI (specifically Claude AI, with model-agnostic patterns for extensibility). It automates the formatting, summarization, validation, and generation of various output formats (Markdown, HTML, PDF) from raw transcript files.

The system emphasizes:
- **Automation**: Streamlined workflow from raw input to diverse outputs.
- **Quality Assurance**: Robust validation steps to ensure fidelity and completeness.
- **Modularity**: Separation of concerns into distinct scripts and modules.
- **User Experience**: Interactive GUI for ease of use, alongside CLI for automation.
- **AI Integration**: Model-agnostic patterns for flexible LLM integration.

## 2. Core Architecture

The architecture is primarily a **pipeline-driven system** orchestrated by a central `pipeline.py` module, which is invoked by either the GUI (`transcript_processor_gui.py`) or individual CLI scripts.

### 2.1. Major Components

- **GUI (`transcript_processor_gui.py`)**:
    - Provides an interactive user interface for executing pipeline stages.
    - Manages file selection, status display, and log output.
    - Orchestrates calls to the `pipeline.py` functions in a sequential workflow.
    - Utilizes `GuiLoggerAdapter` for integrated logging.

- **Pipeline Core (`pipeline.py`)**:
    - The central module that defines and orchestrates the main workflow stages.
    - Contains high-level functions that call into specialized modules for specific tasks (e.g., formatting, summarization, validation, generation).
    - Ensures proper sequencing and error handling across stages.

- **Configuration (`config.py`)**:
    - Centralizes directory paths, constants, and prompt filenames.
    - Ensures consistency across all scripts and facilitates easy environment setup.

- **Utilities (`transcript_utils.py`)**:
    - A shared module providing common functionalities used across the project.
    - **Key functionalities**:
        - API key and input file validation.
        - Robust API calling with retry logic, truncation detection, and token usage tracking (`call_claude_with_retry`, `validate_api_response`).
        - Structured logging (`setup_logging`).
        - Markdown content extraction (`extract_section`, `extract_bowen_references`, `extract_emphasis_items`, `strip_yaml_frontmatter`).
        - Text normalization for validation.

- **Specialized Processing Modules**: Each primary task is encapsulated in its own module:
    - `transcript_format.py`: Handles formatting of raw transcripts using LLMs.
    - `transcript_add_yaml.py`: Adds YAML front matter metadata.
    - `summary_pipeline.py`: Prepares input and generates structured summaries using LLMs.
    - `abstract_pipeline.py`: Prepares input and generates structured abstracts using LLMs.
    - `transcript_to_webpage.py`, `transcript_to_simple_webpage.py`, `transcript_to_pdf.py`: Generate various output formats.

- **Validation Modules**: Dedicated modules for ensuring data integrity and output quality:
    - `transcript_validate_format.py`: Validates word preservation after formatting.
    - `transcript_validate_completeness.py`: Checks completeness of generated outputs.
    - `transcript_validate_emphasis.py`: Verifies emphasis items in source.
    - `transcript_validate_abstract.py`: Iteratively refines and scores abstract quality.
    - `transcript_validate_webpage.py`: Validates content in generated webpages.

## 3. Data Flow and Workflow

The system operates as a sequential pipeline, where the output of one stage often serves as the input for the next.

**High-Level Workflow:**

1.  **Input**: Raw transcript file (`.txt`) placed in `TRANSCRIPTS_BASE/source/`.
2.  **Formatting**: `transcript_format.py` (via `pipeline.py`) uses an LLM to format the raw transcript into a structured Markdown file.
3.  **Validation (Format)**: `transcript_validate_format.py` ensures no word loss during formatting.
4.  **Metadata Addition**: `transcript_add_yaml.py` adds YAML front matter to the formatted transcript.
5.  **Summarization & Extraction**: `summary_pipeline.py` extracts abstract, topics, themes, and key terms using LLMs. `abstract_pipeline.py` handles abstract generation and iterative refinement.
6.  **Validation (Summaries/Abstracts)**: `transcript_validate_completeness.py`, `transcript_validate_emphasis.py`, `transcript_validate_abstract.py` ensure the quality and accuracy of generated summaries and abstracts.
7.  **Output Generation**: `transcript_to_webpage.py`, `transcript_to_simple_webpage.py`, `transcript_to_pdf.py` convert the processed Markdown into HTML and PDF documents.
8.  **Output Validation (Webpages)**: `transcript_validate_webpage.py` verifies the integrity of generated web content.
9.  **Archiving**: The original source file is moved to `TRANSCRIPTS_BASE/processed/`.

**Key Data Structures:**

-   **`SummaryInput` (from `summary_pipeline.py`)**: A dataclass encapsulating all input required for structured summary generation, including metadata, topics, themes, transcript content, and word allocations.
-   **`TopicAllocation`, `OpeningSection`, `BodySection`, `QASection`, `ClosingSection`**: Dataclasses composing `SummaryInput`, defining the structure and word count allocations for different parts of the generated summary.

## 4. AI Integration Strategy (Model-Agnostic)

The system is designed with a model-agnostic approach for interacting with Large Language Models (LLMs), currently using Anthropic's Claude API.

### 4.1. Core Principles:

-   **Abstraction**: Aims to abstract away provider-specific API calls and response structures.
-   **Standardized Validation**: Uses a universal 7-step validation pattern for API responses (implemented in `transcript_utils.py`'s `validate_api_response`). This pattern checks message type, role, completion status, content existence, content format, text validity, and token usage.
-   **Robust Error Handling**: Centralized retry logic, specific exception handling for common API errors (rate limits, authentication, timeouts, bad requests).
-   **Configurable Models**: LLM models are configurable, allowing easy switching between providers (Anthropic, OpenAI, Gemini) with minimal code changes (primarily adapting `AIResponse` abstraction).

### 4.2. Key Files for AI Interaction:

-   **`transcript_utils.py`**: Contains the `call_claude_with_retry` and `validate_api_response` functions, which are the primary interface for making robust, validated LLM calls.
-   **`summary_pipeline.py`**: Constructs specific prompts and `SummaryInput` objects for structured summarization, then calls `transcript_utils.py` for API interaction.
-   **`abstract_pipeline.py`**: Similar to `summary_pipeline.py`, but focused on abstract generation and iterative refinement.
-   **`MODEL_AGNOSTIC_VALIDATION.md`**: Documents the adaptation strategy for different LLM providers, including code examples for OpenAI and Google Gemini.

## 5. Design Decisions and Patterns

-   **Separation of Concerns**: Each script or module has a single, well-defined responsibility.
-   **Fail-Fast Principle**: Early validation (API keys, input files, token budgets) prevents costly or time-consuming errors downstream.
-   **Iterative Refinement**: The abstract validation process (`transcript_validate_abstract.py`) demonstrates an iterative improvement loop, leveraging LLMs to refine their own output based on quality criteria.
-   **File-based Intermediates**: Data is passed between pipeline stages primarily through files, making each stage somewhat independent and facilitating debugging and re-running specific parts of the pipeline.
-   **Metadata-driven Processing**: File naming conventions and YAML front matter are used to embed and extract metadata, guiding the processing workflow.

## 6. Future Considerations

-   **Caching**: Implement caching for LLM responses to reduce API costs and improve performance.
-   **Parallelization**: Identify independent pipeline stages that can be run concurrently to speed up processing.
-   **Advanced Logging**: Centralized, persistent logging for better traceability and debugging.
-   **Extensibility**: Further generalize AI integration with a more complete `AIResponse` abstraction layer that can truly encapsulate responses from any LLM provider.

This document provides a foundational understanding of the project's architecture, which should assist both human developers and AI models in navigating and working with the codebase effectively.
