# Transcript Summarization Pipeline

A robust, automated pipeline for processing audio/video transcripts into high-quality, structured documentation. This project uses Anthropic's Claude API to format raw text, extract key insights, generate summaries and abstracts, and publish final artifacts (Webpages, PDFs).

[![Code Quality](https://img.shields.io/badge/Code%20Quality-A---%23brightgreen)]()
[![Security](https://img.shields.io/badge/Security-Secure-brightgreen)]()
[![Tests](https://img.shields.io/badge/Tests-pytest-blue)]()

## Features

### Core Functionality
- **Automated Formatting**: Cleans raw transcripts, removes timestamps, and applies Markdown formatting
- **Structured Extraction**: Extracts Topics, Themes, Key Terms, and Emphasized Items
- **Multi-Format Output**: Generates Summaries, Abstracts, Blog Posts, HTML Webpages, and PDFs
- **Dual Interface**: Operate via a comprehensive GUI or specialized CLI scripts

### Reliability & Quality (NEW - 2026-01-10)
- **Configuration Validation**: Comprehensive startup validation for 70+ config values with auto-fix capability
- **Secure by Design**: Path traversal protection, input sanitization, XSS prevention
- **Robust Error Handling**: Categorized exceptions with stack traces, no silent failures
- **Template-Based HTML**: Clean separation of logic and presentation using Jinja2
- **API Reliability**: Model-agnostic API validation with automatic retry logic, truncation detection, and token usage tracking
- **Quality Assurance**: Validation steps for word-for-word fidelity, header accuracy, and summary coverage

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
python ts_gui.py
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

The project separates code (logic) from data (transcripts). By default, data directories are located within the project root, but this can be configured.

```text
trans-summary/
├── pipeline.py             # Core business logic
├── config.py               # Configuration and paths
├── transcript_utils.py     # Shared utilities (logging, API calls)
├── transcript_*.py         # CLI wrappers for specific tasks
├── prompts/                # Markdown prompt templates for Claude
├── source/                 # Raw input files (txt)
├── projects/               # Project-specific output folders
│   └── [Transcript Name]/  # Flat artifact set per transcript (md/html/pdf/zip)
└── processed/              # Archive for completed source files
```

## Configuration

Global settings are managed in `config.py`. You can adjust:

- **Directories**: Default locations for inputs/outputs
- **Models**: Default Claude models (currently `DEFAULT_MODEL` = `claude-sonnet-4-20250514`, `AUX_MODEL` = `claude-3-5-haiku-20241022`, `FORMATTING_MODEL` = `claude-3-7-sonnet-20250219`)
- **Token Limits**: Safety limits for API calls
- **Validation Thresholds**: Strictness of fuzzy matching and coverage checks

### Configuration Validation (NEW)

The system now validates all configuration settings at startup to catch errors early:

```python
import config

# Validate configuration (with auto-fix for missing directories)
config.validate_or_exit(verbose=True, auto_fix=True)

# Or get detailed validation results
result = config.validate_configuration(verbose=False, auto_fix=False)
if not result.is_valid():
    print(f"Found {len(result.errors)} configuration errors:")
    for error in result.errors:
        print(f"  - {error}")
```

**Validation Categories:**
- Directory paths (with auto-creation)
- Model names (verified against available models)
- Numeric ranges (token limits, temperatures, timeouts)
- Percentages and ratios (0.0 to 1.0)
- Word and character counts (positive integers)
- Logical consistency (e.g., chunk overlap < chunk size)
- Type validation (sets, proper types)

**Benefits:**
- Fail-fast: Catch configuration errors at startup, not hours into processing
- Clear error messages with actionable fixes
- Auto-fix capability for common issues (missing directories)
- Prevents 70+ potential runtime errors

## Development & Testing

### Setup

Install development dependencies:

```bash
pip install -r requirements.txt
pip install ruff pytest
```

### Running Tests

This project uses `pytest` for unit and integration testing:

```bash
# Run all tests
pytest

# Run specific test suites
pytest test_exception_fix.py          # Exception handling tests
pytest test_path_traversal_fix.py     # Security tests (40+ cases)
pytest test_html_generation.py        # Template rendering tests
pytest test_config_validation.py      # Configuration validation tests

# Run with coverage
pytest --cov=. --cov-report=html
```

**Test Suites:**
- **Exception Handling**: 4 test suites verifying proper error categorization
- **Security**: 9 test suites with 40+ test cases for path traversal protection
- **HTML Generation**: 6 test suites verifying template rendering and highlighting
- **Configuration Validation**: 13 test suites covering all validation categories
- **Integration Tests**: End-to-end workflow validation
- **Parsing Tests**: Regex and metadata parsing verification

Note: there are duplicate test module names in both the repository root and `tests/` package, which can cause `pytest` collection-import mismatch errors unless naming is normalized.

### Linting & Formatting

This project uses `ruff` for fast linting and formatting.

```bash
ruff check .
ruff format .
```

## Validation Pipeline

The system employs a "Trust but Verify" approach:

1.  **API Response Validation**: (7-level) Ensures every AI response is complete, valid, and not truncated before processing.
2.  **Initial Transcript Validation**: Checks for phonetic errors, typos, and repeated phrases before processing begins. Uses fuzzy matching and interactive review.
3.  **Format Validation**: Ensures no words were lost during formatting.
4.  **Header Validation**: Checks that section headers accurately reflect content.
5.  **Coverage & Structure Validation**: Verifies summaries and abstracts cover all key topics.
    *   **Failures**: Missing required semantic content (topics, speaker ID, purpose).
    *   **Warnings**: deviations in length, word allocation, or stylistic constraints (e.g., evaluative language).
6.  **Fidelity Validation**: Ensures quoted text (Bowen References, Emphasis) exists in the source.
7.  **Completeness Validation**: Verifies all required artifacts (files) were generated and meet minimum length requirements.

## Security

### Path Traversal Protection (NEW)

All filename inputs are sanitized to prevent directory traversal attacks:

```python
from transcript_utils import sanitize_filename

# Malicious inputs are safely handled
safe_name = sanitize_filename("../../../etc/passwd")  # → "passwd"
safe_name = sanitize_filename("/absolute/path")       # → "path"
safe_name = sanitize_filename("file\x00name")         # → "filename"
```

**Protection Measures:**
- Removes `../` parent directory references
- Blocks absolute paths (`/`, `C:\`)
- Removes null bytes (`\x00`)
- Strips control characters (ASCII < 32)
- Validates filename length (< 255 characters)
- Ensures non-empty result after sanitization

**Testing:** 40+ attack vectors tested and blocked (CVSS 7.5/10 vulnerability eliminated)

### XSS Prevention

HTML generation uses Jinja2 templates with auto-escaping enabled:

```python
# All user-provided content is automatically escaped
{{ user_input }}  # Automatically escaped

# Only trusted HTML marked as safe
{{ trusted_html|safe }}  # Explicitly marked
```

### Input Validation

- **Configuration**: All settings validated at startup
- **Filenames**: Sanitized before any file operations
- **API Responses**: 7-level validation ensures completeness
- **User Input**: Type checking and range validation

## Technical Details

### HTML Template System (NEW)

The HTML generation system uses Jinja2 templates for clean separation of logic and presentation:

**Architecture:**
```
html_generator.py (650 lines)
  ├─ Template setup & CSS loading
  ├─ Helper functions (metadata formatting)
  ├─ Highlighting logic (word matching, entity handling)
  └─ Generation functions (webpage, simple, PDF)

templates/
  ├─ base.html (inheritance base)
  ├─ webpage.html (sidebar layout)
  ├─ simple_webpage.html (single page)
  ├─ pdf.html (print-ready with TOC)
  └─ styles/
      ├─ common.css (typography, highlighting)
      ├─ webpage.css (responsive sidebar)
      └─ pdf.css (page breaks, print rules)
```

**Benefits:**
- 59% code reduction in Python file (1,584 → 650 lines)
- Designers can modify HTML/CSS without touching Python
- Template inheritance reduces duplication
- Auto-escaping prevents XSS attacks
- CSS loaded once at module level for performance

**Example Usage:**
```python
from html_generator import generate_webpage

# Generate HTML with sidebar
generate_webpage("Transcript - Speaker - 2024-01-01")

# Output: projects/Transcript.../Transcript....html
```

### Topic Parsing Logic

The pipeline uses a robust regular expression to parse the "Topics" section generated by the LLM. This ensures accurate extraction of topic names, descriptions, percentages, and section references, even with minor formatting variations.

**Regex Pattern:**

```python
r"###\s+([^\n]+)\s*\n\s*((?:(?!\n###).)+?)\s*\n\s*[\*_\-\s\[\(]+~?(\d+)%[^;\n]+;\s*Sections?\s+([\d\-,\s]+)(?:\)|\])?[\*_\-\s]*"
```

**Key Features:**

1.  **Non-Greedy Description**: The description group `((?:(?!\n###).)+?)` uses a negative lookahead to ensure it stops _before_ the next topic header (`###`), preventing it from merging multiple topics if metadata is malformed.
2.  **Robust Metadata Matching**: The metadata line matcher handles various markdown wrappers (bold, italics, brackets) and ensures it doesn't bleed into subsequent lines (`[^;\n]+`).
3.  **Single-Line Headers**: Topic names are constrained to a single line `([^\n]+)` to avoid capturing description text as part of the title.

## Code Quality

**Current Metrics** (as of 2026-02-10):
- **Overall Grade**: A- (up from C+)
- **Security**: ✅ Secure (no known vulnerabilities)
- **Testing**: `pytest` suite active with root-level and `tests/` package coverage
- **Technical Debt**: 42.5 hours (down from 54 hours)
- **Critical Issues**: 0/4 remaining (100% complete)

**Recent Improvements:**
- ✅ Fixed path traversal vulnerability (CVSS 7.5/10)
- ✅ Enhanced exception handling with categorization and logging
- ✅ Refactored HTML generation to use templates (59% code reduction)
- ✅ Added comprehensive configuration validation (70+ checks)

**Detailed Review:** See `code_quality_review.md` and `FIXES_SUMMARY.md`

## Documentation

### Core Documentation
- **README.md** (this file): Project overview, installation, usage
- **CHANGELOG.md**: Detailed change history
- **ARCHITECTURE_DESIGN.md**: System architecture and design patterns
- **VALIDATION_CHECKLIST.md**: Quality assurance procedures

### Recent Improvements (2026-01-10)
- **code_quality_review.md**: Comprehensive architecture review (all critical issues resolved)
- **FIXES_SUMMARY.md**: Summary of all 4 critical fixes
- **ISSUE_1_FIXED.md**: Exception handling improvements
- **ISSUE_2_FIXED.md**: Path traversal security fix
- **ISSUE_3_FIXED.md**: Template refactoring details
- **ISSUE_4_FIXED.md**: Configuration validation system

### Technical Documentation
- **API_RESPONSE_VALIDATION.md**: API validation strategy
- **MODEL_AGNOSTIC_VALIDATION.md**: Model-independent validation approach
- **COMPLETENESS_IMPROVEMENTS.md**: Artifact validation improvements

## Contributing

Contributions are welcome! Please ensure:
1. All tests pass: `pytest`
2. Configuration validates: `python -c "import config; config.validate_or_exit()"`
3. Code is formatted: `ruff format .`
4. Linting passes: `ruff check .`
5. New features include tests
6. Security implications are considered

## License

[Insert License Here]
