#!/usr/bin/env python3
"""
Validate generated HTML webpage against source materials.
Checks that all expected content from canonical artifact files appears in the webpage.
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

    # Simple layout - count h2 inside the Transcript section's body
    transcript = _simple_section(soup, "Transcript")
    if transcript is not None:
        sections = [h2.get_text(strip=True) for h2 in transcript.find_all("h2")]
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
    source_labels = [label for label, _, _ in emphasis_items]

    # Extract emphasis labels that are highlighted in HTML
    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")
    highlighted_labels = []
    for mark in soup.find_all("mark", class_="emphasis"):
        label = _title_label(mark.get("title", ""), "Emphasized:")
        if label:
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
    source_labels = [label for label, _, _ in bowen_refs]

    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")
    highlighted_labels = []
    for mark in soup.find_all("mark", class_="bowen-ref"):
        label = _title_label(mark.get("title", ""), "Bowen Reference:")
        if label:
            highlighted_labels.append(label)

    highlighted_labels = set(split_multi_labels(highlighted_labels))

    # A merged reference is listed as "A; B" (load_bowen_references); it is
    # present when every part is highlighted.
    missing = []
    for label in source_labels:
        if not all(part in highlighted_labels for part in split_multi_labels([label])):
            missing.append(label)

    return missing


def extract_topics_themes_metadata(base_name: str):
    """Extract key metadata from canonical artifact files."""
    project_dir = config.PROJECTS_DIR / base_name
    topics_file = project_dir / f"{base_name}{config.SUFFIX_TOPICS}"
    structural_file = project_dir / f"{base_name}{config.SUFFIX_STRUCTURAL_THEMES}"
    interpretive_file = project_dir / f"{base_name}{config.SUFFIX_INTERPRETIVE_THEMES}"
    key_terms_file = project_dir / f"{base_name}{config.SUFFIX_KEY_TERMS}"
    abstract_file = project_dir / f"{base_name}{config.SUFFIX_ABSTRACT_GEN}"
    summary_file = project_dir / f"{base_name}{config.SUFFIX_SUMMARY_GEN}"

    def _read(path: Path) -> str:
        if not path.exists():
            return ""
        content = path.read_text(encoding="utf-8")
        if content.startswith("---"):
            parts = content.split("---\n", 2)
            if len(parts) >= 3:
                content = parts[2]
        return content

    topics_content = _read(topics_file)
    structural_content = _read(structural_file)
    interpretive_content = _read(interpretive_file)
    key_terms_content = _read(key_terms_file)
    abstract_content = _read(abstract_file)
    summary_content = _read(summary_file)

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

    if abstract_content.strip():
        abstract_text = abstract_content.strip()
        metadata["has_abstract"] = True
        metadata["abstract_text"] = abstract_text
        metadata["abstract_length"] = len(abstract_text)

    if summary_content.strip():
        metadata["has_summary"] = True
        metadata["summary_length"] = len(summary_content.strip())

    # Count Topics
    topics_match = re.search(
        r"## (?:\*\*)?(?:Key )?Topics(?:\*\*)?(.*?)(?=^## |\Z)",
        topics_content,
        re.MULTILINE | re.DOTALL,
    )
    if topics_match:
        topics_text = topics_match.group(1).strip()
        # Extract topic names (### Topic Name)
        topics = re.findall(r"^### (.+)$", topics_text, re.MULTILINE)
        metadata["topics_list"] = [t.strip() for t in topics]
        metadata["topics_count"] = len(topics)

    # Count Structural + Interpretive Themes
    theme_sections = re.finditer(
        r"## (?:\*\*)?(?:Structural Themes|Interpretive Themes|Themes|Interpretive / Process Themes)(?:\*\*)?(.*?)(?=^## |\Z)",
        "\n".join([structural_content, interpretive_content]),
        re.MULTILINE | re.DOTALL,
    )
    collected_themes = []
    for m in theme_sections:
        themes_text = m.group(1).strip()
        themes_h3 = re.findall(r"^### (.+)$", themes_text, re.MULTILINE)
        themes_numbered = re.findall(
            r"^\d+\.\s+\*\*([^*]+)\*\*", themes_text, re.MULTILINE
        )
        collected_themes.extend(themes_h3 + themes_numbered)
    if collected_themes:
        metadata["themes_list"] = [t.strip() for t in collected_themes]
        metadata["themes_count"] = len(collected_themes)

    # Count Key Terms
    key_terms_match = re.search(
        r"## (?:\*\*)?Key Terms(?:\*\*)?(.*?)(?=^## |^---+|\Z)",
        key_terms_content,
        re.MULTILINE | re.DOTALL,
    )
    if key_terms_match:
        kt_text = key_terms_match.group(1)
        # Extract term names (### Term Name)
        term_headings = re.findall(r"^### (.+)$", kt_text, re.MULTILINE)
        metadata["key_terms_list"] = [t.strip() for t in term_headings]
        metadata["key_terms_count"] = len(term_headings)

    # Bowen/Emphasis are loaded via centralized loaders in validate_webpage.

    return metadata


def _title_label(title: str, key: str) -> str:
    """The label after ``key`` in a highlight's title, up to the next ``|``.
    Titles look like "Emphasized: X (92%) | Bowen Reference: Y | Timestamp: 00:05:29"."""
    if key not in title:
        return ""
    return title.split(key, 1)[1].split("|")[0].strip()


def _empty_html_metadata() -> dict:
    return {
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


def _metadata_from_sections(get_section, transcript_root) -> dict:
    """Fill the HTML metadata from ``get_section(heading) -> [elements] | None``
    and count the highlights inside ``transcript_root`` (so the legend is not
    counted). Shared by the sidebar and the simple layout."""
    metadata = _empty_html_metadata()

    abstract_elems = get_section("Abstract")
    if abstract_elems:
        text = " ".join(e.get_text(strip=True) for e in abstract_elems)
        if text:
            metadata["has_abstract"] = True
            metadata["abstract_text"] = text
            metadata["abstract_length"] = len(text)

    summary_elems = get_section("Summary")
    if summary_elems:
        text = " ".join(e.get_text(strip=True) for e in summary_elems)
        if text:
            metadata["has_summary"] = True
            metadata["summary_length"] = len(text)

    # Headings are searched INSIDE each element (as the sidebar reader always
    # did); the simple layout passes its section's body <div> as the one element.
    def _h3s(elems):
        return [h.get_text(strip=True) for e in elems for h in e.find_all("h3")]

    topics_elems = get_section("Key Topics")
    if topics_elems:
        # Present = the section has text (the simple layout always renders the
        # body <div>, so "the section exists" proves nothing).
        metadata["has_topics"] = any(e.get_text(strip=True) for e in topics_elems)
        metadata["topics_list"] = _h3s(topics_elems)

    themes_elems = get_section("Themes")
    if themes_elems:
        metadata["has_themes"] = any(e.get_text(strip=True) for e in themes_elems)
        metadata["themes_list"] = _h3s(themes_elems)
        for elem in themes_elems:
            for p in elem.find_all("p"):
                if re.match(r"\d+\.", p.get_text(strip=True)):
                    strong = p.find("strong")
                    if strong:
                        metadata["themes_list"].append(strong.get_text(strip=True))

    terms_elems = get_section("Key Terms")
    if terms_elems:
        dls = [d for e in terms_elems for d in ([e] if e.name == "dl" else e.find_all("dl"))]  # sidebar: <dl> sibling; simple: inside the body
        if dls:
            metadata["key_terms_list"] = [dt.get_text(strip=True) for d in dls for dt in d.find_all("dt")]
            metadata["has_key_terms"] = bool(metadata["key_terms_list"])
        else:
            text = " ".join(e.get_text(strip=True) for e in terms_elems)
            if text and "No key terms found" not in text:
                metadata["has_key_terms"] = True
                metadata["key_terms_list"] = [t.strip() for t in text.split(",") if t.strip()]

    if transcript_root is None:
        return metadata

    bowen_marks = transcript_root.find_all("mark", class_="bowen-ref")
    metadata["bowen_highlights"] = len(bowen_marks)
    metadata["bowen_labels"] = split_multi_labels(
        [label for m in bowen_marks if (label := _title_label(m.get("title", ""), "Bowen Reference:"))])

    emphasis_marks = transcript_root.find_all("mark", class_="emphasis")
    metadata["emphasis_highlights"] = len(emphasis_marks)
    metadata["emphasis_labels"] = [
        label for m in emphasis_marks if (label := _title_label(m.get("title", ""), "Emphasized:"))]
    return metadata


def extract_html_metadata(html_file):
    """Extract metadata from the sidebar layout (sidebar sections, transcript highlights)."""
    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")
    sidebar = soup.find("aside", class_="sidebar")
    if not sidebar:
        return _empty_html_metadata()

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

    main_content = soup.find("div", class_="transcript") or soup.find(
        "div", class_="content") or soup
    return _metadata_from_sections(get_sidebar_section, main_content)


def _simple_section(soup, heading_text):
    """The body <div> of ``<section class="section"><h2>heading</h2><div>…`` in
    templates/simple_webpage.html, or None."""
    for section in soup.find_all("section", class_="section"):
        h2 = section.find("h2", recursive=False)
        if h2 and h2.get_text(strip=True) == heading_text:
            return section.find("div", recursive=False)
    return None


def extract_html_simple_metadata(html_file):
    """Extract metadata from the simple single-column layout
    (templates/simple_webpage.html: one <section class="section"> per block)."""
    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")

    def get_section(heading_text):
        body = _simple_section(soup, heading_text)
        return [body] if body is not None else None

    return _metadata_from_sections(get_section, _simple_section(soup, "Transcript"))


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


def transcript_text_differences(html_file, formatted_file) -> list:
    """Word-level differences between the transcript as published in the HTML
    (the ``div.transcript`` text, headings excluded) and the formatted transcript
    (heading lines excluded). Highlighting and markdown conversion must not add,
    drop or alter any transcript word. Returns up to 10 difference descriptions;
    an empty list means identical."""
    import formatting_pipeline as fp
    from transcript_utils import strip_yaml_frontmatter

    soup = BeautifulSoup(Path(html_file).read_text(encoding="utf-8"), "html.parser")
    container = soup.find("div", class_="transcript")
    if container is None:
        return ["no <div class=\"transcript\"> found in HTML"]
    for heading in container.find_all(["h1", "h2", "h3", "h4"]):
        heading.decompose()
    html_words = [w for w in (fp._normalize_word_for_validation(x)
                              for x in container.get_text(" ").split()) if w]
    formatted = strip_yaml_frontmatter(Path(formatted_file).read_text(encoding="utf-8"))
    source_words = [w for w in (fp._normalize_word_for_validation(x)
                                for line in formatted.splitlines() if not line.startswith("#")
                                for x in line.split()) if w]
    diffs = []
    for tag, i1, i2, j1, j2 in fp._word_opcodes(source_words, html_words):
        if tag != "equal":
            diffs.append(f"{tag}: transcript {' '.join(source_words[i1:i2][:8])!r} "
                         f"-> HTML {' '.join(html_words[j1:j2][:8])!r}")
            if len(diffs) >= 10:
                break
    return diffs


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
    # Use correct HTML filename based on mode
    if simple_mode:
        html_file = project_dir / f"{base_name}{config.SUFFIX_WEBPAGE_SIMPLE}"
    else:
        html_file = project_dir / f"{base_name}{config.SUFFIX_WEBPAGE}"

    # Check files exist
    missing_files = []
    if not formatted_file.exists():
        missing_files.append(f"Formatted: {formatted_file}")
    topics_file = project_dir / f"{base_name}{config.SUFFIX_TOPICS}"
    structural_file = project_dir / f"{base_name}{config.SUFFIX_STRUCTURAL_THEMES}"
    interpretive_file = project_dir / f"{base_name}{config.SUFFIX_INTERPRETIVE_THEMES}"
    key_terms_file = project_dir / f"{base_name}{config.SUFFIX_KEY_TERMS}"
    if not topics_file.exists():
        missing_files.append(f"Topics file not found: {topics_file.name}")
    if not structural_file.exists():
        missing_files.append(f"Structural themes file not found: {structural_file.name}")
    if not interpretive_file.exists():
        missing_files.append(f"Interpretive themes file not found: {interpretive_file.name}")
    if not key_terms_file.exists():
        missing_files.append(f"Key terms file not found: {key_terms_file.name}")
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

    # Transcript body must be word-for-word the formatted transcript.
    text_diffs = transcript_text_differences(html_file, formatted_file)
    if text_diffs:
        print("❌ Transcript text in HTML differs from the formatted transcript:")
        for d in text_diffs:
            print(f"   {d}")
        issues.append(f"Transcript text differs from formatted transcript ({len(text_diffs)}+ difference(s))")
    else:
        print("   Transcript text: ✅ identical to formatted transcript")

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

    source_meta = extract_topics_themes_metadata(base_name)

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
    print(
        f"      Source: {'Present' if source_meta.get('has_summary') else 'Not Generated'}"
    )
    print(
        f"      HTML:   {'Present' if html_meta['has_summary'] else 'Missing'} "
        f"({html_meta['summary_length']} chars)"
    )

    if source_meta.get('has_summary') and not html_meta['has_summary']:
        issues.append("Generated summary is missing from the final webpage.")
    elif not source_meta.get('has_summary') and not html_meta['has_summary']:
        print("      ✅ Summary correctly omitted from webpage.")
    else:
        # This covers cases where it's present in both, or present in HTML but not source.
        print("      ✅ Summary correctly included in webpage.")

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

    # Themes (skip in simple mode - not included in that layout)
    print("\n   Themes:")
    print(f"      Source: {source_meta['themes_count']} items")
    print(f"      HTML:   {'Present' if html_meta['has_themes'] else 'Empty'}")

    if source_meta["themes_count"] > 0 and not html_meta["has_themes"]:
        issues.append(
            f"Themes section empty in HTML (should have {source_meta['themes_count']} items)"
        )
    elif source_meta["themes_count"] > 0:
        print("      ✅ Themes present in HTML")

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
        ("Bowen Ref", label, quote) for label, quote, _ in load_bowen_references(base_name)
    ] + [("Emphasis", label, quote) for label, quote, _ in load_emphasis_items(base_name)]

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

    # Verify Themes (sample 30% rounded up) - skip in simple mode
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
                f"   Themes: ✅ {matched}/{len(sample_indices)} sampled items verified"
            )
        else:
            warnings.append(
                f"Themes content mismatch: only {matched}/{len(sample_indices)} verified"
            )
            print(f"   Themes: ⚠️  Only {matched}/{len(sample_indices)} verified")

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
