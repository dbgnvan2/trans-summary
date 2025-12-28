"""
Configuration for the transcript processing pipeline.
This module holds global variables for directory paths, which can be
updated by the GUI at runtime.
"""

from pathlib import Path
import os

# Default directories. By default, paths are relative to the project root.
TRANSCRIPTS_BASE = Path(os.getenv("TRANSCRIPTS_DIR", "."))
SOURCE_DIR = TRANSCRIPTS_BASE / "source"
FORMATTED_DIR = TRANSCRIPTS_BASE / "formatted"
SUMMARIES_DIR = TRANSCRIPTS_BASE / "summaries"
WEBPAGES_DIR = TRANSCRIPTS_BASE / "webpages"
PDFS_DIR = TRANSCRIPTS_BASE / "pdfs"
PROCESSED_DIR = TRANSCRIPTS_BASE / "processed"
PROMPTS_DIR = TRANSCRIPTS_BASE / "prompts"
LOGS_DIR = Path(__file__).parent / "logs"

# Default Model
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

# Auxiliary Model (used for validation and specific generation tasks)
AUX_MODEL = "claude-sonnet-4-20250514"

# Default Summary Word Count
DEFAULT_SUMMARY_WORD_COUNT = 500

# Token Limits
MAX_TOKENS_FORMATTING = 32000
MAX_TOKENS_SUMMARY = 32000
MAX_TOKENS_EXTRACTION = 8192
MAX_TOKENS_AUDIT = 2000

# Prompt Filenames
PROMPT_FORMATTING_FILENAME = "Transcript Formatting Prompt v11.md"
PROMPT_EXTRACTS_FILENAME = "Transcript Summary Key Items v1.md"
PROMPT_KEY_TERMS_FILENAME = "Transcript Summary Key Terms v1.md"
PROMPT_BLOG_FILENAME = "Transcript Summary Blog Post v1.md"
PROMPT_ABSTRACT_VALIDATION_FILENAME = "abstract_quality_assessment_prompt_v2.md"
PROMPT_VOICE_AUDIT_FILENAME = "Transcript Voice Audit Prompt v1.md"
PROMPT_STRUCTURED_SUMMARY_FILENAME = "Summary Generation Prompt v1.md"
PROMPT_STRUCTURED_ABSTRACT_FILENAME = "Abstract Generation Prompt v1.md"
PROMPT_VALIDATION_COVERAGE_FILENAME = "Validation Coverage Prompt v1.md"

# Validation Settings
VALIDATION_MISMATCH_RATIO = 0.015  # 1.5% tolerance
VALIDATION_LOOKAHEAD_WINDOW = 10

# Minimum Generation Lengths
MIN_EXTRACTS_PERCENT = 0.04  # 4% of transcript word count
TARGET_EXTRACTS_PERCENT = 0.07  # 7% target for generation guidance
MIN_EXTRACTS_WORDS_FLOOR = 150
MIN_TRANSCRIPT_WORDS_FOR_FLOOR = 1000
MIN_EXTRACTS_WORDS_ABSOLUTE = 50
MIN_EXTRACTS_CHARS = 500
MIN_KEY_TERMS_CHARS = 100
MIN_BLOG_CHARS = 1000
MIN_ABSTRACT_VALIDATION_CHARS = 50

# Abstract Settings
ABSTRACT_TARGET_PERCENT = 0.03  # 3% of transcript word count
ABSTRACT_MIN_WORDS = 150

# Summary Structure Allocations
SUMMARY_OPENING_PCT = 0.14
SUMMARY_CLOSING_PCT = 0.06
SUMMARY_QA_PCT = 0.10

# Validation Thresholds
TRANSCRIPT_MIN_WORDS = 1500
BLOG_MIN_WORDS = 800
EVALUATIVE_TERMS = ['valuable', 'insightful', 'excellent']

# Token Estimation & Safety
CHARS_PER_TOKEN = 4
TOKEN_BUDGET_SAFETY_MARGIN = 0.8
TOKEN_USAGE_WARNING_THRESHOLD = 0.9

# Fuzzy Matching Settings
FUZZY_MATCH_THRESHOLD = 0.85
FUZZY_MATCH_EARLY_STOP = 0.98
FUZZY_MATCH_PREFIX_LEN = 20


def set_transcripts_base(path: str | Path):
    """Update the base directory for transcripts and all related paths."""
    global TRANSCRIPTS_BASE, SOURCE_DIR, FORMATTED_DIR, SUMMARIES_DIR, WEBPAGES_DIR, PDFS_DIR, PROCESSED_DIR, PROMPTS_DIR

    TRANSCRIPTS_BASE = Path(path)
    SOURCE_DIR = TRANSCRIPTS_BASE / "source"
    FORMATTED_DIR = TRANSCRIPTS_BASE / "formatted"
    SUMMARIES_DIR = TRANSCRIPTS_BASE / "summaries"
    WEBPAGES_DIR = TRANSCRIPTS_BASE / "webpages"
    PDFS_DIR = TRANSCRIPTS_BASE / "pdfs"
    PROCESSED_DIR = TRANSCRIPTS_BASE / "processed"
    PROMPTS_DIR = TRANSCRIPTS_BASE / "prompts"
