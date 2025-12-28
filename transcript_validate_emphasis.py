#!/usr/bin/env python3
"""
Validate emphasis items from topics-themes against formatted transcript.
Checks that quoted text actually exists in the source document.
"""

import os
import re
from pathlib import Path
from difflib import SequenceMatcher

from transcript_utils import extract_emphasis_items, strip_yaml_frontmatter


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


def extract_emphasis_quotes(topics_themes_file):
    """Extract all quoted text from Emphasized Items section."""
    extracts_path = Path(topics_themes_file)
    stem = extracts_path.stem.replace(' - topics-themes', '')
    emphasis_file = extracts_path.parent / f"{stem} - emphasis-items.md"

    source_file = emphasis_file if emphasis_file.exists() else extracts_path
    content = source_file.read_text(encoding='utf-8')
    content = strip_yaml_frontmatter(content)

    quotes = extract_emphasis_items(content)
    if not quotes:
        print("❌ No Emphasized Items section found")

    return quotes


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


def validate_emphasis_items(formatted_file, topics_themes_file):
    """Validate all emphasis quotes exist in the formatted transcript."""

    # Read formatted transcript
    with open(formatted_file, 'r', encoding='utf-8') as f:
        formatted_content = f.read()

    # Extract emphasis quotes from topics-themes
    quotes = extract_emphasis_quotes(topics_themes_file)

    if not quotes:
        print("❌ No emphasis quotes found to validate")
        return

    print(f"Found {len(quotes)} emphasis items to validate\n")
    print("=" * 80)

    valid_count = 0
    invalid_count = 0
    partial_count = 0

    for i, (label, quote) in enumerate(quotes, 1):
        # Try to find a substantial portion of the quote (first 50+ chars for matching)
        # Use smaller snippet to avoid issues with context boundaries
        quote_core = ' '.join(quote.split()[:15])  # First 15 words

        ratio, match = find_best_match(
            quote_core, formatted_content, threshold=0.80)

        print(f"\n{i}. {label}")
        print(f"   Quote preview: {quote[:80]}...")

        if ratio >= 0.95:
            print(f"   ✅ EXACT MATCH (ratio: {ratio:.2f})")
            valid_count += 1
        elif ratio >= 0.80:
            print(f"   ⚠️  PARTIAL MATCH (ratio: {ratio:.2f})")
            print(f"   May have minor formatting differences")
            partial_count += 1
        else:
            print(f"   ❌ NOT FOUND (best ratio: {ratio:.2f})")
            print(f"   WARNING: Quote may be fabricated or heavily paraphrased")
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
        print("  Review these manually to check if Claude fabricated content.")


if __name__ == "__main__":
    import sys
    import config

    if len(sys.argv) < 2:
        print("Usage: python validate_emphasis.py <base_filename>")
        print("Example: python validate_emphasis.py 'Roots of Bowen Theory - Dr Michael Kerr - 2019-11-15'")
  if    len(sys.argv) < 2:
        print("Usage: python validate_emphasis.py <base_filename>")
        print("Example: python validate_emphasis.py 'Roots of Bowen Theory - Dr Michael Kerr - 2019-11-15'")
  if    len(sys.argv) < 2:
        print("Usage: python validate_emphasis.py <base_filename>")
        print("Example: python validate_emphasis.py 'Roots of Bowen Theory - Dr Michael Kerr - 2019-11-15'")
        sys.exit(1)
nfig.SUMMARIES_DIR / f"{base_name} - emphasis-items.md"

    # Check files exist
    if ntformatted_file.exists():
        print(f"❌ Formatted file not found: {formatted_file}")
        sys.exit(1)

    base_name = sys.argv[1]

    # Construct file pnfig.SUMMARIES_DIR / f"{base_name} - emphasis-items.md"

    # Check files exist
    if nattformatted_file.exists():
        print(f"❌ Formatted file not found: {formatted_file}")
        sys.exit(1)
hs
    formatted_file = config.FORMATTED_DIR / f"{base_name} - formatted.md"
    topics_themes_file = config.SUMMARIES_DIR / f"{base_name} - topics-themes.md"
    emphasis_file = config.SUMMARIES_DIR / f"{base_name} - emphasis-items.md"

    # Check files exist
    if not formatted_file.exists():
        print(f"❌ Formatted file not found: {formatted_file}")
        sys.exit(1)

    if not topics_themes_file.exists() and not emphasis_file.exists():
        print(
            f"❌ Topics-Themes file not found: {topics_themes_file}")
        sys.exit(1)

    print(f"Validating emphasis items...")
    print(f"  Formatted: {formatted_file.name}")
    archival_name = emphasis_file.name if emphasis_file.exists() else topics_themes_file.name
    print(f"  Archival:  {archival_name}\n")

    validate_emphasis_items(formatted_file, topics_themes_file)
