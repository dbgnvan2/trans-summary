#!/usr/bin/env python3
"""
CLI wrapper for validating and revising abstracts.

Usage:
    python transcript_validate_abstract.py "Title - Presenter - Date" [--auto]
"""

import argparse
import sys
from pathlib import Path
from pipeline import validate_abstract, setup_logging
import config


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
    suffixes = [
        config.SUFFIX_FORMATTED.replace('.md', ''),
        config.SUFFIX_YAML.replace('.md', ''),
        '_yaml',
        config.SUFFIX_WEBPAGE_SIMPLE.replace('.html', '')
    ]
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break

    return name


def main():
    """
    Main function to handle command-line execution of the abstract validation process.
    """
    parser = argparse.ArgumentParser(
        description="Validate and revise abstracts using the core pipeline."
    )
    parser.add_argument(
        "base_name",
        help="Base name of the transcript (e.g., 'Title - Presenter - Date')"
    )
    parser.add_argument(
        "--model",
        default=config.DEFAULT_MODEL,
        help=f"Claude model to use (default: {config.DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--target-score",
        type=float,
        default=4.5,
        help="Target quality score (default: 4.5)"
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum number of improvement iterations (default: 3)"
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Run without interactive prompts (auto-continue until target reached)"
    )

    args = parser.parse_args()

    base_name = resolve_base_name(args.base_name)

    logger = setup_logging('validate_abstract_cli')
    logger.info(f"Starting abstract validation for: {base_name}")

    success = validate_abstract(
        base_name=base_name,
        model=args.model,
        target_score=args.target_score,
        max_iterations=args.max_iterations,
        auto_continue=args.auto,
        logger=logger
    )

    if success:
        print("\nAbstract validation completed successfully.")
        return 0
    else:
        print("\nAbstract validation failed. Check the logs for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
