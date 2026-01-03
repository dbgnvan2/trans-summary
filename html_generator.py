"""
HTML generation logic for the transcript processing application.
This module handles the creation of webpages and PDF-ready HTML.
"""

import re
from difflib import SequenceMatcher
from html import escape, unescape
from pathlib import Path

import config
from transcript_utils import (
    extract_section,
    load_bowen_references,
    load_emphasis_items,
    markdown_to_html,
    normalize_text,
    parse_filename_metadata,
    setup_logging,
    strip_yaml_frontmatter,
    validate_input_file,
)

# ============================================================================ 
# WEBPAGE GENERATION
# ============================================================================ 


def _extract_webpage_metadata(topics_themes_file):
    """Extract topics, themes, key terms, and abstract from topics-themes."""
    with open(topics_themes_file, "r", encoding="utf-8") as f:
        content = f.read()

    content = strip_yaml_frontmatter(content)
    content = re.sub(
        r"---\s*#\s*TERMINOLOGY EXTRACTION OUTPUT.*?---\s*#\s*Key Terms",
        "# Key Terms",
        content,
        flags=re.DOTALL,
    )

    # Get key terms with definitions
    key_term_defs = _extract_key_term_definitions(topics_themes_file)

    metadata = {
        "topics": extract_section(content, "Topics"),
        "themes": extract_section(content, "Key Themes"),
        "abstract": extract_section(content, "Abstract"),
        "key_terms": key_term_defs,
    }
    return metadata


def _load_abstract(base_name):
    """Load abstract from generated file, falling back to All Key Items."""
    gen_file = (
        config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_ABSTRACT_GEN}"
    )
    if gen_file.exists():
        return gen_file.read_text(encoding="utf-8")

    # Fallback: Extract from All Key Items
    topics_themes_file = (
        config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"
    )
    if topics_themes_file.exists():
        content = topics_themes_file.read_text(encoding="utf-8")
        content = strip_yaml_frontmatter(content)
        return extract_section(content, "Abstract")
    return ""


def _load_summary(base_name):
    """Load summary from generated or initial file."""
    gen_file = (
        config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_SUMMARY_GEN}"
    )
    if gen_file.exists():
        content = gen_file.read_text(encoding="utf-8")
        content = strip_yaml_frontmatter(content)
        # Remove "Summary" header if present
        content = re.sub(r"^#+\s*Summary\s*", "", content, flags=re.IGNORECASE).strip()
        # Stop at next section header (Topics, etc.) to prevent inclusion of other sections
        content = re.split(r"^##\s+", content, flags=re.MULTILINE)[0].strip()
        return content

    # Fallback: Extract from All Key Items
    topics_themes_file = (
        config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"
    )
    if topics_themes_file.exists():
        content = topics_themes_file.read_text(encoding="utf-8")
        content = strip_yaml_frontmatter(content)
        return extract_section(content, "Summary")

    return ""


def _generate_html_page(
    base_name, formatted_content, metadata, summary, bowen_refs, emphasis_items
):
    """Generate complete HTML page with sidebar."""
    meta = parse_filename_metadata(base_name)
    topics_html = markdown_to_html(metadata["topics"])
    themes_html = markdown_to_html(metadata["themes"])
    abstract_html = markdown_to_html(metadata["abstract"])
    summary_html = markdown_to_html(summary)

    key_terms_html = ""
    if isinstance(metadata.get("key_terms"), list):
        key_terms_html += "<dl>"
        for term in metadata["key_terms"]:
            name = term.get("name", "Unknown Term")
            definition = term.get("definition", "No definition provided.")
            key_terms_html += f"<dt><strong>{escape(name)}</strong></dt>"
            key_terms_html += f"<dd>{markdown_to_html(definition)}</dd>"
        key_terms_html += "</dl>"
    elif metadata.get("key_terms"):
        key_terms_html = f"<p>{escape(str(metadata['key_terms']))}</p>"

    def format_ref_list(items):
        if not items:
            return "<p>None found.</p>"
        html_list = "<ul class='ref-list'>"
        for label, quote in items:
            html_list += f"<li><strong>{escape(label)}</strong>: {escape(quote)}</li>"
        html_list += "</ul>"
        return html_list

    bowen_html = format_ref_list(bowen_refs)
    emphasis_html = format_ref_list(emphasis_items)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(meta["title"]) } </title>
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

        .sidebar dl {{
            font-size: 0.9rem;
        }}

        .sidebar dt {{
            font-weight: bold;
            color: #34495e;
            margin-top: 0.8rem;
        }}

        .sidebar dd {{
            margin-left: 1rem;
        }}

        .sidebar p {{
            margin: 0.5rem 0;
            font-size: 0.9rem;
        }}

        .sidebar .ref-list {{
            list-style-type: none;
            padding-left: 0;
        }}

        .sidebar .ref-list li {{
            margin-bottom: 0.8rem;
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

        mark.emphasis.score-90 {{
            background-color: #bee5eb;
            border-left-color: #138496;
        }}

        mark.emphasis.score-95 {{
            background-color: #a6d9f3;
            border-left-color: #0c5460;
            font-weight: 500;
        }}

        mark.emphasis.bowen-ref {{
            background-color: #fff3cd;
            border-left-color: #ffc107;
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
        <h1>{escape(meta["title"])}</h1>
        <div class="meta">
            <strong>{escape(meta["author"])}</strong> | {escape(meta["date"])}
        </div>
    </header>

    <div class="container">
        <aside class="sidebar">
            <h2>Abstract</h2>
            {abstract_html}

            <h2>Summary</h2>
            {summary_html}

            <h2>Key Topics</h2>
            {topics_html}

            <h2>Key Themes</h2>
            {themes_html}

            <h2>Key Terms</h2>
            {key_terms_html}

            <h2>Bowen References</h2>
            {bowen_html}

            <h2>Emphasized Items</h2>
            {emphasis_html}
        </aside>

        <main class="main-content">
            <div class="legend">
                <strong>Highlights:</strong>
                <span><mark class="bowen-ref">Bowen References</mark></span>
                <span><mark class="emphasis">Emphasis (<90%)</mark></span>
                <span><mark class="emphasis score-90">High Emphasis (90-94%)</mark></span>
                <span><mark class="emphasis score-95">Top Emphasis (95%+)</mark></span>
            </div>

            <div class="transcript">
                {formatted_content}
            </div>
        </main>
    </div>
</body>
</html>"""

    return html


def generate_webpage(base_name: str) -> bool:
    """Orchestrates the generation of the main webpage with a sidebar."""
    logger = setup_logging("generate_webpage")
    try:
        formatted_file = (
            config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_FORMATTED}"
        )
        topics_themes_file = (
            config.PROJECTS_DIR
            / base_name
            / f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"
        )
        output_file = (
            config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_WEBPAGE}"
        )

        validate_input_file(formatted_file)
        validate_input_file(topics_themes_file)

        formatted_content = formatted_file.read_text(encoding="utf-8")
        formatted_content = strip_yaml_frontmatter(formatted_content)

        logger.info("Loading topics-themes materials...")
        bowen_refs = load_bowen_references(base_name)
        emphasis_items = load_emphasis_items(base_name)
        summary = _load_summary(base_name)
        metadata = _extract_webpage_metadata(topics_themes_file)
        # Override abstract with the best available version
        metadata["abstract"] = _load_abstract(base_name)
        logger.info(
            f"Found {len(bowen_refs)} Bowen references and {len(emphasis_items)} emphasis items."
        )

        logger.info("Highlighting transcript...")
        formatted_html = markdown_to_html(formatted_content)
        # Clean up unwanted headers before highlighting to ensure consistency with simple_webpage
        formatted_html = re.sub(
            r"<h1>Transcript Formatting[^<]*</h1>\s*",
            "",
            formatted_html,
            flags=re.IGNORECASE,
        )
        formatted_html = re.sub(r"^<h1>[^<]+</h1>\s*", "", formatted_html)
        formatted_html = _highlight_html_content(
            formatted_html, bowen_refs, emphasis_items
        )

        meta = parse_filename_metadata(base_name)
        formatted_html = f"<h1>{escape(meta['title'])}</h1>\n\n{formatted_html}"

        logger.info("Generating HTML page...")
        html = _generate_html_page(
            base_name, formatted_html, metadata, summary, bowen_refs, emphasis_items
        )

        output_file.write_text(html, encoding="utf-8")

        logger.info(f"✓ Webpage generated successfully: {output_file}")
        return True

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return False


# ============================================================================ 
# SIMPLE WEBPAGE GENERATION
# ============================================================================ 


def _extract_abstract(topics_themes_file):
    """Extract abstract from topics-themes."""
    with open(topics_themes_file, "r", encoding="utf-8") as f:
        content = f.read()
    content = strip_yaml_frontmatter(content)
    abstract = extract_section(content, "Abstract")
    return re.sub(r"^---\s*$", "", abstract, flags=re.MULTILINE).strip()


def _load_definitions_content(topics_themes_file):
    """Load key term definitions from a split file when available."""
    extracts_path = Path(topics_themes_file)
    stem = extracts_path.stem.replace(
        config.SUFFIX_KEY_ITEMS_RAW_LEGACY.replace(".md", ""), ""
    )
    summaries_dir = extracts_path.parent
    candidates = [
        summaries_dir / f"{stem}{config.SUFFIX_KEY_TERMS}",
        summaries_dir / f"{stem} - definitions.md",
        summaries_dir / f"{stem} - key-term-definitions.md",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return None


def _extract_key_terms(topics_themes_file):
    """Extract key term names (without definitions) from archival document."""
    content = _load_definitions_content(topics_themes_file)
    if content is None:
        with open(topics_themes_file, "r", encoding="utf-8") as f:
            content = f.read()

    content = strip_yaml_frontmatter(content)
    content = re.sub(
        r"---\s*#\s*TERMINOLOGY EXTRACTION OUTPUT.*?---\s*#\s*Key Terms",
        "# Key Terms",
        content,
        flags=re.DOTALL,
    )
    term_headings = re.findall(r"^###\s+(.+)$", content, re.MULTILINE)

    return [term.strip() for term in term_headings]


def _extract_key_term_definitions(topics_themes_file):
    """Extract key terms with their definitions and types from archival."""
    content = _load_definitions_content(topics_themes_file)
    if content is None:
        with open(topics_themes_file, "r", encoding="utf-8") as f:
            content = f.read()

    content = strip_yaml_frontmatter(content)

    # Normalize Key Terms header to ## for extraction if it appears as #
    if re.search(r"^# Key Terms", content, re.MULTILINE):
        content = re.sub(r"^# Key Terms", "## Key Terms", content, flags=re.MULTILINE)

    # Extract ONLY the Key Terms section to avoid picking up Topics/Themes
    key_terms_section = extract_section(content, "Key Terms")
    if not key_terms_section:
        # Fallback for alternative header
        key_terms_section = extract_section(content, "Part 2: Key Term Definitions")

    term_pattern = r"###\s+(.+?)\n(.*?)(?=\n###|\Z)"
    matches = re.findall(term_pattern, key_terms_section, re.DOTALL | re.MULTILINE)

    results = []
    for name, raw_def in matches:
        name = name.strip()
        raw_def = raw_def.strip()

        def_type = "def-explicit"
        clean_def = raw_def

        # Check for definition type
        type_match = re.search(
            r"\*\*Definition Type:\*\*\s*(Explicit|Implicit)", raw_def, re.IGNORECASE
        )
        if type_match:
            dtype = type_match.group(1).lower()
            def_type = f"def-{dtype}"
            # Remove the type line to get clean text for searching
            clean_def = re.sub(
                r"\*\*Definition Type:\*\*\s*(Explicit|Implicit)\s*\n?",
                "",
                raw_def,
                flags=re.IGNORECASE,
            ).strip()

        results.append({"name": name, "definition": clean_def, "type": def_type})

    return results


def _highlight_html_content(formatted_html, bowen_refs, emphasis_items):
    """Add HTML highlighting to HTML content for Bowen refs, emphasis, and term definitions."""

    def tokenize_html(html):
        return re.split(r"(<[^>]+>)", html)

    # Pre-process tokens to unescape HTML entities in text nodes
    # This ensures "It&apos;s" in HTML matches "It's" in the quote

    def build_search_text_and_map(tokens):
        search_chars = []
        char_map = []  # List of (token_index, start_idx, end_idx)

        in_strong = False

        for i, tok in enumerate(tokens):
            # Track strong tags for speaker detection
            if tok.lower() in ("<strong>", "<b>"):
                in_strong = True
                search_chars.append(" ")
                char_map.append(None)
                continue

            if tok.lower() in ("</strong>", "</b>"):
                in_strong = False
                search_chars.append(" ")
                char_map.append(None)
                continue

            if tok.startswith("<") or not tok.strip():
                search_chars.append(" ")
                char_map.append(None)
                continue

            # Detect and skip Speaker Labels
            if in_strong:
                # Case 1: Colon inside (e.g. "Speaker:")
                if re.fullmatch(r"[\w\s\.\(\)]+:", tok.strip(), flags=re.IGNORECASE):
                    search_chars.append(" ")
                    char_map.append(None)
                    continue

                # Case 2: Colon outside (e.g. "Speaker" followed by "</strong>" and ":")
                if i + 2 < len(tokens):
                    next_tag = tokens[i + 1].lower()
                    next_text = tokens[i + 2]
                    if next_tag in (
                        "</strong>",
                        "</b>",
                    ) and next_text.strip().startswith(":"):
                        search_chars.append(" ")
                        char_map.append(None)
                        continue

            # Process text token character by character, handling entities
            j = 0
            while j < len(tok):
                if tok[j] == "&":
                    end_entity = tok.find(";", j, j + 10)
                    if end_entity != -1:
                        entity = tok[j : end_entity + 1]
                        decoded = unescape(entity)
                        for char in decoded:
                            search_chars.append(char)
                            char_map.append((i, j, end_entity + 1))
                        j = end_entity + 1
                        continue

                search_chars.append(tok[j])
                char_map.append((i, j, j + 1))
                j += 1

        return "".join(search_chars), char_map

    def find_word_span(quote, search_text, max_words=40):
        """Finds the best character span for a quote using density-based clustering of matching blocks."""
        quote_norm = normalize_text(quote, aggressive=True)
        quote_words = [w for w in quote_norm.split() if w]
        if not quote_words:
            return (None, None)

        # Optimization: Try to find the exact sequence of words first
        # This is much faster and more reliable for exact matches
        n_quote = len(quote_words)
        text_positions = [m for m in re.finditer(r"\b\w+\b", search_text)]
        text_words = [m.group(0) for m in text_positions]
        text_words_norm = [normalize_text(w, aggressive=True) for w in text_words]

        for i in range(len(text_words_norm) - n_quote + 1):
            if text_words_norm[i : i + n_quote] == quote_words:
                start_char = text_positions[i].start()
                end_char = text_positions[i + n_quote - 1].end()
                return (start_char, end_char)

        text_positions = [m for m in re.finditer(r"\b\w+\b", search_text)]
        text_words = [m.group(0) for m in text_positions]
        text_words_norm = [normalize_text(w, aggressive=True) for w in text_words]

        matcher = SequenceMatcher(None, text_words_norm, quote_words, autojunk=False)

        # Get all matching blocks (sequences of matching words)
        matching_blocks = [b for b in matcher.get_matching_blocks() if b.size > 0]
        if not matching_blocks:
            return (None, None)

        # Sliding window algorithm to find the densest cluster of matching blocks
        # This handles cases where the "largest block" is a common word in the wrong place
        best_cluster = []
        best_score = 0

        # Allow a window in the text up to 3x the quote length to account for gaps/speaker tags
        window_limit = len(quote_words) * 3

        current_score = 0
        left = 0

        for right in range(len(matching_blocks)):
            current_score += matching_blocks[right].size

            # Shrink window from the left if it exceeds the limit in text coordinates
            # matching_blocks[right].a is the start index in text_words
            while (
                left < right
                and (matching_blocks[right].a - matching_blocks[left].a) > window_limit
            ):
                current_score -= matching_blocks[left].size
                left += 1

            if current_score > best_score:
                best_score = current_score
                best_cluster = matching_blocks[left : right + 1]

        # Calculate match ratio based on the best cluster found
        match_ratio = best_score / len(quote_words) if quote_words else 0

        # Threshold: 70% of words must match (allows for some hallucination/correction in summary)
        if match_ratio >= 0.7:
            first_block = best_cluster[0]
            last_block = best_cluster[-1]

            start_char_idx = first_block.a
            end_char_idx = last_block.a + last_block.size - 1

            if start_char_idx < len(text_positions) and end_char_idx < len(
                text_positions
            ):
                start_char = text_positions[start_char_idx].start()
                end_char = text_positions[end_char_idx].end()
                return (start_char, end_char)

        return (None, None)

    def map_search_span_to_tokens(char_map, start, end):
        if start is None or end is None or end <= start:
            return None
        if start >= len(char_map):
            return None

        # Adjust start to skip non-content
        while start < end and (start >= len(char_map) or char_map[start] is None):
            start += 1

        # Adjust end to skip non-content
        while end > start and (end - 1 >= len(char_map) or char_map[end - 1] is None):
            end -= 1

        if start >= end:
            return None

        end_index = end - 1
        start_tok, start_off, _ = char_map[start]
        end_tok, _, end_off = char_map[end_index]
        return (start_tok, start_off, end_tok, end_off)

    def insert_mark(tokens, span, open_tag, close_tag):
        if not span:
            return
        start_tok, start_off, end_tok, end_off = span
        if start_tok == end_tok:
            text = tokens[start_tok]
            tokens[start_tok] = (
                text[:start_off]
                + open_tag
                + text[start_off:end_off]
                + close_tag
                + text[end_off:]
            )
            return
        end_text = tokens[end_tok]
        tokens[end_tok] = end_text[:end_off] + close_tag + end_text[end_off:]
        start_text = tokens[start_tok]
        tokens[start_tok] = start_text[:start_off] + open_tag + start_text[start_off:]

    def add_bowen_label(existing, label):
        if not existing[3]:
            existing[3] = label
            return
        lbls = [lbl.strip() for lbl in existing[3].split(";") if lbl.strip()]
        if label not in lbls:
            lbls.append(label)
            existing[3] = "; ".join(lbls)

    tokens = tokenize_html(formatted_html)
    search_text, char_map = build_search_text_and_map(tokens)
    highlights = []
    emphasis_entries = {}

    for label, quote in emphasis_items:
        quote_snippet = " ".join(quote.split()[:75])
        start, end = find_word_span(quote_snippet, search_text)
        span = map_search_span_to_tokens(char_map, start, end)
        if span:
            entry = [span, "emphasis", label, None]
            highlights.append(entry)
            emphasis_entries[label] = entry

    for concept, quote in bowen_refs:
        quote_snippet = " ".join(quote.split()[:75])
        start, end = find_word_span(quote_snippet, search_text)
        if start is None:
            start, end = find_word_span(quote, search_text)
        span = map_search_span_to_tokens(char_map, start, end)
        if span:
            highlights.append([span, "bowen", concept, None])
            continue
        bowen_norm = normalize_text(quote, aggressive=True)
        for emphasis_label, emphasis_quote in emphasis_items:
            if bowen_norm in normalize_text(emphasis_quote, aggressive=True):
                entry = emphasis_entries.get(emphasis_label)
                if entry:
                    add_bowen_label(entry, concept)
                break

    highlights.sort(key=lambda x: (x[0][0], x[0][1]), reverse=True)

    priority = {"emphasis": 3, "bowen": 2}

    def spans_overlap(a, b):
        return not (
            a[2] < b[0]
            or a[0] > b[2]
            or (a[2] == b[0] and a[3] <= b[1])
            or (b[2] == a[0] and b[3] <= a[1])
        )

    filtered_highlights = []
    for h in highlights:
        should_skip = False
        remove_indices = []
        for i, existing in enumerate(filtered_highlights):
            if spans_overlap(h[0], existing[0]):
                if {h[1], existing[1]} == {"emphasis", "bowen"}:
                    if h[1] == "emphasis":
                        add_bowen_label(h, existing[2])
                        remove_indices.append(i)
                    else:
                        add_bowen_label(existing, h[2])
                        should_skip = True
                elif priority.get(h[1], 0) > priority.get(existing[1], 0):
                    remove_indices.append(i)
                else:
                    should_skip = True
                if should_skip:
                    break
        if should_skip:
            continue
        for i in reversed(remove_indices):
            filtered_highlights.pop(i)
        filtered_highlights.append(h)

    for span, htype, label, extra_label in filtered_highlights:
        if htype == "bowen":
            insert_mark(
                tokens,
                span,
                f'<mark class="bowen-ref" title="Bowen Reference: {escape(label)}">',
                "</mark>",
            )
        elif htype == "emphasis":
            score_class = ""
            # Check for score in label: "Concept (95%)"
            score_match = re.search(r"\((\d+)%\)$", label)
            if score_match:
                score = int(score_match.group(1))
                if score >= 95:
                    score_class = " score-95"
                elif score >= 90:
                    score_class = " score-90"

            bowen_title = (
                f" | Bowen Reference: {escape(extra_label)}" if extra_label else ""
            )
            bowen_class = " bowen-ref" if extra_label else ""
            insert_mark(
                tokens,
                span,
                f'<mark class="emphasis{score_class}{bowen_class}" title="Emphasized: {escape(label)}{bowen_title}">',
                "</mark>",
            )

    return "".join(tokens)


def _generate_simple_html_page(
    base_name, formatted_content, metadata, summary, bowen_refs, emphasis_items
):
    """Generate simple HTML page without sidebar."""
    meta = parse_filename_metadata(base_name)

    abstract_html = markdown_to_html(metadata["abstract"])
    summary_html = markdown_to_html(summary)
    topics_html = markdown_to_html(metadata["topics"])
    themes_html = markdown_to_html(metadata["themes"])

    key_terms_html = ""
    if isinstance(metadata.get("key_terms"), list):
        key_terms_html += "<dl>"
        for term in metadata["key_terms"]:
            name = term.get("name", "Unknown Term")
            definition = term.get("definition", "No definition provided.")
            key_terms_html += f"<dt><strong>{escape(name)}</strong></dt>"
            key_terms_html += f"<dd>{markdown_to_html(definition)}</dd>"
        key_terms_html += "</dl>"
    elif metadata.get("key_terms"):
        key_terms_html = f"<p>{escape(str(metadata['key_terms']))}</p>"

    def format_ref_list(items):
        if not items:
            return "<p>None found.</p>"
        html_list = "<ul class='ref-list'>"
        for label, quote in items:
            html_list += f"<li><strong>{escape(label)}</strong>: {escape(quote)}</li>"
        html_list += "</ul>"
        return html_list

    bowen_html = format_ref_list(bowen_refs)
    emphasis_html = format_ref_list(emphasis_items)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(meta["title"])}</title>
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

        .ref-list {{
            list-style-type: none;
            padding-left: 0;
        }}

        .ref-list li {{
            margin-bottom: 0.8rem;
        }}

        .summary-section {{
            margin: 2rem 0;
            padding: 1.5rem;
            background: #f8f9fa;
            border-left: 4px solid #2c3e50;
        }}

        .summary-section h2 {{
            margin-top: 0;
        }}

        .appendices {{
            margin: 2rem 0;
            padding: 1.5rem;
            background: #f0f7ff;
            border-left: 4px solid #17a2b8;
            border-top: 1px solid #ddd;
        }}

        .appendices h2 {{
            margin-top: 1.5rem;
            border-bottom: 2px solid #3498db;
            padding-bottom: 0.3rem;
        }}

        .appendices p, .appendices li {{
            line-height: 1.8;
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

        mark.emphasis.score-90 {{
            background-color: #bee5eb;
            border-left-color: #138496;
        }}

        mark.emphasis.score-95 {{
            background-color: #a6d9f3;
            border-left-color: #0c5460;
            font-weight: 500;
        }}

        mark.emphasis.bowen-ref {{
            background-color: #fff3cd;
            border-left-color: #ffc107;
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
            <h1>{escape(meta["title"])}</h1>
            <div class="meta">
                <div class="author">{escape(meta["author"])}</div>
                <div class="date">{escape(meta["date"])}</div>
            </div>
        </header>

        <div class="content">
            <div class="legend">
                <strong>Highlights:</strong>
                <span><mark class="bowen-ref">Bowen References</mark></span>
                <span><mark class="emphasis">Emphasis (<90%)</mark></span>
                <span><mark class="emphasis score-90">High Emphasis (90-94%)</mark></span>
                <span><mark class="emphasis score-95">Top Emphasis (95%+)</mark></span>
            </div>

            <div class="summary-section">
                <h2>Abstract</h2>{abstract_html}
                <h2>Summary</h2>{summary_html}
            </div>

            {formatted_content}
        </div>

        <div class="content appendices">
            <h1>Appendices</h1>
            
            <h2>Key Topics</h2>
            {topics_html}

            <h2>Key Themes</h2>
            {themes_html}

            <h2>Key Terms</h2>
            {key_terms_html}

            <h2>Bowen References</h2>
            {bowen_html}

            <h2>Emphasized Items</h2>
            {emphasis_html}
        </div>
    </div>
</body>
</html>"""
    return html


def generate_simple_webpage(base_name: str) -> bool:
    """Orchestrates the generation of the simple, single-column webpage."""
    logger = setup_logging("generate_simple_webpage")
    try:
        formatted_file = (
            config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_FORMATTED}"
        )
        topics_themes_file = (
            config.PROJECTS_DIR
            / base_name
            / f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"
        )
        output_file = (
            config.PROJECTS_DIR
            / base_name
            / f"{base_name}{config.SUFFIX_WEBPAGE_SIMPLE}"
        )

        validate_input_file(formatted_file)
        validate_input_file(topics_themes_file)

        formatted_content = formatted_file.read_text(encoding="utf-8")
        formatted_content = strip_yaml_frontmatter(formatted_content)

        logger.info("Loading topics-themes materials for simple webpage...")
        metadata = _extract_webpage_metadata(topics_themes_file)
        summary = _load_summary(base_name)
        # Override abstract with the best available version
        metadata["abstract"] = _load_abstract(base_name)
        bowen_refs = load_bowen_references(base_name)
        emphasis_items = load_emphasis_items(base_name)

        logger.info("Highlighting transcript for simple webpage...")
        formatted_html = markdown_to_html(formatted_content)
        # Clean up HTML before highlighting
        formatted_html = re.sub(
            r"<h1>Transcript Formatting[^<]*</h1>\s*",
            "",
            formatted_html,
            flags=re.IGNORECASE,
        )
        formatted_html = re.sub(r"^<h1>[^<]+</h1>\s*", "", formatted_html)

        highlighted_html = _highlight_html_content(
            formatted_html, bowen_refs, emphasis_items
        )

        logger.info("Generating simple HTML page...")
        html = _generate_simple_html_page(
            base_name, highlighted_html, metadata, summary, bowen_refs, emphasis_items
        )

        output_file.write_text(html, encoding="utf-8")

        logger.info(f"✓ Simple webpage generated successfully: {output_file}")
        return True

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return False


# ============================================================================ 
# PDF GENERATION
# ============================================================================ 


def _sort_key_term_sections(content: str) -> str:
    """Sort key term sections alphabetically by heading."""
    sections = []
    current = None
    for line in content.splitlines():
        if line.startswith("## "):
            if current:
                sections.append(current)
            current = {"title": line[3:].strip(), "lines": [line]}
        else:
            if current is None:
                continue
            current["lines"].append(line)
    if current:
        sections.append(current)

    if not sections:
        return content

    sections.sort(key=lambda s: s["title"].lower())
    return "\n".join("\n".join(section["lines"]) for section in sections).strip()


def _extract_pdf_metadata(topics_themes_file):
    """Extract metadata for PDF generation."""
    with open(topics_themes_file, "r", encoding="utf-8") as f:
        content = f.read()
    content = strip_yaml_frontmatter(content)
    content = re.sub(
        r"---\s*#\s*TERMINOLOGY EXTRACTION OUTPUT.*?---\s*#\s*Key Terms",
        "# Key Terms",
        content,
        flags=re.DOTALL,
    )

    metadata = {
        "topics": extract_section(content, "Topics"),
        "themes": extract_section(content, "Key Themes"),
        "abstract": extract_section(content, "Abstract"),
        "key_terms": extract_section(content, "Key Terms"),
    }

    definitions_content = _load_definitions_content(topics_themes_file)
    if definitions_content:
        definitions_content = strip_yaml_frontmatter(definitions_content)
        definitions_content = re.sub(
            r"```yaml.*?```", "", definitions_content, flags=re.DOTALL | re.IGNORECASE
        )
        definitions_content = re.sub(
            r"^## (Part 2: Key Term Definitions|Key Terms)\s*",
            "",
            definitions_content,
            flags=re.MULTILINE,
        ).strip()
        if definitions_content:
            metadata["key_terms"] = _sort_key_term_sections(definitions_content)

    return metadata


def _generate_html_for_pdf(
    base_name, formatted_content, metadata, summary, bowen_refs, emphasis_items
):
    """Generate complete HTML for PDF conversion."""
    meta = parse_filename_metadata(base_name)
    topics_html = markdown_to_html(metadata["topics"])
    themes_html = markdown_to_html(metadata["themes"])
    abstract_html = markdown_to_html(metadata["abstract"])
    key_terms_html = markdown_to_html(metadata["key_terms"])

    summary_html = markdown_to_html(summary)

    def format_ref_list(items):
        if not items:
            return "<p>None found.</p>"
        html_list = "<ul class='ref-list'>"
        for label, quote in items:
            html_list += f"<li><strong>{escape(label)}</strong>: {escape(quote)}</li>"
        html_list += "</ul>"
        return html_list

    bowen_html = format_ref_list(bowen_refs)
    emphasis_html = format_ref_list(emphasis_items)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{escape(meta["title"])}</title>
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

        mark.emphasis.score-90 {{
            background-color: #bee5eb;
        }}

        mark.emphasis.score-95 {{
            background-color: #a6d9f3;
            font-weight: bold;
        }}

        mark.emphasis.bowen-ref {{
            background-color: #fff3cd;
        }}

        .legend {{
            margin: 18pt 0;
            padding: 12pt;
            background: #f8f9fa;
            border-left: 4px solid #2c3e50;
        }}

        .ref-list {{
            list-style-type: none;
            padding-left: 0;
        }}

        .ref-list li {{
            margin-bottom: 8pt;
        }}

        strong {{
            font-weight: 600;
        }}
    </style>
</head>
<body>
    <div class="cover">
        <h1>{escape(meta["title"])}</h1>
        <div class="meta">
            <p><strong>{escape(meta["author"])}</strong></p>
            <p>{escape(meta["date"])}</p>
        </div>
        <div class="toc">
            <h2>Contents</h2>
            <ol>
                <li>Abstract</li>
                <li>Summary</li>
                <li>Key Topics</li>
                <li>Key Themes</li>
                <li>Key Terms</li>
                <li>Bowen References</li>
                <li>Emphasized Items</li>
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
        <h1>Summary</h1>
        <div class="abstract">
            {summary_html}
        </div>
    </div>

    <div class="section">
        <h1>Key Topics</h1>
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
        <h1>Bowen References</h1>
        <div class="metadata-section">
            {bowen_html}
        </div>
    </div>

    <div class="section">
        <h1>Emphasized Items</h1>
        <div class="metadata-section">
            {emphasis_html}
        </div>
    </div>

    <div class="section">
        <h1>Transcript</h1>
        <div class="legend">
            <strong>Highlights:</strong>
            <mark class="bowen-ref">Bowen References</mark> |
            <mark class="emphasis">Emphasis (<90%)</mark> |
            <mark class="emphasis score-90">High Emphasis (90-94%)</mark> |
            <mark class="emphasis score-95">Top Emphasis (95%+)</mark>
        </div>
        {formatted_content}
    </div>
</body>
</html>"""

    return html


def generate_pdf(base_name: str) -> bool:
    """Orchestrates the generation of the PDF."""
    logger = setup_logging("generate_pdf")
    try:
        from weasyprint import HTML
    except ImportError:
        logger.error(
            "WeasyPrint library not found. Install with: pip install weasyprint"
        )
        return False

    try:
        formatted_file = (
            config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_FORMATTED}"
        )
        topics_themes_file = (
            config.PROJECTS_DIR
            / base_name
            / f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"
        )
        output_file = (
            config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_PDF}"
        )

        validate_input_file(formatted_file)
        validate_input_file(topics_themes_file)

        formatted_content = formatted_file.read_text(encoding="utf-8")
        formatted_content = strip_yaml_frontmatter(formatted_content)

        logger.info("Loading topics-themes materials for PDF...")
        bowen_refs = load_bowen_references(base_name)
        emphasis_items = load_emphasis_items(base_name)
        metadata = _extract_pdf_metadata(topics_themes_file)
        summary = _load_summary(base_name)
        # Override abstract with the best available version
        metadata["abstract"] = _load_abstract(base_name)

        logger.info("Highlighting transcript for PDF...")
        formatted_html = markdown_to_html(formatted_content)
        formatted_html = re.sub(
            r"<h1>Transcript Formatting[^<]*</h1>\s*",
            "",
            formatted_html,
            flags=re.IGNORECASE,
        )
        # Also remove the title header if present, to match simple_webpage logic
        formatted_html = re.sub(r"^<h1>[^<]+</h1>\s*", "", formatted_html)
        highlighted_html = _highlight_html_content(
            formatted_html, bowen_refs, emphasis_items
        )

        logger.info("Generating HTML for PDF...")
        html_content = _generate_html_for_pdf(
            base_name, highlighted_html, metadata, summary, bowen_refs, emphasis_items
        )

        logger.info("Generating PDF...")
        HTML(string=html_content).write_pdf(output_file)
        logger.info(f"✓ PDF generated successfully: {output_file}")
        return True

    except Exception as e:
        logger.error(f"An error occurred during PDF generation: {e}", exc_info=True)
        return False