#!/usr/bin/env python3
"""Debug script to identify which emphasis items fail to match."""

import re
import sys
from difflib import SequenceMatcher

import config

# Import from existing modules
from transcript_utils import extract_emphasis_items, strip_yaml_frontmatter


def normalize_text(text):
    """Normalize text for comparison - removes filler words and punctuation."""
    # Remove speaker tags that can interrupt quotes
    # **Speaker 1:** or **Unknown Speaker:**
    text = re.sub(r"\*\*[^*]+:\*\*\s*", "", text)

    text = text.strip()
    text = text.lower()

    # Remove punctuation for better fuzzy matching
    text = re.sub(r"[.,!?;:—\-\'\"()]", " ", text)

    # Remove common transcription filler words that don't affect meaning
    filler_words = [
        r"\bso\b",
        r"\bagain\b",
        r"\bjust\b",
        r"\breally\b",
        r"\buh\b",
        r"\bum\b",
        r"\byou know\b",
        r"\bi mean\b",
        r"\blike\b",
        r"\bactually\b",
        r"\bbasically\b",
    ]
    for filler in filler_words:
        text = re.sub(filler, " ", text)

    # Collapse multiple spaces again after removals
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def find_text_in_content(needle, haystack):
    """Find text in content with fuzzy matching."""
    needle_normalized = normalize_text(needle)
    haystack_normalized = normalize_text(haystack)

    # Try exact match first
    pos = haystack_normalized.find(needle_normalized)
    if pos != -1:
        return (pos, pos + len(needle_normalized), 1.0)

    # Fall back to fuzzy matching
    needle_words = needle_normalized.split()
    haystack_words = haystack_normalized.split()
    needle_len = len(needle_words)

    if needle_len > len(haystack_words):
        return (None, None, 0.0)

    best_ratio = 0.0
    best_pos = None

    for i in range(len(haystack_words) - needle_len + 1):
        window = " ".join(haystack_words[i : i + needle_len])
        ratio = SequenceMatcher(None, needle_normalized, window).ratio()

        if ratio > best_ratio:
            best_ratio = ratio
            best_pos = i

            # Early termination for very good matches
            if ratio >= 0.98:
                break

    if best_pos is not None and best_ratio >= 0.85:
        # Convert word position back to character position
        char_pos = len(" ".join(haystack_words[:best_pos]))
        if best_pos > 0:
            char_pos += 1  # Account for space
        char_end = char_pos + len(
            " ".join(haystack_words[best_pos : best_pos + needle_len])
        )
        return (char_pos, char_end, best_ratio)

    return (None, None, best_ratio)


def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_emphasis_matching.py '<Title - Author - Date>'")
        sys.exit(1)

    base_name = sys.argv[1]

    project_dir = config.PROJECTS_DIR / base_name
    # Point to the main raw extracts file
    all_key_items_file = project_dir / f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"
    emphasis_file = project_dir / f"{base_name}{config.SUFFIX_EMPHASIS}"
    formatted_file = project_dir / f"{base_name}{config.SUFFIX_FORMATTED}"

    if not all_key_items_file.exists() and not emphasis_file.exists():
        print(f"Error: {all_key_items_file} and {emphasis_file} not found")
        sys.exit(1)

    if not formatted_file.exists():
        print(f"Error: {formatted_file} not found")
        sys.exit(1)

    print("Using files:")
    source_file = emphasis_file if emphasis_file.exists() else all_key_items_file
    print(f"  Source for Emphasis Items: {source_file.name}")

    # Load emphasis items from topics-themes
    with open(source_file, "r", encoding="utf-8") as f:
        content = f.read()

    emphasis_items = extract_emphasis_items(strip_yaml_frontmatter(content))

    # Load formatted content
    with open(formatted_file, "r", encoding="utf-8") as f:
        formatted_content = f.read()

    formatted_content = strip_yaml_frontmatter(formatted_content)

    print(f"\n{'=' * 70}")
    print("EMPHASIS MATCHING DEBUG REPORT")
    print(f"{'=' * 70}\n")
    print(f"Total emphasis items: {len(emphasis_items)}\n")

    matched = []
    failed = []

    for i, (label, quote) in enumerate(emphasis_items, 1):
        quote_words = quote.split()
        search_text = " ".join(quote_words[: min(75, len(quote_words))])
        word_count = len(quote_words)
        start, end, ratio = find_text_in_content(search_text, formatted_content)

        if start is not None and ratio >= 0.85:
            matched.append((i, label, ratio, word_count))
            print(
                f"✅ Item {i}: {label[:60]}... (ratio: {ratio:.2%}, {word_count} words)"
            )
        else:
            failed.append((i, label, ratio, search_text, word_count, quote))
            print(
                f"❌ Item {i}: {label[:60]}... (ratio: {ratio:.2%}, {word_count} words)"
            )
    print(
        f"Failed:  {len(failed)}/{len(emphasis_items)} ({len(failed) / len(emphasis_items):.1%})"
    )

    if failed:
        print(f"\n{'=' * 70}")
        print("FAILED ITEMS DETAILS")
        print(f"{'=' * 70}\n")

        for i, label, ratio, search_text, word_count, full_quote in failed:
            print(f"\n{'─' * 70}")
            print(f"Item #{i}: {label}")
            print(f"{'─' * 70}")
            print(f"Best match ratio: {ratio:.2%}")
            print(f"Quote length: {word_count} words")
            print(
                f"Search text used: {len(search_text.split())} words (first 50 of quote)"
            )
            print("\nFull quote:")
            print(f"  {full_quote[:200]}{'...' if len(full_quote) > 200 else ''}")
            print("\nSearch text:")
            print(f"  {search_text[:200]}{'...' if len(search_text) > 200 else ''}")
            print()

    # Analyze commonalities
    if failed:
        print(f"\n{'=' * 70}")
        print("COMMONALITY ANALYSIS")
        print(f"{'=' * 70}\n")

        avg_ratio = sum(f[2] for f in failed) / len(failed)
        avg_words = sum(f[4] for f in failed) / len(failed)
        short_quotes = sum(1 for f in failed if f[4] < 75)
        very_short = sum(1 for f in failed if f[4] < 30)

        print(f"Average match ratio of failed items: {avg_ratio:.2%}")
        print(f"Average word count of failed items: {avg_words:.1f} words")
        print(f"Failed items with < 75 words: {short_quotes}/{len(failed)}")
        print(f"Failed items with < 30 words: {very_short}/{len(failed)}")
        print("\nNote: Search uses first 75 words only.")
        print("      Threshold is 85% similarity.")
        print("      Normalization removes filler words & punctuation.")


if __name__ == "__main__":
    main()
