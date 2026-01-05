#!/usr/bin/env python3
"""
Utility to fix formatting of existing Bowen References files.
Applies cleaning logic and ensures the header exists.
"""
import argparse
import sys
from pathlib import Path
import config
from extraction_pipeline import _clean_bowen_output


def fix_file(base_name):
    project_dir = config.PROJECTS_DIR / base_name
    bowen_file = project_dir / f"{base_name}{config.SUFFIX_BOWEN}"

    if not bowen_file.exists():
        print(f"❌ File not found: {bowen_file}")
        return False

    print(f"Processing: {bowen_file.name}")
    content = bowen_file.read_text(encoding="utf-8")

    cleaned = _clean_bowen_output(content)
    final_content = f"## Bowen References\n\n{cleaned}"

    bowen_file.write_text(final_content, encoding="utf-8")
    print("✅ File updated with clean formatting and header.")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("base_name", help="Base name of the transcript")
    args = parser.parse_args()

    fix_file(args.base_name)
