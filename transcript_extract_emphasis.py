#!/usr/bin/env python3
"""
CLI wrapper for extracting scored emphasis items from a transcript.

Usage:
    python transcript_extract_emphasis.py "Title - Presenter - Date - yaml.md"
"""

import argparse
import sys
from pathlib import Path
from pipeline import extract_scored_emphasis, _load_formatted_transcript
import config
from transcript_utils import parse_filename_metadata, create_system_message_with_cache


def resolve_filename(filename: str) -> str:
    """
    Resolve filename to support base names and ' - yaml.md' extension.
    """
    # Clean up base name
    base = filename
    suffixes = [
        config.SUFFIX_YAML,
        config.SUFFIX_FORMATTED,
        '.md',
        '.txt'
    ]
    for suffix in suffixes:
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break

    project_dir = config.PROJECTS_DIR / base

    # Try - yaml.md first
    yaml_name = f"{base}{config.SUFFIX_YAML}"
    if (project_dir / yaml_name).exists():
        return yaml_name

    # Try - formatted.md (fallback)
    formatted_name = f"{base}{config.SUFFIX_FORMATTED}"
    if (project_dir / formatted_name).exists():
        return formatted_name

    return filename


def main():
    parser = argparse.ArgumentParser(
        description="Extract scored emphasis items from a transcript using the core pipeline."
    )
    parser.add_argument(
        "formatted_filename",
        help="Filename of formatted transcript (e.g., 'Title... - yaml.md' or base name)"
    )
    parser.add_argument(
        "--model",
        default=config.DEFAULT_MODEL,
        help=f"Claude model to use (default: {config.DEFAULT_MODEL})"
    )

    args = parser.parse_args()

    resolved_filename = resolve_filename(args.formatted_filename)

    # Add a pre-flight check for a better error message
    try:
        meta = parse_filename_metadata(resolved_filename)
        expected_path = config.PROJECTS_DIR / meta['stem'] / resolved_filename

        if not expected_path.exists():
            print(
                f"❌ Error: Input file not found at expected location:\n   {expected_path}")
            print(
                "\n   Please ensure you have run the 'Format' and 'YAML' steps for this transcript first.")
            return 1
    except Exception:
        # If parsing fails, let the pipeline handle the error.
        pass

    print(f"Starting scored emphasis extraction for: {resolved_filename}")

    # Load transcript and create a cached system message to reduce costs
    transcript_content = _load_formatted_transcript(resolved_filename)
    transcript_system_message = create_system_message_with_cache(
        transcript_content)

    success = extract_scored_emphasis(
        formatted_filename=resolved_filename,
        model=args.model,
        transcript_system_message=transcript_system_message
    )

    if success:
        print("\nEmphasis extraction completed successfully.")
        return 0
    else:
        print("\nEmphasis extraction failed. Check the logs for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
