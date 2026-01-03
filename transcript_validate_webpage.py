#!/usr/bin/env python3
"""
Validate generated HTML webpage against source materials.
Checks that all expected content from topics-themes appears in the webpage.
Supports both sidebar layout and simple single-column layout.

Usage:
    python transcript_validate_webpage.py "Title - Presenter - Date" [--simple]

Example:
    python transcript_validate_webpage.py "This is a test - Dave Galloway - 2025-12-07"
    python transcript_validate_webpage.py "This is a test - Dave Galloway - 2025-12-07" --simple
"""

import argparse
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

import config
from transcript_utils import load_bowen_references, load_emphasis_items, normalize_text

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("❌ Error: beautifulsoup4 is not installed. Run: pip install beautifulsoup4")
    sys.exit(1)


def count_sections_in_formatted(formatted_file):
    """Count sections in formatted markdown file."""
    with open(formatted_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Strip YAML front matter
    if content.startswith("---"):
        parts = content.split("---\n", 2)
        if len(parts) >= 3:
            content = parts[2]

    # Count h2 sections (## Section Name)
    sections = re.findall(r"^## (.+)$", content, re.MULTILINE)
    return len(sections), sections


def count_sections_in_html(html_file):
    """Count sections in HTML file (works for both sidebar and simple layouts)."""
    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")

    # Try sidebar layout first
    main_content = soup.find("main", class_="main-content")
    if main_content:
        # Sidebar layout - count h2 in main content area
        sections = [h2.get_text(strip=True) for h2 in main_content.find_all("h2")]
        return len(sections), sections

    # Try simple layout (content class, no sidebar)
    content_div = soup.find("div", class_="content")
    if content_div:
        # Simple layout - count h2 but exclude metadata headers
        sections = [h2.get_text(strip=True) for h2 in content_div.find_all("h2")]
        # Filter out metadata sections (Abstract, Key Terms)
        sections = [s for s in sections if s not in ["Abstract", "Key Terms"]]
        return len(sections), sections

    return 0, []


def normalize_for_comparison(text):
    """Normalize text for comparison - removes extra whitespace and punctuation."""
    # Convert to lowercase
    text = text.lower()
    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text)
    # Remove common punctuation that might differ
    text = re.sub(r"[,;:\.\!\?]", "", text)
    return text.strip()


def split_multi_labels(labels):
    """Split combined labels separated by semicolons."""
    expanded = []
    for label in labels:
        parts = [p.strip() for p in label.split(";") if p.strip()]
        expanded.extend(parts)
    return expanded


def find_missing_emphasis_items(base_name, html_file):
    """Identify which specific emphasis items are missing from HTML."""
    # Use the centralized loader from transcript_utils
    emphasis_items = load_emphasis_items(base_name)
    source_labels = [label for label, _ in emphasis_items]

    # Extract emphasis labels that are highlighted in HTML
    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")
    highlighted_labels = []
    for mark in soup.find_all("mark", class_="emphasis"):
        title = mark.get("title", "")
        if "Emphasized:" in title:
            label = title.split("Emphasized:", 1)[1].split("|")[0].strip()
            highlighted_labels.append(label)

    # Find missing items
    missing = []
    for label in source_labels:
        if label not in highlighted_labels:
            missing.append(label)

    return missing


def find_missing_bowen_items(base_name, html_file):
    """Identify which specific Bowen references are missing from HTML."""
    # Use the centralized loader from transcript_utils
    bowen_refs = load_bowen_references(base_name)
    source_labels = [label for label, _ in bowen_refs]

    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")
    highlighted_labels = []
    for mark in soup.find_all("mark", class_="bowen-ref"):
        title = mark.get("title", "")
        if "Bowen Reference:" in title:
            label = title.split("Bowen Reference:", 1)[1].strip()
            highlighted_labels.append(label)

    highlighted_labels = split_multi_labels(highlighted_labels)

    missing = []
    for label in source_labels:
        if label not in highlighted_labels:
            missing.append(label)

    return missing


def extract_topics_themes_metadata(topics_themes_file):
    """Extract key metadata from topics-themes file."""
    with open(topics_themes_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Strip YAML front matter
    if content.startswith("---"):
        parts = content.split("---\n", 2)
        if len(parts) >= 3:
            content = parts[2]

    metadata = {
        "has_abstract": False,
        "abstract_length": 0,
        "abstract_text": "",
        "topics_count": 0,
        "topics_list": [],
        "themes_count": 0,
        "themes_list": [],
        "key_terms_count": 0,
        "key_terms_list": [],
        "bowen_refs_count": 0,
        "bowen_refs_list": [],
        "emphasis_count": 0,
        "emphasis_list": [],
    }

    # Check Abstract (with or without bold markers)
    abstract_match = re.search(
        r"## (?:\*\*)?Abstract(?:\*\*)?(.*?)(?=^## |^---+|\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if abstract_match:
        abstract_text = abstract_match.group(1).strip()
        if abstract_text:
            metadata["has_abstract"] = True
            metadata["abstract_text"] = abstract_text
            metadata["abstract_length"] = len(abstract_text)

    # Check Summary
    summary_match = re.search(
        r"## (?:\*\*)?Summary(?:\*\*)?(.*?)(?=^## |^---+|\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if summary_match:
        metadata["has_summary"] = True
        metadata["summary_length"] = len(summary_match.group(1).strip())

    # Count Topics (with or without bold markers)
    topics_match = re.search(
        r"## (?:\*\*)?(?:Key )?Topics(?:\*\*)?(.*?)(?=^## |\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if topics_match:
        topics_text = topics_match.group(1).strip()
        # Extract topic names (### Topic Name)
        topics = re.findall(r"^### (.+)$", topics_text, re.MULTILINE)
        metadata["topics_list"] = [t.strip() for t in topics]
        metadata["topics_count"] = len(topics)

    # Count Key Themes (with or without bold markers)
    themes_match = re.search(
        r"## (?:\*\*)?Key Themes(?:\*\*)?(.*?)(?=^## |\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if themes_match:
        themes_text = themes_match.group(1).strip()
        # Extract theme names (### Theme Name or numbered items)
        themes_h3 = re.findall(r"^### (.+)$", themes_text, re.MULTILINE)
        themes_numbered = re.findall(
            r"^\d+\.\s+\*\*([^*]+)\*\*", themes_text, re.MULTILINE
        )
        themes = themes_h3 + themes_numbered
        metadata["themes_list"] = [t.strip() for t in themes]
        metadata["themes_count"] = len(themes)

    # Count Key Terms
    key_terms_match = re.search(
        r"## (?:\*\*)?Key Terms(?:\*\*)?(.*?)(?=^## |^---+|\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if key_terms_match:
        kt_text = key_terms_match.group(1)
        # Extract term names (### Term Name)
        term_headings = re.findall(r"^### (.+)$", kt_text, re.MULTILINE)
        metadata["key_terms_list"] = [t.strip() for t in term_headings]
        metadata["key_terms_count"] = len(term_headings)

    # Count Bowen References (with or without bold markers)
    bowen_match = re.search(
        r"## (?:\*\*)?Bowen References(?:\*\*)?(.*?)(?=^## |\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if bowen_match:
        bowen_text = bowen_match.group(1)
        bowen_refs = re.findall(r'>\s*\*\*([^*]+):\*\*\s*"([^"]+)"', bowen_text)
        metadata["bowen_refs_list"] = [
            (label.strip(), quote.strip()) for label, quote in bowen_refs
        ]
        metadata["bowen_refs_count"] = len(bowen_refs)

    # Count Emphasized Items (with or without bold markers)
    emphasis_match = re.search(
        r"## (?:\*\*)?Emphasized Items(?:\*\*)?(.*?)(?=^## |\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if emphasis_match:
        emphasis_text = emphasis_match.group(1)
        emphasis_items = re.findall(r'>\s*\*\*([^*]+):\*\*\s*"([^"]+)"', emphasis_text)
        metadata["emphasis_list"] = [
            (label.strip(), quote.strip()) for label, quote in emphasis_items
        ]
        metadata["emphasis_count"] = len(emphasis_items)

    return metadata


def extract_html_metadata(html_file):
    """Extract metadata from HTML sidebar."""
    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")

    metadata = {
        "has_abstract": False,
        "abstract_length": 0,
        "abstract_text": "",
        "has_summary": False,
        "summary_length": 0,
        "has_topics": False,
        "topics_list": [],
        "has_themes": False,
        "themes_list": [],
        "has_key_terms": False,
        "key_terms_list": [],
        "bowen_highlights": 0,
        "emphasis_highlights": 0,
        "bowen_labels": [],
        "emphasis_labels": [],
    }

    # Extract sidebar content
    sidebar = soup.find("aside", class_="sidebar")
    if not sidebar:
        return metadata

    # Helper to find section content
    def get_sidebar_section(heading_text):
        h2 = sidebar.find("h2", string=heading_text)
        if not h2:
            return None
        content = []
        curr = h2.find_next_sibling()
        while curr and curr.name != "h2":
            content.append(curr)
            curr = curr.find_next_sibling()
        return content

    # Abstract
    abstract_elems = get_sidebar_section("Abstract")
    if abstract_elems:
        text = " ".join(e.get_text(strip=True) for e in abstract_elems)
        if text:
            metadata["has_abstract"] = True
            metadata["abstract_text"] = text
            metadata["abstract_length"] = len(text)

    # Summary
    summary_elems = get_sidebar_section("Summary")
    if summary_elems:
        text = " ".join(e.get_text(strip=True) for e in summary_elems)
        if text:
            metadata["has_summary"] = True
            metadata["summary_length"] = len(text)

    # Topics
    topics_elems = get_sidebar_section("Key Topics")
    if topics_elems:
        metadata["has_topics"] = True
        for elem in topics_elems:
            metadata["topics_list"].extend(
                [h3.get_text(strip=True) for h3 in elem.find_all("h3")]
            )

    # Key Themes
    themes_elems = get_sidebar_section("Key Themes")
    if themes_elems:
        metadata["has_themes"] = True
        for elem in themes_elems:
            metadata["themes_list"].extend(
                [h3.get_text(strip=True) for h3 in elem.find_all("h3")]
            )
            # Also check numbered items
            for p in elem.find_all("p"):
                if re.match(r"\d+\.", p.get_text()):
                    strong = p.find("strong")
                    if strong:
                        metadata["themes_list"].append(strong.get_text(strip=True))

    # Key Terms
    terms_elems = get_sidebar_section("Key Terms")
    if terms_elems:
        # Check for definition list first
        dl = next((e for e in terms_elems if e.name == "dl"), None)
        if dl:
            metadata["has_key_terms"] = True
            metadata["key_terms_list"] = [
                dt.get_text(strip=True) for dt in dl.find_all("dt")
            ]
        else:
            text = " ".join(e.get_text(strip=True) for e in terms_elems)
            if text:
                metadata["has_key_terms"] = True
                metadata["key_terms_list"] = [
                    t.strip() for t in text.split(",") if t.strip()
                ]

    # Count Bowen reference highlights in main content (exclude legend)
    main_content = soup.find("div", class_="transcript") or soup.find(
        "div", class_="content"
    )
    if not main_content:
        main_content = soup

    bowen_marks = main_content.find_all("mark", class_="bowen-ref")
    metadata["bowen_highlights"] = len(bowen_marks)

    metadata["bowen_labels"] = []
    for mark in bowen_marks:
        title = mark.get("title", "")
        if "Bowen Reference:" in title:
            label = title.split("Bowen Reference:", 1)[1].strip()
            metadata["bowen_labels"].append(label)

    metadata["bowen_labels"] = [label.strip() for label in metadata["bowen_labels"]]
    metadata["bowen_labels"] = split_multi_labels(metadata["bowen_labels"])

    # Count emphasis highlights in main content (exclude legend) - use title attribute for accurate count
    emphasis_marks = main_content.find_all("mark", class_="emphasis")
    metadata["emphasis_highlights"] = len(emphasis_marks)

    metadata["emphasis_labels"] = []
    for mark in emphasis_marks:
        title = mark.get("title", "")
        if "Emphasized:" in title:
            label = title.split("Emphasized:", 1)[1].split("|")[0].strip()
            metadata["emphasis_labels"].append(label)

    metadata["emphasis_labels"] = [
        label.strip() for label in metadata["emphasis_labels"]
    ]

    return metadata


def extract_html_simple_metadata(html_file):
    """Extract metadata from simple HTML (single column, no sidebar)."""
    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")

    metadata = {
        "has_abstract": False,
        "abstract_length": 0,
        "abstract_text": "",
        "has_summary": False,
        "summary_length": 0,
        "has_topics": False,
        "topics_list": [],
        "has_themes": False,
        "themes_list": [],
        "has_key_terms": False,
        "key_terms_list": [],
        "bowen_highlights": 0,
        "emphasis_highlights": 0,
        "bowen_labels": [],
        "emphasis_labels": [],
    }

    # Extract content div
    main_content = soup.find("div", class_="content")
    if not main_content:
        return metadata

    # 1. Summary Section (Abstract + Summary)
    summary_section = soup.find("div", class_="summary-section")
    if summary_section:
        # Abstract
        abs_h2 = summary_section.find("h2", string="Abstract")
        if abs_h2:
            text = ""
            curr = abs_h2.find_next_sibling()
            while curr and curr.name != "h2":
                text += curr.get_text(strip=True) + " "
                curr = curr.find_next_sibling()
            if text.strip():
                metadata["has_abstract"] = True
                metadata["abstract_text"] = text.strip()
                metadata["abstract_length"] = len(text.strip())

        # Summary
        sum_h2 = summary_section.find("h2", string="Summary")
        if sum_h2:
            text = ""
            curr = sum_h2.find_next_sibling()
            while curr and curr.name != "h2":
                text += curr.get_text(strip=True) + " "
                curr = curr.find_next_sibling()
            if text.strip():
                metadata["has_summary"] = True
                metadata["summary_length"] = len(text.strip())

    # 2. Appendices (Topics, Themes, Key Terms)
    appendices = soup.find("div", class_="appendices")
    if appendices:
        # Topics
        topics_h2 = appendices.find("h2", string="Key Topics")
        if topics_h2:
            metadata["has_topics"] = True
            curr = topics_h2.find_next_sibling()
            while curr and curr.name != "h2":
                if curr.name == "h3":
                    metadata["topics_list"].append(curr.get_text(strip=True))
                curr = curr.find_next_sibling()

        # Key Themes
        themes_h2 = appendices.find("h2", string="Key Themes")
        if themes_h2:
            metadata["has_themes"] = True
            curr = themes_h2.find_next_sibling()
            while curr and curr.name != "h2":
                if curr.name == "h3":
                    metadata["themes_list"].append(curr.get_text(strip=True))
                if curr.name == "p":
                    strong = curr.find("strong")
                    if strong and re.match(r"\d+\.", curr.get_text(strip=True)):
                        metadata["themes_list"].append(strong.get_text(strip=True))
                curr = curr.find_next_sibling()

        # Key Terms
        terms_h2 = appendices.find("h2", string="Key Terms")
        if terms_h2:
            metadata["has_key_terms"] = True
            curr = terms_h2.find_next_sibling()
            while curr and curr.name != "h2":
                if curr.name == "dl":
                    metadata["key_terms_list"].extend(
                        [dt.get_text(strip=True) for dt in curr.find_all("dt")]
                    )
                curr = curr.find_next_sibling()

    # Count highlights
    bowen_marks = main_content.find_all("mark", class_="bowen-ref")
    metadata["bowen_highlights"] = len(bowen_marks)

    metadata["bowen_labels"] = []
    for mark in bowen_marks:
        title = mark.get("title", "")
        if "Bowen Reference:" in title:
            label = title.split("Bowen Reference:", 1)[1].strip()
            metadata["bowen_labels"].append(label)

    metadata["bowen_labels"] = [label.strip() for label in metadata["bowen_labels"]]
    metadata["bowen_labels"] = split_multi_labels(metadata["bowen_labels"])

    emphasis_marks = main_content.find_all("mark", class_="emphasis")
    metadata["emphasis_highlights"] = len(emphasis_marks)

    metadata["emphasis_labels"] = []
    for mark in emphasis_marks:
        title = mark.get("title", "")
        if "Emphasized:" in title:
            label = title.split("Emphasized:", 1)[1].split("|")[0].strip()
            metadata["emphasis_labels"].append(label)

    metadata["emphasis_labels"] = [
        label.strip() for label in metadata["emphasis_labels"]
    ]

    return metadata


def validate_css_definitions(html_file):
    """Check if required CSS classes are defined in the style block."""
    try:
        soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")
        style = soup.find("style")
        if not style:
            return False, "No <style> block found"

        css_content = style.get_text()
        missing = []

        # Check for specific highlighting classes
        if ".bowen-ref" not in css_content and "mark.bowen-ref" not in css_content:
            missing.append(".bowen-ref")

        if ".emphasis" not in css_content and "mark.emphasis" not in css_content:
            missing.append(".emphasis")

        if ".legend" not in css_content:
            missing.append(".legend")

        if "score-90" not in css_content:
            missing.append(".score-90")

        if "score-95" not in css_content:
            missing.append(".score-95")

        if ".ref-list" not in css_content:
            missing.append(".ref-list")

        if missing:
            return False, f"Missing CSS definitions for: {', '.join(missing)}"

        return True, "CSS definitions present"
    except Exception as e:
        return False, f"Error parsing CSS: {e}"


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
        window = " ".join(haystack_words[i : i + needle_len])
        ratio = SequenceMatcher(None, needle_normalized, window).ratio()

        if ratio > best_ratio:
            best_ratio = ratio
            best_match = window
            if ratio > 0.98:  # Early exit
                break

    return (best_ratio, best_match)


def _load_abstract_content(base_name):
    """Load abstract from generated file if available."""
    gen_file = (
        config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_ABSTRACT_GEN}"
    )
    if gen_file.exists():
        return gen_file.read_text(encoding="utf-8")
    return None


def validate_webpage(base_name: str, simple_mode: bool = False) -> bool:
    """Validate HTML webpage against source materials."""

    print(f"\n{'=' * 70}")
    print(f"WEBPAGE VALIDATION: {base_name}")
    if simple_mode:
        print("(Simple Single-Column Layout)")
    print(f"{'=' * 70}\n")

    # File paths
    project_dir = config.PROJECTS_DIR / base_name
    formatted_file = project_dir / f"{base_name}{config.SUFFIX_FORMATTED}"
    topics_themes_file = project_dir / f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"

    # Use correct HTML filename based on mode
    if simple_mode:
        html_file = project_dir / f"{base_name}{config.SUFFIX_WEBPAGE_SIMPLE}"
    else:
        html_file = project_dir / f"{base_name}{config.SUFFIX_WEBPAGE}"

    # Check files exist
    missing_files = []
    if not formatted_file.exists():
        missing_files.append(f"Formatted: {formatted_file}")
    if not topics_themes_file.exists():
        # The primary file is missing, report it.
        missing_files.append(f"All Key Items file not found: {topics_themes_file.name}")
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
    print("\n📝 Metadata Validation")
    print("-" * 70)

    source_meta = extract_topics_themes_metadata(topics_themes_file)

    # OVERRIDE with specialized files if they exist (matching html_generator logic)
    # This ensures we validate against what was actually put in the HTML

    # 1. Abstract
    gen_abstract = _load_abstract_content(base_name)
    if gen_abstract:
        source_meta["has_abstract"] = True
        source_meta["abstract_text"] = gen_abstract
        source_meta["abstract_length"] = len(gen_abstract)

    # 2. Bowen References
    real_bowen = load_bowen_references(base_name)
    if real_bowen:
        source_meta["bowen_refs_list"] = real_bowen
        source_meta["bowen_refs_count"] = len(real_bowen)

    # 3. Emphasis Items
    real_emphasis = load_emphasis_items(base_name)
    if real_emphasis:
        source_meta["emphasis_list"] = real_emphasis
        source_meta["emphasis_count"] = len(real_emphasis)

    # Use appropriate extraction function based on mode
    if simple_mode:
        html_meta = extract_html_simple_metadata(html_file)
    else:
        html_meta = extract_html_metadata(html_file)

    # Abstract
    print("   Abstract:")
    print(
        f"      Source: {'Present' if source_meta['has_abstract'] else 'Missing'} "
        f"({source_meta['abstract_length']} chars)"
    )
    print(
        f"      HTML:   {'Present' if html_meta['has_abstract'] else 'Missing'} "
        f"({html_meta['abstract_length']} chars)"
    )

    if source_meta["has_abstract"] and not html_meta["has_abstract"]:
        location = "content" if simple_mode else "sidebar"
        issues.append(f"Abstract missing in HTML {location}")
    elif (
        source_meta["has_abstract"]
        and html_meta["abstract_length"] < source_meta["abstract_length"] * 0.5
    ):
        warnings.append(
            f"Abstract in HTML ({html_meta['abstract_length']} chars) is much shorter "
            f"than source ({source_meta['abstract_length']} chars)"
        )
    else:
        print("      ✅ Abstract present in HTML")

    # Summary
    print("\n   Summary:")
    # Note: Source summary might be in a different file (summary-generated.md),
    # so source_meta['has_summary'] might be False if it only checked All Key Items.
    # We'll just check if HTML has it if we know we generated it.
    print(
        f"      HTML:   {'Present' if html_meta['has_summary'] else 'Missing'} "
        f"({html_meta['summary_length']} chars)"
    )

    if not html_meta["has_summary"]:
        warnings.append("Summary section missing in HTML")
    else:
        print("      ✅ Summary present in HTML")

    # Topics (skip in simple mode - not included in that layout)
    print("\n   Key Topics:")
    print(f"      Source: {source_meta['topics_count']} items")
    print(f"      HTML:   {'Present' if html_meta['has_topics'] else 'Empty'}")

    if source_meta["topics_count"] > 0 and not html_meta["has_topics"]:
        issues.append(
            f"Key Topics section empty in HTML (should have {source_meta['topics_count']} items)"
        )
    elif source_meta["topics_count"] > 0:
        print("      ✅ Key Topics present in HTML")

    # Key Themes (skip in simple mode - not included in that layout)
    print("\n   Key Themes:")
    print(f"      Source: {source_meta['themes_count']} items")
    print(f"      HTML:   {'Present' if html_meta['has_themes'] else 'Empty'}")

    if source_meta["themes_count"] > 0 and not html_meta["has_themes"]:
        issues.append(
            f"Key Themes section empty in HTML (should have {source_meta['themes_count']} items)"
        )
    elif source_meta["themes_count"] > 0:
        print("      ✅ Key Themes present in HTML")

    # Key Terms
    print("\n   Key Terms:")
    print(f"      Source: {source_meta['key_terms_count']} terms")
    print(f"      HTML:   {'Present' if html_meta['has_key_terms'] else 'Empty'}")

    if source_meta["key_terms_count"] > 0 and not html_meta["has_key_terms"]:
        issues.append(
            f"Key Terms section empty in HTML (should have {source_meta['key_terms_count']} terms)"
        )
    elif source_meta["key_terms_count"] > 0:
        print("      ✅ Key Terms present in HTML")

    # 3. Highlighting validation
    print("\n🖍️  Highlighting Validation")
    print("-" * 70)

    # Check CSS definitions
    css_ok, css_msg = validate_css_definitions(html_file)
    if not css_ok:
        issues.append(f"CSS Validation failed: {css_msg}")
        print(f"   ❌ {css_msg}")
    else:
        print("   ✅ CSS definitions present")

    print("   Bowen References:")
    print(f"      Source:      {source_meta['bowen_refs_count']} references")
    bowen_label_count = (
        len(set(html_meta["bowen_labels"]))
        if html_meta.get("bowen_labels")
        else html_meta["bowen_highlights"]
    )
    print(f"      Highlighted: {bowen_label_count} references")

    missing_bowen = find_missing_bowen_items(base_name, html_file)

    if source_meta["bowen_refs_count"] > 0 and bowen_label_count == 0:
        issues.append(
            f"No Bowen reference highlights in HTML (should have {source_meta['bowen_refs_count']})"
        )
        print("      ❌ No Bowen references highlighted")
    elif bowen_label_count < source_meta["bowen_refs_count"] * 0.5:
        warnings.append(
            f"Only {bowen_label_count} Bowen highlights found, "
            f"expected around {source_meta['bowen_refs_count']}"
        )
        print(
            f"      ⚠️  Low highlight rate ({bowen_label_count}/{source_meta['bowen_refs_count']})"
        )
    else:
        print("      ✅ Bowen references highlighted")

    print("\n   Emphasized Items:")
    print(f"      Source:      {source_meta['emphasis_count']} items")
    emphasis_label_count = (
        len(set(html_meta["emphasis_labels"]))
        if html_meta.get("emphasis_labels")
        else html_meta["emphasis_highlights"]
    )
    print(f"      Highlighted: {emphasis_label_count} items")

    # Check for missing emphasis items
    missing_emphasis = find_missing_emphasis_items(base_name, html_file)

    if source_meta["emphasis_count"] > 0 and emphasis_label_count == 0:
        issues.append(
            f"No emphasis highlights in HTML (should have {source_meta['emphasis_count']})"
        )
        print("      ❌ No emphasis items highlighted")
    elif emphasis_label_count < source_meta["emphasis_count"] * 0.5:
        warnings.append(
            f"Only {emphasis_label_count} emphasis highlights found, "
            f"expected around {source_meta['emphasis_count']}"
        )
        print(
            f"      ⚠️  Low highlight rate ({emphasis_label_count}/{source_meta['emphasis_count']})"
        )
    else:
        success_rate = (
            emphasis_label_count / source_meta["emphasis_count"] * 100
            if source_meta["emphasis_count"] > 0
            else 0
        )
        print(f"      ✅ Emphasis items highlighted ({success_rate:.0f}%)")

    # Show missing items if any
    if missing_emphasis:
        print(f"\n      Missing {len(missing_emphasis)} emphasis item(s):")
        for i, label in enumerate(missing_emphasis, 1):
            print(f"         {i}. {label[:60]}{'...' if len(label) > 60 else ''}")

    if missing_bowen:
        print(f"\n      Missing {len(missing_bowen)} Bowen reference(s):")
        for i, label in enumerate(missing_bowen, 1):
            print(f"         {i}. {label[:60]}{'...' if len(label) > 60 else ''}")

    # 4. Text Content Verification (The logic from Step 11)
    print("\n🔍 Text Content Verification")
    print("-" * 70)

    # Read and normalize HTML (stripping tags to check text presence)
    html_content = html_file.read_text(encoding="utf-8")
    html_normalized = normalize_text(html_content, aggressive=True)

    all_items = [
        ("Bowen Ref", label, quote) for label, quote in load_bowen_references(base_name)
    ] + [("Emphasis", label, quote) for label, quote in load_emphasis_items(base_name)]

    text_missing_count = 0
    if all_items:
        for type_, label, quote in all_items:
            ratio, _ = find_best_match_in_html(quote, html_normalized, threshold=0.80)
            if ratio < 0.85:
                text_missing_count += 1
                issues.append(f"Quote text missing for {type_}: {label}")
                print(f"   ❌ MISSING TEXT {type_}: {label}")

        if text_missing_count == 0:
            print(f"   ✅ All {len(all_items)} quotes found in HTML text")
    else:
        print("   ℹ️  No quotes to verify.")

    # 5. Metadata Content Verification (Sampling)
    print("\n🔍 Metadata Content Verification (Sampling)")
    print("-" * 70)

    import math

    # Verify Abstract content (full text since it's a single item)
    if source_meta["has_abstract"] and html_meta["has_abstract"]:
        # More robust comparison - normalize and compare full abstract
        source_norm = normalize_for_comparison(source_meta["abstract_text"])
        html_norm = normalize_for_comparison(html_meta["abstract_text"])

        # Check if content is substantially the same (allowing for minor differences)
        ratio = SequenceMatcher(None, source_norm, html_norm).ratio()

        if ratio >= 0.95:  # 95% similarity is close enough
            print(f"   Abstract: ✅ Content matches ({ratio:.1%} similarity)")
        else:
            warnings.append(
                f"Abstract content differs from source ({ratio:.1%} similarity, {abs(len(source_norm) - len(html_norm))} char difference)"
            )
            print(f"   Abstract: ⚠️  Content mismatch ({ratio:.1%} similarity)")

    # Verify Topics (sample 30% rounded up) - skip in simple mode
    if source_meta["topics_count"] > 0 and len(html_meta["topics_list"]) > 0:
        sample_size = math.ceil(source_meta["topics_count"] * 0.3)
        sample_indices = range(0, min(sample_size, len(source_meta["topics_list"])))
        matched = 0
        for idx in sample_indices:
            source_topic = normalize_for_comparison(source_meta["topics_list"][idx])
            # Check if any HTML topic matches
            found = any(
                source_topic in normalize_for_comparison(html_topic)
                or normalize_for_comparison(html_topic) in source_topic
                for html_topic in html_meta["topics_list"]
            )
            if found:
                matched += 1

        if matched == len(sample_indices):
            print(
                f"   Key Topics: ✅ {matched}/{len(sample_indices)} sampled items verified"
            )
        else:
            warnings.append(
                f"Key Topics content mismatch: only {matched}/{len(sample_indices)} verified"
            )
            print(f"   Key Topics: ⚠️  Only {matched}/{len(sample_indices)} verified")

    # Verify Key Themes (sample 30% rounded up) - skip in simple mode
    if source_meta["themes_count"] > 0 and len(html_meta["themes_list"]) > 0:
        sample_size = math.ceil(source_meta["themes_count"] * 0.3)
        sample_indices = range(0, min(sample_size, len(source_meta["themes_list"])))
        matched = 0
        for idx in sample_indices:
            source_theme = normalize_for_comparison(source_meta["themes_list"][idx])
            # Check if any HTML theme matches
            found = any(
                source_theme in normalize_for_comparison(html_theme)
                or normalize_for_comparison(html_theme) in source_theme
                for html_theme in html_meta["themes_list"]
            )
            if found:
                matched += 1

        if matched == len(sample_indices):
            print(
                f"   Key Themes: ✅ {matched}/{len(sample_indices)} sampled items verified"
            )
        else:
            warnings.append(
                f"Key Themes content mismatch: only {matched}/{len(sample_indices)} verified"
            )
            print(f"   Key Themes: ⚠️  Only {matched}/{len(sample_indices)} verified")

    # Verify Key Terms (sample 30% rounded up)
    if source_meta["key_terms_count"] > 0 and len(html_meta["key_terms_list"]) > 0:
        sample_size = math.ceil(source_meta["key_terms_count"] * 0.3)
        sample_indices = range(0, min(sample_size, len(source_meta["key_terms_list"])))
        matched = 0
        for idx in sample_indices:
            source_term = normalize_for_comparison(source_meta["key_terms_list"][idx])
            # Check if any HTML term matches
            found = any(
                source_term in normalize_for_comparison(html_term)
                or normalize_for_comparison(html_term) in source_term
                for html_term in html_meta["key_terms_list"]
            )
            if found:
                matched += 1

        if matched == len(sample_indices):
            print(
                f"   Key Terms: ✅ {matched}/{len(sample_indices)} sampled items verified"
            )
        else:
            warnings.append(
                f"Key Terms content mismatch: only {matched}/{len(sample_indices)} verified"
            )
            print(f"   Key Terms: ⚠️  Only {matched}/{len(sample_indices)} verified")

    # Summary
    print(f"\n{'=' * 70}")
    print("VALIDATION SUMMARY")
    print(f"{'=' * 70}\n")

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


def resolve_base_name(input_name: str) -> str:
    """
    Resolve input string to a base name by stripping extensions and suffixes.
    Example: "Title - Presenter - Date - formatted.md" -> "Title - Presenter - Date"
    """
    # Remove extension
    name = input_name
    if name.endswith(".md") or name.endswith(".txt"):
        name = Path(name).stem

    # Remove known suffixes
    suffixes = [
        config.SUFFIX_FORMATTED.replace(".md", ""),
        config.SUFFIX_YAML.replace(".md", ""),
        "_yaml",
        config.SUFFIX_WEBPAGE_SIMPLE.replace(".html", ""),
    ]
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break

    return name


def main():
    parser = argparse.ArgumentParser(
        description="Validate generated HTML webpage against source materials. "
        "Supports both sidebar layout and simple single-column layout."
    )
    parser.add_argument(
        "base_name",
        help='Base name of the transcript (e.g., "Title - Presenter - Date")',
    )
    parser.add_argument(
        "--simple",
        action="store_true",
        help="Validate simple webpage format (single-column, no sidebar)",
    )

    args = parser.parse_args()

    base_name = resolve_base_name(args.base_name)

    success = validate_webpage(base_name, simple_mode=args.simple)
    exit(0 if success else 1)


if __name__ == "__main__":
    main()
