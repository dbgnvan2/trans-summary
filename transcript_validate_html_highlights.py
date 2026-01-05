#!/usr/bin/env python3
"""
Validate that Emphasized Items and Bowen References appear in the generated HTML.
This ensures that the highlighting logic in the HTML generator worked correctly.
"""

import sys
from difflib import SequenceMatcher

import config
from transcript_utils import (
    load_bowen_references,
    load_emphasis_items,
    normalize_text,
    setup_logging,
)


def find_best_match_in_html(needle, haystack_normalized, threshold=0.85):
    """
    Find the best matching substring in normalized HTML content.
    Returns (ratio, match_text).
    """
    needle_normalized = normalize_text(needle, aggressive=True)

    if needle_normalized in haystack_normalized:
        return (1.0, needle)

    # Fuzzy match
    needle_words = needle_normalized.split()
    haystack_words = haystack_normalized.split()
    needle_len = len(needle_words)

    if needle_len > len(haystack_words):
        return (0.0, None)

    best_ratio = 0
    best_match = None

    # Optimization: Check window only if first word matches (optional, but speeds up large files)
    # For now, we use standard sliding window
    for i in range(len(haystack_words) - needle_len + 1):
        window = ' '.join(haystack_words[i:i + needle_len])
        ratio = SequenceMatcher(None, needle_normalized, window).ratio()

        if ratio > best_ratio:
            best_ratio = ratio
            best_match = window
            if ratio > 0.98:  # Early exit
                break

    return (best_ratio, best_match)


def validate_html_highlights(base_name: str, logger=None):
    if logger is None:
        logger = setup_logging('validate_html_highlights')

    html_file = config.PROJECTS_DIR / base_name / \
        f"{base_name}{config.SUFFIX_WEBPAGE}"

    if not html_file.exists():
        logger.error("HTML file not found: %s", html_file)
        return False

    logger.info("Validating HTML content for: %s", html_file.name)

    # Read and normalize HTML (stripping tags to check text presence)
    html_content = html_file.read_text(encoding='utf-8')
    html_normalized = normalize_text(html_content, aggressive=True)

    # Load items to validate
    bowen_refs = load_bowen_references(base_name)
    emphasis_items = load_emphasis_items(base_name)

    all_items = [("Bowen Ref", label, quote) for label, quote in bowen_refs] + \
                [("Emphasis", label, quote) for label, quote in emphasis_items]

    if not all_items:
        logger.warning("No items found to validate.")
        return True

    logger.info("Checking %d items against HTML content...", len(all_items))

    found_count = 0
    missing_count = 0

    for type_, label, quote in all_items:
        # We use a slightly lower threshold for HTML because of potential
        # spacing/tag artifacts that normalization might miss
        ratio, _ = find_best_match_in_html(
            quote, html_normalized, threshold=0.80)

        if ratio >= 0.85:
            found_count += 1
            # logger.info(f"  ✓ Found {type_}: {label}")
        else:
            missing_count += 1
            logger.error("  ❌ MISSING in HTML %s: %s", type_, label)
            logger.error("     Quote: %s...", quote[:100])
            logger.error("     Best match ratio: %.2f", ratio)

    logger.info("-" * 40)
    logger.info("Validation Complete: %d found, %d missing.",
                found_count, missing_count)
    return missing_count == 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python transcript_validate_html_highlights.py <base_filename>")
        sys.exit(1)
    validate_html_highlights(sys.argv[1])
