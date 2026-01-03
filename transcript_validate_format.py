#!/usr/bin/env python3
"""
CLI wrapper for validating the format of a transcript.

Usage:
    python transcript_validate_format.py "Title - Presenter - Date.txt"
"""

import argparse
import sys

from pipeline import validate_format


def main():
    """
    Main function to handle command-line execution of the format validation process.
    """
    parser = argparse.ArgumentParser(
        description="Validate the format of a transcript using the core pipeline."
    )
    parser.add_argument(
        "raw_filename",
        help="Filename of the raw transcript in the source directory (e.g., 'Title - Presenter - Date.txt')",
    )
    parser.add_argument(
        "--formatted-file",
        default=None,
        help="Optional: specify formatted file name explicitly (otherwise auto-constructed)",
    )
    parser.add_argument(
        "--skip-words",
        help="Optional file with one skip word per line",
        default=None,
    )

    args = parser.parse_args()

    print(f"Starting format validation for: {args.raw_filename}")

    success = validate_format(
        raw_filename=args.raw_filename,
        formatted_filename=args.formatted_file,
        skip_words_file=args.skip_words,
    )

    if success:
        print("\nFormat validation completed successfully.")
        return 0
    else:
        print("\nFormat validation failed. Check the logs for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
