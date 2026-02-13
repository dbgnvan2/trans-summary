#!/usr/bin/env python3
"""
CLI wrapper for abstract coverage validation.

Usage:
    python transcript_validate_abstract.py "Title - Presenter - Date"
"""

import argparse
import sys
from pathlib import Path

import config
from pipeline import setup_logging, validate_abstract_coverage


def resolve_base_name(input_name: str) -> str:
    """
    Resolve input string to a base name by stripping extensions and suffixes.
    Example: "Title - Presenter - Date - formatted.md" -> "Title - Presenter - Date"
    """
    # Remove extension
    name = input_name
    if name.endswith(".md") or name.endswith(".txt"):
        name = Path(name).stem

    # Remove known suffixes
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
    """
    Main function to run abstract coverage validation.
    """
    parser = argparse.ArgumentParser(
        description="Validate abstract coverage against transcript content."
    )
    parser.add_argument(
        "base_name",
        help="Base name of the transcript (e.g., 'Title - Presenter - Date')",
    )
    parser.add_argument(
        "--model",
        default=config.AUX_MODEL,
        help=f"Claude model to use (default: {config.AUX_MODEL})",
    )

    args = parser.parse_args()

    base_name = resolve_base_name(args.base_name)

    logger = setup_logging("validate_abstract_cli")
    logger.info(f"Starting abstract validation for: {base_name}")

    success = validate_abstract_coverage(
        base_name=base_name,
        model=args.model,
        logger=logger,
    )

    if success:
        print("\nAbstract validation completed successfully.")
        return 0
    else:
        print("\nAbstract validation failed. Check the logs for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
