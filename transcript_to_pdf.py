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


# Directories (from environment variable)
TRANSCRIPTS_BASE = Path(
    os.getenv("TRANSCRIPTS_DIR", Path.home() / "transcripts"))
FORMATTED_DIR = TRANSCRIPTS_BASE / "formatted"
SUMMARIES_DIR = TRANSCRIPTS_BASE / "summaries"
OUTPUT_DIR = TRANSCRIPTS_BASE / "pdfs"


def normalize_text(text):
    """Normalize text for comparison."""
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

    if best_pos is not None:
        words_before = ' '.join(haystack_words[:best_pos])
        approx_start = len(words_before)
        approx_end = approx_start + \
            len(' '.join(haystack_words[best_pos:best_pos + needle_len]))
        return (approx_start, approx_end, best_ratio)

    return (None, None, 0)


def extract_bowen_references(extracts_summary_file):
    """Extract Bowen reference quotes from extracts-summary document."""
    with open(extracts_summary_file, 'r', encoding='utf-8') as f:
        content = f.read()

    match = re.search(
        r'## \*\*Bowen References\*\*(.*?)(?=^## \*\*|---|\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )
    if not match:
        return []

    bowen_section = match.group(1)
    quote_pattern = r'>\s*\*\*Concept:\s*([^*]+)\*\*[^"]*"([^"]+)"'
    quotes = re.findall(quote_pattern, bowen_section)

    return [(concept.strip(), quote.strip()) for concept, quote in quotes]


def extract_emphasis_items(extracts_summary_file):
    """Extract emphasis item quotes from extracts-summary document."""
    with open(extracts_summary_file, 'r', encoding='utf-8') as f:
        content = f.read()

    match = re.search(
        r'## \*\*Emphasized Items\*\*(.*?)(?=^## \*\*|---|\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )
    if not match:
        return []

    emphasis_section = match.group(1)
    quote_pattern = r'>\s*\*\*([^*]+):\*\*\s*"([^"]+)"'
    quotes = re.findall(quote_pattern, emphasis_section)

    return [(label.strip(), quote.strip()) for label, quote in quotes]


def extract_metadata(extracts_summary_file):
    """Extract topics, themes, key terms, and abstract from extracts-summary."""
    with open(extracts_summary_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Strip YAML front matter if present
    if content.startswith('---'):
        parts = content.split('---\n', 2)
        if len(parts) >= 3:
            content = parts[2]

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
        'key_terms': [],
        'abstract': ''
    }

    # Extract Topics section
    topics_match = re.search(
        r'## \*\*Topics\*\*(.*?)(?=^## \*\*|\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )
    if topics_match:
        metadata['topics'] = topics_match.group(1).strip()

    # Extract Key Themes section
    themes_match = re.search(
        r'## \*\*Key Themes\*\*(.*?)(?=^## [^*]|\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )
    if themes_match:
        metadata['themes'] = themes_match.group(1).strip()

    # Extract Key Terms (all terms with definitions)
    key_terms_section = re.search(
        r'# Key Terms(.*?)(?=^## \*\*|\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )

    if key_terms_section:
        terms_content = key_terms_section.group(1)

        # Try new format with <<<TERM_START>>> and <<<TERM_END>>> markers first
        if '<<<TERM_START>>>' in terms_content:
            # Split by term markers
            term_blocks = re.split(r'<<<TERM_START>>>', terms_content)

            for block in term_blocks[1:]:  # Skip first empty split
                if '<<<TERM_END>>>' not in block:
                    continue
                block = block.split('<<<TERM_END>>>')[0].strip()

                # Extract term name
                name_match = re.search(r'^## (.+?)$', block, re.MULTILINE)
                if not name_match:
                    continue
                term_name = name_match.group(1).strip()

                # Extract definition type
                def_type_match = re.search(
                    r'\*\*Definition Type:\*\*\s*(.+?)$', block, re.MULTILINE)
                def_type = def_type_match.group(
                    1).strip() if def_type_match else 'Not Specified'

                # Extract definition
                def_match = re.search(
                    r'\*\*Definition:\*\*\s*(.+?)(?=\*\*Source Location:|$)', block, re.DOTALL)
                definition = def_match.group(1).strip() if def_match else ''

                # Extract source location
                source_match = re.search(
                    r'\*\*Source Location:\*\*\s*(.+?)(?=\*\*Context/Usage Notes:|$)', block, re.DOTALL)
                source = source_match.group(1).strip() if source_match else ''

                # Extract context/usage notes
                context_match = re.search(
                    r'\*\*Context/Usage Notes:\*\*\s*(.+?)$', block, re.DOTALL)
                context = context_match.group(
                    1).strip() if context_match else ''

                metadata['key_terms'].append({
                    'name': term_name,
                    'type': def_type,
                    'definition': definition,
                    'source': source,
                    'context': context
                })
        else:
            # Fallback to old format with --- separators
            term_blocks = re.split(r'\n---\n', terms_content)

            for block in term_blocks:
                block = block.strip()
                if not block or not block.startswith('##'):
                    continue

                # Extract term name
                name_match = re.search(r'^## (.+?)$', block, re.MULTILINE)
                if not name_match:
                    continue
                term_name = name_match.group(1).strip()

                # Extract definition type
                def_type_match = re.search(
                    r'\*\*Definition Type:\*\*\s*(.+?)$', block, re.MULTILINE)
                def_type = def_type_match.group(
                    1).strip() if def_type_match else 'Not Specified'

                # Extract definition
                def_match = re.search(
                    r'\*\*Definition:\*\*\s*(.+?)(?=\*\*Source Location:|$)', block, re.DOTALL)
                definition = def_match.group(1).strip() if def_match else ''

                # Extract source location
                source_match = re.search(
                    r'\*\*Source Location:\*\*\s*(.+?)(?=\*\*Context/Usage Notes:|$)', block, re.DOTALL)
                source = source_match.group(1).strip() if source_match else ''

                # Extract context/usage notes
                context_match = re.search(
                    r'\*\*Context/Usage Notes:\*\*\s*(.+?)$', block, re.DOTALL)
                context = context_match.group(
                    1).strip() if context_match else ''

                metadata['key_terms'].append({
                    'name': term_name,
                    'type': def_type,
                    'definition': definition,
                    'source': source,
                    'context': context
                })

    # Extract Abstract
    abstract_match = re.search(
        r'## \*\*Abstract\*\*(.*?)(?=^## \*\*|\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )
    if abstract_match:
        metadata['abstract'] = abstract_match.group(1).strip()

    return metadata


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

    for concept, quote in bowen_refs:
        quote_words = quote.split()
        search_text = ' '.join(quote_words[:min(50, len(quote_words))])
        start, end, ratio = find_text_in_content(
            search_text, formatted_content)
        if start is not None and ratio >= 0.85:
            highlights.append((start, end, 'bowen', concept))

    for label, quote in emphasis_items:
        quote_words = quote.split()
        search_text = ' '.join(quote_words[:min(50, len(quote_words))])
        start, end, ratio = find_text_in_content(
            search_text, formatted_content)
        if start is not None and ratio >= 0.85:
            highlights.append((start, end, 'emphasis', label))

    highlights.sort(key=lambda x: x[0], reverse=True)

    filtered_highlights = []
    for h in highlights:
        overlaps = False
        for existing in filtered_highlights:
            if (h[0] >= existing[0] and h[0] < existing[1]) or \
               (h[1] > existing[0] and h[1] <= existing[1]):
                overlaps = True
                break
        if not overlaps:
            filtered_highlights.append(h)

    result = formatted_content
    for start, end, htype, label in filtered_highlights:
        if htype == 'bowen':
            before = result[:start]
            text = result[start:end]
            after = result[end:]
            result = (before +
                      f'<mark class="bowen-ref">' +
                      text + '</mark>' + after)
        elif htype == 'emphasis':
            before = result[:start]
            text = result[start:end]
            after = result[end:]
            result = (before +
                      f'<mark class="emphasis">' +
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

    # Generate key terms HTML
    key_terms_html = ''
    if metadata['key_terms']:
        key_terms_html = '<div class="key-terms">'
        for term in metadata['key_terms']:
            # Determine definition type class for styling
            def_type_class = 'explicit' if 'Explicit' in term['type'] else 'implicit'
            def_type_label = term['type']

            key_terms_html += f'''
            <div class="term">
                <h3>{escape(term['name'])}</h3>
                <p class="def-type {def_type_class}"><strong>Definition Type:</strong> <span class="badge">{escape(def_type_label)}</span></p>
                <p class="definition"><strong>Definition:</strong> {escape(term['definition'])}</p>
                <p class="source"><strong>Source Location:</strong> {escape(term['source'])}</p>
                {f'<p class="context"><strong>Context/Usage Notes:</strong> {escape(term["context"])}</p>' if term['context'] else ''}
            </div>
            '''
        key_terms_html += '</div>'

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
            margin-bottom: 1in;
            color: #2c3e50;
        }}

        .cover .meta {{
            font-size: 14pt;
            margin-bottom: 0.5in;
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

        .term {{
            margin-bottom: 24pt;
            padding: 12pt;
            background: #f8f9fa;
            border-left: 4px solid #2c3e50;
            page-break-inside: avoid;
        }}

        .term h3 {{
            color: #2c3e50;
            margin-bottom: 8pt;
            font-size: 14pt;
        }}

        .term p {{
            margin: 6pt 0;
            line-height: 1.4;
        }}

        .term .def-type {{
            margin-bottom: 8pt;
        }}

        .term .badge {{
            padding: 2pt 8pt;
            border-radius: 3pt;
            font-weight: 600;
            font-size: 9pt;
        }}

        .term .def-type.explicit .badge {{
            background: #d4edda;
            color: #155724;
        }}

        .term .def-type.implicit .badge {{
            background: #d1ecf1;
            color: #0c5460;
        }}

        .term .definition {{
            font-style: italic;
            margin-left: 8pt;
        }}

        .term .source {{
            font-size: 9pt;
            color: #666;
        }}

        .term .context {{
            font-size: 9pt;
            color: #555;
            margin-left: 8pt;
            border-left: 2pt solid #ccc;
            padding-left: 8pt;
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
        {key_terms_html}
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
    extracts_summary_file = SUMMARIES_DIR / f"{base_name} - extracts-summary.md"
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
    bowen_refs = extract_bowen_references(extracts_summary_file)
    emphasis_items = extract_emphasis_items(extracts_summary_file)
    metadata = extract_metadata(extracts_summary_file)

    print(f"   Found {len(bowen_refs)} Bowen references")
    print(f"   Found {len(emphasis_items)} emphasis items")
    print(f"   Found {len(metadata['key_terms'])} key terms")

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
