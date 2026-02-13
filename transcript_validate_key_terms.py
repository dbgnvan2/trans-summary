#!/usr/bin/env python3
"""
Validate key terms against formatted transcript text.
Writes a key-terms-validation report in the transcript project folder.
"""

import argparse
from pathlib import Path

import config
from transcript_utils import setup_logging
from validation_pipeline import validate_key_terms_fidelity


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate generated key terms against the formatted transcript."
    )
    parser.add_argument(
        "base_name", help="Base transcript name: 'Title - Presenter - Date'"
    )
    args = parser.parse_args()

    base_name = args.base_name
    formatted_file = (
        config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_FORMATTED}"
    )

    if not formatted_file.exists():
        print(f"❌ Formatted file not found: {formatted_file}")
        return 1

    logger = setup_logging("validate_key_terms")
    ok = validate_key_terms_fidelity(formatted_file, base_name, logger)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
