#!/usr/bin/env python3
"""
CLI wrapper for cleaning up transcript source files.
Moves original and validated files to 'processed/', deletes intermediate '_vN' files.

Usage:
    python transcript_cleanup.py "Title - Presenter - Date"
"""

import argparse
import sys
from pathlib import Path

import config
from cleanup_pipeline import cleanup_transcript_files


def resolve_base_name(input_name: str) -> str:
    """
    Resolve input string to a base name by stripping extensions and suffixes.
    """
    # Remove extension
    name = input_name
    if name.endswith(".md") or name.endswith(".txt"):
        name = Path(name).stem

    # Remove known suffixes to get back to the clean base name
    # We want "Title - Presenter - Date", not "Title..._validated" or "Title..._v1"
    
    # First remove version/validated suffixes which are most likely if picking a file
    # Matches _v1, _v12, _validated at the end of the stem
    import re
    clean_name = re.sub(r'(_v\d+|_validated)$', '', name)
    
    return clean_name


def main():
    parser = argparse.ArgumentParser(
        description="Clean up source directory: Move original/validated files to processed/, delete intermediate versions."
    )
    parser.add_argument(
        "base_name",
        help="Base name of the transcript (e.g., 'Title - Presenter - Date')",
    )
    args = parser.parse_args()
    base_name = resolve_base_name(args.base_name)

    print(f"Running cleanup for: {base_name}")
    success = cleanup_transcript_files(base_name)

    if success:
        print("\nCleanup completed successfully.")
        return 0
    else:
        print("\nCleanup failed. Check the logs for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
