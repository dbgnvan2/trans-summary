#!/usr/bin/env python3
"""
CLI wrapper for extracting Bowen references from a transcript.

Usage:
    python transcript_extract_bowen.py "Title - Presenter - Date - yaml.md" [--show-prompt]
"""

import argparse
import sys
from pathlib import Path

import config
from pipeline import (
    _load_formatted_transcript,
    extract_bowen_references_from_transcript,
)
from transcript_utils import create_system_message_with_cache, parse_filename_metadata


def resolve_filename(filename: str) -> str:
    """
    Resolve filename to support base names and ' - yaml.md' extension.
    """
    # Clean up base name from any potential full path or extension
    base = Path(filename).stem
    suffixes_to_strip = [
        config.SUFFIX_YAML.replace(".md", ""),
        config.SUFFIX_FORMATTED.replace(".md", ""),
    ]
    for suffix in suffixes_to_strip:
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break

    # Check for preferred file types in the project directory
    project_dir = config.PROJECTS_DIR / base
    yaml_name = f"{base}{config.SUFFIX_YAML}"
    if (project_dir / yaml_name).exists():
        return yaml_name

    formatted_name = f"{base}{config.SUFFIX_FORMATTED}"
    if (project_dir / formatted_name).exists():
        return formatted_name

    # If not found, return original to let the pipeline handle the error
    return filename


def main():
    parser = argparse.ArgumentParser(
        description="Extract Bowen references from a transcript using a dedicated pipeline step."
    )
    parser.add_argument(
        "formatted_filename",
        help="Filename of formatted transcript (e.g., 'Title... - yaml.md' or base name)",
    )
    parser.add_argument(
        "--model",
        default=config.DEFAULT_MODEL,
        help=f"Claude model to use (default: {config.DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Display the prompt template being used and exit",
    )

    args = parser.parse_args()

    if args.show_prompt:
        prompt_path = config.PROMPTS_DIR / config.PROMPT_BOWEN_EXTRACTION_FILENAME
        if prompt_path.exists():
            print(f"\n--- Prompt Template ({prompt_path.name}) ---")
            print(prompt_path.read_text(encoding="utf-8"))
            print("-------------------------------------------\n")
        else:
            print(f"❌ Prompt file not found: {prompt_path}")
        return 0

    resolved_filename = resolve_filename(args.formatted_filename)

    # Add a pre-flight check for a better error message
    try:
        meta = parse_filename_metadata(resolved_filename)
        expected_path = config.PROJECTS_DIR / meta["stem"] / resolved_filename

        if not expected_path.exists():
            print(
                f"❌ Error: Input file not found at expected location:\n   {expected_path}"
            )
            print(
                "\n   Please ensure you have run the 'Format' and 'YAML' steps for this transcript first."
            )
            return 1
    except Exception:
        # If parsing fails, let the pipeline handle the error.
        pass

    print(f"Starting Bowen reference extraction for: {resolved_filename}")

    # Load transcript and create a cached system message to reduce costs
    transcript_content = _load_formatted_transcript(resolved_filename)
    transcript_system_message = create_system_message_with_cache(transcript_content)

    success = extract_bowen_references_from_transcript(
        formatted_filename=resolved_filename,
        model=args.model,
        transcript_system_message=transcript_system_message,
    )

    if success:
        print("\nBowen reference extraction completed successfully.")
        return 0
    else:
        print("\nBowen reference extraction failed. Check the logs for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
