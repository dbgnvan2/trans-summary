#!/usr/bin/env python3
"""
Generate simple single-column HTML webpage from transcript.
Highlights Bowen references and emphasis items inline, no sidebar.

Usage:
    python transcript_to_simple_webpage.py "Title - Presenter - Date"
    
Example:
    python transcript_to_simple_webpage.py "Roots of Bowen Theory - Dr Michael Kerr - 2019-11-15"
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
OUTPUT_DIR = TRANSCRIPTS_BASE / "webpages"


def normalize_text(text):
    """Normalize text for comparison."""
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text.lower()


def find_text_in_content(needle, haystack, context=50):
    """Find needle in haystack and return (start_pos, end_pos, match_ratio)."""
    needle_normalized = normalize_text(needle)
    haystack_normalized = normalize_text(haystack)

    # Try exact match first
    if needle_normalized in haystack_normalized:
        search_start = needle[:min(20, len(needle))].strip()
        pos = haystack.lower().find(search_start.lower())
        if pos >= 0:
            return (pos, pos + len(needle), 1.0)

    # Fuzzy match - try sliding window
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
    """Extract Bowen reference quotes from archival document."""
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
    # Pattern: > **Label:** "quote" (Section X)
    quote_pattern = r'>\s*\*\*([^*]+):\*\*\s*"([^"]+)"'
    quotes = re.findall(quote_pattern, bowen_section)

    return [(concept.strip(), quote.strip()) for concept, quote in quotes]


def extract_emphasis_items(extracts_summary_file):
    """Extract emphasis item quotes from archival document."""
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
    # Pattern: number. **Label:** "quote" - **[Type]** (Section X)
    quote_pattern = r'\d+\.\s*\*\*([^*]+):\*\*\s*"([^"]+)"'
    quotes = re.findall(quote_pattern, emphasis_section)

    return [(label.strip(), quote.strip()) for label, quote in quotes]


def extract_abstract(extracts_summary_file):
    """Extract abstract from archival document."""
    with open(extracts_summary_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Strip YAML front matter if present
    if content.startswith('---'):
        parts = content.split('---\n', 2)
        if len(parts) >= 3:
            content = parts[2]

    match = re.search(
        r'## \*\*Abstract\*\*(.*?)(?=^## \*\*|\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )
    if match:
        return match.group(1).strip()
    return ''


def extract_key_terms(extracts_summary_file):
    """Extract key term names (without definitions) from archival document."""
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

    # Pattern: ## Term Name (followed by blank line and **Definition Type:**)
    term_headings = re.findall(
        r'^## ([A-Z][^\n#]+?)[\s]*\n+\*\*Definition Type:',
        content,
        re.MULTILINE
    )

    return [term.strip() for term in term_headings]


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


def extract_key_term_definitions(extracts_summary_file):
    """Extract key terms with their definitions and types from archival."""
    with open(extracts_summary_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Strip YAML
    if content.startswith('---'):
        parts = content.split('---\n', 2)
        if len(parts) >= 3:
            content = parts[2]

    # Remove YAML embedded blocks
    content = re.sub(
        r'---\s*#\s*TERMINOLOGY EXTRACTION OUTPUT.*?---\s*#\s*Key Terms',
        '# Key Terms',
        content,
        flags=re.DOTALL
    )

    # Find all term sections with definition type
    term_pattern = r'## ([A-Z][^\n#]+?)[\s]*\n+\*\*Definition Type:\*\*\s*(Explicit Definition|Implicit Definition|Not Explicitly Defined)[\s\S]*?\*\*Definition:\*\*\s*([^*]+?)(?=\n\*\*|\n##|\Z)'
    matches = re.findall(term_pattern, content, re.MULTILINE)

    terms = []
    for term_name, def_type, definition in matches:
        terms.append({
            'name': term_name.strip(),
            'type': def_type.strip(),
            'definition': definition.strip()
        })

    return terms


def highlight_transcript(formatted_content, bowen_refs, emphasis_items, key_term_defs):
    """Add HTML highlighting to transcript for Bowen refs, emphasis, and term definitions."""
    highlights = []

    # Find Bowen references
    for concept, quote in bowen_refs:
        quote_words = quote.split()
        search_text = ' '.join(quote_words[:min(50, len(quote_words))])
        start, end, ratio = find_text_in_content(
            search_text, formatted_content)
        if start is not None and ratio >= 0.85:
            highlights.append((start, end, 'bowen', concept))

    # Find emphasis items
    for label, quote in emphasis_items:
        quote_words = quote.split()
        search_text = ' '.join(quote_words[:min(50, len(quote_words))])
        start, end, ratio = find_text_in_content(
            search_text, formatted_content)
        if start is not None and ratio >= 0.85:
            highlights.append((start, end, 'emphasis', label))

    # Find key term definitions
    for term in key_term_defs:
        definition = term['definition']
        def_words = definition.split()
        # Try first 30 words of definition
        search_text = ' '.join(def_words[:min(30, len(def_words))])
        start, end, ratio = find_text_in_content(
            search_text, formatted_content)
        if start is not None and ratio >= 0.80:
            htype = 'def-explicit' if 'Explicit' in term['type'] else 'def-implicit'
            highlights.append((start, end, htype, term['name']))

    # Sort by position (reverse order for easier insertion)
    highlights.sort(key=lambda x: x[0], reverse=True)

    # Remove overlaps
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

    # Apply highlights
    result = formatted_content
    for start, end, htype, label in filtered_highlights:
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
            result = (before +
                      f'<mark class="emphasis" title="Emphasized: {escape(label)}">' +
                      text + '</mark>' + after)
        elif htype in ['def-explicit', 'def-implicit']:
            before = result[:start]
            text = result[start:end]
            after = result[end:]
            def_type = 'Explicit Definition' if htype == 'def-explicit' else 'Implicit Definition'
            result = (before +
                      f'<span class="{htype}" title="{def_type}: {escape(label)}">' +
                      text + '</span>' + after)

    return result


def generate_html_page(base_name, formatted_content, abstract='', key_terms=[]):
    """Generate simple HTML page without sidebar."""

    parts = base_name.split(' - ')
    title = parts[0] if len(parts) > 0 else base_name
    author = parts[1] if len(parts) > 1 else "Unknown"
    date = parts[2] if len(parts) > 2 else "Unknown"

    # Format abstract HTML
    abstract_html = ''
    if abstract:
        abstract_html = f'''
            <section class="abstract">
                <h2>Abstract</h2>
                {markdown_to_html(abstract)}
            </section>
        '''

    # Format key terms HTML
    key_terms_html = ''
    if key_terms:
        terms_list = ', '.join(
            f'<strong>{escape(term)}</strong>' for term in key_terms)
        key_terms_html = f'''
            <section class="key-terms">
                <h2>Key Terms</h2>
                <p>{terms_list}</p>
            </section>
        '''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(title)}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Georgia', serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
        }}
        
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            box-shadow: 0 0 20px rgba(0,0,0,0.1);
        }}
        
        header {{
            background: #2c3e50;
            color: white;
            padding: 2rem;
            text-align: center;
        }}
        
        header h1 {{
            font-size: 2rem;
            margin-bottom: 0.5rem;
        }}
        
        header .meta {{
            font-size: 1rem;
            opacity: 0.9;
        }}
        
        .content {{
            padding: 2rem 3rem;
        }}
        
        .legend {{
            margin: 0 0 2rem 0;
            padding: 1rem;
            background: #f8f9fa;
            border-radius: 5px;
            font-size: 0.9rem;
        }}
        
        .legend span {{
            display: inline-block;
            margin-right: 1.5rem;
        }}
        
        .abstract {{
            margin: 2rem 0;
            padding: 1.5rem;
            background: #f8f9fa;
            border-left: 4px solid #2c3e50;
        }}
        
        .abstract h2 {{
            margin-top: 0;
        }}
        
        .key-terms {{
            margin: 2rem 0;
            padding: 1.5rem;
            background: #f0f7ff;
            border-left: 4px solid #17a2b8;
        }}
        
        .key-terms h2 {{
            margin-top: 0;
        }}
        
        .key-terms p {{
            line-height: 1.8;
        }}
        
        .def-explicit {{
            background-color: #d4edda;
            border-left: 3px solid #28a745;
            padding: 0 0.2rem;
            font-weight: 500;
        }}
        
        .def-implicit {{
            background-color: #d1ecf1;
            border-left: 3px solid #17a2b8;
            padding: 0 0.2rem;
            font-style: italic;
        }}
        
        h1 {{
            font-size: 2rem;
            margin: 2rem 0 1rem 0;
            color: #2c3e50;
        }}
        
        h2 {{
            font-size: 1.5rem;
            margin: 1.5rem 0 1rem 0;
            color: #2c3e50;
        }}
        
        h3 {{
            font-size: 1.2rem;
            margin: 1.2rem 0 0.8rem 0;
            color: #34495e;
        }}
        
        p {{
            margin: 1rem 0;
            text-align: justify;
        }}
        
        mark.bowen-ref {{
            background-color: #fff3cd;
            border-left: 3px solid #ffc107;
            padding: 0 0.2rem;
            cursor: help;
        }}
        
        mark.emphasis {{
            background-color: #d1ecf1;
            border-left: 3px solid #17a2b8;
            padding: 0 0.2rem;
            cursor: help;
        }}
        
        @media (max-width: 768px) {{
            .content {{
                padding: 1.5rem;
            }}
        }}
        
        @media print {{
            body {{
                background: white;
            }}
            
            .container {{
                box-shadow: none;
            }}
            
            mark {{
                background: white !important;
                font-weight: bold;
                border-left: none !important;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>{escape(title)}</h1>
            <div class="meta">
                <strong>{escape(author)}</strong> | {escape(date)}
            </div>
        </header>
        
        <div class="content">
            <div class="legend">
                <strong>Highlights:</strong>
                <span><mark class="bowen-ref">Bowen References</mark></span>
                <span><mark class="emphasis">Emphasized Items</mark></span>
                <span><span class="def-explicit">Explicit Definitions</span></span>
                <span><span class="def-implicit">Implicit Definitions</span></span>
            </div>
            
            {abstract_html}
            
            {key_terms_html}
            
            {formatted_content}
        </div>
    </div>
</body>
</html>'''

    return html


def generate_simple_webpage(base_name: str) -> bool:
    """Generate simple HTML webpage from transcript and extracts-summary materials."""

    formatted_file = FORMATTED_DIR / f"{base_name} - formatted.md"
    extracts_summary_file = SUMMARIES_DIR / f"{base_name} - extracts-summary.md"
    output_file = OUTPUT_DIR / f"{base_name} - simple.html"

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

    # Extract all materials from archival
    abstract = extract_abstract(extracts_summary_file)
    key_terms = extract_key_terms(extracts_summary_file)
    bowen_refs = extract_bowen_references(extracts_summary_file)
    emphasis_items = extract_emphasis_items(extracts_summary_file)
    key_term_defs = extract_key_term_definitions(extracts_summary_file)

    print(f"   Found abstract: {len(abstract) > 0}")
    print(f"   Found {len(key_terms)} key terms")
    print(f"   Found {len(bowen_refs)} Bowen references")
    print(f"   Found {len(emphasis_items)} emphasis items")
    print(f"   Found {len(key_term_defs)} key term definitions")

    print("🖍️  Highlighting transcript...")

    # Apply highlights to raw content first (before HTML conversion)
    highlighted_content = highlight_transcript(
        formatted_content, bowen_refs, emphasis_items, key_term_defs)

    # Convert markdown to HTML
    formatted_html = markdown_to_html(highlighted_content)

    # Remove the "Transcript Formatting" H1 if present
    formatted_html = re.sub(
        r'<h1>Transcript Formatting[^<]*</h1>\s*',
        '',
        formatted_html,
        flags=re.IGNORECASE
    )

    # Remove any stray YAML delimiters or markdown artifacts
    formatted_html = re.sub(r'<p>---</p>\s*', '', formatted_html)
    formatted_html = re.sub(r'<p>```yaml.*?</p>\s*', '',
                            formatted_html, flags=re.DOTALL)
    formatted_html = re.sub(r'<p>```</p>\s*', '', formatted_html)

    # Add title H1 at the start
    parts = base_name.split(' - ')
    title = parts[0] if len(parts) > 0 else base_name
    formatted_html = f'<h1>{escape(title)}</h1>\n\n{formatted_html}'

    print("📝 Generating simple HTML page...")

    # Generate complete HTML page
    html = generate_html_page(base_name, formatted_html, abstract, key_terms)

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save HTML file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"✅ Simple webpage generated successfully!")
    print(f"   File: {output_file}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Generate simple single-column HTML webpage from transcript"
    )
    parser.add_argument(
        "base_name",
        help='Base name without suffix (e.g., "Title - Presenter - Date")'
    )

    args = parser.parse_args()

    try:
        success = generate_simple_webpage(args.base_name)
        return 0 if success else 1

    except (OSError, IOError) as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
