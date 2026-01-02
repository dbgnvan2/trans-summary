#!/usr/bin/env python3
"""
CLI wrapper for generating summaries from a formatted transcript.

Usage:
    python transcript_summarize.py "Title - Presenter - Date - yaml.md" [--skip-extracts-summary] [--skip-emphasis] [--skip-blog]
"""

import argparse
import sys
from pathlib import Path
from pipeline import summarize_transcript
import config


def resolve_filename(filename: str) -> str:
    """
    Resolve filename to support base names and ' - yaml.md' extension.
    Prioritizes ' - yaml.md' as it contains the metadata needed for summaries.
    """
    # If exact match exists in formatted dir, return it
    if (config.FORMATTED_DIR / filename).exists():
        return filename

    # Clean up base name
    base = filename
    suffixes = [
        config.SUFFIX_YAML,
        config.SUFFIX_FORMATTED,
        '.md',
        '.txt'
    ]
    for suffix in suffixes:
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break

    # Try - yaml.md first (preferred for summaries)
    yaml_name = f"{base}{config.SUFFIX_YAML}"
    if (config.FORMATTED_DIR / yaml_name).exists():
        return yaml_name

    # Try - formatted.md (fallback)
    formatted_name = f"{base}{config.SUFFIX_FORMATTED}"
    if (config.FORMATTED_DIR / formatted_name).exists():
        return formatted_name

    return filename


def main():
    """
    Main function to handle command-line execution of the transcript summarization process.
    """
    parser = argparse.ArgumentParser(
        description="Generate summaries from a formatted transcript using the core pipeline."
    )
    parser.add_argument(
        "formatted_filename",
        help="Filename of formatted transcript (e.g., 'Title... - yaml.md' or base name)"
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
        "--skip-emphasis",
        action="store_true",
        help="Skip scored emphasis extraction (Part 2)"
    )
    parser.add_argument(
        "--skip-blog",
        action="store_true",
        help="Skip blog post generation (Part 3)"
    )

    args = parser.parse_args()

    resolved_filename = resolve_filename(args.formatted_filename)

    print(f"Starting transcript summarization for: {resolved_filename}")

    success = summarize_transcript(
        formatted_filename=resolved_filename,
        model=args.model,
        focus_keyword=args.focus_keyword,
        target_audience=args.target_audience,
        skip_extracts_summary=args.skip_extracts_summary,
        skip_emphasis=args.skip_emphasis,
        skip_blog=args.skip_blog
    )

    if success:
        print("\nSummarization completed successfully.")
        return 0
    else:
        print("\nSummarization failed. Check the logs for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
