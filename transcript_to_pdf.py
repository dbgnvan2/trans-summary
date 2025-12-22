#!/usr/bin/env python3
"""
Generate comprehensive PDF from transcript and extracts-summary materials.
Includes all metadata, topics, themes, key terms, and highlighted transcript.

Requires: weasyprint library
Install: pip install weasyprint

Usage:
    python transcript_to_pdf.py "Title - Presenter - Date"

Example:
    python transcript_to_pdf.py "Roots of Bowen Theory - Dr Michael Kerr - 2019-11-15"
"""

import argparse
import os
import re
from pathlib import Path
from html import escape
from difflib import SequenceMatcher

# Import centralized extraction functions
from transcript_utils import (
    extract_section,
    extract_bowen_references,
    extract_emphasis_items,
    strip_yaml_frontmatter
)


# Directories (from environment variable)
TRANSCRIPTS_BASE = Path(
    os.getenv("TRANSCRIPTS_DIR", Path.home() / "transcripts"))
FORMATTED_DIR = TRANSCRIPTS_BASE / "formatted"
SUMMARIES_DIR = TRANSCRIPTS_BASE / "summaries"
OUTPUT_DIR = TRANSCRIPTS_BASE / "pdfs"


def normalize_text(text):
    """Normalize text for comparison."""
    # Remove HTML tags that can break matching
    text = re.sub(r'<[^>]+>', ' ', text)

    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text.lower()


def find_text_in_content(needle, haystack, context=50):
    """Find needle in haystack and return (start_pos, end_pos, match_ratio)."""
    needle_normalized = normalize_text(needle)
    haystack_normalized = normalize_text(haystack)

    if needle_normalized in haystack_normalized:
        search_start = needle[:min(20, len(needle))].strip()
        pos = haystack.lower().find(search_start.lower())
        if pos >= 0:
            return (pos, pos + len(needle), 1.0)

    needle_words = needle_normalized.split()
    haystack_words = haystack_normalized.split()
    needle_len = len(needle_words)

    best_ratio = 0
    best_pos = None

    for i in range(len(haystack_words) - needle_len + 1):
        window = ' '.join(haystack_words[i:i + needle_len])
        ratio = SequenceMatcher(None, needle_normalized, window).ratio()

        if ratio > best_ratio and ratio >= 0.85:
            best_ratio = ratio
            best_pos = i

            # Early termination if we find a perfect or near-perfect match
            if ratio >= 0.98:
                break

    if best_pos is not None:
        words_before = ' '.join(haystack_words[:best_pos])
        approx_start = len(words_before)
        approx_end = approx_start + \
            len(' '.join(haystack_words[best_pos:best_pos + needle_len]))
        return (approx_start, approx_end, best_ratio)

    return (None, None, 0)


def load_bowen_references(extracts_summary_file):
    """Load Bowen reference quotes from extracts-summary file."""
    extracts_path = Path(extracts_summary_file)
    stem = extracts_path.stem.replace(' - extracts-summary', '')
    bowen_file = extracts_path.parent / f"{stem} - bowen-references.md"
    source_file = bowen_file if bowen_file.exists() else extracts_path

    with open(source_file, 'r', encoding='utf-8') as f:
        content = f.read()
    content = strip_yaml_frontmatter(content)
    return extract_bowen_references(content)


def load_emphasis_items(extracts_summary_file):
    """Load emphasis item quotes from extracts-summary file."""
    extracts_path = Path(extracts_summary_file)
    stem = extracts_path.stem.replace(' - extracts-summary', '')
    emphasis_file = extracts_path.parent / f"{stem} - emphasis-items.md"
    source_file = emphasis_file if emphasis_file.exists() else extracts_path

    with open(source_file, 'r', encoding='utf-8') as f:
        content = f.read()
    content = strip_yaml_frontmatter(content)
    return extract_emphasis_items(content)


def load_definitions_content(extracts_summary_file):
    """Load key term definitions from a split file when available."""
    extracts_path = Path(extracts_summary_file)
    stem = extracts_path.stem.replace(' - extracts-summary', '')
    summaries_dir = extracts_path.parent

    candidates = [
        summaries_dir / f"{stem} - key-terms.md",
        summaries_dir / f"{stem} - definitions.md",
        summaries_dir / f"{stem} - key-term-definitions.md",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding='utf-8')

    return None


def extract_metadata(extracts_summary_file):
    """Extract topics, themes, key terms, and abstract from extracts-summary."""
    with open(extracts_summary_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Strip YAML front matter if present
    content = strip_yaml_frontmatter(content)

    # Remove "TERMINOLOGY EXTRACTION OUTPUT" section with YAML
    content = re.sub(
        r'---\s*#\s*TERMINOLOGY EXTRACTION OUTPUT.*?---\s*#\s*Key Terms',
        '# Key Terms',
        content,
        flags=re.DOTALL
    )

    metadata = {
        'topics': '',
        'themes': '',
        'key_terms': '',
        'abstract': ''
    }

    # Extract sections using centralized functions
    metadata['topics'] = extract_section(content, 'Topics')
    metadata['themes'] = extract_section(content, 'Key Themes')
    metadata['abstract'] = extract_section(content, 'Abstract')
    metadata['key_terms'] = extract_section(content, 'Key Terms')

    definitions_content = load_definitions_content(extracts_summary_file)
    if definitions_content:
        definitions_content = strip_yaml_frontmatter(definitions_content)
        # Drop fenced YAML blocks if present
        definitions_content = re.sub(
            r'```yaml.*?```',
            '',
            definitions_content,
            flags=re.DOTALL | re.IGNORECASE
        )
        definitions_content = re.sub(
            r'^## (Part 2: Key Term Definitions|Key Terms)\s*',
            '',
            definitions_content,
            flags=re.MULTILINE
        ).strip()
        if definitions_content:
            metadata['key_terms'] = sort_key_term_sections(definitions_content)

    return metadata


def sort_key_term_sections(content: str) -> str:
    """Sort key term sections alphabetically by heading."""
    sections = []
    current = None
    for line in content.splitlines():
        if line.startswith('## '):
            if current:
                sections.append(current)
            current = {'title': line[3:].strip(), 'lines': [line]}
        else:
            if current is None:
                # Skip any leading content without a heading
                continue
            current['lines'].append(line)
    if current:
        sections.append(current)

    if not sections:
        return content

    sections.sort(key=lambda s: s['title'].lower())
    return '\n'.join('\n'.join(section['lines']) for section in sections).strip()


def markdown_to_html(text):
    """Convert basic markdown to HTML."""
    text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)

    paragraphs = text.split('\n\n')
    paragraphs = [f'<p>{p.strip()}</p>' if not p.strip().startswith('<') else p.strip()
                  for p in paragraphs if p.strip()]

    return '\n'.join(paragraphs)


def highlight_transcript(formatted_content, bowen_refs, emphasis_items):
    """Add HTML highlighting to transcript for Bowen refs and emphasis."""
    highlights = []

    # Find section header positions to exclude them from highlighting
    section_headers = []
    for match in re.finditer(r'^##[^\n]+$', formatted_content, re.MULTILINE):
        section_headers.append((match.start(), match.end()))

    def is_in_section_header(start, end):
        """Check if a position overlaps with any section header."""
        for header_start, header_end in section_headers:
            if (start >= header_start and start < header_end) or \
               (end > header_start and end <= header_end) or \
               (start <= header_start and end >= header_end):
                return True
        return False

    def add_bowen_label(existing, label):
        if not existing[4]:
            existing[4] = label
            return
        labels = [l.strip() for l in existing[4].split(';') if l.strip()]
        if label not in labels:
            labels.append(label)
            existing[4] = '; '.join(labels)

    def find_text_in_lines(needle, content, max_words=20):
        """Find needle in content without crossing line boundaries."""
        needle_words = normalize_text(needle).split()
        if not needle_words:
            return (None, None, 0)
        offset = 0
        for line in content.splitlines(keepends=True):
            line_words = normalize_text(line).split()
            if not line_words:
                offset += len(line)
                continue
            snippet_words = needle_words[:min(len(needle_words), len(line_words), max_words)]
            snippet = ' '.join(snippet_words)
            start, end, ratio = find_text_in_content(snippet, line)
            if start is not None:
                return (offset + start, offset + end, ratio)
            offset += len(line)
        return (None, None, 0)

    def find_quote_in_lines(quote, content, max_words=20, min_words=6):
        """Find a quote by scanning windows within each line."""
        quote_words = quote.split()
        if len(quote_words) < min_words:
            return (None, None, 0)
        offset = 0
        for line in content.splitlines(keepends=True):
            line_words = normalize_text(line).split()
            if not line_words:
                offset += len(line)
                continue
            window_max = min(max_words, len(quote_words))
            for window in range(window_max, min_words - 1, -1):
                for start_idx in range(0, len(quote_words) - window + 1):
                    snippet = ' '.join(quote_words[start_idx:start_idx + window])
                    start, end, ratio = find_text_in_content(snippet, line)
                    if start is not None and ratio >= 0.85:
                        return (offset + start, offset + end, ratio)
            offset += len(line)
        return (None, None, 0)

    emphasis_entries = {}

    for label, quote in emphasis_items:
        quote_words = quote.split()
        search_text = ' '.join(quote_words[:min(50, len(quote_words))])
        start, end, ratio = find_text_in_content(
            search_text, formatted_content)
        if start is not None and ratio >= 0.85 and not is_in_section_header(start, end):
            entry = [start, end, 'emphasis', label, None]
            highlights.append(entry)
            emphasis_entries[label] = entry

    for concept, quote in bowen_refs:
        quote_words = quote.split()
        first_sentence = re.split(r'[.!?]', quote, 1)[0].strip()
        search_text = first_sentence if first_sentence else ' '.join(
            quote_words[:min(50, len(quote_words))])
        start, end, ratio = find_text_in_lines(
            search_text, formatted_content)
        if start is None:
            start, end, ratio = find_quote_in_lines(
                quote, formatted_content)
        if start is not None and ratio >= 0.85 and not is_in_section_header(start, end):
            highlights.append([start, end, 'bowen', concept, None])
            continue

        bowen_norm = normalize_text(quote)
        for emphasis_label, emphasis_quote in emphasis_items:
            if bowen_norm in normalize_text(emphasis_quote):
                entry = emphasis_entries.get(emphasis_label)
                if entry:
                    add_bowen_label(entry, concept)
                break

    highlights.sort(key=lambda x: x[0], reverse=True)

    priority = {
        'emphasis': 2,
        'bowen': 1,
    }

    def overlaps(a, b):
        return (a[0] >= b[0] and a[0] < b[1]) or \
               (a[1] > b[0] and a[1] <= b[1])

    filtered_highlights = []
    for h in highlights:
        remove_indices = []
        should_skip = False
        for i, existing in enumerate(filtered_highlights):
            if overlaps(h, existing):
                if {h[2], existing[2]} == {'emphasis', 'bowen'}:
                    if h[2] == 'emphasis':
                        add_bowen_label(h, existing[3])
                        remove_indices.append(i)
                    else:
                        add_bowen_label(existing, h[3])
                        should_skip = True
                        break
                elif priority.get(h[2], 0) > priority.get(existing[2], 0):
                    remove_indices.append(i)
                else:
                    should_skip = True
                    break
        if should_skip:
            continue
        for i in reversed(remove_indices):
            filtered_highlights.pop(i)
        filtered_highlights.append(h)

    filtered_highlights.sort(key=lambda x: x[0], reverse=True)

    result = formatted_content
    for start, end, htype, label, extra_label in filtered_highlights:
        if htype == 'bowen':
            before = result[:start]
            text = result[start:end]
            after = result[end:]
            result = (before +
                      f'<mark class="bowen-ref" title="Bowen Reference: {escape(label)}">' +
                      text + '</mark>' + after)
        elif htype == 'emphasis':
            before = result[:start]
            text = result[start:end]
            after = result[end:]
            bowen_title = f' | Bowen Reference: {escape(extra_label)}' if extra_label else ''
            bowen_class = ' bowen-ref' if extra_label else ''
            result = (before +
                      f'<mark class="emphasis{bowen_class}" title="Emphasized: {escape(label)}{bowen_title}">' +
                      text + '</mark>' + after)

    return result


def generate_html_for_pdf(base_name, formatted_content, metadata):
    """Generate complete HTML for PDF conversion."""

    parts = base_name.split(' - ')
    title = parts[0] if len(parts) > 0 else base_name
    author = parts[1] if len(parts) > 1 else "Unknown"
    date = parts[2] if len(parts) > 2 else "Unknown"

    # Convert markdown metadata to HTML
    topics_html = markdown_to_html(metadata['topics'])
    themes_html = markdown_to_html(metadata['themes'])
    abstract_html = markdown_to_html(metadata['abstract'])
    key_terms_html = markdown_to_html(metadata['key_terms'])

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{escape(title)}</title>
    <style>
        @page {{
            size: Letter;
            margin: 0.75in;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Georgia', serif;
            font-size: 11pt;
            line-height: 1.5;
            color: #333;
        }}

        .cover {{
            page-break-after: always;
            text-align: center;
            padding-top: 3in;
        }}

        .cover h1 {{
            font-size: 28pt;
            margin-bottom: 0.5in;
            color: #2c3e50;
        }}

        .cover .meta {{
            font-size: 14pt;
            margin-bottom: 0.3in;
        }}

        .cover .toc {{
            text-align: left;
            margin: 0 auto;
            max-width: 4in;
            font-size: 12pt;
            line-height: 1.6;
        }}

        .cover .toc h2 {{
            font-size: 16pt;
            margin-bottom: 0.3in;
            color: #2c3e50;
            text-align: center;
        }}

        .cover .toc ol {{
            margin-left: 0.3in;
            padding-left: 0;
        }}

        .cover .toc li {{
            margin-bottom: 8pt;
        }}

        .section {{
            page-break-before: always;
        }}

        h1 {{
            font-size: 20pt;
            margin: 24pt 0 12pt 0;
            color: #2c3e50;
            page-break-after: avoid;
        }}

        h2 {{
            font-size: 16pt;
            margin: 18pt 0 10pt 0;
            color: #2c3e50;
            page-break-after: avoid;
        }}

        h3 {{
            font-size: 13pt;
            margin: 14pt 0 8pt 0;
            color: #34495e;
            page-break-after: avoid;
        }}

        p {{
            margin: 8pt 0;
            text-align: justify;
            orphans: 3;
            widows: 3;
        }}

        .abstract, .metadata-section {{
            margin-bottom: 24pt;
        }}

        mark.bowen-ref {{
            background-color: #fff3cd;
            padding: 2px 4px;
        }}

        mark.emphasis {{
            background-color: #d1ecf1;
            padding: 2px 4px;
        }}

        .legend {{
            margin: 18pt 0;
            padding: 12pt;
            background: #f8f9fa;
            border-left: 4px solid #2c3e50;
        }}

        strong {{
            font-weight: 600;
        }}
    </style>
</head>
<body>
    <div class="cover">
        <h1>{escape(title)}</h1>
        <div class="meta">
            <p><strong>{escape(author)}</strong></p>
            <p>{escape(date)}</p>
        </div>
        <div class="toc">
            <h2>Contents</h2>
            <ol>
                <li>Abstract</li>
                <li>Topics</li>
                <li>Key Themes</li>
                <li>Key Terms</li>
                <li>Transcript</li>
            </ol>
        </div>
    </div>

    <div class="section">
        <h1>Abstract</h1>
        <div class="abstract">
            {abstract_html}
        </div>
    </div>

    <div class="section">
        <h1>Topics</h1>
        <div class="metadata-section">
            {topics_html}
        </div>
    </div>

    <div class="section">
        <h1>Key Themes</h1>
        <div class="metadata-section">
            {themes_html}
        </div>
    </div>

    <div class="section">
        <h1>Key Terms</h1>
        <div class="metadata-section">
            {key_terms_html}
        </div>
    </div>

    <div class="section">
        <h1>Transcript</h1>
        <div class="legend">
            <strong>Highlights:</strong>
            <mark class="bowen-ref">Bowen References</mark> |
            <mark class="emphasis">Emphasized Items</mark>
        </div>
        {formatted_content}
    </div>
</body>
</html>'''

    return html


def generate_pdf(base_name: str) -> bool:
    """Generate comprehensive PDF from transcript and extracts-summary materials."""

    try:
        from weasyprint import HTML
    except ImportError:
        print("❌ WeasyPrint library not found.")
        print("   Install with: pip install weasyprint")
        return False

    formatted_file = FORMATTED_DIR / f"{base_name} - formatted.md"
    extracts_summary_file = SUMMARIES_DIR / \
        f"{base_name} - extracts-summary.md"
    output_file = OUTPUT_DIR / f"{base_name}.pdf"

    if not formatted_file.exists():
        print(f"❌ Formatted file not found: {formatted_file}")
        return False

    if not extracts_summary_file.exists():
        print(f"❌ Extracts-summary file not found: {extracts_summary_file}")
        return False

    # Read formatted transcript
    with open(formatted_file, 'r', encoding='utf-8') as f:
        formatted_content = f.read()

    # Strip YAML front matter if present
    if formatted_content.startswith('---'):
        parts = formatted_content.split('---\n', 2)
        if len(parts) >= 3:
            formatted_content = parts[2]

    print("📄 Loading extracts-summary materials...")

    # Extract all metadata
    bowen_refs = load_bowen_references(extracts_summary_file)
    emphasis_items = load_emphasis_items(extracts_summary_file)
    metadata = extract_metadata(extracts_summary_file)

    print(f"   Found {len(bowen_refs)} Bowen references")
    print(f"   Found {len(emphasis_items)} emphasis items")
    if metadata['key_terms']:
        print(f"   Found key terms section")

    print("🖍️  Highlighting transcript...")

    # Convert markdown to HTML and add highlights
    formatted_html = markdown_to_html(formatted_content)

    # Remove the "Transcript Formatting" H1 if present
    formatted_html = re.sub(
        r'<h1>Transcript Formatting[^<]*</h1>\s*',
        '',
        formatted_html,
        flags=re.IGNORECASE
    )

    highlighted_html = highlight_transcript(
        formatted_html, bowen_refs, emphasis_items)

    print("📝 Generating PDF...")

    # Generate HTML for PDF
    html_content = generate_html_for_pdf(base_name, highlighted_html, metadata)

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Convert HTML to PDF
    try:
        HTML(string=html_content).write_pdf(output_file)
    except Exception as e:
        print(f"❌ PDF generation failed: {e}")
        return False

    print(f"✅ PDF generated successfully!")
    print(f"   File: {output_file}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Generate comprehensive PDF from transcript and extracts-summary"
    )
    parser.add_argument(
        "base_name",
        help='Base name without suffix (e.g., "Title - Presenter - Date")'
    )

    args = parser.parse_args()

    try:
        success = generate_pdf(args.base_name)
        return 0 if success else 1

    except (OSError, IOError) as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
