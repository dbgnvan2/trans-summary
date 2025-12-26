#!/usr/bin/env python3
"""
CLI wrapper for formatting a raw transcript using the core pipeline.

Usage:
    python transcript_format.py "Title - Presenter - Date.txt"
"""

import argparse
import sys
from pipeline import format_transcript
import config


def main():
    """
    Main function to handle command-line execution of the transcript formatting process.
    """
    parser = argparse.ArgumentParser(
        description="Format a raw transcript using the core processing pipeline."
    )
    parser.add_argument(
        "raw_filename",
        help="Filename of the raw transcript in the source directory (e.g., 'Title - Presenter - Date.txt')"
    )
    parser.add_argument(
        "--model",
        default=config.DEFAULT_MODEL,
        help=f"Claude model to use (default: {config.DEFAULT_MODEL})"
    )

    args = parser.parse_args()

    print(f"Starting transcript formatting for: {args.raw_filename}")

    success = format_transcript(args.raw_filename, model=args.model)

    if success:
        print("\nFormatting completed successfully.")
        return 0
    else:
        print("\nFormatting failed. Check the logs for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
