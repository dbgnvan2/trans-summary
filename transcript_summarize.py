#!/usr/bin/env python3
"""
CLI wrapper for generating summaries from a formatted transcript.

Usage:
    python transcript_summarize.py "Title - Presenter - Date - formatted.md" [--skip-extracts-summary] [--skip-terms] [--skip-blog] [--generate-structured] [--structured-word-count WORDS]
"""

import argparse
import sys
from pipeline import summarize_transcript, setup_logging
import config


def main():
    """
    Main function to handle command-line execution of the transcript summarization process.
    """
    parser = argparse.ArgumentParser(
        description="Generate summaries from a formatted transcript using the core pipeline."
    )
    parser.add_argument(
        "formatted_filename",
        help="Filename of formatted transcript (e.g., 'Title - Presenter - Date - formatted.md')"
    )
    parser.add_argument(
        "--focus-keyword",
        default="Family Systems",
        help="Focus keyword for SEO (default: Family Systems)"
    )
    parser.add_argument(
        "--target-audience",
        default="General public interested in psychology",
        help="Target audience description"
    )
    parser.add_argument(
        "--model",
        default=config.DEFAULT_MODEL,
        help=f"Claude model to use (default: {config.DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--skip-extracts-summary",
        action="store_true",
        help="Skip extracts-summary analysis (Part 1)"
    )
    parser.add_argument(
        "--skip-terms",
        action="store_true",
        help="Skip key terms extraction (Part 2)"
    )
    parser.add_argument(
        "--skip-blog",
        action="store_true",
        help="Skip blog post generation (Part 3)"
    )
    parser.add_argument(
        "--generate-structured",
        action="store_true",
        help="Generate a structured summary using the new pipeline (requires extracts-summary)"
    )
    parser.add_argument(
        "--structured-word-count",
        type=int,
        default=500,
        help="Target word count for the structured summary (default: 500)"
    )


    args = parser.parse_args()

    logger = setup_logging('transcript_summarize_cli') # Initialize logger
    logger.info(f"Starting transcript summarization for: {args.formatted_filename}") # Use logger.info

    success = summarize_transcript(
        formatted_filename=args.formatted_filename,
        model=args.model,
        focus_keyword=args.focus_keyword,
        target_audience=args.target_audience,
        skip_extracts_summary=args.skip_extracts_summary,
        skip_terms=args.skip_terms,
        skip_blog=args.skip_blog,
        generate_structured=args.generate_structured,
        structured_word_count=args.structured_word_count,
        trans_summary_logger=logger # Pass logger via new parameter
    )

    if success:
        logger.info("\nSummarization completed successfully.")
        return 0
    else:
        logger.error("\nSummarization failed. Check the logs for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
