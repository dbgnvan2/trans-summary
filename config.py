"""
Configuration for the transcript processing pipeline.
This module holds global variables for directory paths, which can be
updated by the GUI at runtime.

REFACTOR NOTE: This file now uses a Singleton pattern for settings.
Direct access to variables (e.g. config.SOURCE_DIR) is proxied to the singleton instance
to maintain backward compatibility while enabling safer state management.
"""

import os
import sys
from pathlib import Path
from typing import Union, Dict, List, Tuple
import model_specs  # ADDED: Import model_specs


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
        if getattr(self, "_initialized", False):
            return

        # Default initialization
        self.TRANSCRIPTS_BASE = Path(os.getenv("TRANSCRIPTS_DIR", "."))
        self._update_derived_paths()

        # Initialize model variables
        self.DEFAULT_MODEL = "claude-sonnet-4-20250514"  # Successor default to Claude 3.7 Sonnet
        self.AUX_MODEL = "claude-3-5-haiku-20241022"      # Updated for Caching Support
        self.FORMATTING_MODEL = "claude-3-7-sonnet-20250219" # Extended Output Support with Caching
        self.VALIDATION_MODEL = "claude-3-5-haiku-20241022" # Cheaper model for validation

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

    # ADDED: Methods to dynamically get and set model names
    def get_all_model_names(self) -> list[str]:
        """Returns a list of all model names from model_specs.PRICING."""
        return sorted(model_specs.PRICING.keys())

    def set_default_model(self, model_name: str):
        if model_name in model_specs.PRICING:
            self.DEFAULT_MODEL = model_name
        else:
            raise ValueError(
                f"Model '{model_name}' not found in model_specs.PRICING.")

    def set_aux_model(self, model_name: str):
        if model_name in model_specs.PRICING:
            self.AUX_MODEL = model_name
        else:
            raise ValueError(
                f"Model '{model_name}' not found in model_specs.PRICING.")

    def set_formatting_model(self, model_name: str):
        if model_name in model_specs.PRICING:
            self.FORMATTING_MODEL = model_name
        else:
            raise ValueError(
                f"Model '{model_name}' not found in model_specs.PRICING.")


# Initialize the singleton
settings = ProjectSettings()

# ============================================================================
# BACKWARD COMPATIBILITY PROXIES
# ============================================================================
# These properties allow existing code to continue using `config.SOURCE_DIR`
# while actually reading from the singleton `settings` object.


def __getattr__(name):
    # Only proxy for non-existent attributes to allow direct access to
    # attributes already defined on the module (like SUFFIX_FORMATTED)
    # and to the model variables.
    # ADDED explicit check for model variables
    if name in ["DEFAULT_MODEL", "AUX_MODEL", "FORMATTING_MODEL", "VALIDATION_MODEL"]:
        return getattr(settings, name)
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

# ADDED: Expose model variables as globals for backward compatibility and direct access
DEFAULT_MODEL = settings.DEFAULT_MODEL
AUX_MODEL = settings.AUX_MODEL
FORMATTING_MODEL = settings.FORMATTING_MODEL
VALIDATION_MODEL = settings.VALIDATION_MODEL


def set_transcripts_base(path: Union[str, Path]):
    """Global function to update the singleton settings."""
    settings.set_transcripts_base(path)
    # Update module-level globals to reflect the change for code that imported them directly
    # (Note: Code that did `from config import SOURCE_DIR` will still have the OLD value.
    # This is why `import config; config.SOURCE_DIR` is preferred.)
    global TRANSCRIPTS_BASE, SOURCE_DIR, PROCESSED_DIR, PROJECTS_DIR
    # ADDED: Make model variables global
    global DEFAULT_MODEL, AUX_MODEL, FORMATTING_MODEL
    TRANSCRIPTS_BASE = settings.TRANSCRIPTS_BASE
    SOURCE_DIR = settings.SOURCE_DIR
    PROCESSED_DIR = settings.PROCESSED_DIR
    PROJECTS_DIR = settings.PROJECTS_DIR
    # Update global model variables from settings object
    DEFAULT_MODEL = settings.DEFAULT_MODEL
    AUX_MODEL = settings.AUX_MODEL
    FORMATTING_MODEL = settings.FORMATTING_MODEL


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

# Model variables moved into ProjectSettings and exposed as globals
# Defaults: DEFAULT_MODEL = "claude-sonnet-4-20250514"
#           AUX_MODEL = "claude-3-5-haiku-20241022"
#           FORMATTING_MODEL = "claude-3-7-sonnet-20250219"

# Default Summary Word Count
# Set to 650 - Claude 3.7 Sonnet tends to generate slightly more
# Typically results in 700-900 word summaries
DEFAULT_SUMMARY_WORD_COUNT = 650

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
TIMEOUT_SUMMARY = 900  # 15 minutes
TIMEOUT_DEFAULT = 300  # 5 minutes

# Prompt Filenames
PROMPT_FORMATTING_HEADER_VALIDATION_FILENAME = (
    "Transcript Formatting Headers Validation Prompt 12.md"
)
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
PROMPT_BOWEN_FILTER_FILENAME = "bowen_reference_filter_v1.md"

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
EVALUATIVE_TERMS = ["valuable", "insightful", "excellent"]

# Token Estimation & Safety
CHARS_PER_TOKEN = 4
TOKEN_BUDGET_SAFETY_MARGIN = 0.8
TOKEN_USAGE_WARNING_THRESHOLD = 0.9

# Fuzzy Matching Settings
FUZZY_MATCH_THRESHOLD = 0.85
FUZZY_MATCH_EARLY_STOP = 0.98
FUZZY_MATCH_PREFIX_LEN = 20

# ============================================================================
# VALIDATION V2 SETTINGS
# ============================================================================

# Chunked Processing
VALIDATION_CHUNK_SIZE = 1500           # WORDS per chunk (not tokens)
VALIDATION_CHUNK_OVERLAP = 200         # WORDS overlap

# Context Requirements
VALIDATION_MIN_CONTEXT_WORDS = 5       # Min words for unique context
VALIDATION_MAX_CONTEXT_WORDS = 30      # Max words to include
VALIDATION_MIN_UNIQUE_WORDS = 7        # Threshold for ambiguous matches

# Fuzzy Matching Thresholds (V2)
VALIDATION_FUZZY_AUTO_APPLY = 0.95     # 95% similarity for auto-apply
VALIDATION_FUZZY_REVIEW = 0.90         # 90% for manual review
VALIDATION_FUZZY_REJECT = 0.85         # < 85% reject
VALIDATION_FUZZY_HALLUCINATION = 0.85  # Hallucination detection threshold

# Confidence Filtering
VALIDATION_AUTO_APPLY_CONFIDENCE = {'high'}
VALIDATION_REVIEW_CONFIDENCE = {'medium'}
VALIDATION_SKIP_CONFIDENCE = {'low'}

# Iteration Control
VALIDATION_MAX_ITERATIONS = 5
VALIDATION_STALL_THRESHOLD = 0.20      # Stop if < 20% improvement
VALIDATION_MAX_STALLED_ITERATIONS = 2

# Error Types
VALIDATION_ERROR_TYPES = {
    'spelling', 'homophone', 'proper_noun', 'word_boundary',
    'capitalization', 'repetition', 'punctuation', 'incomplete', 'grammar'
}

# Logging
VALIDATION_VERBOSE_LOGGING = True
VALIDATION_SAVE_REVIEW_FILE = True


# ============================================================================
# CONFIGURATION VALIDATION
# ============================================================================

class ValidationResult:
    """Stores validation results with errors and warnings."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def add_error(self, message: str):
        """Add a critical error that prevents operation."""
        self.errors.append(message)

    def add_warning(self, message: str):
        """Add a warning that should be reviewed but doesn't prevent operation."""
        self.warnings.append(message)

    def is_valid(self) -> bool:
        """Returns True if no errors (warnings are allowed)."""
        return len(self.errors) == 0

    def format_report(self) -> str:
        """Format a human-readable validation report."""
        lines = []

        if self.errors:
            lines.append("=" * 70)
            lines.append("❌ CONFIGURATION ERRORS")
            lines.append("=" * 70)
            for i, error in enumerate(self.errors, 1):
                lines.append(f"{i}. {error}")
            lines.append("")

        if self.warnings:
            lines.append("=" * 70)
            lines.append("⚠️  CONFIGURATION WARNINGS")
            lines.append("=" * 70)
            for i, warning in enumerate(self.warnings, 1):
                lines.append(f"{i}. {warning}")
            lines.append("")

        if not self.errors and not self.warnings:
            lines.append("✅ Configuration validation passed - no issues found.")

        return "\n".join(lines)


def validate_configuration(verbose: bool = True, auto_fix: bool = False) -> ValidationResult:
    """
    Validates all configuration settings for correctness and consistency.

    Args:
        verbose: If True, print validation report to stdout
        auto_fix: If True, attempt to fix issues (e.g., create missing directories)

    Returns:
        ValidationResult with any errors and warnings found

    Raises:
        SystemExit: If critical errors found and not in test mode
    """
    result = ValidationResult()

    # ========================================================================
    # 1. VALIDATE DIRECTORY PATHS
    # ========================================================================

    # Check TRANSCRIPTS_BASE exists or is creatable
    if not settings.TRANSCRIPTS_BASE.exists():
        if auto_fix:
            try:
                settings.TRANSCRIPTS_BASE.mkdir(parents=True, exist_ok=True)
                result.add_warning(f"Created TRANSCRIPTS_BASE directory: {settings.TRANSCRIPTS_BASE}")
            except Exception as e:
                result.add_error(
                    f"TRANSCRIPTS_BASE does not exist and cannot be created: {settings.TRANSCRIPTS_BASE}\n"
                    f"  Error: {e}\n"
                    f"  Fix: Set TRANSCRIPTS_DIR environment variable or ensure directory is writable"
                )
        else:
            result.add_error(
                f"TRANSCRIPTS_BASE directory does not exist: {settings.TRANSCRIPTS_BASE}\n"
                f"  Fix: Create directory or set TRANSCRIPTS_DIR environment variable\n"
                f"  Example: export TRANSCRIPTS_DIR=/path/to/transcripts"
            )
    elif not settings.TRANSCRIPTS_BASE.is_dir():
        result.add_error(
            f"TRANSCRIPTS_BASE exists but is not a directory: {settings.TRANSCRIPTS_BASE}\n"
            f"  Fix: Remove file and create directory, or choose different location"
        )
    elif not os.access(settings.TRANSCRIPTS_BASE, os.W_OK):
        result.add_warning(
            f"TRANSCRIPTS_BASE is not writable: {settings.TRANSCRIPTS_BASE}\n"
            f"  This may cause issues when creating processed files\n"
            f"  Fix: chmod +w {settings.TRANSCRIPTS_BASE}"
        )

    # Check derived directories
    derived_dirs = {
        "SOURCE_DIR": settings.SOURCE_DIR,
        "PROCESSED_DIR": settings.PROCESSED_DIR,
        "PROJECTS_DIR": settings.PROJECTS_DIR,
    }

    for name, path in derived_dirs.items():
        if not path.exists():
            if auto_fix:
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    result.add_warning(f"Created {name}: {path}")
                except Exception as e:
                    result.add_error(
                        f"{name} does not exist and cannot be created: {path}\n"
                        f"  Error: {e}\n"
                        f"  Fix: Ensure parent directory {settings.TRANSCRIPTS_BASE} is writable"
                    )
            else:
                result.add_warning(
                    f"{name} does not exist: {path}\n"
                    f"  Will be created automatically when needed\n"
                    f"  Or run: validate_configuration(auto_fix=True)"
                )

    # Check PROMPTS_DIR exists
    if not settings.PROMPTS_DIR.exists():
        result.add_error(
            f"PROMPTS_DIR does not exist: {settings.PROMPTS_DIR}\n"
            f"  This directory should contain prompt template files\n"
            f"  Fix: Create directory and add prompt files\n"
            f"  Expected location: {Path(__file__).parent / 'prompts'}"
        )
    elif not settings.PROMPTS_DIR.is_dir():
        result.add_error(
            f"PROMPTS_DIR exists but is not a directory: {settings.PROMPTS_DIR}\n"
            f"  Fix: Remove file and create directory with prompt files"
        )

    # Check LOGS_DIR is writable
    if not settings.LOGS_DIR.exists():
        if auto_fix:
            try:
                settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
                result.add_warning(f"Created LOGS_DIR: {settings.LOGS_DIR}")
            except Exception as e:
                result.add_error(
                    f"LOGS_DIR does not exist and cannot be created: {settings.LOGS_DIR}\n"
                    f"  Error: {e}\n"
                    f"  Fix: Ensure application directory is writable"
                )
    elif not os.access(settings.LOGS_DIR, os.W_OK):
        result.add_error(
            f"LOGS_DIR is not writable: {settings.LOGS_DIR}\n"
            f"  Logging will fail without write access\n"
            f"  Fix: chmod +w {settings.LOGS_DIR}"
        )

    # ========================================================================
    # 2. VALIDATE MODEL NAMES
    # ========================================================================

    models_to_check = {
        "DEFAULT_MODEL": settings.DEFAULT_MODEL,
        "AUX_MODEL": settings.AUX_MODEL,
        "FORMATTING_MODEL": settings.FORMATTING_MODEL,
        "VALIDATION_MODEL": settings.VALIDATION_MODEL,
    }

    available_models = sorted(model_specs.PRICING.keys())

    for model_var, model_name in models_to_check.items():
        if model_name not in model_specs.PRICING:
            result.add_error(
                f"{model_var} specifies unknown model: '{model_name}'\n"
                f"  Available models: {', '.join(available_models[:5])}...\n"
                f"  Fix: Update config.py or set via settings.set_{model_var.lower()}()\n"
                f"  Example: settings.set_default_model('claude-sonnet-4-20250514')"
            )

    # ========================================================================
    # 3. VALIDATE NUMERIC RANGES
    # ========================================================================

    # Token limits (must be positive)
    token_limits = {
        "MAX_TOKENS_FORMATTING": MAX_TOKENS_FORMATTING,
        "MAX_TOKENS_SUMMARY": MAX_TOKENS_SUMMARY,
        "MAX_TOKENS_EXTRACTION": MAX_TOKENS_EXTRACTION,
        "MAX_TOKENS_AUDIT": MAX_TOKENS_AUDIT,
        "MAX_TOKENS_HEADER_VALIDATION": MAX_TOKENS_HEADER_VALIDATION,
    }

    for name, value in token_limits.items():
        if not isinstance(value, int) or value <= 0:
            result.add_error(
                f"{name} must be a positive integer, got: {value}\n"
                f"  Fix: Set to reasonable token limit (e.g., 8192, 32000)"
            )
        elif value > 200000:  # Claude's max context
            result.add_warning(
                f"{name} exceeds Claude's maximum context window (200,000): {value}\n"
                f"  This may cause API errors\n"
                f"  Fix: Reduce to ≤ 200000"
            )

    # Temperatures (must be 0.0 to 1.0)
    temperatures = {
        "TEMP_STRICT": TEMP_STRICT,
        "TEMP_ANALYSIS": TEMP_ANALYSIS,
        "TEMP_BALANCED": TEMP_BALANCED,
        "TEMP_CREATIVE": TEMP_CREATIVE,
    }

    for name, value in temperatures.items():
        if not isinstance(value, (int, float)) or not (0.0 <= value <= 1.0):
            result.add_error(
                f"{name} must be between 0.0 and 1.0, got: {value}\n"
                f"  0.0 = deterministic, 1.0 = maximum creativity\n"
                f"  Fix: Set to value in range [0.0, 1.0]"
            )

    # Timeouts (must be positive)
    timeouts = {
        "TIMEOUT_FORMATTING": TIMEOUT_FORMATTING,
        "TIMEOUT_SUMMARY": TIMEOUT_SUMMARY,
        "TIMEOUT_DEFAULT": TIMEOUT_DEFAULT,
    }

    for name, value in timeouts.items():
        if not isinstance(value, (int, float)) or value <= 0:
            result.add_error(
                f"{name} must be a positive number (seconds), got: {value}\n"
                f"  Fix: Set to reasonable timeout (e.g., 300 for 5 minutes)"
            )
        elif value < 10:
            result.add_warning(
                f"{name} is very short: {value} seconds\n"
                f"  May cause premature timeouts for long operations\n"
                f"  Consider: Increase to ≥ 60 seconds"
            )

    # Percentages (must be 0.0 to 1.0)
    percentages = {
        "MIN_EXTRACTS_PERCENT": MIN_EXTRACTS_PERCENT,
        "TARGET_EXTRACTS_PERCENT": TARGET_EXTRACTS_PERCENT,
        "ABSTRACT_TARGET_PERCENT": ABSTRACT_TARGET_PERCENT,
        "SUMMARY_OPENING_PCT": SUMMARY_OPENING_PCT,
        "SUMMARY_CLOSING_PCT": SUMMARY_CLOSING_PCT,
        "SUMMARY_QA_PCT": SUMMARY_QA_PCT,
        "TOKEN_BUDGET_SAFETY_MARGIN": TOKEN_BUDGET_SAFETY_MARGIN,
        "TOKEN_USAGE_WARNING_THRESHOLD": TOKEN_USAGE_WARNING_THRESHOLD,
        "FUZZY_MATCH_THRESHOLD": FUZZY_MATCH_THRESHOLD,
        "FUZZY_MATCH_EARLY_STOP": FUZZY_MATCH_EARLY_STOP,
        "VALIDATION_FUZZY_AUTO_APPLY": VALIDATION_FUZZY_AUTO_APPLY,
        "VALIDATION_FUZZY_REVIEW": VALIDATION_FUZZY_REVIEW,
        "VALIDATION_FUZZY_REJECT": VALIDATION_FUZZY_REJECT,
        "VALIDATION_FUZZY_HALLUCINATION": VALIDATION_FUZZY_HALLUCINATION,
        "VALIDATION_MISMATCH_RATIO": VALIDATION_MISMATCH_RATIO,
        "VALIDATION_STALL_THRESHOLD": VALIDATION_STALL_THRESHOLD,
    }

    for name, value in percentages.items():
        if not isinstance(value, (int, float)) or not (0.0 <= value <= 1.0):
            result.add_error(
                f"{name} must be between 0.0 and 1.0, got: {value}\n"
                f"  This represents a percentage or ratio\n"
                f"  Fix: Set to value in range [0.0, 1.0]"
            )

    # Word counts (must be positive integers)
    word_counts = {
        "DEFAULT_SUMMARY_WORD_COUNT": DEFAULT_SUMMARY_WORD_COUNT,
        "MIN_EXTRACTS_WORDS_FLOOR": MIN_EXTRACTS_WORDS_FLOOR,
        "MIN_TRANSCRIPT_WORDS_FOR_FLOOR": MIN_TRANSCRIPT_WORDS_FOR_FLOOR,
        "MIN_EXTRACTS_WORDS_ABSOLUTE": MIN_EXTRACTS_WORDS_ABSOLUTE,
        "ABSTRACT_MIN_WORDS": ABSTRACT_MIN_WORDS,
        "TRANSCRIPT_MIN_WORDS": TRANSCRIPT_MIN_WORDS,
        "BLOG_MIN_WORDS": BLOG_MIN_WORDS,
        "VALIDATION_CHUNK_SIZE": VALIDATION_CHUNK_SIZE,
        "VALIDATION_CHUNK_OVERLAP": VALIDATION_CHUNK_OVERLAP,
        "VALIDATION_MIN_CONTEXT_WORDS": VALIDATION_MIN_CONTEXT_WORDS,
        "VALIDATION_MAX_CONTEXT_WORDS": VALIDATION_MAX_CONTEXT_WORDS,
        "VALIDATION_MIN_UNIQUE_WORDS": VALIDATION_MIN_UNIQUE_WORDS,
    }

    for name, value in word_counts.items():
        if not isinstance(value, int) or value <= 0:
            result.add_error(
                f"{name} must be a positive integer, got: {value}\n"
                f"  Fix: Set to reasonable word count (e.g., 100, 500, 1500)"
            )

    # Character counts (must be positive integers)
    char_counts = {
        "MIN_EXTRACTS_CHARS": MIN_EXTRACTS_CHARS,
        "MIN_KEY_TERMS_CHARS": MIN_KEY_TERMS_CHARS,
        "MIN_BLOG_CHARS": MIN_BLOG_CHARS,
        "MIN_ABSTRACT_VALIDATION_CHARS": MIN_ABSTRACT_VALIDATION_CHARS,
        "CHARS_PER_TOKEN": CHARS_PER_TOKEN,
        "VALIDATION_FUZZY_PREFIX_LEN": FUZZY_MATCH_PREFIX_LEN,
    }

    for name, value in char_counts.items():
        if not isinstance(value, int) or value <= 0:
            result.add_error(
                f"{name} must be a positive integer, got: {value}\n"
                f"  Fix: Set to reasonable character count"
            )

    # Iteration controls
    if not isinstance(VALIDATION_MAX_ITERATIONS, int) or VALIDATION_MAX_ITERATIONS <= 0:
        result.add_error(
            f"VALIDATION_MAX_ITERATIONS must be positive integer, got: {VALIDATION_MAX_ITERATIONS}\n"
            f"  Fix: Set to reasonable iteration limit (e.g., 3, 5, 10)"
        )

    if not isinstance(VALIDATION_MAX_STALLED_ITERATIONS, int) or VALIDATION_MAX_STALLED_ITERATIONS <= 0:
        result.add_error(
            f"VALIDATION_MAX_STALLED_ITERATIONS must be positive integer, got: {VALIDATION_MAX_STALLED_ITERATIONS}\n"
            f"  Fix: Set to reasonable iteration limit (e.g., 2, 3)"
        )

    if not isinstance(VALIDATION_LOOKAHEAD_WINDOW, int) or VALIDATION_LOOKAHEAD_WINDOW <= 0:
        result.add_error(
            f"VALIDATION_LOOKAHEAD_WINDOW must be positive integer, got: {VALIDATION_LOOKAHEAD_WINDOW}\n"
            f"  Fix: Set to reasonable window size (e.g., 5, 10, 20)"
        )

    # ========================================================================
    # 4. VALIDATE PROMPT FILES
    # ========================================================================

    if settings.PROMPTS_DIR.exists():
        prompt_files = {
            "PROMPT_FORMATTING_HEADER_VALIDATION_FILENAME": PROMPT_FORMATTING_HEADER_VALIDATION_FILENAME,
            "PROMPT_FORMATTING_FILENAME": PROMPT_FORMATTING_FILENAME,
            "PROMPT_EXTRACTS_FILENAME": PROMPT_EXTRACTS_FILENAME,
            "PROMPT_KEY_TERMS_FILENAME": PROMPT_KEY_TERMS_FILENAME,
            "PROMPT_BLOG_FILENAME": PROMPT_BLOG_FILENAME,
            "PROMPT_ABSTRACT_VALIDATION_FILENAME": PROMPT_ABSTRACT_VALIDATION_FILENAME,
            "PROMPT_VOICE_AUDIT_FILENAME": PROMPT_VOICE_AUDIT_FILENAME,
            "PROMPT_STRUCTURED_SUMMARY_FILENAME": PROMPT_STRUCTURED_SUMMARY_FILENAME,
            "PROMPT_STRUCTURED_ABSTRACT_FILENAME": PROMPT_STRUCTURED_ABSTRACT_FILENAME,
            "PROMPT_VALIDATION_COVERAGE_FILENAME": PROMPT_VALIDATION_COVERAGE_FILENAME,
        "PROMPT_PROBLEMATIC_HEADER_TERMS_FILENAME": PROMPT_PROBLEMATIC_HEADER_TERMS_FILENAME,
        "PROMPT_EMPHASIS_SCORING_FILENAME": PROMPT_EMPHASIS_SCORING_FILENAME,
        "PROMPT_BOWEN_EXTRACTION_FILENAME": PROMPT_BOWEN_EXTRACTION_FILENAME,
        "PROMPT_BOWEN_FILTER_FILENAME": PROMPT_BOWEN_FILTER_FILENAME,
        }

        missing_prompts = []
        for name, filename in prompt_files.items():
            prompt_path = settings.PROMPTS_DIR / filename
            if not prompt_path.exists():
                missing_prompts.append(f"  - {name}: {filename}")

        if missing_prompts:
            result.add_warning(
                f"Missing {len(missing_prompts)} prompt file(s) in {settings.PROMPTS_DIR}:\n" +
                "\n".join(missing_prompts) +
                "\n  These files are required for transcript processing\n"
                f"  Fix: Add prompt files to {settings.PROMPTS_DIR}"
            )

    # ========================================================================
    # 5. VALIDATE LOGICAL CONSISTENCY
    # ========================================================================

    # Check chunk overlap < chunk size
    if VALIDATION_CHUNK_OVERLAP >= VALIDATION_CHUNK_SIZE:
        result.add_error(
            f"VALIDATION_CHUNK_OVERLAP ({VALIDATION_CHUNK_OVERLAP}) must be < "
            f"VALIDATION_CHUNK_SIZE ({VALIDATION_CHUNK_SIZE})\n"
            f"  Otherwise chunks will overlap completely\n"
            f"  Fix: Set overlap to < 50% of chunk size"
        )

    # Check min < max context words
    if VALIDATION_MIN_CONTEXT_WORDS >= VALIDATION_MAX_CONTEXT_WORDS:
        result.add_error(
            f"VALIDATION_MIN_CONTEXT_WORDS ({VALIDATION_MIN_CONTEXT_WORDS}) must be < "
            f"VALIDATION_MAX_CONTEXT_WORDS ({VALIDATION_MAX_CONTEXT_WORDS})\n"
            f"  Fix: Set min < max"
        )

    # Check fuzzy match thresholds are ordered correctly
    if not (VALIDATION_FUZZY_REJECT <= VALIDATION_FUZZY_REVIEW <= VALIDATION_FUZZY_AUTO_APPLY):
        result.add_error(
            f"Fuzzy match thresholds must be ordered: "
            f"REJECT ({VALIDATION_FUZZY_REJECT}) ≤ "
            f"REVIEW ({VALIDATION_FUZZY_REVIEW}) ≤ "
            f"AUTO_APPLY ({VALIDATION_FUZZY_AUTO_APPLY})\n"
            f"  Fix: Ensure thresholds increase from reject to auto-apply"
        )

    # Check summary structure allocations sum to reasonable amount
    summary_total = SUMMARY_OPENING_PCT + SUMMARY_CLOSING_PCT + SUMMARY_QA_PCT
    if summary_total > 0.5:
        result.add_warning(
            f"Summary structure allocations sum to {summary_total:.1%} of content\n"
            f"  OPENING: {SUMMARY_OPENING_PCT:.1%}, "
            f"CLOSING: {SUMMARY_CLOSING_PCT:.1%}, "
            f"QA: {SUMMARY_QA_PCT:.1%}\n"
            f"  This leaves < 50% for main content\n"
            f"  Consider: Reduce allocations"
        )

    # ========================================================================
    # 6. VALIDATE CONFIDENCE SETS
    # ========================================================================

    if not isinstance(VALIDATION_AUTO_APPLY_CONFIDENCE, set):
        result.add_error(
            f"VALIDATION_AUTO_APPLY_CONFIDENCE must be a set, got: {type(VALIDATION_AUTO_APPLY_CONFIDENCE)}\n"
            f"  Fix: Use set syntax, e.g., {{'high', 'medium'}}"
        )

    if not isinstance(VALIDATION_REVIEW_CONFIDENCE, set):
        result.add_error(
            f"VALIDATION_REVIEW_CONFIDENCE must be a set, got: {type(VALIDATION_REVIEW_CONFIDENCE)}\n"
            f"  Fix: Use set syntax, e.g., {{'medium'}}"
        )

    if not isinstance(VALIDATION_SKIP_CONFIDENCE, set):
        result.add_error(
            f"VALIDATION_SKIP_CONFIDENCE must be a set, got: {type(VALIDATION_SKIP_CONFIDENCE)}\n"
            f"  Fix: Use set syntax, e.g., {{'low'}}"
        )

    # ========================================================================
    # 7. VALIDATE ERROR TYPES SET
    # ========================================================================

    if not isinstance(VALIDATION_ERROR_TYPES, set):
        result.add_error(
            f"VALIDATION_ERROR_TYPES must be a set, got: {type(VALIDATION_ERROR_TYPES)}\n"
            f"  Fix: Use set syntax"
        )
    elif not VALIDATION_ERROR_TYPES:
        result.add_warning(
            "VALIDATION_ERROR_TYPES is empty\n"
            f"  Consider: Add error types like {{'homophone', 'proper_noun', 'grammar'}}"
        )

    # ========================================================================
    # OUTPUT RESULTS
    # ========================================================================

    if verbose:
        print(result.format_report())

    return result


def validate_or_exit(verbose: bool = True, auto_fix: bool = False):
    """
    Validate configuration and exit with error code if validation fails.

    This function is intended to be called at application startup to ensure
    configuration is valid before proceeding with operations.

    Args:
        verbose: If True, print validation report
        auto_fix: If True, attempt to fix issues automatically
    """
    result = validate_configuration(verbose=verbose, auto_fix=auto_fix)

    if not result.is_valid():
        print("\n" + "=" * 70)
        print("❌ CRITICAL: Configuration validation failed")
        print("=" * 70)
        print("The application cannot start with invalid configuration.")
        print("Please fix the errors above and try again.")
        print("=" * 70)
        sys.exit(1)
    elif result.warnings and verbose:
        print("\n⚠️  Configuration has warnings but is usable.")
        print("Consider addressing warnings for optimal operation.\n")
