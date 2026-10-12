#!/usr/bin/env python3
"""
Validate emphasis items from topics-themes against formatted transcript.
Checks that quoted text actually exists in the source document.
"""

import re
from difflib import SequenceMatcher
from pathlib import Path

import config
from transcript_utils import load_emphasis_items


def normalize_text(text):
    """Normalize text for comparison by removing tags and punctuation."""
    # Remove speaker tags that can interrupt quotes
    text = re.sub(
        r"(\*\*[^*]+:\*\*\s*|<strong>[^<]+:</strong>\s*)", "", text, flags=re.IGNORECASE
    )

    # Remove [sic] and its variations
    text = re.sub(r"\[sic\]\s*\([^)]+\)", "", text)
    text = re.sub(r"\[sic\]", "", text)

    # Remove timestamps like [00:00:00]
    text = re.sub(r"\[\d{2}:\d{2}:\d{2}\]", " ", text)

    text = text.strip().lower()

    # Remove punctuation for better fuzzy matching
    text = re.sub(r"[.,!?;:—\-\'\"()]", " ", text)

    # Collapse multiple spaces after removals
    text = re.sub(r"\s+", " ", text)
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
        window = " ".join(haystack_words[i : i + needle_len])
        ratio = SequenceMatcher(None, needle_normalized, window).ratio()

        if ratio > best_ratio:
            best_ratio = ratio
            best_match = window

            if ratio >= 0.98:
                break

    if best_ratio >= threshold:
        return (best_ratio, best_match)

    return (best_ratio, None)


def validate_emphasis_items(base_name: str, formatted_file: Path) -> bool:
    """Check every emphasis quote with the release gate's verbatim test
    (``validation_pipeline.quote_is_verbatim_for_gate``) and print a report.
    Returns True when every quote passes (False when none were found or any fails).

    It used to unpack 2-tuples (crashing when the scored file gives 3-tuples) and
    match only a quote's first 15 words.
    Spec:  docs/plan_todo_triage_2026-10-11.md#D6
    Tests: tests/test_emphasis_threshold_d6.py::test_d6_standalone_cli_runs_and_uses_gate_test
    """
    from validation_pipeline import quote_is_verbatim_for_gate

    formatted_content = Path(formatted_file).read_text(encoding="utf-8")
    quotes = load_emphasis_items(base_name)

    if not quotes:
        print("❌ No emphasis quotes found to validate")
        return False

    print(f"Found {len(quotes)} emphasis items to validate\n")
    print("=" * 80)

    valid_count = partial_count = invalid_count = 0
    for i, item in enumerate(quotes, 1):
        label, quote = item[0], item[1]
        ok, ends, coverage = quote_is_verbatim_for_gate(quote, formatted_content)

        print(f"\n{i}. {label}")
        print(f"   Quote preview: {quote[:80]}...")
        if not ok:
            print(f"   ❌ NOT FOUND (match {ends:.2f}, word coverage {coverage:.2f})")
            print("   The release gate will block this quote.")
            invalid_count += 1
        elif ends >= config.EMPHASIS_QUOTE_FOUND_RATIO:
            print(f"   ✅ EXACT MATCH (ratio: {ends:.2f})")
            valid_count += 1
        else:
            print(f"   ⚠️  PARTIAL MATCH (ratio: {ends:.2f}); passes the gate")
            partial_count += 1

    print("\n" + "=" * 80)
    print("\nValidation Summary:")
    print(f"  ✅ Exact matches: {valid_count}")
    print(f"  ⚠️  Partial matches: {partial_count}")
    print(f"  ❌ Not found: {invalid_count}")
    print(f"  Total: {len(quotes)}")
    if invalid_count:
        print(f"\n⚠️  WARNING: {invalid_count} quote(s) are not verbatim in the transcript.")
    return invalid_count == 0


if __name__ == "__main__":
    import sys

    import config

    base_name = sys.argv[1]

    formatted_file = (
        config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_FORMATTED}"
    )

    if not formatted_file.exists():
        print(f"❌ Formatted file not found: {formatted_file}")
        sys.exit(1)

    print(f"Validating emphasis items for {base_name}...")
    print(f"  Formatted: {formatted_file.name}")

    sys.exit(0 if validate_emphasis_items(base_name, formatted_file) else 1)
