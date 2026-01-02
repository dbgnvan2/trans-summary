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
from transcript_utils import parse_filename_metadata


def resolve_filename(filename: str) -> str:
    """
    Resolve filename to support base names and ' - formatted.md' extension.
    """
    # Clean up base name
    base = Path(filename).stem
    suffixes_to_strip = [
        config.SUFFIX_FORMATTED.replace('.md', ''),
    ]
    for suffix in suffixes_to_strip:
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break

    project_dir = config.PROJECTS_DIR / base
    # Try - formatted.md
    formatted_name = f"{base}{config.SUFFIX_FORMATTED}"
    if (project_dir / formatted_name).exists():
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

    # Add a pre-flight check for a better error message
    try:
        meta = parse_filename_metadata(resolved_filename)
        expected_path = config.PROJECTS_DIR / meta['stem'] / resolved_filename

        if not expected_path.exists():
            print(
                f"❌ Error: Input file not found at expected location:\n   {expected_path}")
            print(
                "\n   Please ensure you have run the 'Format' step for this transcript first.")
            return 1
    except Exception:
        # If parsing fails, let the pipeline handle the error.
        pass

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
