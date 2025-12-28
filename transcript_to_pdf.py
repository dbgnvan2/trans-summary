#!/usr/bin/env python3
"""
CLI wrapper for generating a PDF from a transcript.

Usage:
    python transcript_to_pdf.py "Title - Presenter - Date"
"""

import argparse
import sys
from pathlib import Path
from pipeline import generate_pdf


def resolve_base_name(input_name: str) -> str:
    """
    Resolve input string to a base name by stripping extensions and suffixes.
    Example: "Title - Presenter - Date - formatted.md" -> "Title - Presenter - Date"
    """
    # Remove extension
    name = input_name
    if name.endswith('.md') or name.endswith('.txt'):
        name = Path(name).stem

    # Remove known suffixes
    suffixes = [' - formatted', ' - yaml', '_yaml', ' - simple']
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break

    return name


def main():
    """
    Main function to handle command-line execution of the PDF generation process.
    """
    parser = argparse.ArgumentParser(
        description="Generate a PDF for a transcript using the core pipeline."
    )
    parser.add_argument(
        "base_name",
        help="Base name of the transcript (e.g., 'Title - Presenter - Date')"
    )

    args = parser.parse_args()

    base_name = resolve_base_name(args.base_name)

    print(f"Starting PDF generation for: {base_name}")

    success = generate_pdf(base_name)

    if success:
        print("\nPDF generation completed successfully.")
        return 0
    else:
        print("\nPDF generation failed. Check the logs for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
