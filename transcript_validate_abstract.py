#!/usr/bin/env python3
"""
CLI wrapper for validating and revising abstracts.

Usage:
    python transcript_validate_abstract.py "Title - Presenter - Date" [--model MODEL] [--target-score SCORE] [--max-iterations N] [--auto] [--generate-structured] [--validate-structured]
"""

import argparse
import sys
from pipeline import validate_abstract, generate_abstract_with_structured_pipeline, validate_abstract_with_structured_pipeline, setup_logging
import config


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
        help="Target quality score for iterative validation (default: 4.5)"
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum number of improvement iterations for iterative validation (default: 3)"
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Run iterative validation without interactive prompts (auto-continue until target reached)"
    )
    parser.add_argument(
        "--generate-structured",
        action="store_true",
        help="Generate a new abstract using the structured pipeline."
    )
    parser.add_argument(
        "--validate-structured",
        action="store_true",
        help="Validate an existing abstract using the structured coverage validation."
    )


    args = parser.parse_args()

    logger = setup_logging('validate_abstract_cli')
    logger.info(f"Starting abstract process for: {args.base_name}")

    success = False
    if args.generate_structured:
        logger.info("Generating structured abstract...")
        success = generate_abstract_with_structured_pipeline(
            base_name=args.base_name,
            logger=logger
        )
        if success:
            logger.info("\nStructured abstract generation completed successfully.")
        else:
            logger.error("\nStructured abstract generation failed.")
    elif args.validate_structured:
        logger.info("Validating abstract using structured coverage validation...")
        success = validate_abstract_with_structured_pipeline(
            base_name=args.base_name,
            logger=logger
        )
        if success:
            logger.info("\nStructured abstract validation completed successfully.")
        else:
            logger.error("\nStructured abstract validation failed.")
    else:
        logger.info("Running iterative abstract validation (old method)...")
        success = validate_abstract(
            base_name=args.base_name,
            model=args.model,
            target_score=args.target_score,
            max_iterations=args.max_iterations,
            auto_continue=args.auto,
            logger=logger
        )
        if success:
            print("\nIterative abstract validation completed successfully.")
        else:
            print("\nIterative abstract validation failed. Check the logs for details.")

    if success:
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
