#!/usr/bin/env python3
"""
Validate Bowen reference quotes from topics-themes against formatted transcript.
Checks that quoted text actually exists in the source document.
"""

import os
import re
from pathlib import Path
from difflib import SequenceMatcher

from transcript_utils import load_bowen_references
import config
import sys


def normalize_text(text):
    """Normalize text for comparison by removing tags and punctuation."""
    # Remove speaker tags that can interrupt quotes
    text = re.sub(
        r'(\*\*[^*]+:\*\*\s*|<strong>[^<]+:</strong>\s*)',
        '',
        text,
        flags=re.IGNORECASE
    )

    # Remove [sic] and its variations
    text = re.sub(r'\[sic\]\s*\([^)]+\)', '', text)
    text = re.sub(r'\[sic\]', '', text)

    # Remove timestamps like [00:00:00]
    text = re.sub(r'\[\d{2}:\d{2}:\d{2}\]', ' ', text)

    text = text.strip().lower()

    # Remove punctuation for better fuzzy matching
    text = re.sub(r'[.,!?;:—\-\'\"()]', ' ', text)

    # Collapse multiple spaces after removals
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def find_best_match(needle, haystack, threshold=0.85):
    """Find the best matching substring in haystack for needle."""
    needle_normalized = normalize_text(needle)
    haystack_normalized = normalize_text(haystack)

    pos = haystack_normalized.find(needle_normalized)
    if pos != -1:
        return (1.0, needle)

    needle_words = needle_normalized.split()
    haystack_words = haystack_normalized.split()
    needle_len = len(needle_words)

    if needle_len > len(haystack_words):
        return (0, None)

    best_ratio = 0
    best_match = None

    for i in range(len(haystack_words) - needle_len + 1):
        window = ' '.join(haystack_words[i:i + needle_len])
        ratio = SequenceMatcher(None, needle_normalized, window).ratio()

        if ratio > best_ratio:
            best_ratio = ratio
            best_match = window

            if ratio >= 0.98:
                break

    if best_ratio >= threshold:
        return (best_ratio, best_match)

    return (best_ratio, None)


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
        ratio, match = find_best_match(
            quote_core, formatted_content, threshold=0.80)

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
    formatted_file = config.PROJECTS_DIR / base_name / \
        f"{base_name}{config.SUFFIX_FORMATTED}"
    if not formatted_file.exists():
        print(f"❌ Formatted file not found: {formatted_file}")
        sys.exit(1)
    validate_bowen_items(base_name, formatted_file)
