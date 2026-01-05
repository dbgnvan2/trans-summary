# Transcript Summarization Pipeline

A robust, automated pipeline for processing audio/video transcripts into high-quality, structured documentation. This project uses Anthropic's Claude API to format raw text, extract key insights, generate summaries and abstracts, and publish final artifacts (Webpages, PDFs).

## Features

- **Automated Formatting**: Cleans raw transcripts, removes timestamps, and applies Markdown formatting.
- **Structured Extraction**: Extracts Topics, Themes, Key Terms, and Emphasized Items.
- **Multi-Format Output**: Generates Summaries, Abstracts, Blog Posts, HTML Webpages, and PDFs.
- **API Reliability**: Robust, model-agnostic API validation with automatic retry logic, truncation detection, and token usage tracking.
- **Quality Assurance**: Includes validation steps for word-for-word fidelity, header accuracy, and summary coverage.
- **Dual Interface**: Operate via a comprehensive GUI or specialized CLI scripts.

## Installation

1.  **Clone the repository**:

    ```bash
    git clone <repository-url>
    cd trans-summary
    ```

2.  **Install dependencies**:

    ```bash
    pip install anthropic python-dotenv weasyprint beautifulsoup4
    ```

    _Note: `weasyprint` may require additional system libraries (e.g., Pango, Cairo) depending on your OS._

3.  **Configuration**:
    Create a `.env` file in the project root:
    ```env
    ANTHROPIC_API_KEY=your_api_key_here
    ```

## Usage

### Graphical Interface (Recommended)

The GUI guides you through the entire process step-by-step.

```bash
python transcript_processor_gui.py
```

### Command Line Interface

You can run the full interactive wizard:

```bash
python transcript_process.py
```

Or run individual steps manually:

1.  **Format**: `python transcript_format.py "filename.txt"`
2.  **Add Metadata**: `python transcript_add_yaml.py "filename - formatted.md"`
3.  **Summarize**: `python transcript_summarize.py "filename - yaml.md"`
4.  **Generate Webpage**: `python transcript_to_webpage.py "filename"`
5.  **Generate PDF**: `python transcript_to_pdf.py "filename"`

## Project Structure

The project separates code (logic) from data (transcripts).

```text
trans-summary/
├── pipeline.py             # Core business logic
├── config.py               # Configuration and paths
├── transcript_utils.py     # Shared utilities (logging, API calls)
├── transcript_*.py         # CLI wrappers for specific tasks
├── prompts/                # Markdown prompt templates for Claude


transcripts/            # Data directory (configurable)
    ├── source/             # Raw input files
    ├── formatted/          # Cleaned markdown files
    ├── summaries/          # Generated analysis & extracts
    ├── webpages/           # Final HTML outputs
    └── pdfs/               # Final PDF outputs
```

## Configuration

Global settings are managed in `config.py`. You can adjust:

- **Directories**: Default locations for inputs/outputs.
- **Models**: Default Claude models (`DEFAULT_MODEL`, `AUX_MODEL`).
- **Token Limits**: Safety limits for API calls.
- **Validation Thresholds**: Strictness of fuzzy matching and coverage checks.

## Development & Testing

### Setup
Install development dependencies:
```bash
pip install -r requirements.txt
pip install ruff pytest
```

### Running Tests
This project uses `pytest` for unit testing.
```bash
pytest tests
```

### Linting & Formatting
This project uses `ruff` for fast linting and formatting.
```bash
ruff check .
ruff format .
```

## Validation Pipeline

The system employs a "Trust but Verify" approach:

1.  **API Response Validation**: (7-level) Ensures every AI response is complete, valid, and not truncated before processing.
2.  **Format Validation**: Ensures no words were lost during formatting.
3.  **Header Validation**: Checks that section headers accurately reflect content.
4.  **Coverage Validation**: Verifies summaries and abstracts cover all key topics and comply with structure.
5.  **Fidelity Validation**: Ensures quoted text (Bowen References, Emphasis) exists in the source.
6.  **Completeness Validation**: Verifies all required artifacts (files) were generated and meet minimum length requirements.

## License

[Insert License Here]
