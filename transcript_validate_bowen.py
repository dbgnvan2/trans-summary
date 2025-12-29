#!/usr/bin/env python3
"""
Validate Bowen reference quotes from topics-themes against formatted transcript.
Checks that quoted text actually exists in the source document.
"""

import os
import re
from pathlib import Path
from difflib import SequenceMatcher

from transcript_utils import load_bowen_references, find_text_in_content
import config
import sys

# ...

base_name = sys.argv[1]

formatted_file = config.FORMATTED_DIR / \
     f"{base_name}{config.SUFFIX_FORMATTED}"
 topics_themes_file = config.SUMMARIES_DIR / \
      f"{base_name}{config.SUFFIX_KEY_ITEMS_RAW_LEGACY}"
  bowen_file = config.SUMMARIES_DIR / f"{base_name}{config.SUFFIX_BOWEN}"

   if not formatted_file.exists():
        print(f"❌ Formatted file not found: {formatted_file}")
        sys.exit(1)

    if not topics_themes_file.exists() and not bowen_file.exists():
        print(f"❌ Topics-Themes file not found: {topics_themes_file}")
        sys.exit(1)

    print(f"Validating Bowen references...")
    print(f"  Formatted: {formatted_file.name}")
    print(
        f"  Archival:  {bowen_file.name if bowen_file.exists() else topics_themes_file.name}\n")

    validate_bowen_items(formatted_file, topics_themes_file)


def validate_bowen_items(base_name: str, formatted_file: Path):
    """Validate all Bowen reference quotes exist in the formatted transcript."""

    # Read formatted transcript
    with open(formatted_file, 'r', encoding='utf-8') as f:
        formatted_content = f.read()

    # Extract quotes using the centralized loader
    quotes = load_bowen_references(base_name)

    if not quotes:
        print("⚠️ No Bowen references found to validate")
        return

    print(f"Found {len(quotes)} Bowen references to validate\n")
    print("=" * 80)

    valid_count = 0
    invalid_count = 0
    partial_count = 0

    for i, (label, quote) in enumerate(quotes, 1):
        quote_core = ' '.join(quote.split()[:15])

        _, _, ratio = find_text_in_content(quote_core, formatted_content)

        print(f"\n{i}. {label}")
        print(f"   Quote preview: {quote[:80]}...")

        if ratio >= 0.95:
            print(f"   ✅ EXACT MATCH (ratio: {ratio:.2f})")
            valid_count += 1
        elif ratio >= 0.80:
            print(f"   ⚠️  PARTIAL MATCH (ratio: {ratio:.2f})")
            partial_count += 1
        else:
            print(f"   ❌ NOT FOUND (best ratio: {ratio:.2f})")
            invalid_count += 1

    print("\n" + "=" * 80)
    print(f"\nValidation Summary:")
    print(f"  ✅ Exact matches: {valid_count}")
    print(f"  ⚠️  Partial matches: {partial_count}")
    print(f"  ❌ Not found: {invalid_count}")
    print(f"  Total: {len(quotes)}")

    accuracy = (valid_count + partial_count) / \
        len(quotes) * 100 if quotes else 0
    print(f"\n  Overall accuracy: {accuracy:.1f}%")

    if invalid_count > 0:
        print(f"\n⚠️  WARNING: {invalid_count} quotes could not be validated!")


if __name__ == "__main__":
    # The main block was incomplete in context, this is a reconstruction
    if len(sys.argv) < 2:
        print("Usage: python transcript_validate_bowen.py <base_filename>")
        sys.exit(1)
    base_name = sys.argv[1]
    formatted_file = config.FORMATTED_DIR / \
        f"{base_name}{config.SUFFIX_FORMATTED}"
    if not formatted_file.exists():
        print(f"❌ Formatted file not found: {formatted_file}")
        sys.exit(1)
    validate_bowen_items(base_name, formatted_file)
