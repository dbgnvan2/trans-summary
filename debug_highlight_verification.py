#!/usr/bin/env python3
"""
Debug script to verify that highlighted text in HTML matches the source quotes.
Compares the text inside <mark> tags in the generated HTML against the 
original quotes from Bowen References, Emphasis Items, and Key Terms.

Usage:
    python debug_highlight_verification.py "Title - Presenter - Date"
"""

import argparse
import os
import re
import sys
from pathlib import Path
from difflib import SequenceMatcher
from html import unescape

import config
from transcript_utils import (
    load_bowen_references,
    load_emphasis_items,
    strip_yaml_frontmatter
)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("❌ Error: beautifulsoup4 is not installed. Run: pip install beautifulsoup4")
    sys.exit(1)


def normalize(text):
    """Normalize text for comparison."""
    if not text:
        return ""
    # Strip Speaker Labels (Noise in HTML)
    text = re.sub(
        r'(?:Speaker \d+|Unknown Speaker|[\w\s\.]+):', '', text, flags=re.IGNORECASE)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    # Strip punctuation
    text = re.sub(r'[^\w\s]', '', text)
    return text.strip().lower()


def extract_html_highlights(html_path):
    """Extract all highlights from HTML content."""
    if not html_path.exists():
        print(f"❌ HTML file not found: {html_path}")
        return []

    soup = BeautifulSoup(html_path.read_text(encoding='utf-8'), 'html.parser')
    highlights = []

    # Pattern for mark tags (Bowen/Emphasis)
    for tag in soup.find_all('mark', class_=['bowen-ref', 'emphasis']):
        text = tag.get_text(separator=" ", strip=True)
        highlights.append({
            'tag': 'mark',
            'class': " ".join(tag.get('class', [])),
            'title': tag.get('title', ''),
            'text': text,
            'clean_text': normalize(text)
        })

    return highlights


def verify_highlights(base_name):
    """Compare source quotes against HTML highlights."""
    print(f"Verifying highlights for: {base_name}")

    # 1. Load Source Data
    bowen_refs = load_bowen_references(base_name)
    emphasis_items = load_emphasis_items(base_name)

    print(f"  Loaded {len(bowen_refs)} Bowen references")
    print(f"  Loaded {len(emphasis_items)} Emphasis items")

    # 2. Load HTML Highlights
    html_path = config.WEBPAGES_DIR / f"{base_name}.html"
    highlights = extract_html_highlights(html_path)
    print(f"  Found {len(highlights)} highlights in HTML")

    print("\n" + "="*80)
    print("VERIFICATION REPORT")
    print("="*80)

    # Helper to find match
    def find_match(quote, category_filter):
        norm_quote = normalize(quote)
        best_ratio = 0
        best_h = None

        for h in highlights:
            # Filter by category if needed (e.g. only check 'bowen-ref' class)
            if category_filter not in h['class']:
                continue

            ratio = SequenceMatcher(None, norm_quote, h['clean_text']).ratio()

            # Also check if one is a substring of the other
            if norm_quote in h['clean_text'] or h['clean_text'] in norm_quote:
                if ratio < 0.8:  # Boost ratio if substring
                    ratio = 0.9

            if ratio > best_ratio:
                best_ratio = ratio
                best_h = h

        return best_ratio, best_h

    # Verify Bowen References
    print("\n--- Bowen References ---")
    for label, quote in bowen_refs:
        ratio, match = find_match(quote, 'bowen-ref')
        if ratio > 0.85:
            print(f"✅ MATCH: {label}")
        elif ratio > 0.5:
            print(f"⚠️  PARTIAL: {label}")
            print(f"   Source: '{quote[:60]}...'")
            print(f"   HTML:   '{match['text'][:60]}...'")
            print(f"   Ratio:  {ratio:.2f}")
        else:
            print(f"❌ MISSING: {label}")
            print(f"   Source: '{quote[:60]}...'")

    # Verify Emphasis Items
    print("\n--- Emphasis Items ---")
    for label, quote in emphasis_items:
        ratio, match = find_match(quote, 'emphasis')
        if ratio > 0.85:
            print(f"✅ MATCH: {label}")
        elif ratio > 0.5:
            print(f"⚠️  PARTIAL: {label}")
            print(f"   Source: '{quote[:60]}...'")
            print(f"   HTML:   '{match['text'][:60]}...'")
            print(f"   Ratio:  {ratio:.2f}")
        else:
            print(f"❌ MISSING: {label}")
            print(f"   Source: '{quote[:60]}...'")


def main():
    parser = argparse.ArgumentParser(
        description="Verify HTML highlights against source quotes.")
    parser.add_argument("base_name", help="Base name of the transcript")
    args = parser.parse_args()

    verify_highlights(args.base_name)


if __name__ == "__main__":
    main()
