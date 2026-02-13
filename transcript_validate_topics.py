#!/usr/bin/env python3
"""
Run lightweight deterministic validation of generated topics.
Writes topics-validation report in the transcript project folder.
"""

import argparse

import config
from transcript_utils import setup_logging
from validation_pipeline import validate_topics_lightweight


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate generated topics against formatted transcript text."
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

    logger = setup_logging("validate_topics")
    ok = validate_topics_lightweight(formatted_file, base_name, logger)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
