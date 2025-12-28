#!/usr/bin/env python3
"""
CLI wrapper for adding YAML front matter to a formatted transcript.

Usage:
    python transcript_add_yaml.py "Title - Presenter - Date - formatted.md" [--source-ext mp3]
"""

import argparse
import sys
from pathlib import Path
from pipeline import add_yaml
import config


def resolve_filename(filename: str) -> str:
    """
    Resolve filename to support base names and ' - formatted.md' extension.
    """
    # If exact match exists in formatted dir, return it
    if (config.FORMATTED_DIR / filename).exists():
        return filename

    # Clean up base name
    base = filename
    for suffix in [' - formatted.md', '.md', '.txt']:
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break

    # Try - formatted.md
    formatted_name = f"{base} - formatted.md"
    if (config.FORMATTED_DIR / formatted_name).exists():
        return formatted_name

    return filename


def main():
    """
    Main function to handle command-line execution of the YAML injection process.
    """
    parser = argparse.ArgumentParser(
        description="Prepend YAML front matter to a formatted transcript."
    )
    parser.add_argument(
        "transcript_filename",
        help="Filename of the formatted transcript (e.g., 'Title... - formatted.md' or base name)"
    )
    parser.add_argument(
        "--source-ext",
        default="mp4",
        help="Extension of source recording file (default: mp4)"
    )

    args = parser.parse_args()

    resolved_filename = resolve_filename(args.transcript_filename)

    print(f"Adding YAML to: {resolved_filename}")

    success = add_yaml(
        transcript_filename=resolved_filename,
        source_ext=args.source_ext
    )

    if success:
        print("\nYAML injection completed successfully.")
        return 0
    else:
        print("\nYAML injection failed. Check the logs for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
