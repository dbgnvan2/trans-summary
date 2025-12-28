#!/usr/bin/env python3
"""
Robust Highlight Verification Script using BeautifulSoup.
Verifies that HTML highlights match Markdown source quotes, handling HTML noise.

Usage:
    python verify_highlights_bs4.py "This is a test - Dave Galloway - 2025-12-07"
"""

import sys
import re
import os
from pathlib import Path
from difflib import SequenceMatcher
import config

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("❌ Error: beautifulsoup4 is not installed. Run: pip install beautifulsoup4")
    sys.exit(1)


def normalize_text(text):
    """
    Aggressively normalize text for comparison.
    Strips punctuation, speaker labels, and collapses whitespace.
    """
    if not text:
        return ""

    # 1. Strip Speaker Labels (Noise in HTML)
    # Matches "Speaker 1:", "Unknown Speaker:", "Dr. Kerr:", etc.
    text = re.sub(
        r'(?:Speaker \d+|Unknown Speaker|[\w\s\.]+):', '', text, flags=re.IGNORECASE)

    # 2. Collapse whitespace and newlines
    text = re.sub(r'\s+', ' ', text)

    # 3. Strip punctuation (keep only alphanumeric and spaces)
    text = re.sub(r'[^\w\s]', '', text)

    return text.strip().lower()


def load_source_quotes(md_file):
    """Extract quotes from Markdown file (Bowen References or Emphasis Items)."""
    if not md_file.exists():
        print(f"❌ Source file not found: {md_file}")
        return []

    content = md_file.read_text(encoding='utf-8')

    # Extract quotes: > **Label:** "Quote"
    # Handles variations in bolding and spacing
    pattern = r'>\s*\*\*([^*]+):\*\*\s*"([^"]+)"'
    matches = re.findall(pattern, content)

    return [(label.strip(), quote.strip()) for label, quote in matches]


def extract_html_highlights(html_file):
    """Parse HTML with BeautifulSoup and extract highlighted text."""
    if not html_file.exists():
        print(f"❌ HTML file not found: {html_file}")
        return []

    soup = BeautifulSoup(html_file.read_text(encoding='utf-8'), 'html.parser')

    highlights = []

    # Find all <mark> tags with relevant classes
    for tag in soup.find_all('mark', class_=['bowen-ref', 'emphasis']):
        # Get text content, stripping nested tags but keeping text
        text = tag.get_text(separator=" ", strip=True)

        highlights.append({
            'type': 'bowen' if 'bowen-ref' in tag.get('class', []) else 'emphasis',
            'text': text,
            'normalized': normalize_text(text)
        })

    return highlights


def verify(base_name):
    print(f"Verifying highlights for: {base_name}\n")

    # 1. Resolve File Paths
    # Handle the _yaml suffix mentioned in the prompt if standard files aren't found
    html_file = config.WEBPAGES_DIR / f"{base_name}.html"

    # Try standard name first, then _yaml variant
    emphasis_file = config.SUMMARIES_DIR / f"{base_name} - emphasis-items.md"
    if not emphasis_file.exists():
        emphasis_file = config.SUMMARIES_DIR / \
            f"{base_name} - yaml - emphasis-items.md"

    bowen_file = config.SUMMARIES_DIR / f"{base_name} - bowen-references.md"
    if not bowen_file.exists():
        bowen_file = config.SUMMARIES_DIR / \
            f"{base_name} - yaml - bowen-references.md"

    # 2. Load Data
    html_highlights = extract_html_highlights(html_file)
    emphasis_quotes = load_source_quotes(emphasis_file)
    bowen_quotes = load_source_quotes(bowen_file)

    print(f"Loaded {len(html_highlights)} highlights from HTML.")
    print(f"Loaded {len(emphasis_quotes)} emphasis items from MD.")
    print(f"Loaded {len(bowen_quotes)} bowen references from MD.")
    print("-" * 60)

    # 3. Compare
    all_quotes = [('emphasis', q) for q in emphasis_quotes] + \
                 [('bowen', q) for q in bowen_quotes]

    matches = 0
    failures = 0

    for category, (label, quote) in all_quotes:
        target = normalize_text(quote)
        best_ratio = 0.0
        best_match_text = ""

        # Search against all HTML highlights of the same category
        for h in html_highlights:
            # Allow cross-category matching if needed, but prefer strict
            if h['type'] != category and h['type'] != 'bowen':  # bowen often overlaps emphasis
                continue

            ratio = SequenceMatcher(None, target, h['normalized']).ratio()

            # Check for substring match (common if highlight is partial)
            if target in h['normalized'] or h['normalized'] in target:
                if ratio < 0.9:
                    ratio = 0.9

            if ratio > best_ratio:
                best_ratio = ratio
                best_match_text = h['text']

        if best_ratio > 0.85:
            print(f"✅ MATCH: {label[:50]}...")
            matches += 1
        else:
            print(f"❌ FAIL:  {label[:50]}...")
            print(f"   Source: '{quote[:60]}...'")
            print(
                f"   Best HTML Match ({best_ratio:.2f}): '{best_match_text[:60]}...'")
            failures += 1

    print("-" * 60)
    print(f"Summary: {matches} Passed, {failures} Failed.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_highlights_bs4.py <base_name>")
        sys.exit(1)
    verify(sys.argv[1])
