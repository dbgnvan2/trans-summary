"""
Configuration for the transcript processing pipeline.
This module holds global variables for directory paths, which can be
updated by the GUI at runtime.

REFACTOR NOTE: This file now uses a Singleton pattern for settings.
Direct access to variables (e.g. config.SOURCE_DIR) is proxied to the singleton instance
to maintain backward compatibility while enabling safer state management.
"""

from pathlib import Path
import os
from typing import Union

class ProjectSettings:
    """
    Singleton class to manage project settings and paths.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProjectSettings, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        # Default initialization
        self.TRANSCRIPTS_BASE = Path(os.getenv("TRANSCRIPTS_DIR", "."))
        self._update_derived_paths()
        self._initialized = True

    def _update_derived_paths(self):
        """Update paths derived from TRANSCRIPTS_BASE."""
        self.SOURCE_DIR = self.TRANSCRIPTS_BASE / "source"
        self.PROCESSED_DIR = self.TRANSCRIPTS_BASE / "processed"
        self.PROJECTS_DIR = self.TRANSCRIPTS_BASE / "projects"
        self.PROMPTS_DIR = Path(__file__).parent / "prompts"
        self.LOGS_DIR = Path(__file__).parent / "logs"

    def set_transcripts_base(self, path: Union[str, Path]):
        """Update the base directory for transcripts and all related paths."""
        self.TRANSCRIPTS_BASE = Path(path)
        self._update_derived_paths()

# Initialize the singleton
settings = ProjectSettings()

# ============================================================================
# BACKWARD COMPATIBILITY PROXIES
# ============================================================================
# These properties allow existing code to continue using `config.SOURCE_DIR`
# while actually reading from the singleton `settings` object.

def __getattr__(name):
    if hasattr(settings, name):
        return getattr(settings, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

# Explicitly define for static analysis tools (optional but good practice)
TRANSCRIPTS_BASE = settings.TRANSCRIPTS_BASE
SOURCE_DIR = settings.SOURCE_DIR
PROCESSED_DIR = settings.PROCESSED_DIR
PROJECTS_DIR = settings.PROJECTS_DIR
PROMPTS_DIR = settings.PROMPTS_DIR
LOGS_DIR = settings.LOGS_DIR


def set_transcripts_base(path: Union[str, Path]):
    """Global function to update the singleton settings."""
    settings.set_transcripts_base(path)
    # Update module-level globals to reflect the change for code that imported them directly
    # (Note: Code that did `from config import SOURCE_DIR` will still have the OLD value.
    # This is why `import config; config.SOURCE_DIR` is preferred.)
    global TRANSCRIPTS_BASE, SOURCE_DIR, PROCESSED_DIR, PROJECTS_DIR
    TRANSCRIPTS_BASE = settings.TRANSCRIPTS_BASE
    SOURCE_DIR = settings.SOURCE_DIR
    PROCESSED_DIR = settings.PROCESSED_DIR
    PROJECTS_DIR = settings.PROJECTS_DIR


# ============================================================================
# CONSTANTS (Stateless)
# ============================================================================

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
PROMPT_BOWEN_EXTRACTION_FILENAME = "bowen_reference_extraction_v1.md"

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