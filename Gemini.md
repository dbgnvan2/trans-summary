# Project Overview: Transcript Summarization Pipeline

## 1. Purpose

This project (`trans-summary`) is an automated pipeline designed to process raw transcripts (typically from audio/video recordings) into high-quality, structured documentation. It uses Anthropic's Claude API to format text, extract key insights, generate summaries and abstracts, and publish final artifacts (Webpages, PDFs).

## 2. Core Workflow

The pipeline operates in sequential stages, moving files through specific directories defined in `config.py`.

### Stage 1: Ingestion & Formatting

- **Input**: Raw `.txt` files in `source/`.
- **Process**:
  1.  **Format**: Cleans raw text, removes timestamps, and applies Markdown formatting (`transcript_format.py`).
  2.  **Validate**: Ensures word-for-word fidelity against the source (`transcript_validate_format.py`).
  3.  **Metadata**: Adds YAML front matter (Title, Presenter, Date) (`transcript_add_yaml.py`).
- **Output**: `formatted/Title - Presenter - Date - formatted.md` (and `- yaml.md`).

### Stage 2: Extraction & Analysis

- **Process**: Analyzes the formatted transcript to extract structured data (`transcript_summarize.py` calling `pipeline.py`).
- **Outputs** (in `summaries/`):
  - `All Key Items.md`: Raw extraction of Topics, Themes, Key Terms, Emphasis Items, and Bowen References.
  - `key-terms.md`: Specific terminology definitions.
  - `bowen-references.md`: Quotes related to Bowen Theory.
  - `emphasis-items.md`: Key quotes emphasized by the speaker.

### Stage 3: Generation (Structured)

- **Process**: Uses extracted data to generate cohesive narratives.
  - **Summary**: Generates a proportional summary with Opening, Body (Topics), Q&A, and Closing (`summary_pipeline.py`).
  - **Abstract**: Generates a structured abstract (`abstract_pipeline.py`).
  - **Blog**: Generates a blog post adaptation.

### Stage 4: Validation (Quality Assurance)

- **Coverage**: Verifies that generated summaries/abstracts cover all required topics and keywords (`summary_validation.py`, `abstract_validation.py`).
- **Fidelity**: Verifies that quoted text (Emphasis/Bowen) exists in the source (`transcript_validate_emphasis.py`, `transcript_validate_bowen.py`).
- **Completeness**: Checks for missing sections or truncation (`transcript_validate_completeness.py`).
- **Voice**: Audits content for specific stylistic voice characteristics (`transcript_audit_voice.py`).

### Stage 5: Publication

- **Process**: Converts Markdown artifacts into presentation formats (`html_generator.py`).
- **Outputs**:
  - `webpages/`: HTML files (Sidebar layout and Simple layout).
  - `pdfs/`: PDF documents generated via WeasyPrint.

## 3. Key Modules & Architecture

### Orchestration

- `transcript_process.py`: Interactive CLI wizard that guides the user through the full pipeline.
- `transcript_processor_gui.py`: Tkinter-based GUI for the pipeline.
- `pipeline.py`: The central business logic hub. Connects CLI/GUI actions to specific processing functions.

### Configuration

- `config.py`: Central configuration for paths (`TRANSCRIPTS_BASE`), model selection (`DEFAULT_MODEL`), and validation thresholds.
- `.env`: Stores `ANTHROPIC_API_KEY`.

### Utilities

- `transcript_utils.py`: Shared helpers for API calls (with retry/validation), file I/O, and text normalization.
- `emphasis_detector.py`: Regex-based engine for detecting emphasized speech patterns.

### Generators

- `summary_pipeline.py` & `abstract_pipeline.py`: Logic for preparing prompts and parsing responses for structured generation.
- `html_generator.py`: Handles Markdown-to-HTML conversion and highlighting (using `BeautifulSoup`).

## 4. Naming Conventions

Files follow a strict naming pattern to maintain lineage:

- **Base**: `Title - Presenter - Date` (e.g., `Roots of Bowen Theory - Dr Michael Kerr - 2019-11-15`)
- **Suffixes**:
  - ` - formatted.md`: Cleaned transcript.
  - ` - yaml.md`: Formatted + Metadata.
  - ` - All Key Items.md`: Main extraction output.
  - ` - summary-generated.md`: Final summary.
  - ` - abstract-generated.md`: Final abstract.
  - ` - blog.md`: Blog post.

## 5. Directory Structure

```text
transcripts/
├── source/       # Raw input files
├── formatted/    # Cleaned markdown files
├── summaries/    # Generated analysis, summaries, and abstracts
├── webpages/     # Final HTML outputs
├── pdfs/         # Final PDF outputs
├── processed/    # Archived source files after completion
└── prompts/      # Markdown prompt templates for Claude
```

## 6. Tech Stack & Libraries

- **Language**: Python 3.11+
- **Core AI**: Anthropic Claude API (Sonnet 3.5) via `anthropic` SDK.
- **PDF Generation**: `weasyprint` (requires system dependencies like Pango/Cairo).
- **HTML Processing**: `beautifulsoup4` for parsing and manipulation.
- **GUI**: `tkinter` (standard library) for the graphical interface.
- **Utilities**: `python-dotenv` for configuration, `pathlib` for robust path handling.

## 7. Recurring Coding Patterns

- **Centralized Logic**: Business logic is decoupled from interfaces. `pipeline.py` contains the core logic,
  while `transcript_*.py` scripts serve as CLI wrappers and `transcript_processor_gui.py` serves as the GUI wrapper.
- **Logging**: Logging is centralized in `transcript_utils.setup_logging`. It creates timestamped log files
  in a `logs/` directory and streams to the console/GUI simultaneously.
- **Error Handling & Validation**:
  - **Fail-Fast**: Scripts validate API keys and input file existence immediately using
    `transcript_utils.validate_input_file`.
  - **API Robustness**: API calls use `call_claude_with_retry` which handles rate limits, timeouts,
    and response validation (truncation detection).
  - **Trust but Verify**: Generation steps (Summary, Abstract) are immediately followed by validation steps
    (Coverage, Fidelity) that parse the output and score it against the source.
- **Regex Extraction**: Markdown parsing relies heavily on robust regex patterns (centralized in `transcript_utils.py`)
  rather than strict JSON parsing, allowing for more natural LLM outputs.
