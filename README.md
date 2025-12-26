# Transcript Processing Pipeline

A comprehensive Python application for processing academic and professional transcripts using Claude AI. The system formats, analyzes, and generates multiple output formats from raw transcript files.

## Features

- 🤖 **AI-Powered Formatting**: Uses Claude API to intelligently format raw transcripts
- ✅ **Validation System**: Ensures word preservation and content integrity
- 📊 **Multiple Output Formats**: Markdown, HTML, PDF
- 🎯 **Quality Control**: Iterative abstract validation targeting 4.5/5.0 quality scores
- 🖥️ **Dual Interface**: GUI for interactive use, CLI for automation
- 📝 **Comprehensive Summaries**: Extracts key terms, emphasis items, and generates blog posts
- 🔍 **Smart Highlighting**: Identifies and highlights Bowen theory references

## Workflow



The pipeline consists of 6 main stages:



1.  **Format & Validate** - Clean and structure raw transcripts

2.  **Add YAML** - Add metadata front matter

3.  **Generate Summaries** - Create extracts-summary with abstract, topics, and key items

4.  **Generate Blog** - Produce SEO-optimized blog posts

5.  **Validate Abstracts** - Iteratively improve abstract quality

6.  **Generate Web-PDF** - Create HTML and PDF outputs



## Detailed Workflow



The full processing pipeline, as implemented in the GUI, follows these steps:



1.  **Format & Validate**

    *   **Format Transcript**: Cleans and structures the raw text file using the Claude API. (`transcript_format.py`)

    *   **Validate Formatting**: Ensures no words were lost during formatting by comparing the source and formatted files. (`transcript_validate_format.py`)



2.  **Add YAML**

    *   Adds a YAML front-matter block to the formatted transcript for metadata. (`transcript_add_yaml.py`)



3.  **Generate Summaries & Initial Webpage**

    *   **Create Extracts Summary**: Generates a summary document containing an abstract, key discussion points, and emphasized items. (`transcript_summarize.py`)

    *   **Validate Emphasis & Bowen Items**: Checks that all quoted "emphasis" and "Bowen" items in the summary exist in the original transcript. (`transcript_validate_emphasis.py`, `transcript_validate_bowen.py`)

    *   **Extract Key Terms**: Identifies and defines key terminology from the transcript. (`transcript_summarize.py`)

    *   **Merge Terms into Summary**: Merges the key terms into the main extracts-summary document. (`transcript_merge_archival.py`)

    *   **Generate Main Webpage**: Creates the primary, two-column HTML version of the transcript with a sidebar. (`transcript_to_webpage.py`)



4.  **Create Blog Post**

    *   Generates a separate, SEO-optimized blog post from the transcript content. (`transcript_summarize.py`)



5.  **Validate Abstracts**

    *   Iteratively refines and scores the generated abstract for quality, aiming for a score of 4.5/5.0 or higher. (`transcript_validate_abstract.py`)



6.  **Generate Final Outputs (Web & PDF)**

    *   **Generate Simple Webpage**: Creates a single-column, simplified HTML version of the transcript. (`transcript_to_simple_webpage.py`)

    *   **Validate Webpage Content**: Verifies that all content from the formatted transcript is present in the simple webpage. (`transcript_validate_webpage.py`)

    *   **Generate PDF**: Creates a PDF version of the transcript from the simple webpage. (`transcript_to_pdf.py`)



7.  **Archive Source File**

    *   Moves the original source `.txt` file to the `processed` directory to prevent reprocessing.



## Quick Start

### Prerequisites

- Python 3.8 or higher
- Anthropic API key ([get one here](https://console.anthropic.com/))

### Installation

1. **Clone or download this repository**

2. **Create virtual environment**:

```bash
python3 -m venv .venv
source .venv/bin/activate  # On macOS/Linux
```

3. **Install dependencies**:

```bash
pip install -r requirements.txt
```

4. **Configure environment**:

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

5. **Set up transcript directories**:

```bash
export TRANSCRIPTS_DIR="$HOME/transcripts"
mkdir -p "$TRANSCRIPTS_DIR"/{source,formatted,summaries,webpages,pdfs,processed,prompts}
```

### Usage

#### GUI Interface (Recommended)

```bash
python transcript_processor_gui.py
```

The GUI provides:

- File selection from source directory
- Step-by-step workflow with progress indicators
- Status tracking showing completed stages
- Clear log output

#### Command Line Interface

````bash
# Format a transcript
python transcript_format.py "Title - Presenter - Date.txt"

# Generate summaries
python transcript_summarize.py "Title - Presenter - Date - formatted.md"

# Validate abstracts
# Transcript Processing Pipeline

A comprehensive Python application for processing academic and professional transcripts using Claude AI. The system formats, analyzes, and generates multiple output formats from raw transcript files.

**Maintainer:** dbgnvan2 (sole maintainer)

## Features

- 🤖 **AI-Powered Formatting**: Uses Claude API to intelligently format raw transcripts
- ✅ **Validation System**: Ensures word preservation and content integrity
- 📊 **Multiple Output Formats**: Markdown, HTML, PDF
- 🎯 **Quality Control**: Iterative abstract validation targeting 4.5/5.0 quality scores
- 🖥️ **Dual Interface**: GUI for interactive use, CLI for automation
- 📝 **Comprehensive Summaries**: Extracts key terms, emphasis items, and generates blog posts
- 🔍 **Smart Highlighting**: Identifies and highlights Bowen theory references

## Workflow

The pipeline consists of 6 main stages:

1. **Format & Validate** - Clean and structure raw transcripts
2. **Add YAML** - Add metadata front matter
3. **Generate Summaries** - Create extracts-summary with abstract, topics, and key items
4. **Generate Blog** - Produce SEO-optimized blog posts
5. **Validate Abstracts** - Iteratively improve abstract quality
6. **Generate Web-PDF** - Create HTML and PDF outputs

## Quick Start

### Prerequisites

- Python 3.8 or higher
- Anthropic API key ([get one here](https://console.anthropic.com/))

### Installation

1. **Clone or download this repository**

2. **Create virtual environment**:

```bash
python3 -m venv .venv
source .venv/bin/activate  # On macOS/Linux
````

3. **Install dependencies**:

```bash
pip install -r requirements.txt
```

4. **Configure environment**:

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

5. **Set up transcript directories**:

```bash
export TRANSCRIPTS_DIR="$HOME/transcripts"
mkdir -p "$TRANSCRIPTS_DIR"/{source,formatted,summaries,webpages,pdfs,processed,prompts}
```

### Usage

#### GUI Interface (Recommended)

```bash
python transcript_processor_gui.py
```

The GUI provides:

- File selection from source directory
- Step-by-step workflow with progress indicators
- Status tracking showing completed stages
- Clear log output

#### Command Line Interface

```bash
# Format a transcript
python transcript_format.py "Title - Presenter - Date.txt"

# Generate summaries
python transcript_summarize.py "Title - Presenter - Date - formatted.md"

# Validate abstracts
python transcript_validate_abstract.py "Title - Presenter - Date"

# Generate webpage and PDF
python transcript_to_webpage.py "Title - Presenter - Date"
python transcript_to_pdf.py "Title - Presenter - Date"
```

## File Structure

```
~/transcripts/
├── source/           # Raw transcript files (.txt)
├── formatted/        # Formatted transcripts with YAML metadata
├── summaries/        # All summary outputs
│   ├── *-extracts-summary.md
│   ├── *-key-terms.md
│   ├── *-blog.md
│   └── *-abstracts.md
├── webpages/         # HTML outputs
├── pdfs/             # PDF outputs
├── processed/        # Archived source files
└── prompts/          # Claude AI prompt templates
```

## Output Files

Each transcript generates multiple outputs:

- **formatted.md** - Structured transcript with speaker labels
- **formatted_yaml.md** - Formatted file with YAML metadata
- **extracts-summary.md** - Comprehensive summary with abstract, topics, themes, key items
- **key-terms.md** - Terminology and definitions
- **blog.md** - SEO-optimized blog post
- **abstracts.md** - Quality-validated abstracts (short and extended)
- **.html** - Two-column webpage with highlighting
- **.pdf** - Publication-ready PDF

## Configuration

### Environment Variables

- `ANTHROPIC_API_KEY` - Your Anthropic API key (required)
- `TRANSCRIPTS_DIR` - Base directory for all transcript files (default: `~/transcripts`)

### File Naming Convention

All files must follow this pattern:

```
Title - Presenter - Date.ext
```

Examples:

- `Roots of Bowen Theory - Dr Michael Kerr - 2019-11-15.txt`
- `Emotional Process in Society - Kerr and Bowen - 1981-03-20.txt`

## Script Reference

| Script                            | Purpose                       | Usage                                               |
| --------------------------------- | ----------------------------- | --------------------------------------------------- |
| `transcript_processor_gui.py`     | Main GUI application          | Interactive workflow                                |
| `transcript_format.py`            | Format raw transcripts        | `python transcript_format.py "file.txt"`            |
| `transcript_validate_format.py`   | Validate word preservation    | Automatic in pipeline                               |
| `transcript_add_yaml.py`          | Add YAML front matter         | `python transcript_add_yaml.py "file.txt"`          |
| `transcript_summarize.py`         | Generate summaries            | `python transcript_summarize.py "formatted.md"`     |
| `transcript_validate_abstract.py` | Validate abstract quality     | `python transcript_validate_abstract.py "basename"` |
| `transcript_validate_webpage.py`  | Validate webpage completeness | `python transcript_validate_webpage.py "basename"`  |
| `transcript_to_webpage.py`        | Generate HTML (sidebar)       | `python transcript_to_webpage.py "basename"`        |
| `transcript_to_simple_webpage.py` | Generate HTML (single-column) | `python transcript_to_simple_webpage.py "basename"` |
| `transcript_to_pdf.py`            | Generate PDF                  | `python transcript_to_pdf.py "basename"`            |

## Validation Features

### Word Preservation

Ensures formatting doesn't alter content by comparing source and formatted files word-by-word.

### Emphasis Validation

Verifies all quoted text exists in the source using fuzzy matching (85% threshold).

### Abstract Quality

Iteratively improves abstracts across 5 dimensions with **interactive user control**:

- Content Accuracy (1-5)
- Structural Organization (1-5)
- Language Quality (1-5)
- Completeness (1-5)
- Professional Tone (1-5)

**Features:**

- Evaluates initial abstract quality (Iteration 0 baseline)
- Shows score breakdown after each iteration
- Prompts user to continue or stop when satisfied
- Always uses best iteration result
- Target: 4.5+ average score

### Webpage Validation

Deterministic Python validation of generated webpages:

- **Section counting**: Verifies all sections from formatted file appear in HTML
- **Metadata verification**: Validates Abstract, Topics, Themes, and Key Terms
- **Content sampling**: Checks 30% of items with fuzzy text matching
- **Highlighting counts**: Verifies Bowen references and emphasis items
- **Dual format support**: Both sidebar and simple webpage layouts

Run with: `python transcript_validate_webpage.py "basename" [--simple]`

## Development

### Project Structure

```
trans-summary/
├── transcript_*.py        # Core processing scripts
├── ARCHITECTURE_DESIGN.md # High-level architecture and design overview
├── CODE_REVIEW.md         # Detailed code review and recommendations
├── DOCUMENT_REFERENCE.md  # Output format specifications
├── requirements.txt       # Python dependencies
├── .env.example          # Environment configuration template
└── oldfiles/             # Archived legacy scripts
```

### Dependencies

- **anthropic**: Claude API client
- **weasyprint**: HTML to PDF conversion
- **pillow**: Image processing for PDF generation
- **python-dotenv**: Environment variable management

## Troubleshooting

### "ANTHROPIC_API_KEY not set"

Make sure you've created a `.env` file with your API key:

```bash
cp .env.example .env
# Edit .env and add your key
```

### GUI button not enabling

Check that previous steps completed successfully. The GUI enforces workflow sequence:

- Format must complete before YAML
- YAML must exist before summaries
- Summaries must exist before blog/validation/web-PDF

### Validation failures

If word preservation validation fails, it usually means:

- Speaker labels weren't properly removed
- Extra text was added during formatting
- Use the "Continue anyway?" prompt if you've verified the content is correct

## Cost Estimates

Approximate Claude API costs per transcript (using Claude Sonnet 4):

- Format: ~$0.10-0.50 (depends on length)
- Summaries: ~$0.30-0.80
- Blog: ~$0.20-0.40
- Abstract validation: ~$0.10-0.30 (iterative)
- **Total**: ~$0.70-2.00 per transcript

## License

This project is for academic and professional use. See LICENSE file for details.

## Contributing

This repository is maintained by a single developer (the maintainer above). If you'd like to suggest changes or report issues, please open an issue on GitHub; external pull requests will be reviewed by the maintainer.

## Support

For issues or questions, refer to:

- [CODE_REVIEW.md](CODE_REVIEW.md) - Detailed technical documentation
- [DOCUMENT_REFERENCE.md](DOCUMENT_REFERENCE.md) - Output format specifications

## Credits

Built with Claude AI (Anthropic) for transcript processing and content generation.
