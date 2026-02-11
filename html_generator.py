"""
HTML generation logic for the transcript processing application.
This module handles the creation of webpages and PDF-ready HTML using Jinja2 templates.

REFACTORED: Extracted 1000+ lines of HTML/CSS to separate template files.
"""

import re
from difflib import SequenceMatcher
from html import escape, unescape
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

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
# JINJA2 TEMPLATE SETUP
# ============================================================================

# Initialize Jinja2 environment
TEMPLATES_DIR = Path(__file__).parent / "templates"
STYLES_DIR = TEMPLATES_DIR / "styles"

template_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(['html', 'xml']),
    trim_blocks=True,
    lstrip_blocks=True
)

# Load CSS files once at module level for efficiency
def _load_css(filename: str) -> str:
    """Load a CSS file from the styles directory."""
    css_path = STYLES_DIR / filename
    if css_path.exists():
        return css_path.read_text(encoding='utf-8')
    return ""

COMMON_CSS = _load_css("common.css")
WEBPAGE_CSS = _load_css("webpage.css")
PDF_CSS = _load_css("pdf.css")


# ============================================================================
# WEBPAGE GENERATION - METADATA EXTRACTION
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

    structural = extract_section(content, "Structural Themes")
    interpretive = extract_section(content, "Interpretive Themes")
    if structural and interpretive:
        themes_block = f"### Structural Themes\n\n{structural}\n\n### Interpretive Themes\n\n{interpretive}"
    else:
        themes_block = interpretive or structural

    metadata = {
        "topics": extract_section(content, "Topics"),
        "themes": themes_block,
        "abstract": extract_section(content, "Abstract"),
        "key_terms": key_term_defs,
    }
    return metadata


def _load_abstract(base_name):
    """Load abstract from generated file, falling back to All Key Items."""
    gen_file = (
        config.PROJECTS_DIR / base_name /
        f"{base_name}{config.SUFFIX_ABSTRACT_GEN}"
    )
    if gen_file.exists():
        return gen_file.read_text(encoding="utf-8")

    # Fallback: Extract from All Key Items
    topics_themes_file = (
        config.PROJECTS_DIR / base_name /
        f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"
    )
    if topics_themes_file.exists():
        content = topics_themes_file.read_text(encoding="utf-8")
        content = strip_yaml_frontmatter(content)
        return extract_section(content, "Abstract")
    return ""


def _load_summary(base_name):
    """Load summary from generated or initial file."""
    gen_file = (
        config.PROJECTS_DIR / base_name /
        f"{base_name}{config.SUFFIX_SUMMARY_GEN}"
    )
    if gen_file.exists():
        content = gen_file.read_text(encoding="utf-8")
        content = strip_yaml_frontmatter(content)
        # Remove "Summary" header if present
        content = re.sub(r"^#+\s*Summary\s*", "", content,
                         flags=re.IGNORECASE).strip()
        # Stop at next section header
        content = re.split(r"^##\s+", content, flags=re.MULTILINE)[0].strip()
        return content

    # Fallback: Extract from All Key Items
    topics_themes_file = (
        config.PROJECTS_DIR / base_name /
        f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"
    )
    if topics_themes_file.exists():
        content = topics_themes_file.read_text(encoding="utf-8")
        content = strip_yaml_frontmatter(content)
        return extract_section(content, "Summary")

    return ""


def _extract_key_term_definitions(topics_themes_file):
    """Extract key term definitions from topics-themes file."""
    with open(topics_themes_file, "r", encoding="utf-8") as f:
        content = f.read()

    content = strip_yaml_frontmatter(content)

    # Extract Key Terms section
    terms_section = extract_section(content, "Key Terms")
    if not terms_section:
        return []

    terms = []

    # Strategy 1: Look for Header-based terms (### Term Name)
    # Matches: ### Term \n Definition
    # We use a lookahead to stop at the next header or end of string
    header_pattern = r'(?:^|\n)###\s+([^\n]+)\s*\n+(.+?)(?=\n###|\Z)'
    header_matches = re.findall(header_pattern, terms_section, re.DOTALL)

    if header_matches:
        for name, raw_def in header_matches:
            name = name.strip()
            # Clean up definition (remove formatting if it leaked)
            clean_def = raw_def.strip()
            terms.append({"name": name, "definition": clean_def})
    
    # Strategy 2: Look for Bold-based terms (**Term**: Definition)
    # Only run if Strategy 1 failed to find significant items, or combine them?
    # Usually a file uses one style or the other. We'll append if not duplicates.
    
    bold_pattern = r'\*\*([^\*]+?)\*\*\s*[:\-]\s*(.+?)(?=\n\*\*|\n\n|$)'
    bold_matches = re.findall(bold_pattern, terms_section, re.DOTALL)

    existing_names = {t['name'].lower() for t in terms}

    for name, raw_def in bold_matches:
        name = name.strip()
        if name.lower() in existing_names:
            continue

        raw_def = raw_def.strip()
        # Clean up definition
        clean_def = raw_def
        # Remove surrounding parentheses if present
        if clean_def.startswith('(') and clean_def.endswith(')'):
            clean_def = clean_def[1:-1].strip()

        # Remove markdown emphasis
        clean_def = re.sub(r'\*\*(.+?)\*\*', r'\1', clean_def)
        clean_def = re.sub(r'\*(.+?)\*', r'\1', clean_def)

        terms.append({
            "name": name,
            "definition": clean_def
        })

    return terms


def _format_ref_list(items):
    """Format a list of (label, quote) tuples as HTML."""
    if not items:
        return "<p>None found.</p>"

    html_parts = ["<ul class='ref-list'>"]
    for label, quote in items:
        html_parts.append(
            f"<li><strong>{escape(label)}</strong>: {escape(quote)}</li>"
        )
    html_parts.append("</ul>")
    return "".join(html_parts)


def _format_key_terms(key_terms):
    """Format key terms as HTML definition list."""
    if not isinstance(key_terms, list) or not key_terms:
        if key_terms and isinstance(key_terms, str):
            return f"<p>{escape(key_terms)}</p>"
        return "<p>No key terms found.</p>"

    html_parts = ["<dl>"]
    for term in key_terms:
        name = term.get("name", "Unknown Term")
        definition = term.get("definition", "No definition provided.")
        html_parts.append(f"<dt><strong>{escape(name)}</strong></dt>")
        html_parts.append(f"<dd>{markdown_to_html(definition)}</dd>")
    html_parts.append("</dl>")
    return "".join(html_parts)


# ============================================================================
# HTML GENERATION USING TEMPLATES
# ============================================================================

def _generate_html_page(base_name, formatted_content, metadata, summary, bowen_refs, emphasis_items):
    """Generate complete HTML page with sidebar using Jinja2 template."""
    meta = parse_filename_metadata(base_name)

    # Prepare template context
    context = {
        "meta": meta,
        "formatted_content": formatted_content,
        "abstract_html": markdown_to_html(metadata["abstract"]),
        "summary_html": markdown_to_html(summary),
        "topics_html": markdown_to_html(metadata["topics"]),
        "themes_html": markdown_to_html(metadata["themes"]),
        "key_terms_html": _format_key_terms(metadata.get("key_terms")),
        "bowen_html": _format_ref_list(bowen_refs),
        "emphasis_html": _format_ref_list(emphasis_items),
        "common_css": COMMON_CSS,
        "webpage_css": WEBPAGE_CSS,
    }

    # Render template
    template = template_env.get_template("webpage.html")
    return template.render(context)


def _generate_simple_html_page(base_name, formatted_content, metadata, summary, bowen_refs, emphasis_items):
    """Generate simple HTML page using Jinja2 template."""
    meta = parse_filename_metadata(base_name)

    # Prepare template context
    context = {
        "meta": meta,
        "formatted_content": formatted_content,
        "abstract_html": markdown_to_html(metadata["abstract"]),
        "summary_html": markdown_to_html(summary),
        "topics_html": markdown_to_html(metadata["topics"]),
        "themes_html": markdown_to_html(metadata["themes"]),
        "key_terms_html": _format_key_terms(metadata.get("key_terms")),
        "bowen_html": _format_ref_list(bowen_refs),
        "emphasis_html": _format_ref_list(emphasis_items),
        "common_css": COMMON_CSS,
    }

    # Render template
    template = template_env.get_template("simple_webpage.html")
    return template.render(context)


def _generate_pdf_html(base_name, formatted_content, metadata, summary, bowen_refs, emphasis_items):
    """Generate PDF-ready HTML using Jinja2 template."""
    meta = parse_filename_metadata(base_name)

    # Prepare template context
    context = {
        "meta": meta,
        "formatted_content": formatted_content,
        "abstract_html": markdown_to_html(metadata["abstract"]),
        "summary_html": markdown_to_html(summary),
        "topics_html": markdown_to_html(metadata["topics"]),
        "themes_html": markdown_to_html(metadata["themes"]),
        "key_terms_html": _format_key_terms(metadata.get("key_terms")),
        "bowen_html": _format_ref_list(bowen_refs),
        "emphasis_html": _format_ref_list(emphasis_items),
        "common_css": COMMON_CSS,
        "pdf_css": PDF_CSS,
    }

    # Render template
    template = template_env.get_template("pdf.html")
    return template.render(context)


# ============================================================================
# HTML CONTENT HIGHLIGHTING
# ============================================================================
# This complex function handles highlighting of Bowen references and emphasis
# items in the HTML content. Kept unchanged for reliability.

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
                        entity = tok[j: end_entity + 1]
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
        text_words_norm = [normalize_text(
            w, aggressive=True) for w in text_words]

        for i in range(len(text_words_norm) - n_quote + 1):
            if text_words_norm[i: i + n_quote] == quote_words:
                start_char = text_positions[i].start()
                end_char = text_positions[i + n_quote - 1].end()
                return (start_char, end_char)

        text_positions = [m for m in re.finditer(r"\b\w+\b", search_text)]
        text_words = [m.group(0) for m in text_positions]
        text_words_norm = [normalize_text(
            w, aggressive=True) for w in text_words]

        matcher = SequenceMatcher(
            None, text_words_norm, quote_words, autojunk=False)

        # Get all matching blocks (sequences of matching words)
        matching_blocks = [
            b for b in matcher.get_matching_blocks() if b.size > 0]
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
                best_cluster = matching_blocks[left: right + 1]

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
        tokens[start_tok] = start_text[:start_off] + \
            open_tag + start_text[start_off:]

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

    # Prepare template context
    context = {
        "meta": meta,
        "formatted_content": formatted_content,
        "abstract_html": abstract_html,
        "summary_html": summary_html,
        "topics_html": topics_html,
        "themes_html": themes_html,
        "key_terms_html": key_terms_html,
        "bowen_html": bowen_html,
        "emphasis_html": emphasis_html,
        "common_css": COMMON_CSS,
    }

    template = template_env.get_template("simple_webpage.html")
    return template.render(context)



# ============================================================================
# MAIN GENERATION FUNCTIONS
# ============================================================================

def generate_webpage(base_name: str) -> bool:
    """Orchestrates the generation of the main webpage with a sidebar."""
    logger = setup_logging("generate_webpage")
    try:
        formatted_file = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_FORMATTED}"
        )
        topics_themes_file = (
            config.PROJECTS_DIR
            / base_name
            / f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"
        )
        output_file = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_WEBPAGE}"
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
            "Found %d Bowen references and %d emphasis items.", len(bowen_refs), len(emphasis_items))

        logger.info("Highlighting transcript...")
        formatted_html = markdown_to_html(formatted_content)
        # Clean up unwanted headers before highlighting
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

        logger.info("Generating HTML page using template...")
        html = _generate_html_page(
            base_name, formatted_html, metadata, summary, bowen_refs, emphasis_items
        )

        output_file.write_text(html, encoding="utf-8")

        logger.info("✓ Webpage generated successfully: %s", output_file)
        return True

    except Exception as e:
        logger.error("An error occurred: %s", e, exc_info=True)
        return False


def generate_simple_webpage(base_name: str) -> bool:
    """Generates a simple standalone webpage (no sidebar)."""
    logger = setup_logging("generate_simple_webpage")
    try:
        formatted_file = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_FORMATTED}"
        )
        topics_themes_file = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"
        )
        output_file = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_WEBPAGE_SIMPLE}"
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

        logger.info("Highlighting transcript...")
        formatted_html = markdown_to_html(formatted_content)
        # Clean up headers
        formatted_html = re.sub(r"^<h1>[^<]+</h1>\s*", "", formatted_html)
        formatted_html = _highlight_html_content(
            formatted_html, bowen_refs, emphasis_items
        )

        logger.info("Generating simple HTML page using template...")
        html = _generate_simple_html_page(
            base_name, formatted_html, metadata, summary, bowen_refs, emphasis_items
        )

        output_file.write_text(html, encoding="utf-8")

        logger.info("✓ Simple webpage generated successfully: %s", output_file)
        return True

    except Exception as e:
        logger.error("An error occurred: %s", e, exc_info=True)
        return False


def generate_pdf(base_name: str) -> bool:
    """Generates a PDF from the formatted transcript."""
    logger = setup_logging("generate_pdf")
    try:
        from weasyprint import HTML

        formatted_file = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_FORMATTED}"
        )
        topics_themes_file = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"
        )
        output_file = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_PDF}"
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

        logger.info("Highlighting transcript...")
        formatted_html = markdown_to_html(formatted_content)
        # Remove title header
        formatted_html = re.sub(r"^<h1>[^<]+</h1>\s*", "", formatted_html)
        highlighted_html = _highlight_html_content(
            formatted_html, bowen_refs, emphasis_items
        )

        logger.info("Generating HTML for PDF using template...")
        html_content = _generate_pdf_html(
            base_name, highlighted_html, metadata, summary, bowen_refs, emphasis_items
        )

        logger.info("Generating PDF...")
        HTML(string=html_content).write_pdf(output_file)
        logger.info("✓ PDF generated successfully: %s", output_file)
        return True

    except Exception as e:
        logger.error("An error occurred during PDF generation: %s",
                     e, exc_info=True)
        return False
