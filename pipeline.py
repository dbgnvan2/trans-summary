"""
Core pipeline logic for the transcript processing application.
This module acts as a facade, orchestrating the business logic by delegating
to specialized pipeline modules.
"""

from extraction_pipeline import (
    _load_formatted_transcript,  # Helper used by CLI scripts
    extract_bowen_references_from_transcript,
    extract_scored_emphasis,
    generate_structured_abstract,
    generate_structured_summary,
    summarize_transcript,
)
from formatting_pipeline import (
    add_yaml,
    format_transcript,
    validate_format,
)
from html_generator import (
    generate_pdf,
    generate_simple_webpage,
    generate_webpage,
)
from packaging_pipeline import package_transcript
from transcript_utils import delete_logs, setup_logging
from validation_pipeline import (
    validate_abstract_coverage,
    validate_headers,
    validate_key_terms_fidelity,
    validate_topics_lightweight,
    validate_summary_coverage,
)
from validation_pipeline import (
    validate_abstract_legacy as validate_abstract,  # Legacy
)

# Explicitly export symbols to prevent linters from removing them
__all__ = [
    "add_yaml",
    "format_transcript",
    "validate_format",
    "validate_abstract_coverage",
    "validate_headers",
    "validate_key_terms_fidelity",
    "validate_topics_lightweight",
    "validate_summary_coverage",
    "validate_abstract",
    "_load_formatted_transcript",
    "extract_bowen_references_from_transcript",
    "extract_scored_emphasis",
    "generate_structured_abstract",
    "generate_structured_summary",
    "summarize_transcript",
    "generate_pdf",
    "generate_simple_webpage",
    "generate_webpage",
    "package_transcript",
    "delete_logs",
    "setup_logging",
]
