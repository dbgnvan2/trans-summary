#!/usr/bin/env python3
"""
Validate generated HTML webpage against source materials.
Checks that all expected content from extracts-summary appears in the webpage.
Supports both sidebar layout and simple single-column layout.

Usage:
    python transcript_validate_webpage.py "Title - Presenter - Date" [--simple]

Example:
    python transcript_validate_webpage.py "This is a test - Dave Galloway - 2025-12-07"
    python transcript_validate_webpage.py "This is a test - Dave Galloway - 2025-12-07" --simple
"""

import argparse
import os
import re
from pathlib import Path
from html import unescape
from difflib import SequenceMatcher


# Directories
TRANSCRIPTS_BASE = Path(
    os.getenv("TRANSCRIPTS_DIR", Path.home() / "transcripts"))
FORMATTED_DIR = TRANSCRIPTS_BASE / "formatted"
SUMMARIES_DIR = TRANSCRIPTS_BASE / "summaries"
WEBPAGES_DIR = TRANSCRIPTS_BASE / "webpages"


def strip_html_tags(text):
    """Remove HTML tags from text."""
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    return text.strip()


def count_sections_in_formatted(formatted_file):
    """Count sections in formatted markdown file."""
    with open(formatted_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Strip YAML front matter
    if content.startswith('---'):
        parts = content.split('---\n', 2)
        if len(parts) >= 3:
            content = parts[2]

    # Count h2 sections (## Section Name)
    sections = re.findall(r'^## (.+)$', content, re.MULTILINE)
    return len(sections), sections


def count_sections_in_html(html_file):
    """Count sections in HTML file (works for both sidebar and simple layouts)."""
    with open(html_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Try sidebar layout first (main-content class)
    main_content_match = re.search(
        r'<main class="main-content">(.*?)</main>',
        content,
        re.DOTALL
    )

    if main_content_match:
        # Sidebar layout - count h2 in main content area
        main_content = main_content_match.group(1)
        sections = re.findall(r'<h2>([^<]+)</h2>', main_content)
        return len(sections), sections

    # Try simple layout (content class, no sidebar)
    simple_content_match = re.search(
        r'<div class="content">(.*?)</div>\s*</div>\s*</body>',
        content,
        re.DOTALL
    )

    if simple_content_match:
        # Simple layout - count h2 but exclude metadata headers
        main_content = simple_content_match.group(1)
        sections = re.findall(r'<h2>([^<]+)</h2>', main_content)
        # Filter out metadata sections (Abstract, Key Terms)
        sections = [s for s in sections if s.strip() not in [
            'Abstract', 'Key Terms']]
        return len(sections), sections

    return 0, []


def normalize_for_comparison(text):
    """Normalize text for comparison - removes extra whitespace and punctuation."""
    # Convert to lowercase
    text = text.lower()
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove common punctuation that might differ
    text = re.sub(r'[,;:\.\!\?]', '', text)
    return text.strip()


def split_multi_labels(labels):
    """Split combined labels separated by semicolons."""
    expanded = []
    for label in labels:
        parts = [p.strip() for p in label.split(';') if p.strip()]
        expanded.extend(parts)
    return expanded


def find_missing_emphasis_items(base_name, html_file):
    """Identify which specific emphasis items are missing from HTML."""
    # Use transcript_utils to extract emphasis items the same way the webpage script does
    from transcript_utils import extract_emphasis_items, strip_yaml_frontmatter

    # Try dedicated emphasis file first (more efficient)
    emphasis_file = SUMMARIES_DIR / f"{base_name} - emphasis-items.md"
    if emphasis_file.exists():
        with open(emphasis_file, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        # Fall back to extracts-summary for backward compatibility
        extracts_file = SUMMARIES_DIR / f"{base_name} - extracts-summary.md"
        with open(extracts_file, 'r', encoding='utf-8') as f:
            content = f.read()

    # Extract emphasis items using the same method as webpage generation
    emphasis_items = extract_emphasis_items(strip_yaml_frontmatter(content))
    source_labels = [label for label, _ in emphasis_items]

    # Extract emphasis labels that are highlighted in HTML
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()

    highlighted_labels = re.findall(
        r'<mark class="[^"]*\bemphasis\b[^"]*"[^>]*title="[^"]*Emphasized:\s*([^"|]+)',
        html_content
    )
    highlighted_labels = [label.strip() for label in highlighted_labels]

    # Find missing items
    missing = []
    for label in source_labels:
        if label not in highlighted_labels:
            missing.append(label)

    return missing


def find_missing_bowen_items(base_name, html_file):
    """Identify which specific Bowen references are missing from HTML."""
    from transcript_utils import extract_bowen_references, strip_yaml_frontmatter

    bowen_file = SUMMARIES_DIR / f"{base_name} - bowen-references.md"
    if bowen_file.exists():
        with open(bowen_file, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        extracts_file = SUMMARIES_DIR / f"{base_name} - extracts-summary.md"
        with open(extracts_file, 'r', encoding='utf-8') as f:
            content = f.read()

    bowen_refs = extract_bowen_references(strip_yaml_frontmatter(content))
    source_labels = [label for label, _ in bowen_refs]

    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()

    highlighted_labels = re.findall(
        r'<mark class="[^"]*\bbowen-ref\b[^"]*"[^>]*title="[^"]*Bowen Reference:\s*([^"|]+)',
        html_content
    )
    highlighted_labels = [label.strip() for label in highlighted_labels]
    highlighted_labels = split_multi_labels(highlighted_labels)

    missing = []
    for label in source_labels:
        if label not in highlighted_labels:
            missing.append(label)

    return missing


def extract_extracts_summary_metadata(extracts_summary_file):
    """Extract key metadata from extracts-summary file."""
    with open(extracts_summary_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Strip YAML front matter
    if content.startswith('---'):
        parts = content.split('---\n', 2)
        if len(parts) >= 3:
            content = parts[2]

    metadata = {
        'has_abstract': False,
        'abstract_length': 0,
        'abstract_text': '',
        'topics_count': 0,
        'topics_list': [],
        'themes_count': 0,
        'themes_list': [],
        'key_terms_count': 0,
        'key_terms_list': [],
        'bowen_refs_count': 0,
        'bowen_refs_list': [],
        'emphasis_count': 0,
        'emphasis_list': []
    }

    # Check Abstract (with or without bold markers)
    abstract_match = re.search(
        r'## (?:\*\*)?Abstract(?:\*\*)?(.*?)(?=^## |^---+|\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )
    if abstract_match:
        abstract_text = abstract_match.group(1).strip()
        if abstract_text:
            metadata['has_abstract'] = True
            metadata['abstract_text'] = abstract_text
            metadata['abstract_length'] = len(abstract_text)

    # Count Topics (with or without bold markers)
    topics_match = re.search(
        r'## (?:\*\*)?Topics(?:\*\*)?(.*?)(?=^## |\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )
    if topics_match:
        topics_text = topics_match.group(1).strip()
        # Extract topic names (### Topic Name)
        topics = re.findall(r'^### (.+)$', topics_text, re.MULTILINE)
        metadata['topics_list'] = [t.strip() for t in topics]
        metadata['topics_count'] = len(topics)

    # Count Key Themes (with or without bold markers)
    themes_match = re.search(
        r'## (?:\*\*)?Key Themes(?:\*\*)?(.*?)(?=^## |\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )
    if themes_match:
        themes_text = themes_match.group(1).strip()
        # Extract theme names (### Theme Name or numbered items)
        themes_h3 = re.findall(r'^### (.+)$', themes_text, re.MULTILINE)
        themes_numbered = re.findall(
            r'^\d+\.\s+\*\*([^*]+)\*\*', themes_text, re.MULTILINE)
        themes = themes_h3 + themes_numbered
        metadata['themes_list'] = [t.strip() for t in themes]
        metadata['themes_count'] = len(themes)

    # Count Key Terms (term headings)
    term_headings = re.findall(
        r'^## ([A-Z][^\n#]+?)[\s]*\n+\*\*Definition Type:',
        content,
        re.MULTILINE
    )
    metadata['key_terms_list'] = [t.strip() for t in term_headings]
    metadata['key_terms_count'] = len(term_headings)

    # Count Bowen References (with or without bold markers)
    bowen_match = re.search(
        r'## (?:\*\*)?Bowen References(?:\*\*)?(.*?)(?=^## |\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )
    if bowen_match:
        bowen_text = bowen_match.group(1)
        bowen_refs = re.findall(
            r'>\s*\*\*([^*]+):\*\*\s*"([^"]+)"', bowen_text)
        metadata['bowen_refs_list'] = [
            (label.strip(), quote.strip()) for label, quote in bowen_refs]
        metadata['bowen_refs_count'] = len(bowen_refs)

    # Count Emphasized Items (with or without bold markers)
    emphasis_match = re.search(
        r'## (?:\*\*)?Emphasized Items(?:\*\*)?(.*?)(?=^## |\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )
    if emphasis_match:
        emphasis_text = emphasis_match.group(1)
        emphasis_items = re.findall(
            r'>\s*\*\*([^*]+):\*\*\s*"([^"]+)"', emphasis_text)
        metadata['emphasis_list'] = [
            (label.strip(), quote.strip()) for label, quote in emphasis_items]
        metadata['emphasis_count'] = len(emphasis_items)

    return metadata


def extract_html_metadata(html_file):
    """Extract metadata from HTML sidebar."""
    with open(html_file, 'r', encoding='utf-8') as f:
        content = f.read()

    metadata = {
        'has_abstract': False,
        'abstract_length': 0,
        'abstract_text': '',
        'has_topics': False,
        'topics_list': [],
        'has_themes': False,
        'themes_list': [],
        'has_key_terms': False,
        'key_terms_list': [],
        'bowen_highlights': 0,
        'emphasis_highlights': 0,
        'bowen_labels': [],
        'emphasis_labels': []
    }

    # Extract sidebar content
    sidebar_match = re.search(
        r'<aside class="sidebar">(.*?)</aside>',
        content,
        re.DOTALL
    )

    if not sidebar_match:
        return metadata

    sidebar = sidebar_match.group(1)

    # Check Abstract
    abstract_match = re.search(
        r'<h2>Abstract</h2>(.*?)(?=<h2>|\Z)',
        sidebar,
        re.DOTALL
    )
    if abstract_match:
        abstract_html = abstract_match.group(1).strip()
        abstract_text = strip_html_tags(abstract_html)
        if abstract_text:
            metadata['has_abstract'] = True
            metadata['abstract_text'] = abstract_text
            metadata['abstract_length'] = len(abstract_text)

    # Check Topics
    topics_match = re.search(
        r'<h2>Topics</h2>(.*?)(?=<h2>|\Z)',
        sidebar,
        re.DOTALL
    )
    if topics_match:
        topics_html = topics_match.group(1).strip()
        topics_text = strip_html_tags(topics_html)
        if topics_text:
            metadata['has_topics'] = True
            # Extract topic names from h3 tags
            topics = re.findall(r'<h3>([^<]+)</h3>', topics_html)
            metadata['topics_list'] = [t.strip() for t in topics]

    # Check Key Themes
    themes_match = re.search(
        r'<h2>Key Themes</h2>(.*?)(?=<h2>|\Z)',
        sidebar,
        re.DOTALL
    )
    if themes_match:
        themes_html = themes_match.group(1).strip()
        themes_text = strip_html_tags(themes_html)
        if themes_text:
            metadata['has_themes'] = True
            # Extract theme names from h3 tags or numbered lists
            themes = re.findall(r'<h3>([^<]+)</h3>', themes_html)
            # Also check for numbered items
            numbered = re.findall(
                r'<p>\d+\.\s+<strong>([^<]+)</strong>', themes_html)
            metadata['themes_list'] = [t.strip() for t in (themes + numbered)]

    # Check Key Terms
    terms_match = re.search(
        r'<h2>Key Terms</h2>(.*?)(?=</aside>|\Z)',
        sidebar,
        re.DOTALL
    )
    if terms_match:
        terms_html = terms_match.group(1).strip()
        terms_text = strip_html_tags(terms_html)
        if terms_text:
            metadata['has_key_terms'] = True
            # Split comma-separated terms
            metadata['key_terms_list'] = [t.strip()
                                          for t in terms_text.split(',') if t.strip()]

    # Count Bowen reference highlights in main content (exclude legend)
    # Extract only the content section, not the legend
    content_match = re.search(
        r'<div class="content">(.*?)</div>\s*</div>\s*</body>', content, re.DOTALL)
    if content_match:
        main_content = content_match.group(1)
    else:
        main_content = content

    bowen_marks = re.findall(
        r'<mark class="[^"]*\bbowen-ref\b[^"]*"[^>]*title=', main_content)
    metadata['bowen_highlights'] = len(bowen_marks)
    metadata['bowen_labels'] = re.findall(
        r'<mark class="[^"]*\bbowen-ref\b[^"]*"[^>]*title="[^"]*Bowen Reference:\s*([^"|]+)',
        main_content
    )
    metadata['bowen_labels'] = [label.strip() for label in metadata['bowen_labels']]
    metadata['bowen_labels'] = split_multi_labels(metadata['bowen_labels'])

    # Count emphasis highlights in main content (exclude legend) - use title attribute for accurate count
    emphasis_marks = re.findall(
        r'<mark class="[^"]*\bemphasis\b[^"]*"[^>]*title="Emphasized:', main_content)
    metadata['emphasis_highlights'] = len(emphasis_marks)
    metadata['emphasis_labels'] = re.findall(
        r'<mark class="[^"]*\bemphasis\b[^"]*"[^>]*title="[^"]*Emphasized:\s*([^"|]+)',
        main_content
    )
    metadata['emphasis_labels'] = [label.strip() for label in metadata['emphasis_labels']]

    return metadata


def extract_html_simple_metadata(html_file):
    """Extract metadata from simple HTML (single column, no sidebar)."""
    with open(html_file, 'r', encoding='utf-8') as f:
        content = f.read()

    metadata = {
        'has_abstract': False,
        'abstract_length': 0,
        'abstract_text': '',
        'has_topics': False,
        'topics_list': [],
        'has_themes': False,
        'themes_list': [],
        'has_key_terms': False,
        'key_terms_list': [],
        'bowen_highlights': 0,
        'emphasis_highlights': 0,
        'bowen_labels': [],
        'emphasis_labels': []
    }

    # Extract content div
    content_match = re.search(
        r'<div class="content">(.*?)</div>\s*</div>\s*</body>',
        content,
        re.DOTALL
    )

    if not content_match:
        return metadata

    main_content = content_match.group(1)

    # Check Abstract - should be present in simple format too
    abstract_match = re.search(
        r'<section class="abstract">(.*?)</section>',
        main_content,
        re.DOTALL
    )
    if abstract_match:
        abstract_html = abstract_match.group(1).strip()
        abstract_text = strip_html_tags(abstract_html)
        if abstract_text:
            metadata['has_abstract'] = True
            metadata['abstract_text'] = abstract_text
            metadata['abstract_length'] = len(abstract_text)

    # Check Key Terms - in simple format, look for <section class="key-terms">
    terms_match = re.search(
        r'<section class="key-terms">(.*?)</section>',
        main_content,
        re.DOTALL
    )
    if terms_match:
        terms_html = terms_match.group(1).strip()
        # Extract bold terms from paragraph
        term_items = re.findall(r'<strong>([^<]+)</strong>', terms_html)
        if term_items:
            metadata['has_key_terms'] = True
            metadata['key_terms_list'] = [t.strip() for t in term_items]

    # Topics and Themes are not in simple webpage format
    # So we mark them as present but empty lists (to skip validation)
    metadata['has_topics'] = True
    metadata['has_themes'] = True

    # Count highlights
    bowen_marks = re.findall(r'<mark class="[^"]*\bbowen-ref\b[^"]*"[^>]*>', content)
    metadata['bowen_highlights'] = len(bowen_marks)
    metadata['bowen_labels'] = re.findall(
        r'<mark class="[^"]*\bbowen-ref\b[^"]*"[^>]*title="[^"]*Bowen Reference:\s*([^"|]+)',
        content
    )
    metadata['bowen_labels'] = [label.strip() for label in metadata['bowen_labels']]
    metadata['bowen_labels'] = split_multi_labels(metadata['bowen_labels'])

    emphasis_marks = re.findall(r'<mark class="[^"]*\bemphasis\b[^"]*"[^>]*>', content)
    metadata['emphasis_highlights'] = len(emphasis_marks)
    metadata['emphasis_labels'] = re.findall(
        r'<mark class="[^"]*\bemphasis\b[^"]*"[^>]*title="[^"]*Emphasized:\s*([^"|]+)',
        content
    )
    metadata['emphasis_labels'] = [label.strip() for label in metadata['emphasis_labels']]

    return metadata


def validate_webpage(base_name: str, simple_mode: bool = False) -> bool:
    """Validate HTML webpage against source materials."""

    print(f"\n{'='*70}")
    print(f"WEBPAGE VALIDATION: {base_name}")
    if simple_mode:
        print("(Simple Single-Column Layout)")
    print(f"{'='*70}\n")

    # File paths
    formatted_file = FORMATTED_DIR / f"{base_name} - formatted.md"
    extracts_summary_file = SUMMARIES_DIR / \
        f"{base_name} - extracts-summary.md"

    # Use correct HTML filename based on mode
    if simple_mode:
        html_file = WEBPAGES_DIR / f"{base_name} - simple.html"
    else:
        html_file = WEBPAGES_DIR / f"{base_name}.html"

    # Check files exist
    missing_files = []
    if not formatted_file.exists():
        missing_files.append(f"Formatted: {formatted_file}")
    if not extracts_summary_file.exists():
        missing_files.append(f"Extracts-summary: {extracts_summary_file}")
    if not html_file.exists():
        missing_files.append(f"HTML: {html_file}")

    if missing_files:
        print("❌ MISSING FILES:")
        for f in missing_files:
            print(f"   {f}")
        return False

    # Validation checks
    issues = []
    warnings = []

    # 1. Section count validation
    print("📊 Section Count Validation")
    print("-" * 70)

    md_section_count, md_sections = count_sections_in_formatted(formatted_file)
    html_section_count, html_sections = count_sections_in_html(html_file)

    print(f"   Formatted MD sections: {md_section_count}")
    print(f"   HTML sections:         {html_section_count}")

    if md_section_count != html_section_count:
        issues.append(
            f"Section count mismatch: {md_section_count} in source, "
            f"{html_section_count} in HTML"
        )
    else:
        print("   ✅ Section counts match")

    # 2. Metadata validation
    print(f"\n📝 Metadata Validation")
    print("-" * 70)

    source_meta = extract_extracts_summary_metadata(extracts_summary_file)

    # Use appropriate extraction function based on mode
    if simple_mode:
        html_meta = extract_html_simple_metadata(html_file)
    else:
        html_meta = extract_html_metadata(html_file)

    # Abstract
    print(f"   Abstract:")
    print(f"      Source: {'Present' if source_meta['has_abstract'] else 'Missing'} "
          f"({source_meta['abstract_length']} chars)")
    print(f"      HTML:   {'Present' if html_meta['has_abstract'] else 'Missing'} "
          f"({html_meta['abstract_length']} chars)")

    if source_meta['has_abstract'] and not html_meta['has_abstract']:
        location = "content" if simple_mode else "sidebar"
        issues.append(f"Abstract missing in HTML {location}")
    elif source_meta['has_abstract'] and html_meta['abstract_length'] < source_meta['abstract_length'] * 0.5:
        warnings.append(
            f"Abstract in HTML ({html_meta['abstract_length']} chars) is much shorter "
            f"than source ({source_meta['abstract_length']} chars)"
        )
    else:
        print("      ✅ Abstract present in HTML")

    # Topics (skip in simple mode - not included in that layout)
    if not simple_mode:
        print(f"\n   Topics:")
        print(f"      Source: {source_meta['topics_count']} items")
        print(
            f"      HTML:   {'Present' if html_meta['has_topics'] else 'Empty'}")

        if source_meta['topics_count'] > 0 and not html_meta['has_topics']:
            issues.append(
                f"Topics section empty in HTML (should have {source_meta['topics_count']} items)")
        elif source_meta['topics_count'] > 0:
            print("      ✅ Topics present in HTML")

    # Key Themes (skip in simple mode - not included in that layout)
    if not simple_mode:
        print(f"\n   Key Themes:")
        print(f"      Source: {source_meta['themes_count']} items")
        print(
            f"      HTML:   {'Present' if html_meta['has_themes'] else 'Empty'}")

        if source_meta['themes_count'] > 0 and not html_meta['has_themes']:
            issues.append(
                f"Key Themes section empty in HTML (should have {source_meta['themes_count']} items)")
        elif source_meta['themes_count'] > 0:
            print("      ✅ Key Themes present in HTML")

    # Key Terms
    print(f"\n   Key Terms:")
    print(f"      Source: {source_meta['key_terms_count']} terms")
    print(
        f"      HTML:   {'Present' if html_meta['has_key_terms'] else 'Empty'}")

    if source_meta['key_terms_count'] > 0 and not html_meta['has_key_terms']:
        issues.append(
            f"Key Terms section empty in HTML (should have {source_meta['key_terms_count']} terms)")
    elif source_meta['key_terms_count'] > 0:
        print("      ✅ Key Terms present in HTML")

    # 3. Highlighting validation
    print(f"\n🖍️  Highlighting Validation")
    print("-" * 70)

    print(f"   Bowen References:")
    print(f"      Source:      {source_meta['bowen_refs_count']} references")
    bowen_label_count = len(set(html_meta['bowen_labels'])) if html_meta.get(
        'bowen_labels') else html_meta['bowen_highlights']
    print(f"      Highlighted: {bowen_label_count} references")

    missing_bowen = find_missing_bowen_items(
        base_name, html_file)

    if source_meta['bowen_refs_count'] > 0 and bowen_label_count == 0:
        issues.append(
            f"No Bowen reference highlights in HTML (should have {source_meta['bowen_refs_count']})"
        )
        print("      ❌ No Bowen references highlighted")
    elif bowen_label_count < source_meta['bowen_refs_count'] * 0.5:
        warnings.append(
            f"Only {bowen_label_count} Bowen highlights found, "
            f"expected around {source_meta['bowen_refs_count']}"
        )
        print(
            f"      ⚠️  Low highlight rate ({bowen_label_count}/{source_meta['bowen_refs_count']})")
    else:
        print("      ✅ Bowen references highlighted")

    print(f"\n   Emphasized Items:")
    print(f"      Source:      {source_meta['emphasis_count']} items")
    emphasis_label_count = len(set(html_meta['emphasis_labels'])) if html_meta.get(
        'emphasis_labels') else html_meta['emphasis_highlights']
    print(f"      Highlighted: {emphasis_label_count} items")

    # Check for missing emphasis items
    missing_emphasis = find_missing_emphasis_items(
        base_name, html_file)

    if source_meta['emphasis_count'] > 0 and emphasis_label_count == 0:
        issues.append(
            f"No emphasis highlights in HTML (should have {source_meta['emphasis_count']})"
        )
        print("      ❌ No emphasis items highlighted")
    elif emphasis_label_count < source_meta['emphasis_count'] * 0.5:
        warnings.append(
            f"Only {emphasis_label_count} emphasis highlights found, "
            f"expected around {source_meta['emphasis_count']}"
        )
        print(
            f"      ⚠️  Low highlight rate ({emphasis_label_count}/{source_meta['emphasis_count']})")
    else:
        success_rate = emphasis_label_count / \
            source_meta['emphasis_count'] * \
            100 if source_meta['emphasis_count'] > 0 else 0
        print(f"      ✅ Emphasis items highlighted ({success_rate:.0f}%)")

    # Show missing items if any
    if missing_emphasis:
        print(f"\n      Missing {len(missing_emphasis)} emphasis item(s):")
        for i, label in enumerate(missing_emphasis, 1):
            print(
                f"         {i}. {label[:60]}{'...' if len(label) > 60 else ''}")

    if missing_bowen:
        print(f"\n      Missing {len(missing_bowen)} Bowen reference(s):")
        for i, label in enumerate(missing_bowen, 1):
            print(
                f"         {i}. {label[:60]}{'...' if len(label) > 60 else ''}")

    # 4. Content Verification (sample 30% rounded up)
    print(f"\n🔍 Content Verification (Sampling)")
    print("-" * 70)

    import math

    # Verify Abstract content (full text since it's a single item)
    if source_meta['has_abstract'] and html_meta['has_abstract']:
        # More robust comparison - normalize and compare full abstract
        source_norm = normalize_for_comparison(source_meta['abstract_text'])
        html_norm = normalize_for_comparison(html_meta['abstract_text'])

        # Check if content is substantially the same (allowing for minor differences)
        ratio = SequenceMatcher(None, source_norm, html_norm).ratio()

        if ratio >= 0.95:  # 95% similarity is close enough
            print(f"   Abstract: ✅ Content matches ({ratio:.1%} similarity)")
        else:
            warnings.append(
                f"Abstract content differs from source ({ratio:.1%} similarity, {abs(len(source_norm) - len(html_norm))} char difference)")
            print(
                f"   Abstract: ⚠️  Content mismatch ({ratio:.1%} similarity)")

    # Verify Topics (sample 30% rounded up) - skip in simple mode
    if not simple_mode and source_meta['topics_count'] > 0 and len(html_meta['topics_list']) > 0:
        sample_size = math.ceil(source_meta['topics_count'] * 0.3)
        sample_indices = range(
            0, min(sample_size, len(source_meta['topics_list'])))
        matched = 0
        for idx in sample_indices:
            source_topic = normalize_for_comparison(
                source_meta['topics_list'][idx])
            # Check if any HTML topic matches
            found = any(source_topic in normalize_for_comparison(html_topic) or
                        normalize_for_comparison(html_topic) in source_topic
                        for html_topic in html_meta['topics_list'])
            if found:
                matched += 1

        if matched == len(sample_indices):
            print(
                f"   Topics: ✅ {matched}/{len(sample_indices)} sampled items verified")
        else:
            warnings.append(
                f"Topics content mismatch: only {matched}/{len(sample_indices)} verified")
            print(
                f"   Topics: ⚠️  Only {matched}/{len(sample_indices)} verified")

    # Verify Key Themes (sample 30% rounded up) - skip in simple mode
    if not simple_mode and source_meta['themes_count'] > 0 and len(html_meta['themes_list']) > 0:
        sample_size = math.ceil(source_meta['themes_count'] * 0.3)
        sample_indices = range(
            0, min(sample_size, len(source_meta['themes_list'])))
        matched = 0
        for idx in sample_indices:
            source_theme = normalize_for_comparison(
                source_meta['themes_list'][idx])
            # Check if any HTML theme matches
            found = any(source_theme in normalize_for_comparison(html_theme) or
                        normalize_for_comparison(html_theme) in source_theme
                        for html_theme in html_meta['themes_list'])
            if found:
                matched += 1

        if matched == len(sample_indices):
            print(
                f"   Key Themes: ✅ {matched}/{len(sample_indices)} sampled items verified")
        else:
            warnings.append(
                f"Key Themes content mismatch: only {matched}/{len(sample_indices)} verified")
            print(
                f"   Key Themes: ⚠️  Only {matched}/{len(sample_indices)} verified")

    # Verify Key Terms (sample 30% rounded up)
    if source_meta['key_terms_count'] > 0 and len(html_meta['key_terms_list']) > 0:
        sample_size = math.ceil(source_meta['key_terms_count'] * 0.3)
        sample_indices = range(
            0, min(sample_size, len(source_meta['key_terms_list'])))
        matched = 0
        for idx in sample_indices:
            source_term = normalize_for_comparison(
                source_meta['key_terms_list'][idx])
            # Check if any HTML term matches
            found = any(source_term in normalize_for_comparison(html_term) or
                        normalize_for_comparison(html_term) in source_term
                        for html_term in html_meta['key_terms_list'])
            if found:
                matched += 1

        if matched == len(sample_indices):
            print(
                f"   Key Terms: ✅ {matched}/{len(sample_indices)} sampled items verified")
        else:
            warnings.append(
                f"Key Terms content mismatch: only {matched}/{len(sample_indices)} verified")
            print(
                f"   Key Terms: ⚠️  Only {matched}/{len(sample_indices)} verified")

    # Summary
    print(f"\n{'='*70}")
    print("VALIDATION SUMMARY")
    print(f"{'='*70}\n")

    if not issues and not warnings:
        print("✅ ALL CHECKS PASSED - Webpage is complete and valid\n")
        return True

    if issues:
        print(f"❌ CRITICAL ISSUES FOUND: {len(issues)}")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")
        print()

    if warnings:
        print(f"⚠️  WARNINGS: {len(warnings)}")
        for i, warning in enumerate(warnings, 1):
            print(f"   {i}. {warning}")
        print()

    return len(issues) == 0


def main():
    parser = argparse.ArgumentParser(
        description='Validate generated HTML webpage against source materials. '
                    'Supports both sidebar layout and simple single-column layout.'
    )
    parser.add_argument(
        'base_name',
        help='Base name of the transcript (e.g., "Title - Presenter - Date")'
    )
    parser.add_argument(
        '--simple',
        action='store_true',
        help='Validate simple webpage format (single-column, no sidebar)'
    )

    args = parser.parse_args()

    success = validate_webpage(args.base_name, simple_mode=args.simple)
    exit(0 if success else 1)


if __name__ == '__main__':
    main()
