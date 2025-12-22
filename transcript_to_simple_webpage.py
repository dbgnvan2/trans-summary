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
OUTPUT_DIR = TRANSCRIPTS_BASE / "webpages"


def normalize_text(text):
    """Normalize text for comparison - removes filler words and punctuation."""
    # Remove HTML tags that can break matching
    text = re.sub(r'<[^>]+>', ' ', text)

    # Remove speaker tags that can interrupt quotes
    # **Speaker 1:** or **Unknown Speaker:**
    text = re.sub(r'\*\*[^*]+:\*\*\s*', '', text)

    text = text.strip()
    text = text.lower()

    # Remove punctuation for better fuzzy matching
    text = re.sub(r'[.,!?;:—\-\'\"()]', ' ', text)

    # Collapse multiple spaces again after removals
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


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


def load_bowen_references(base_name):
    """Load Bowen reference quotes from dedicated file (falls back to extracts-summary)."""
    # Try dedicated file first
    bowen_file = SUMMARIES_DIR / f"{base_name} - bowen-references.md"
    if bowen_file.exists():
        with open(bowen_file, 'r', encoding='utf-8') as f:
            content = f.read()
        content = strip_yaml_frontmatter(content)
        return extract_bowen_references(content)

    # Fall back to extracts-summary for backward compatibility
    extracts_file = SUMMARIES_DIR / f"{base_name} - extracts-summary.md"
    if extracts_file.exists():
        with open(extracts_file, 'r', encoding='utf-8') as f:
            content = f.read()
        content = strip_yaml_frontmatter(content)
        return extract_bowen_references(content)

    return []


def load_emphasis_items(base_name):
    """Load emphasis item quotes from dedicated file (falls back to extracts-summary)."""
    # Try dedicated file first
    emphasis_file = SUMMARIES_DIR / f"{base_name} - emphasis-items.md"
    if emphasis_file.exists():
        with open(emphasis_file, 'r', encoding='utf-8') as f:
            content = f.read()
        content = strip_yaml_frontmatter(content)
        return extract_emphasis_items(content)

    # Fall back to extracts-summary for backward compatibility
    extracts_file = SUMMARIES_DIR / f"{base_name} - extracts-summary.md"
    if extracts_file.exists():
        with open(extracts_file, 'r', encoding='utf-8') as f:
            content = f.read()
        content = strip_yaml_frontmatter(content)
        return extract_emphasis_items(content)

    return []


def extract_abstract(extracts_summary_file):
    """Extract abstract from extracts-summary."""
    with open(extracts_summary_file, 'r', encoding='utf-8') as f:
        content = f.read()
    content = strip_yaml_frontmatter(content)
    abstract = extract_section(content, 'Abstract')
    # Remove separator lines that might be included
    abstract = re.sub(r'^---\s*$', '', abstract, flags=re.MULTILINE).strip()
    return abstract


def extract_key_terms(extracts_summary_file):
    """Extract key term names (without definitions) from archival document."""
    content = load_definitions_content(extracts_summary_file)
    if content is None:
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
    content = load_definitions_content(extracts_summary_file)
    if content is None:
        with open(extracts_summary_file, 'r', encoding='utf-8') as f:
            content = f.read()

    # Strip YAML
    content = strip_yaml_frontmatter(content)

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


def load_definitions_content(extracts_summary_file):
    """Load key term definitions from a split file when available."""
    extracts_path = Path(extracts_summary_file)
    stem = extracts_path.stem.replace(' - extracts-summary', '')
    summaries_dir = extracts_path.parent

    candidates = [
        summaries_dir / f"{stem} - definitions.md",
        summaries_dir / f"{stem} - key-term-definitions.md",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding='utf-8')

    return None


def highlight_transcript(formatted_html, bowen_refs, emphasis_items, key_term_defs):
    """Add HTML highlighting to transcript for Bowen refs, emphasis, and term definitions."""
    def tokenize_html(html):
        return re.split(r'(<[^>]+>)', html)

    def build_search_text_and_map(tokens):
        search_chars = []
        char_map = []
        for i, tok in enumerate(tokens):
            if tok.startswith('<'):
                continue
            if not tok:
                continue
            prev_tag = tokens[i - 1] if i > 0 else ''
            next_tag = tokens[i + 1] if i + 1 < len(tokens) else ''
            speaker_label = re.fullmatch(
                r'(Speaker \d+|Unknown Speaker):', tok.strip(), flags=re.IGNORECASE)
            if prev_tag.lower() == '<strong>' and next_tag.lower() == '</strong>' and speaker_label:
                continue
            for j, ch in enumerate(tok):
                search_chars.append(ch)
                char_map.append((i, j))
        return ''.join(search_chars), char_map

    def find_word_span(quote, search_text, max_words=40):
        quote_words = re.findall(r"\b[\w']+\b", quote.lower())
        if not quote_words:
            return (None, None)
        text_positions = [m for m in re.finditer(r"\b[\w']+\b", search_text.lower())]
        text_words = [m.group(0) for m in text_positions]
        if not text_words:
            return (None, None)

        anchor_len = min(6, len(quote_words))
        anchor = quote_words[:anchor_len]
        best = (None, 0)
        for i in range(len(text_words) - anchor_len + 1):
            if text_words[i:i + anchor_len] != anchor:
                continue
            match_len = anchor_len
            for j in range(anchor_len, min(len(quote_words), max_words)):
                if i + j >= len(text_words) or quote_words[j] != text_words[i + j]:
                    break
                match_len += 1
            if match_len > best[1]:
                best = (i, match_len)
        if best[0] is None:
            return (None, None)
        start_word = best[0]
        end_word = min(start_word + best[1] - 1, len(text_positions) - 1)
        return (text_positions[start_word].start(), text_positions[end_word].end())

    def map_search_span_to_tokens(char_map, start, end):
        if start is None or end is None or end <= start:
            return None
        if start >= len(char_map):
            return None
        end_index = min(end - 1, len(char_map) - 1)
        start_tok, start_off = char_map[start]
        end_tok, end_off = char_map[end_index]
        return (start_tok, start_off, end_tok, end_off + 1)

    def insert_mark(tokens, span, open_tag, close_tag):
        if not span:
            return
        start_tok, start_off, end_tok, end_off = span
        if start_tok == end_tok:
            text = tokens[start_tok]
            tokens[start_tok] = text[:start_off] + open_tag + text[start_off:end_off] + close_tag + text[end_off:]
            return
        # Insert close tag first
        end_text = tokens[end_tok]
        tokens[end_tok] = end_text[:end_off] + close_tag + end_text[end_off:]
        start_text = tokens[start_tok]
        tokens[start_tok] = start_text[:start_off] + open_tag + start_text[start_off:]

    def add_bowen_label(existing, label):
        if not existing[3]:
            existing[3] = label
            return
        labels = [l.strip() for l in existing[3].split(';') if l.strip()]
        if label not in labels:
            labels.append(label)
            existing[3] = '; '.join(labels)

    def find_quote_start_index(clean_quote, plain_text_stripped):
        """Anchor-first matcher on stripped text."""
        words = re.findall(r"\b[\w']+\b", clean_quote.lower())
        if not words:
            return -1
        anchor_length = min(len(words), 5)
        anchor_words = words[:anchor_length]

        text_words = []
        text_positions = []
        for match in re.finditer(r"\b[\w']+\b", plain_text_stripped.lower()):
            text_words.append(match.group(0))
            text_positions.append((match.start(), match.end()))

        for i in range(len(text_words) - anchor_length + 1):
            if text_words[i:i + anchor_length] == anchor_words:
                return text_positions[i][0]

        return -1

    def find_quote_span(clean_quote, plain_text_stripped, max_words=30):
        words = re.findall(r"\b[\w']+\b", clean_quote.lower())
        if not words:
            return (None, None)
        start_index = find_quote_start_index(clean_quote, plain_text_stripped)
        if start_index == -1:
            from difflib import SequenceMatcher
            matcher = SequenceMatcher(None, plain_text_stripped.lower(), clean_quote.lower())
            match = matcher.find_longest_match(0, len(plain_text_stripped), 0, len(clean_quote))
            if match.size > 10:
                return (match.a, match.a + match.size)
            return (None, None)

        # Expand to a reasonable word window
        text_positions = [m for m in re.finditer(r"\b[\w']+\b", plain_text_stripped.lower())]
        start_word_index = None
        for i, match in enumerate(text_positions):
            if match.start() == start_index:
                start_word_index = i
                break
        if start_word_index is None:
            return (None, None)

        window = min(len(words), max_words)
        end_word_index = min(start_word_index + window - 1, len(text_positions) - 1)
        return (text_positions[start_word_index].start(), text_positions[end_word_index].end())

    tokens = tokenize_html(formatted_html)
    search_text, char_map = build_search_text_and_map(tokens)
    highlights = []
    emphasis_entries = {}

    # Find emphasis items
    for label, quote in emphasis_items:
        quote_words = quote.split()
        quote_snippet = ' '.join(quote_words[:min(75, len(quote_words))])
        start, end = find_word_span(quote_snippet, search_text)
        span = map_search_span_to_tokens(char_map, start, end)
        if span:
            entry = [span, 'emphasis', label, None]
            highlights.append(entry)
            emphasis_entries[label] = entry

    # Find Bowen references
    for concept, quote in bowen_refs:
        quote_words = quote.split()
        first_sentence = re.split(r'[.!?]', quote, 1)[0].strip()
        quote_snippet = first_sentence if first_sentence else ' '.join(
            quote_words[:min(75, len(quote_words))])
        start, end = find_word_span(quote_snippet, search_text)
        if start is None:
            start, end = find_word_span(quote, search_text)
        span = map_search_span_to_tokens(char_map, start, end)
        if span:
            highlights.append([span, 'bowen', concept, None])
            continue

        bowen_norm = normalize_text(quote)
        for emphasis_label, emphasis_quote in emphasis_items:
            if bowen_norm in normalize_text(emphasis_quote):
                entry = emphasis_entries.get(emphasis_label)
                if entry:
                    add_bowen_label(entry, concept)
                break

    # Find key term definitions
    for term in key_term_defs:
        definition = term['definition']
        def_words = definition.split()
        quote_snippet = ' '.join(def_words[:min(30, len(def_words))])
        start, end = find_word_span(quote_snippet, search_text)
        span = map_search_span_to_tokens(char_map, start, end)
        if span:
            htype = 'def-explicit' if 'Explicit' in term['type'] else 'def-implicit'
            highlights.append([span, htype, term['name'], None])

    highlights.sort(key=lambda x: (x[0][0], x[0][1]), reverse=True)

    priority = {
        'emphasis': 3,
        'bowen': 2,
        'def-explicit': 1,
        'def-implicit': 1,
    }

    def span_before(a, b):
        if a[2] < b[0]:
            return True
        if a[2] == b[0] and a[3] <= b[1]:
            return True
        return False

    def spans_overlap(a, b):
        return not (span_before(a, b) or span_before(b, a))

    filtered_highlights = []
    for h in highlights:
        remove_indices = []
        should_skip = False
        for i, existing in enumerate(filtered_highlights):
            if spans_overlap(h[0], existing[0]):
                if {h[1], existing[1]} == {'emphasis', 'bowen'}:
                    if h[1] == 'emphasis':
                        add_bowen_label(h, existing[2])
                        remove_indices.append(i)
                    else:
                        add_bowen_label(existing, h[2])
                        should_skip = True
                        break
                elif priority.get(h[1], 0) > priority.get(existing[1], 0):
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

    result = formatted_html
    for span, htype, label, extra_label in filtered_highlights:
        if htype == 'bowen':
            insert_mark(tokens, span, f'<mark class="bowen-ref" title="Bowen Reference: {escape(label)}">', '</mark>')
        elif htype == 'emphasis':
            bowen_title = f' | Bowen Reference: {escape(extra_label)}' if extra_label else ''
            bowen_class = ' bowen-ref' if extra_label else ''
            insert_mark(tokens, span, f'<mark class="emphasis{bowen_class}" title="Emphasized: {escape(label)}{bowen_title}">', '</mark>')
        elif htype in ['def-explicit', 'def-implicit']:
            def_type = 'Explicit Definition' if htype == 'def-explicit' else 'Implicit Definition'
            insert_mark(tokens, span, f'<span class="{htype}" title="{def_type}: {escape(label)}">', '</span>')

    return ''.join(tokens)


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
            background: #f0f4f8;
            color: #1f2a44;
            padding: 2rem;
            text-align: center;
            border-bottom: 3px solid #d6dee8;
        }}
        
        header h1 {{
            font-size: 2rem;
            margin-bottom: 0.5rem;
        }}
        
        header .meta {{
            font-size: 1rem;
            opacity: 0.9;
            display: flex;
            flex-direction: column;
            gap: 0.2rem;
        }}

        header .meta .author {{
            font-weight: 600;
        }}

        header .meta .date {{
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
                <div class="author">{escape(author)}</div>
                <div class="date">{escape(date)}</div>
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
    extracts_summary_file = SUMMARIES_DIR / \
        f"{base_name} - extracts-summary.md"
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
    bowen_refs = load_bowen_references(base_name)
    emphasis_items = load_emphasis_items(base_name)
    key_term_defs = extract_key_term_definitions(extracts_summary_file)

    print(f"   Found abstract: {len(abstract) > 0}")
    print(f"   Found {len(key_terms)} key terms")
    print(f"   Found {len(bowen_refs)} Bowen references")
    print(f"   Found {len(emphasis_items)} emphasis items")
    print(f"   Found {len(key_term_defs)} key term definitions")

    print("🖍️  Highlighting transcript...")

    # Convert markdown to HTML
    formatted_html = markdown_to_html(formatted_content)

    # Remove the "Transcript Formatting" H1 if present
    formatted_html = re.sub(
        r'<h1>Transcript Formatting[^<]*</h1>\s*',
        '',
        formatted_html,
        flags=re.IGNORECASE
    )

    # Remove any first H1 (title) from the content - it's already in the header
    formatted_html = re.sub(
        r'^<h1>[^<]+</h1>\s*',
        '',
        formatted_html
    )

    # Remove any stray YAML delimiters or markdown artifacts
    formatted_html = re.sub(r'<p>---</p>\s*', '', formatted_html)
    formatted_html = re.sub(r'<p>```yaml.*?</p>\s*', '',
                            formatted_html, flags=re.DOTALL)
    formatted_html = re.sub(r'<p>```</p>\s*', '', formatted_html)

    # Apply highlights on HTML (avoids tag offset issues)
    formatted_html = highlight_transcript(
        formatted_html, bowen_refs, emphasis_items, key_term_defs)

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
