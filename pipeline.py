"""
Core pipeline logic for the transcript processing application.
This module acts as a facade, orchestrating the business logic by delegating
to specialized pipeline modules.
"""

# Re-exporting functions to maintain backward compatibility
from formatting_pipeline import (
    format_transcript,
    validate_format,
    add_yaml
)

from validation_pipeline import (
    validate_headers,
    validate_abstract_legacy as validate_abstract, # Legacy
    validate_abstract_coverage,
    validate_summary_coverage
)

from extraction_pipeline import (
    summarize_transcript,
    extract_scored_emphasis,
    extract_bowen_references_from_transcript,
    generate_structured_summary,
    generate_structured_abstract, # Added
    _load_formatted_transcript # Helper used by CLI scripts
)

from html_generator import (
    generate_webpage,
    generate_simple_webpage,
    generate_pdf
)

from packaging_pipeline import package_transcript

from transcript_utils import delete_logs

# Optional: expose other helpers if needed by GUI directly
from transcript_utils import setup_logging
import config

# End of facade