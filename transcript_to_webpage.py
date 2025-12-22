#!/usr/bin/env python3
"""
Generate single-page HTML webpage from transcript and extracts-summary materials.
Highlights Bowen references and emphasis items inline in the transcript.

Usage:
    python transcript_to_webpage.py "Title - Presenter - Date"
    
Example:
    python transcript_to_webpage.py "Roots of Bowen Theory - Dr Michael Kerr - 2019-11-15"
"""

import argparse
import os
import re
from pathlib import Path
from html import escape
from difflib import SequenceMatcher

from transcript_utils import (
    extract_bowen_references,
    extract_emphasis_items,
    extract_section,
    strip_yaml_frontmatter,
)

# Directories (from environment variable)
TRANSCRIPTS_BASE = Path(
    os.getenv("TRANSCRIPTS_DIR", Path.home() / "transcripts"))
FORMATTED_DIR = TRANSCRIPTS_BASE / "formatted"
SUMMARIES_DIR = TRANSCRIPTS_BASE / "summaries"
OUTPUT_DIR = TRANSCRIPTS_BASE / "webpages"


def normalize_text(text):
    """Normalize text for comparison."""
    # Remove HTML tags that can break matching
    text = re.sub(r'<[^>]+>', ' ', text)

    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text.lower()


def find_text_in_content(needle, haystack, context=50):
    """Find needle in haystack and return (start_pos, end_pos, match_ratio)."""
    needle_normalized = normalize_text(needle)
    haystack_normalized = normalize_text(haystack)

    # Try exact match first
    if needle_normalized in haystack_normalized:
        # Find position in original (non-normalized) text
        # Use first 20 chars to locate in original
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
        # Approximate position in original text
        # This is rough but works for highlighting
        words_before = ' '.join(haystack_words[:best_pos])
        approx_start = len(words_before)
        approx_end = approx_start + \
            len(' '.join(haystack_words[best_pos:best_pos + needle_len]))
        return (approx_start, approx_end, best_ratio)

    return (None, None, 0)


def load_bowen_references(base_name, extracts_summary_file):
    """Load Bowen reference quotes from split file or extracts-summary."""
    bowen_file = SUMMARIES_DIR / f"{base_name} - bowen-references.md"
    source_file = bowen_file if bowen_file.exists() else extracts_summary_file

    with open(source_file, 'r', encoding='utf-8') as f:
        content = f.read()

    content = strip_yaml_frontmatter(content)
    return extract_bowen_references(content)


def load_emphasis_items(base_name, extracts_summary_file):
    """Load emphasis item quotes from split file or extracts-summary."""
    emphasis_file = SUMMARIES_DIR / f"{base_name} - emphasis-items.md"
    source_file = emphasis_file if emphasis_file.exists() else extracts_summary_file

    with open(source_file, 'r', encoding='utf-8') as f:
        content = f.read()

    content = strip_yaml_frontmatter(content)
    return extract_emphasis_items(content)


def extract_metadata(extracts_summary_file):
    """Extract topics, themes, key terms, and abstract from extracts-summary."""
    with open(extracts_summary_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Strip YAML front matter if present (at beginning and any embedded blocks)
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

    metadata['topics'] = extract_section(content, 'Topics')
    metadata['themes'] = extract_section(content, 'Key Themes')

    # Extract Key Terms (all terms for sidebar)
    # Pattern: ## Term Name (followed by blank line and **Definition Type:**)
    term_headings = re.findall(
        r'^## ([A-Z][^\n#]+?)[\s]*\n+\*\*Definition Type:',
        content,
        re.MULTILINE
    )

    if term_headings:
        metadata['key_terms'] = ', '.join(term_headings)

    metadata['abstract'] = extract_section(content, 'Abstract')

    return metadata


def markdown_to_html(text):
    """Convert basic markdown to HTML."""
    # Handle section headings
    text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)

    # Handle bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

    # Handle italic
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)

    # Handle paragraphs
    paragraphs = text.split('\n\n')
    paragraphs = [f'<p>{p.strip()}</p>' if not p.strip().startswith('<') else p.strip()
                  for p in paragraphs if p.strip()]

    return '\n'.join(paragraphs)


def highlight_transcript(formatted_content, bowen_refs, emphasis_items):
    """Add HTML highlighting to transcript for Bowen refs and emphasis."""
    # Create a list of (position, length, type, label) for all highlights
    highlights = []

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

    # Find emphasis items
    for label, quote in emphasis_items:
        # Use first 50 words of quote for matching
        quote_words = quote.split()
        search_text = ' '.join(quote_words[:min(50, len(quote_words))])

        start, end, ratio = find_text_in_content(
            search_text, formatted_content)
        if start is not None and ratio >= 0.85:
            entry = [start, end, 'emphasis', label, None]
            highlights.append(entry)
            emphasis_entries[label] = entry

    # Find Bowen references
    for concept, quote in bowen_refs:
        # Use first 50 words of quote for matching
        quote_words = quote.split()
        first_sentence = re.split(r'[.!?]', quote, 1)[0].strip()
        search_text = first_sentence if first_sentence else ' '.join(
            quote_words[:min(50, len(quote_words))])

        start, end, ratio = find_text_in_lines(
            search_text, formatted_content)
        if start is None:
            start, end, ratio = find_quote_in_lines(
                quote, formatted_content)
        if start is not None and ratio >= 0.85:
            highlights.append([start, end, 'bowen', concept, None])
            continue

        bowen_norm = normalize_text(quote)
        for emphasis_label, emphasis_quote in emphasis_items:
            if bowen_norm in normalize_text(emphasis_quote):
                entry = emphasis_entries.get(emphasis_label)
                if entry:
                    add_bowen_label(entry, concept)
                break

    # Sort by position (reverse order for easier insertion)
    highlights.sort(key=lambda x: x[0], reverse=True)

    priority = {
        'emphasis': 2,
        'bowen': 1,
    }

    def overlaps(a, b):
        return (a[0] >= b[0] and a[0] < b[1]) or \
               (a[1] > b[0] and a[1] <= b[1])

    # Remove overlaps, preferring higher-priority highlights
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

    # Apply highlights (working backwards to preserve positions)
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


def generate_html_page(base_name, formatted_content, metadata):
    """Generate complete HTML page."""

    # Parse title, author, date from base_name
    parts = base_name.split(' - ')
    title = parts[0] if len(parts) > 0 else base_name
    author = parts[1] if len(parts) > 1 else "Unknown"
    date = parts[2] if len(parts) > 2 else "Unknown"

    # Convert markdown metadata to HTML
    topics_html = markdown_to_html(metadata['topics'])
    themes_html = markdown_to_html(metadata['themes'])
    abstract_html = markdown_to_html(metadata['abstract'])

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
            display: flex;
            max-width: 1400px;
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
        
        .sidebar {{
            flex: 0 0 350px;
            padding: 2rem;
            background: #ecf0f1;
            overflow-y: auto;
            max-height: calc(100vh - 200px);
            position: sticky;
            top: 0;
        }}
        
        .sidebar h2 {{
            font-size: 1.2rem;
            margin: 1.5rem 0 0.5rem 0;
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 0.3rem;
        }}
        
        .sidebar h2:first-child {{
            margin-top: 0;
        }}
        
        .sidebar p {{
            margin: 0.5rem 0;
            font-size: 0.9rem;
        }}
        
        .main-content {{
            flex: 1;
            padding: 2rem;
            overflow-y: auto;
        }}
        
        .transcript {{
            max-width: 800px;
            margin: 0 auto;
        }}
        
        .transcript h2 {{
            font-size: 1.5rem;
            margin: 2rem 0 1rem 0;
            color: #2c3e50;
        }}
        
        .transcript h3 {{
            font-size: 1.2rem;
            margin: 1.5rem 0 0.8rem 0;
            color: #34495e;
        }}
        
        .transcript p {{
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
        
        .legend {{
            margin: 1rem 0;
            padding: 1rem;
            background: #f8f9fa;
            border-radius: 5px;
            font-size: 0.9rem;
        }}
        
        .legend span {{
            display: inline-block;
            margin-right: 1.5rem;
        }}
        
        @media (max-width: 968px) {{
            .container {{
                flex-direction: column;
            }}
            
            .sidebar {{
                flex: none;
                max-height: none;
                position: relative;
            }}
        }}
        
        @media print {{
            .sidebar {{
                display: none;
            }}
            
            mark {{
                background: white !important;
                font-weight: bold;
            }}
        }}
    </style>
</head>
<body>
    <header>
        <h1>{escape(title)}</h1>
        <div class="meta">
            <strong>{escape(author)}</strong> | {escape(date)}
        </div>
    </header>
    
    <div class="container">
        <aside class="sidebar">
            <h2>Abstract</h2>
            {abstract_html}
            
            <h2>Topics</h2>
            {topics_html}
            
            <h2>Key Themes</h2>
            {themes_html}
            
            <h2>Key Terms</h2>
            <p>{escape(metadata['key_terms'])}</p>
        </aside>
        
        <main class="main-content">
            <div class="legend">
                <strong>Highlights:</strong>
                <span><mark class="bowen-ref">Bowen References</mark></span>
                <span><mark class="emphasis">Emphasized Items</mark></span>
            </div>
            
            <div class="transcript">
                {formatted_content}
            </div>
        </main>
    </div>
</body>
</html>'''

    return html


def generate_webpage(base_name: str) -> bool:
    """Generate HTML webpage from transcript and extracts-summary materials."""

    # File paths
    formatted_file = FORMATTED_DIR / f"{base_name} - formatted.md"
    extracts_summary_file = SUMMARIES_DIR / f"{base_name} - extracts-summary.md"
    output_file = OUTPUT_DIR / f"{base_name}.html"

    # Check files exist
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

    # Extract Bowen references and emphasis items
    bowen_refs = load_bowen_references(base_name, extracts_summary_file)
    emphasis_items = load_emphasis_items(base_name, extracts_summary_file)
    metadata = extract_metadata(extracts_summary_file)

    print(f"   Found {len(bowen_refs)} Bowen references")
    print(f"   Found {len(emphasis_items)} emphasis items")

    print("🖍️  Highlighting transcript...")

    # Apply highlights to markdown BEFORE converting to HTML
    # This ensures character positions remain accurate
    highlighted_markdown = highlight_transcript(
        formatted_content, bowen_refs, emphasis_items)

    # Convert highlighted markdown to HTML
    formatted_html = markdown_to_html(highlighted_markdown)

    # Remove the "Transcript Formatting" H1 if present and add proper title
    formatted_html = re.sub(
        r'<h1>Transcript Formatting[^<]*</h1>\s*',
        '',
        formatted_html,
        flags=re.IGNORECASE
    )

    # Add title H1 at the start
    parts = base_name.split(' - ')
    title = parts[0] if len(parts) > 0 else base_name
    formatted_html = f'<h1>{escape(title)}</h1>\n\n{formatted_html}'

    print("📝 Generating HTML page...")

    # Generate complete HTML page
    html = generate_html_page(base_name, formatted_html, metadata)

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save HTML file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"✅ Webpage generated successfully!")
    print(f"   File: {output_file}")
    print(f"   Open in browser to view")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Generate single-page HTML webpage from transcript and extracts-summary"
    )
    parser.add_argument(
        "base_name",
        help='Base name without suffix (e.g., "Title - Presenter - Date")'
    )

    args = parser.parse_args()

    try:
        success = generate_webpage(args.base_name)
        return 0 if success else 1

    except (OSError, IOError) as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
