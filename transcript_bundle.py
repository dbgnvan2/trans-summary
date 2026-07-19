#!/usr/bin/env python3
"""
CLI wrapper for exporting a run's Markdown collection to DOCX and/or PDF.

Usage:
    python transcript_bundle.py "Title - Presenter - Date" --format both
    python transcript_bundle.py "Title - Presenter - Date" --format docx

Spec: docs/spec_bundle_export_2026-07-16.md
"""

import argparse
import sys
from pathlib import Path

import config
from bundle_export import export_bundle


def resolve_base_name(input_name: str) -> str:
    """Resolve input string to a base name by stripping extensions/suffixes
    (mirrors transcript_to_pdf.py / transcript_package.py)."""
    name = input_name
    if name.endswith(".md") or name.endswith(".txt"):
        name = Path(name).stem

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
        description="Export a run's Markdown collection to DOCX and/or PDF."
    )
    parser.add_argument(
        "base_name",
        help="Base name of the transcript (e.g., 'Title - Presenter - Date')",
    )
    parser.add_argument(
        "--format",
        choices=["docx", "pdf", "both"],
        default="both",
        help="Which format(s) to produce (default: both).",
    )
    args = parser.parse_args()

    base_name = resolve_base_name(args.base_name)

    print(f"Exporting bundle ({args.format}) for: {base_name}")
    success = export_bundle(base_name, fmt=args.format)

    if success:
        print("\nBundle export completed successfully.")
        return 0
    print("\nBundle export failed. Check the logs for details.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
