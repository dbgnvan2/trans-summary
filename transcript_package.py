#!/usr/bin/env python3
"""
CLI wrapper for packaging final artifacts into a zip file.

Usage:
    python transcript_package.py "Title - Presenter - Date"
"""

import argparse
import sys
from pathlib import Path

import config
from pipeline import package_transcript


def resolve_base_name(input_name: str) -> str:
    """
    Resolve input string to a base name by stripping extensions and suffixes.
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
    parser = argparse.ArgumentParser(
        description="Package final transcript artifacts (HTML, PDF, Markdown) into a zip file."
    )
    parser.add_argument(
        "base_name",
        help="Base name of the transcript (e.g., 'Title - Presenter - Date')",
    )
    args = parser.parse_args()
    base_name = resolve_base_name(args.base_name)

    print(f"Packaging artifacts for: {base_name}")
    success = package_transcript(base_name)

    if success:
        print("\nPackaging completed successfully.")
        return 0
    else:
        print("\nPackaging failed. Check the logs for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
