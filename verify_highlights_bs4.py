#!/usr/bin/env python3
"""
Robust Highlight Verification Script using BeautifulSoup.
Verifies that HTML highlights match Markdown source quotes, handling HTML noise.

Usage:
    python verify_highlights_bs4.py "This is a test - Dave Galloway - 2025-12-07"
"""

import re
import sys
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
        r"(?:Speaker \d+|Unknown Speaker|[\w\s\.]+):", "", text, flags=re.IGNORECASE
    )

    # 2. Collapse whitespace and newlines
    text = re.sub(r"\s+", " ", text)

    # 3. Strip punctuation (keep only alphanumeric and spaces)
    text = re.sub(r"[^\w\s]", "", text)

    return text.strip().lower()


def load_source_quotes(md_file):
    """Extract (label, quote) pairs from a Bowen-references or emphasis-scored file.

    Reads the formats the producers ACTUALLY write (A7/P19). The prior regex only
    matched the abandoned `> **Label:** "Quote"` shape, so it returned [] on the
    real artifacts and the verifier reported a clean pass having checked nothing.
    Now handles, in order:
      1. Bowen:           `### Concept [hh:mm:ss]` newline `> "Quote"`
      2. Emphasis-scored: `[meta...] Concept: Name` newline `"Quote"`
      3. Legacy:          `> **Label:** "Quote"`
    A non-empty file that yields zero quotes is surfaced loudly, not silently
    treated as "no highlights to verify".
    """
    if not md_file.exists():
        print(f"❌ Source file not found: {md_file}")
        return []

    content = md_file.read_text(encoding="utf-8")

    results = []

    # 1. Bowen: `### Concept [ts]` then a blockquoted quote (reuses the canonical
    #    load_bowen_references shape).
    bowen_pat = r'###\s+([^\n\[]+?)(?:\s+\[\d{2}:\d{2}:\d{2}\])?\s*\n>\s+"([^"]+)"'
    results.extend(
        (label.strip(), quote.strip())
        for label, quote in re.findall(bowen_pat, content)
    )

    # 2. Emphasis-scored: `[Clinical - C1 - Rank: 95% | 00:00:07] Concept: Name`
    #    followed on the next line by the quoted text.
    emph_pat = r'^\[[^\]]*\]\s*Concept:\s*(.+?)\s*\n\s*"([^"]+)"'
    results.extend(
        (label.strip(), quote.strip())
        for label, quote in re.findall(emph_pat, content, flags=re.MULTILINE)
    )

    # 3. Legacy: `> **Label:** "Quote"`.
    legacy_pat = r'>\s*\*\*([^*]+):\*\*\s*"([^"]+)"'
    results.extend(
        (label.strip(), quote.strip())
        for label, quote in re.findall(legacy_pat, content)
    )

    if content.strip() and not results:
        print(
            f"⚠️  {md_file.name}: file is non-empty but ZERO quotes parsed — "
            f"producer/consumer format drift (A7/P19), NOT 'nothing to verify'."
        )

    return results


def extract_html_highlights(html_file):
    """Parse HTML with BeautifulSoup and extract highlighted text."""
    if not html_file.exists():
        print(f"❌ HTML file not found: {html_file}")
        return []

    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")

    highlights = []

    # Find all <mark> tags with relevant classes
    for tag in soup.find_all("mark", class_=["bowen-ref", "emphasis"]):
        # Get text content, stripping nested tags but keeping text
        text = tag.get_text(separator=" ", strip=True)

        highlights.append(
            {
                "type": "bowen" if "bowen-ref" in tag.get("class", []) else "emphasis",
                "text": text,
                "normalized": normalize_text(text),
            }
        )

    return highlights


def verify(base_name):
    print(f"Verifying highlights for: {base_name}\n")

    # 1. Resolve File Paths
    # Handle the _yaml suffix mentioned in the prompt if standard files aren't found
    project_dir = config.PROJECTS_DIR / base_name
    html_file = project_dir / f"{base_name}{config.SUFFIX_WEBPAGE}"

    # Emphasis: the pipeline writes the scored artifact; fall back to the legacy
    # emphasis-items names for older projects.
    emphasis_file = project_dir / f"{base_name}{config.SUFFIX_EMPHASIS_SCORED}"
    if not emphasis_file.exists():
        emphasis_file = project_dir / f"{base_name}{config.SUFFIX_EMPHASIS}"
    if not emphasis_file.exists():
        emphasis_file = project_dir / f"{base_name} - yaml - emphasis-items.md"

    bowen_file = project_dir / f"{base_name}{config.SUFFIX_BOWEN}"
    if not bowen_file.exists():
        bowen_file = project_dir / f"{base_name} - yaml - bowen-references.md"

    # 2. Load Data
    html_highlights = extract_html_highlights(html_file)
    emphasis_quotes = load_source_quotes(emphasis_file)
    bowen_quotes = load_source_quotes(bowen_file)

    print(f"Loaded {len(html_highlights)} highlights from HTML.")
    print(f"Loaded {len(emphasis_quotes)} emphasis items from MD.")
    print(f"Loaded {len(bowen_quotes)} bowen references from MD.")
    print("-" * 60)

    # 3. Compare
    all_quotes = [("emphasis", q) for q in emphasis_quotes] + [
        ("bowen", q) for q in bowen_quotes
    ]

    matches = 0
    failures = 0

    for category, (label, quote) in all_quotes:
        target = normalize_text(quote)
        best_ratio = 0.0
        best_match_text = ""

        # Search against all HTML highlights of the same category
        for h in html_highlights:
            # Allow cross-category matching if needed, but prefer strict
            if (
                h["type"] != category and h["type"] != "bowen"
            ):  # bowen often overlaps emphasis
                continue

            ratio = SequenceMatcher(None, target, h["normalized"]).ratio()

            # Check for substring match (common if highlight is partial)
            if target in h["normalized"] or h["normalized"] in target:
                if ratio < 0.9:
                    ratio = 0.9

            if ratio > best_ratio:
                best_ratio = ratio
                best_match_text = h["text"]

        if best_ratio > 0.85:
            print(f"✅ MATCH: {label[:50]}...")
            matches += 1
        else:
            print(f"❌ FAIL:  {label[:50]}...")
            print(f"   Source: '{quote[:60]}...'")
            print(f"   Best HTML Match ({best_ratio:.2f}): '{best_match_text[:60]}...'")
            failures += 1

    print("-" * 60)
    print(f"Summary: {matches} Passed, {failures} Failed.")

    # A7/P19: a source file that has quote content but parsed to ZERO quotes is
    # format drift, NOT "nothing to verify" — make it fail the exit code, not just
    # log. (A header-only / genuinely empty file has no `"` and is benign.)
    drift = []
    for name, src in (("emphasis", emphasis_file), ("bowen", bowen_file)):
        if src.exists() and '"' in src.read_text(encoding="utf-8"):
            parsed = emphasis_quotes if name == "emphasis" else bowen_quotes
            if not parsed:
                drift.append(name)
    if drift:
        print(
            f"⚠️  Format drift: {', '.join(drift)} file(s) contain quotes but parsed "
            f"ZERO — producer/consumer contract drift (A7/P19)."
        )

    return failures == 0 and not drift


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_highlights_bs4.py <base_name>")
        sys.exit(1)
    sys.exit(0 if verify(sys.argv[1]) else 1)
