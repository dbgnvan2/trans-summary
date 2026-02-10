#!/usr/bin/env python3
"""
Validate Bowen reference quotes against formatted transcript.
Checks that quoted text exists in the source document and includes attribution.
"""

import re
import sys
from pathlib import Path

import config
from transcript_utils import find_text_in_content, load_bowen_references, normalize_text


def contains_attribution(text: str) -> bool:
    """Require explicit attribution to Murray Bowen in the quote text."""
    t = normalize_text(text, aggressive=True)
    # Positive patterns: explicit attribution verbs near Bowen
    patterns = [
        r"\bmurray\s+bowen\b.*\b(said|wrote|thought|believed|described|referred|called|defined|voiced|stated|observed|explained)\b",
        r"\bbowen\b.*\b(said|wrote|thought|believed|described|referred|called|defined|voiced|stated|observed|explained)\b",
        r"\bto\s+quote\s+bowen\b",
        r"\bbowen'?s\s+quote\b",
    ]
    return any(re.search(p, t) for p in patterns)


def validate_bowen_items(base_name: str, formatted_file: Path):
    """Validate all Bowen reference quotes exist in the formatted transcript."""

    # Read formatted transcript
    with open(formatted_file, "r", encoding="utf-8") as f:
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
    attribution_missing = 0

    for i, (label, quote) in enumerate(quotes, 1):
        has_attr = contains_attribution(quote)
        start, end, ratio = find_text_in_content(
            quote, formatted_content, aggressive_normalization=True
        )

        print(f"\n{i}. {label}")
        print(f"   Quote preview: {quote[:80]}...")
        if not has_attr:
            print("   ❌ MISSING ATTRIBUTION (quote text lacks Bowen attribution)")
            attribution_missing += 1
            invalid_count += 1
            continue

        if ratio >= 0.95:
            print(f"   ✅ EXACT MATCH (ratio: {ratio:.2f})")
            valid_count += 1
        elif ratio >= config.FUZZY_MATCH_THRESHOLD:
            print(f"   ⚠️  PARTIAL MATCH (ratio: {ratio:.2f})")
            partial_count += 1
        else:
            print(f"   ❌ NOT FOUND (best ratio: {ratio:.2f})")
            invalid_count += 1

    print("\n" + "=" * 80)
    print("\nValidation Summary:")
    print(f"  ✅ Exact matches: {valid_count}")
    print(f"  ⚠️  Partial matches: {partial_count}")
    print(f"  ❌ Not found: {invalid_count}")
    print(f"  ❌ Missing attribution: {attribution_missing}")
    print(f"  Total: {len(quotes)}")

    accuracy = (valid_count + partial_count) / len(quotes) * 100 if quotes else 0
    print(f"\n  Overall accuracy: {accuracy:.1f}%")

    if invalid_count > 0:
        print(f"\n⚠️  WARNING: {invalid_count} quotes could not be validated!")


if __name__ == "__main__":
    # The main block was incomplete in context, this is a reconstruction
    if len(sys.argv) < 2:
        print("Usage: python transcript_validate_bowen.py <base_filename>")
        sys.exit(1)
    base_name = sys.argv[1]
    formatted_file = (
        config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_FORMATTED}"
    )
    if not formatted_file.exists():
        print(f"❌ Formatted file not found: {formatted_file}")
        sys.exit(1)
    validate_bowen_items(base_name, formatted_file)
