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
PACKAGES_DIR = TRANSCRIPTS_BASE / "packages"
PROJECTS_DIR = TRANSCRIPTS_BASE / "projects"
PROMPTS_DIR = Path(__file__).parent / "prompts"
LOGS_DIR = Path(__file__).parent / "logs"

# File Suffixes
SUFFIX_FORMATTED = " - formatted.md"
SUFFIX_YAML = " - yaml.md"
SUFFIX_KEY_ITEMS_ALL = " - All Key Items.md"
SUFFIX_KEY_ITEMS_RAW_LEGACY = " - topics-themes.md"
SUFFIX_KEY_ITEMS_CLEAN = " - topics-themes-terms.md"
SUFFIX_KEY_TERMS = " - key-terms.md"
SUFFIX_BOWEN = " - bowen-references.md"
SUFFIX_EMPHASIS = " - emphasis-items.md"
SUFFIX_EMPHASIS_SCORED = " - emphasis-scored.md"
SUFFIX_ABSTRACT_INIT = " - abstract-initial.md"
SUFFIX_SUMMARY_INIT = " - summary-initial.md"
SUFFIX_SUMMARY_GEN = " - summary-generated.md"
SUFFIX_SUMMARY_VAL = " - summary-validation.txt"
SUFFIX_ABSTRACT_GEN = " - abstract-generated.md"
SUFFIX_ABSTRACT_VAL = " - abstract-validation.txt"
SUFFIX_BLOG = " - blog.md"
SUFFIX_WEBPAGE = ".html"
SUFFIX_WEBPAGE_SIMPLE = " - simple.html"
SUFFIX_PDF = ".pdf"
SUFFIX_HEADER_VAL_REPORT = " - header-validation.md"
SUFFIX_ABSTRACTS_LEGACY = " - abstracts.md"
SUFFIX_VOICE_AUDIT = " - voice-audit.json"

# Default Model
DEFAULT_MODEL = "claude-3-7-sonnet-20250219"

# Auxiliary Model (used for validation and specific generation tasks)
AUX_MODEL = "claude-haiku-4-5-20251001"

# Formatting Model (High speed/low cost for full text rewriting)
FORMATTING_MODEL = "claude-haiku-4-5-20251001"

# Default Summary Word Count
DEFAULT_SUMMARY_WORD_COUNT = 500

# Token Limits
MAX_TOKENS_FORMATTING = 32000
MAX_TOKENS_SUMMARY = 32000
MAX_TOKENS_EXTRACTION = 8192
MAX_TOKENS_AUDIT = 2000
MAX_TOKENS_HEADER_VALIDATION = 32000

# Temperature Settings
TEMP_STRICT = 0.0
TEMP_ANALYSIS = 0.2
TEMP_BALANCED = 0.3
TEMP_CREATIVE = 0.4

# Timeouts (seconds)
TIMEOUT_FORMATTING = 1200  # 20 minutes
TIMEOUT_SUMMARY = 900      # 15 minutes
TIMEOUT_DEFAULT = 300      # 5 minutes

# Prompt Filenames
PROMPT_FORMATTING_HEADER_VALIDATION_FILENAME = "Transcript Formatting Headers Validation Prompt 12.md"
PROMPT_FORMATTING_FILENAME = "Transcript Formatting Prompt v12-Lite.md"
PROMPT_EXTRACTS_FILENAME = "Transcript Summary Key Items v1.md"
PROMPT_KEY_TERMS_FILENAME = "Transcript Summary Key Terms v1.md"
PROMPT_BLOG_FILENAME = "Transcript Summary Blog Post v1.md"
PROMPT_ABSTRACT_VALIDATION_FILENAME = "abstract_quality_assessment_prompt_v2.md"
PROMPT_VOICE_AUDIT_FILENAME = "Transcript Voice Audit Prompt v1.md"
PROMPT_STRUCTURED_SUMMARY_FILENAME = "Summary Generation Prompt v1.md"
PROMPT_STRUCTURED_ABSTRACT_FILENAME = "Abstract Generation Prompt v1.md"
PROMPT_VALIDATION_COVERAGE_FILENAME = "Validation Coverage Prompt v1.md"
PROMPT_PROBLEMATIC_HEADER_TERMS_FILENAME = "problematic_header_terms_v2.md"
PROMPT_EMPHASIS_SCORING_FILENAME = "emphasis_dedection_v3_production.md"

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
    global TRANSCRIPTS_BASE, SOURCE_DIR, FORMATTED_DIR, SUMMARIES_DIR, WEBPAGES_DIR, PDFS_DIR, PROCESSED_DIR, PACKAGES_DIR, PROJECTS_DIR

    TRANSCRIPTS_BASE = Path(path)
    SOURCE_DIR = TRANSCRIPTS_BASE / "source"
    FORMATTED_DIR = TRANSCRIPTS_BASE / "formatted"
    SUMMARIES_DIR = TRANSCRIPTS_BASE / "summaries"
    WEBPAGES_DIR = TRANSCRIPTS_BASE / "webpages"
    PDFS_DIR = TRANSCRIPTS_BASE / "pdfs"
    PROCESSED_DIR = TRANSCRIPTS_BASE / "processed"
    PACKAGES_DIR = TRANSCRIPTS_BASE / "packages"
    PROJECTS_DIR = TRANSCRIPTS_BASE / "projects"
