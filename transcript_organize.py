#!/usr/bin/env python3
"""
Transcript Organizer

Consolidates scattered transcript artifacts into per-transcript project folders.
This implements an Entity-based structure (projects/{Base Name}/) instead of
the current Component-based structure (formatted/, summaries/, etc.).

Usage:
    python transcript_organize.py [--move]

    --move: Actually move files (default is copy)
"""

import argparse
import shutil
from pathlib import Path
import config


def get_all_base_names():
    """
    Identify all unique transcript base names from the source and formatted directories.
    """
    base_names = set()

    # Check source
    if config.SOURCE_DIR.exists():
        for f in config.SOURCE_DIR.glob("*.txt"):
            base_names.add(f.stem)

    # Check formatted (in case source was moved)
    if config.FORMATTED_DIR.exists():
        for f in config.FORMATTED_DIR.glob("* - formatted.md"):
            base_names.add(f.name.replace(" - formatted.md", ""))

    return sorted(list(base_names))


def organize_transcript(base_name, move=False):
    """
    Find all files related to base_name and move/copy them to a project folder.
    """
    # Define the project folder
    project_dir = config.TRANSCRIPTS_BASE / "projects" / base_name
    project_dir.mkdir(parents=True, exist_ok=True)

    # Define where to look and what patterns to look for
    # (Source dir, glob_pattern)
    search_locations = [
        (config.SOURCE_DIR, f"{base_name}.txt"),
        (config.FORMATTED_DIR, f"{base_name} - *.md"),
        (config.SUMMARIES_DIR, f"{base_name} - *.md"),
        (config.SUMMARIES_DIR, f"{base_name} - *.txt"),
        (config.SUMMARIES_DIR, f"{base_name} - *.json"),
        (config.WEBPAGES_DIR, f"{base_name}*.html"),
        (config.PDFS_DIR, f"{base_name}*.pdf"),
        (config.PACKAGES_DIR, f"{base_name}.zip"),
        (config.PROCESSED_DIR, f"{base_name}*.txt"),  # Processed source files
    ]

    files_found = 0

    for source_dir, pattern in search_locations:
        if not source_dir.exists():
            continue

        for file_path in source_dir.glob(pattern):
            if file_path.is_file():
                dest_path = project_dir / file_path.name

                # Don't overwrite if same (e.g. running script multiple times)
                if dest_path.exists() and dest_path.stat().st_size == file_path.stat().st_size:
                    continue

                if move:
                    shutil.move(str(file_path), str(dest_path))
                    print(f"  Moved: {file_path.name}")
                else:
                    shutil.copy2(str(file_path), str(dest_path))
                    print(f"  Copied: {file_path.name}")

                files_found += 1

    if files_found > 0:
        print(f"✅ Organized '{base_name}': {files_found} files")


def main():
    parser = argparse.ArgumentParser(
        description="Organize transcript files into project folders.")
    parser.add_argument("--move", action="store_true",
                        help="Move files instead of copying (Destructive)")
    args = parser.parse_args()

    base_names = get_all_base_names()
    print(f"Found {len(base_names)} unique transcripts.")
    print(f"Target Directory: {config.TRANSCRIPTS_BASE / 'projects'}\n")

    for base_name in base_names:
        organize_transcript(base_name, move=args.move)


if __name__ == "__main__":
    main()
