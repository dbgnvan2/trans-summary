#!/usr/bin/env python3
"""
CLI wrapper for extracting scored emphasis items from a transcript.

Usage:
    python transcript_extract_emphasis.py "Title - Presenter - Date - yaml.md"
"""

import argparse
import sys
from pathlib import Path
from pipeline import extract_scored_emphasis
import config


def resolve_filename(filename: str) -> str:
    """
    Resolve filename to support base names and ' - yaml.md' extension.
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

    # Try - yaml.md first
    yaml_name = f"{base}{config.SUFFIX_YAML}"
    if (config.FORMATTED_DIR / yaml_name).exists():
        return yaml_name

    # Try - formatted.md (fallback)
    formatted_name = f"{base}{config.SUFFIX_FORMATTED}"
    if (config.FORMATTED_DIR / formatted_name).exists():
        return formatted_name

    return filename


def main():
    parser = argparse.ArgumentParser(
        description="Extract scored emphasis items from a transcript using the core pipeline."
    )
    parser.add_argument(
        "formatted_filename",
        help="Filename of formatted transcript (e.g., 'Title... - yaml.md' or base name)"
    )
    parser.add_argument(
        "--model",
        default=config.DEFAULT_MODEL,
        help=f"Claude model to use (default: {config.DEFAULT_MODEL})"
    )

    args = parser.parse_args()

    resolved_filename = resolve_filename(args.formatted_filename)

    print(f"Starting scored emphasis extraction for: {resolved_filename}")

    success = extract_scored_emphasis(
        formatted_filename=resolved_filename,
        model=args.model
    )

    if success:
        print("\nEmphasis extraction completed successfully.")
        return 0
    else:
        print("\nEmphasis extraction failed. Check the logs for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
