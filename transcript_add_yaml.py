#!/usr/bin/env python3
"""
CLI wrapper for adding YAML front matter to a formatted transcript.

Usage:
    python transcript_add_yaml.py "Title - Presenter - Date.txt" [--source-ext mp3]
"""

import argparse
import sys
from pipeline import add_yaml

def main():
    """
    Main function to handle command-line execution of the YAML injection process.
    """
    parser = argparse.ArgumentParser(
        description="Prepend YAML front matter to a formatted transcript."
    )
    parser.add_argument(
        "transcript_filename",
        help="Filename of the formatted transcript (e.g., 'Title - Presenter - Date.txt')"
    )
    parser.add_argument(
        "--source-ext",
        default="mp4",
        help="Extension of source recording file (default: mp4)"
    )

    args = parser.parse_args()

    print(f"Adding YAML to: {args.transcript_filename}")
    
    success = add_yaml(
        transcript_filename=args.transcript_filename,
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