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


# Directories (from environment variable)
TRANSCRIPTS_BASE = Path(
    os.getenv("TRANSCRIPTS_DIR", Path.home() / "transcripts"))
FORMATTED_DIR = TRANSCRIPTS_BASE / "formatted"
SUMMARIES_DIR = TRANSCRIPTS_BASE / "summaries"
OUTPUT_DIR = TRANSCRIPTS_BASE / "webpages"


def normalize_text(text):
    """Normalize text for comparison."""
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


def extract_bowen_references(extracts_summary_file):
    """Extract Bowen reference quotes from extracts-summary document."""
    with open(extracts_summary_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find Bowen References section (with or without bold markers)
    match = re.search(
        r'## (?:\*\*)?Bowen References(?:\*\*)?(.*?)(?=^## |---|\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )
    if not match:
        return []

    bowen_section = match.group(1)

    # Extract quotes: > **Label:** "quote" (Section X)
    quote_pattern = r'>\s*\*\*([^*]+):\*\*\s*"([^"]+)"'
    quotes = re.findall(quote_pattern, bowen_section)

    return [(concept.strip(), quote.strip()) for concept, quote in quotes]


def extract_emphasis_items(extracts_summary_file):
    """Extract emphasis item quotes from extracts-summary document."""
    with open(extracts_summary_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find Emphasized Items section (with or without bold markers)
    match = re.search(
        r'## (?:\*\*)?Emphasized Items(?:\*\*)?(.*?)(?=^## |---|\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )
    if not match:
        return []

    emphasis_section = match.group(1)

    # Extract quotes: number. **Label:** "quote" - **[Type]** (Section X)
    quote_pattern = r'\d+\.\s*\*\*([^*]+):\*\*\s*"([^"]+)"'
    quotes = re.findall(quote_pattern, emphasis_section)

    return [(label.strip(), quote.strip()) for label, quote in quotes]


def extract_metadata(extracts_summary_file):
    """Extract topics, themes, key terms, and abstract from extracts-summary."""
    with open(extracts_summary_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Strip YAML front matter if present (at beginning and any embedded blocks)
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
        'key_terms': '',
        'abstract': ''
    }

    # Extract Topics section (with or without bold markers)
    topics_match = re.search(
        r'## (?:\*\*)?Topics(?:\*\*)?(.*?)(?=^## |\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )
    if topics_match:
        metadata['topics'] = topics_match.group(1).strip()

    # Extract Key Themes section (with or without bold markers)
    themes_match = re.search(
        r'## (?:\*\*)?Key Themes(?:\*\*)?(.*?)(?=^## |\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )
    if themes_match:
        metadata['themes'] = themes_match.group(1).strip()

    # Extract Key Terms (all terms for sidebar)
    # Pattern: ## Term Name (followed by blank line and **Definition Type:**)
    term_headings = re.findall(
        r'^## ([A-Z][^\n#]+?)[\s]*\n+\*\*Definition Type:',
        content,
        re.MULTILINE
    )

    if term_headings:
        metadata['key_terms'] = ', '.join(term_headings)

    # Extract Abstract (with or without bold markers)
    abstract_match = re.search(
        r'## (?:\*\*)?Abstract(?:\*\*)?(.*?)(?=^## |---+|\Z)',
        content,
        re.MULTILINE | re.DOTALL
    )
    if abstract_match:
        metadata['abstract'] = abstract_match.group(1).strip()

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

    # Find Bowen references
    for concept, quote in bowen_refs:
        # Use first 50 words of quote for matching
        quote_words = quote.split()
        search_text = ' '.join(quote_words[:min(50, len(quote_words))])

        start, end, ratio = find_text_in_content(
            search_text, formatted_content)
        if start is not None and ratio >= 0.85:
            highlights.append((start, end, 'bowen', concept))

    # Find emphasis items
    for label, quote in emphasis_items:
        # Use first 50 words of quote for matching
        quote_words = quote.split()
        search_text = ' '.join(quote_words[:min(50, len(quote_words))])

        start, end, ratio = find_text_in_content(
            search_text, formatted_content)
        if start is not None and ratio >= 0.85:
            highlights.append((start, end, 'emphasis', label))

    # Sort by position (reverse order for easier insertion)
    highlights.sort(key=lambda x: x[0], reverse=True)

    # Remove overlaps - keep first (emphasis takes priority over bowen)
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

    # Apply highlights (working backwards to preserve positions)
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
    bowen_refs = extract_bowen_references(extracts_summary_file)
    emphasis_items = extract_emphasis_items(extracts_summary_file)
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
