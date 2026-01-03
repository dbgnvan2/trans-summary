#!/usr/bin/env python3
"""
CLI wrapper for generating the main webpage for a transcript.

Usage:
    python transcript_to_webpage.py "Title - Presenter - Date"
"""

import argparse
import sys
from pathlib import Path

import config
from pipeline import generate_webpage


def resolve_base_name(input_name: str) -> str:
    """
    Resolve input string to a base name by stripping extensions and suffixes.
    Example: "Title - Presenter - Date - formatted.md" -> "Title - Presenter - Date"
    """
    # Remove extension
    name = input_name
    if name.endswith(".md") or name.endswith(".txt"):
        name = Path(name).stem

    # Remove known suffixes
    suffixes = [
        config.SUFFIX_FORMATTED.replace(".md", ""),
        config.SUFFIX_YAML.replace(".md", ""),
        "_yaml",
        config.SUFFIX_WEBPAGE_SIMPLE.replace(".html", ""),
    ]
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break

    return name


def main():
    """
    Main function to handle command-line execution of the webpage generation process.
    """
    parser = argparse.ArgumentParser(
        description="Generate the main webpage for a transcript using the core pipeline."
    )
    parser.add_argument(
        "base_name",
        help="Base name of the transcript (e.g., 'Title - Presenter - Date')",
    )

    args = parser.parse_args()

    base_name = resolve_base_name(args.base_name)

    print(f"Starting webpage generation for: {base_name}")

    success = generate_webpage(base_name)

    if success:
        print("\nWebpage generation completed successfully.")
        return 0
    else:
        print("\nWebpage generation failed. Check the logs for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
