#!/usr/bin/env python3
"""
Validate emphasis items from archival summary against formatted transcript.
Checks that quoted text actually exists in the source document.
"""

import os
import re
from pathlib import Path
from difflib import SequenceMatcher


def normalize_text(text):
    """Normalize text for comparison by removing [sic] markers, extra whitespace, and punctuation variations."""
    # Remove [sic] and its variations
    text = re.sub(r'\[sic\]\s*\([^)]+\)', '', text)
    text = re.sub(r'\[sic\]', '', text)

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)

    # Remove leading/trailing whitespace
    text = text.strip()

    return text.lower()


def extract_emphasis_quotes(extracts_summary_file):
    """Extract all quoted text from Emphasized Items section."""
    with open(extracts_summary_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the Emphasized Items section
    match = re.search(
        r'## \*\*Emphasized Items\*\*(.*?)(?=---|\Z)', content, re.DOTALL)
    if not match:
        print("❌ No Emphasized Items section found")
        return []

    emphasis_section = match.group(1)

    # Extract all quotes (text between quotes after >)
    # Pattern: > **[Label]:** "quote text" - **[Type]**
    quote_pattern = r'>\s*\*\*([^*]+):\*\*\s*"([^"]+)"'
    quotes = re.findall(quote_pattern, emphasis_section)

    return [(label.strip(), quote.strip()) for label, quote in quotes]


def find_best_match(needle, haystack, threshold=0.85):
    """Find the best matching substring in haystack for needle.
    Returns (match_ratio, matched_text) or (0, None) if no good match."""

    needle_normalized = normalize_text(needle)
    haystack_normalized = normalize_text(haystack)

    # Try exact match first
    if needle_normalized in haystack_normalized:
        return (1.0, needle)

    # Try fuzzy matching on sliding windows
    needle_words = needle_normalized.split()
    needle_len = len(needle_words)

    # Use word-level matching for better handling of small differences
    haystack_words = haystack_normalized.split()

    best_ratio = 0
    best_match = None

    # Slide a window across the haystack
    for i in range(len(haystack_words) - needle_len + 1):
        window = ' '.join(haystack_words[i:i + needle_len])
        ratio = SequenceMatcher(None, needle_normalized, window).ratio()

        if ratio > best_ratio:
            best_ratio = ratio
            # Find the actual text in the original (non-normalized) haystack
            # This is approximate but good enough for validation
            best_match = window

    if best_ratio >= threshold:
        return (best_ratio, best_match)

    return (best_ratio, None)


def validate_emphasis_items(formatted_file, extracts_summary_file):
    """Validate all emphasis quotes exist in the formatted transcript."""

    # Read formatted transcript
    with open(formatted_file, 'r', encoding='utf-8') as f:
        formatted_content = f.read()

    # Extract emphasis quotes from archival
    quotes = extract_emphasis_quotes(extracts_summary_file)

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

    TRANSCRIPTS_BASE = Path(os.environ.get(
        'TRANSCRIPTS_DIR', Path.home() / 'transcripts'))

    if len(sys.argv) < 2:
        print("Usage: python validate_emphasis.py <base_filename>")
        print("Example: python validate_emphasis.py 'Roots of Bowen Theory - Dr Michael Kerr - 2019-11-15'")
        sys.exit(1)

    base_name = sys.argv[1]

    # Construct file paths
    formatted_file = TRANSCRIPTS_BASE / \
        "formatted" / f"{base_name} - formatted.md"
    extracts_summary_file = TRANSCRIPTS_BASE / \
        "summaries" / f"{base_name} - extracts-summary.md"

    # Check files exist
    if not formatted_file.exists():
        print(f"❌ Formatted file not found: {formatted_file}")
        sys.exit(1)

    if not extracts_summary_file.exists():
        print(f"❌ Extracts-summary file not found: {extracts_summary_file}")
        sys.exit(1)

    print(f"Validating emphasis items...")
    print(f"  Formatted: {formatted_file.name}")
    print(f"  Archival:  {extracts_summary_file.name}\n")

    validate_emphasis_items(formatted_file, extracts_summary_file)
