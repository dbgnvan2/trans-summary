"""
Core pipeline logic for the transcript processing application.
This module consolidates the business logic for each step of the pipeline,
making it reusable by both the GUI and the CLI scripts.
"""

from transcript_utils import (
    call_claude_with_retry,
    validate_input_file,
    setup_logging,
    normalize_text,
    extract_emphasis_items,
    strip_yaml_frontmatter,
    parse_filename_metadata,
    load_bowen_references,
    load_emphasis_items,
    find_text_in_content,
    markdown_to_html,
    extract_section,
    extract_bowen_references,
    estimate_token_count,
)
import anthropic
import os
import re
import threading
import time
from html import unescape
from pathlib import Path
from html import escape
from difflib import SequenceMatcher
from typing import Set, Dict, List, Optional, Any

import config
from dotenv import load_dotenv
load_dotenv()


import abstract_pipeline
import abstract_validation
import summary_pipeline
import summary_validation

# Prompt filename
PROMPT_FILENAME = "Transcript Formatting Prompt v10.md"


def load_prompt() -> str:
    """Load the formatting prompt template."""
    prompts_dir = config.TRANSCRIPTS_BASE / "prompts"
    prompt_path = prompts_dir / PROMPT_FILENAME

    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path}\n"
            f"Expected location: {prompts_dir}/{PROMPT_FILENAME}"
        )
    return prompt_path.read_text(encoding='utf-8')


def load_raw_transcript(filename: str) -> str:
    """Load the raw transcript from source directory."""
    transcript_path = config.SOURCE_DIR / filename
    validate_input_file(transcript_path)
    return transcript_path.read_text(encoding='utf-8')


def format_transcript_with_claude(raw_transcript: str, prompt_template: str, model: str = config.DEFAULT_MODEL, logger=None) -> str:
    """Send transcript to Claude for formatting."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set.")

    client = anthropic.Anthropic(api_key=api_key)

    full_prompt = f"{prompt_template}\n\n---\n\nRAW TRANSCRIPT:\n\n{raw_transcript}"

    if logger:
        logger.info("Sending transcript to Claude...")
        word_count = len(raw_transcript.split())
        logger.info(
            f"Transcript length: {word_count:,} words, {len(raw_transcript):,} characters")
        logger.info("Waiting for Claude response...")
    else:
        print("Sending transcript to Claude...", flush=True)
        print(
            f"Transcript length: {len(raw_transcript.split()):,} words, {len(raw_transcript):,} characters", flush=True)
        print("⏳ Waiting for Claude response (may take 2-5 minutes for longer transcripts)...", flush=True)

    message = call_claude_with_retry(
        client=client,
        model=model,
        messages=[{"role": "user", "content": full_prompt}],
        max_tokens=8192,
        logger=logger,
    )

    return message.content[0].text


def save_formatted_transcript(content: str, original_filename: str) -> Path:
    """Save formatted transcript with naming convention."""
    stem = Path(original_filename).stem
    output_filename = f"{stem} - formatted.md"
    output_path = config.FORMATTED_DIR / output_filename

    config.FORMATTED_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding='utf-8')
    return output_path


def format_transcript(raw_filename: str, model: str = config.DEFAULT_MODEL, logger=None) -> bool:
    """
    Orchestrates the transcript formatting process.
    """
    if logger is None:
        logger = setup_logging('format_transcript')

    try:
        if not config.SOURCE_DIR.exists():
            raise FileNotFoundError(
                f"Source directory not found: {config.SOURCE_DIR}")

        logger.info(
            f"Loading prompt template from: {config.TRANSCRIPTS_BASE / 'prompts'}")
        prompt_template = load_prompt()

        logger.info(f"Loading raw transcript: {raw_filename}")
        raw_transcript = load_raw_transcript(raw_filename)

        formatted_content = format_transcript_with_claude(
            raw_transcript, prompt_template, model=model, logger=logger)

        output_path = save_formatted_transcript(
            formatted_content, raw_filename)

        logger.info("✓ Success!")
        logger.info(f"Formatted transcript saved to: {output_path}")
        return True

    except ValueError as e:
        # Re-raise configuration errors so they appear in the GUI
        logger.error(f"Configuration error: {e}")
        raise e
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return False

# ============================================================================
# SUMMARIZATION PIPELINE
# ============================================================================


# Prompt file names
EXTRACTS_SUMMARY_PROMPT = "Transcript Summary Abstract Key Items v1.md"
KEY_TERMS_PROMPT = "Transcript Summary Key Terms v1.md"
BLOG_PROMPT = "Transcript Summary Blog Post v1.md"


def _extract_emphasis_quotes(extracts_summary_file):
    """Extract all quoted text from Emphasized Items section."""
    extracts_path = Path(extracts_summary_file)
    stem = extracts_path.stem.replace(' - extracts-summary', '')
    emphasis_file = extracts_path.parent / f"{stem} - emphasis-items.md"

    source_file = emphasis_file if emphasis_file.exists() else extracts_path
    content = source_file.read_text(encoding='utf-8')
    content = strip_yaml_frontmatter(content)

    return extract_emphasis_items(content)


def _find_best_match(needle, haystack, threshold=0.85):
    """Find the best matching substring in haystack for needle.
    Returns (match_ratio, matched_text) or (0, None) if no good match."""

    needle_normalized = normalize_text(needle, aggressive=True)
    haystack_normalized = normalize_text(haystack, aggressive=True)

    if needle_normalized in haystack_normalized:
        return (1.0, needle)

    needle_words = needle_normalized.split()
    needle_len = len(needle_words)
    haystack_words = haystack_normalized.split()

    best_ratio = 0
    best_match = None

    for i in range(len(haystack_words) - needle_len + 1):
        window = ' '.join(haystack_words[i:i + needle_len])
        ratio = SequenceMatcher(None, needle_normalized, window).ratio()

        if ratio > best_ratio:
            best_ratio = ratio
            best_match = window

    if best_ratio >= threshold:
        return (best_ratio, best_match)

    return (best_ratio, None)


def _validate_emphasis_items(formatted_file, extracts_summary_file, logger):
    """Validate all emphasis quotes exist in the formatted transcript."""
    formatted_content = formatted_file.read_text(encoding='utf-8')
    quotes = _extract_emphasis_quotes(extracts_summary_file)

    if not quotes:
        logger.warning("No emphasis quotes found to validate")
        return

    valid_count, partial_count, invalid_count = 0, 0, 0

    for label, quote in quotes:
        quote_core = ' '.join(quote.split()[:15])
        ratio, _ = _find_best_match(
            quote_core, formatted_content, threshold=0.80)

        if ratio >= 0.95:
            valid_count += 1
        elif ratio >= 0.80:
            partial_count += 1
        else:
            logger.error(f"NOT FOUND: {label} - Quote: {quote[:100]}...")
            invalid_count += 1

    logger.info("Emphasis Items Validation:")
    logger.info(f"  Exact matches: {valid_count}")
    if partial_count > 0:
        logger.warning(f"  Partial matches: {partial_count}")
    if invalid_count > 0:
        logger.error(f"  Not found: {invalid_count}")

    accuracy = (valid_count + partial_count) / \
        len(quotes) * 100 if quotes else 0
    logger.info(f"  Overall accuracy: {accuracy:.1f}%")


def _load_summary_prompt(prompt_filename: str) -> str:
    """Load a summary prompt template."""
    prompts_dir = config.TRANSCRIPTS_BASE / "prompts"
    prompt_path = prompts_dir / prompt_filename
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path}\nExpected location: {prompts_dir}/{prompt_filename}")
    return prompt_path.read_text(encoding='utf-8')


def _load_formatted_transcript(filename: str) -> str:
    """Load the formatted transcript."""
    transcript_path = config.FORMATTED_DIR / filename
    validate_input_file(transcript_path)
    return transcript_path.read_text(encoding='utf-8')


def _fill_prompt_template(template: str, metadata: dict, transcript: str, **kwargs) -> str:
    """Fill in the prompt template."""
    placeholders = {**metadata, **kwargs}
    for key, value in placeholders.items():
        # Case-insensitive replacement for {{key}} and {{ key }}
        pattern = re.compile(
            r"\{\{\s*" + re.escape(key) + r"\s*\}\}", re.IGNORECASE)
        template = pattern.sub(lambda m: str(value), template)
    template = template.replace("{{insert_transcript_text_here}}", transcript)
    return template


def _generate_summary_with_claude(prompt: str, model: str, temperature: float, logger) -> str:
    """Send prompt to Claude for summary generation."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set.")
    client = anthropic.Anthropic(api_key=api_key)

    message = call_claude_with_retry(
        client=client,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=8192,
        temperature=temperature,
        logger=logger,
    )
    return message.content[0].text


def _save_summary(content: str, original_filename: str, summary_type: str) -> Path:
    """Save summary output."""
    stem = Path(original_filename).stem
    if stem.endswith(' - formatted'):
        stem = stem[:-12]
    if stem.endswith('_yaml'):
        stem = stem[:-5]
    output_filename = f"{stem} - {summary_type}.md"
    output_path = config.SUMMARIES_DIR / output_filename
    config.SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding='utf-8')
    return output_path


def _split_extracts_summary(extracts_summary_path: Path, logger):
    """Split extracts-summary into focused extract files."""
    logger.info("Splitting extracts into focused files...")
    content = extracts_summary_path.read_text(encoding='utf-8')
    clean_content = strip_yaml_frontmatter(content)
    stem = extracts_summary_path.stem.replace(' - extracts-summary', '')

    bowen_refs = extract_bowen_references(clean_content)
    if bowen_refs:
        bowen_output = "## Bowen References\n\n" + \
            "\n\n".join(f'> **{label}:** "{quote}"' for label,
                        quote in bowen_refs)
        bowen_path = config.SUMMARIES_DIR / f"{stem} - bowen-references.md"
        bowen_path.write_text(bowen_output, encoding='utf-8')
        logger.info(
            f"  ✓ {len(bowen_refs)} Bowen references → {bowen_path.name}")

    emphasis_items = extract_emphasis_items(clean_content)
    if emphasis_items:
        emphasis_output = "## Emphasized Items\n\n" + \
            "\n\n".join(f'> **{label}:** "{quote}"' for label,
                        quote in emphasis_items)
        emphasis_path = config.SUMMARIES_DIR / f"{stem} - emphasis-items.md"
        emphasis_path.write_text(emphasis_output, encoding='utf-8')
        logger.info(
            f"  ✓ {len(emphasis_items)} emphasis items → {emphasis_path.name}")


def summarize_transcript(formatted_filename: str, model: str, focus_keyword: str, target_audience: str,
                         skip_extracts_summary: bool, skip_terms: bool, skip_blog: bool,
                         generate_structured: bool = False, structured_word_count: int = 500, trans_summary_logger=None) -> bool:
    """Orchestrates the transcript summarization process."""
    if trans_summary_logger is None:
        trans_summary_logger = setup_logging('summarize_transcript')

    try:
        # Explicitly cast to int right at the beginning of the function body
        # This will convert structured_word_count to int or raise TypeError/ValueError
        try:
            structured_word_count = int(structured_word_count)
        except (TypeError, ValueError) as e:
            trans_summary_logger.error(f"Error: structured_word_count expected to be an integer or a string representing an integer, but received type {type(structured_word_count)} with value '{structured_word_count}'. Original error: {e}", exc_info=True)
            return False

        if not config.SOURCE_DIR.exists():
            raise FileNotFoundError(
                f"Source directory not found: {config.SOURCE_DIR}")

        trans_summary_logger.info(f"Loading formatted transcript: {formatted_filename}")
        transcript = _load_formatted_transcript(formatted_filename)
        metadata = parse_filename_metadata(formatted_filename)
        trans_summary_logger.info(f"Transcript metadata: {metadata}")

        extracts_summary_path = None

        if not skip_extracts_summary:
            trans_summary_logger.info("PART 1: Generating Extracts Summary Analysis...")
            prompt_template = _load_summary_prompt(EXTRACTS_SUMMARY_PROMPT)
            prompt = _fill_prompt_template(
                prompt_template, metadata, transcript, target_audience=target_audience)
            output = _generate_summary_with_claude(prompt, model, 0.2, trans_summary_logger)
            extracts_summary_path = _save_summary(
                output, formatted_filename, "extracts-summary")
            trans_summary_logger.info(
                f"✓ Extracts summary analysis saved to: {extracts_summary_path}")
            _split_extracts_summary(extracts_summary_path, trans_summary_logger)
        else:
            # If skipping extracts, try to load it if it already exists for structured summary later
            base_name_from_formatted = Path(formatted_filename).stem.replace(' - formatted', '')
            potential_extracts_path = config.SUMMARIES_DIR / \
                f"{base_name_from_formatted} - extracts-summary.md"
            if potential_extracts_path.exists():
                extracts_summary_path = potential_extracts_path
                trans_summary_logger.info(f"Skipping extracts-summary generation, using existing file: {extracts_summary_path}")


        if not skip_terms:
            trans_summary_logger.info("PART 2: Extracting Key Terms...")
            prompt_template = _load_summary_prompt(KEY_TERMS_PROMPT)
            prompt = _fill_prompt_template(
                prompt_template, metadata, transcript)
            output = _generate_summary_with_claude(prompt, model, 0.4, trans_summary_logger)
            key_terms_path = _save_summary(
                output, formatted_filename, "key-terms")
            trans_summary_logger.info(f"✓ Key terms document saved to: {key_terms_path}")

        if not skip_blog:
            trans_summary_logger.info("PART 3: Generating Blog Post...")
            prompt_template = _load_summary_prompt(BLOG_PROMPT)
            prompt = _fill_prompt_template(
                prompt_template, metadata, transcript, focus_keyword=focus_keyword, target_audience=target_audience)
            output = _generate_summary_with_claude(prompt, model, 0.3, trans_summary_logger)
            blog_path = _save_summary(output, formatted_filename, "blog")
            trans_summary_logger.info(f"✓ Blog post saved to: {blog_path}")

        trans_summary_logger.info("✓ Summary generation complete!")

        if not skip_extracts_summary: # Only validate emphasis if extracts were generated or explicitly not skipped
            trans_summary_logger.info("VALIDATION: Checking Emphasis Items...")
            formatted_path = config.FORMATTED_DIR / formatted_filename
            if extracts_summary_path:
                _validate_emphasis_items(
                    formatted_path, extracts_summary_path, trans_summary_logger)

        if generate_structured:
            if extracts_summary_path:
                trans_summary_logger.info("Generating structured summary...")
                # The generate_structured_summary function expects base_name
                base_name = Path(formatted_filename).stem.replace(' - formatted', '')
                
                # word_count_for_generation = int(structured_word_count) # Removed explicit cast here
                
                structured_success = generate_structured_summary(
                    base_name=base_name,
                    summary_target_word_count=structured_word_count, # Use the directly cast variable
                    gen_summary_logger=trans_summary_logger 
                )
                if structured_success:
                    trans_summary_logger.info("Structured summary generation complete. Validating structured summary...")
                    validate_summary_coverage(base_name=base_name, logger=trans_summary_logger)
                else:
                    trans_summary_logger.error("Structured summary generation failed.")
                    return False
            else:
                trans_summary_logger.warning("Cannot generate structured summary: extracts-summary was skipped or not found.")
                
        return True

    except ValueError as e:
        # Re-raise configuration errors so they appear in the GUI
        trans_summary_logger.error(f"Configuration error: {e}")
        raise e
    except Exception as e:
        trans_summary_logger.error(f"An error occurred: {e}", exc_info=True)
        return False

# ============================================================================
# YAML INJECTION
# ============================================================================


def _generate_yaml_front_matter(meta: dict, source_filename: str) -> str:
    """
    Generate YAML front matter block.
    """
    authenticity = (
        "Verified line-by-line against the original recording. No wording has been\n"
        "  omitted, merged, reordered, paraphrased, or corrected. All text remains\n"
        "  exactly as spoken except for added section headings and removal of timestamps."
    )

    return f'''---
Title: "{meta['title']}"
Presenter: "{meta['presenter']}"
Lecture date: "{meta['date']}"
Source recording: "{source_filename}"
Transcriber: "Automated; human-reviewed"
Authenticity: "{authenticity}"
Version: "v1.0"
License: "© {meta['year']} {meta['presenter']}. All rights reserved."
DOI: ""
---

'''


def add_yaml(transcript_filename: str, source_ext: str = "mp4", logger=None) -> bool:
    """
    Orchestrates the process of adding YAML front matter to a transcript.
    """
    if logger is None:
        logger = setup_logging('add_yaml')

    try:
        logger.info(f"Adding YAML to {transcript_filename}")

        transcript_path = config.FORMATTED_DIR / transcript_filename
        validate_input_file(transcript_path)

        meta = parse_filename_metadata(transcript_filename)

        source_filename = f"{meta['stem']}.{source_ext.lstrip('.')}"

        formatted_content = transcript_path.read_text(encoding='utf-8')

        yaml_block = _generate_yaml_front_matter(meta, source_filename)
        final_content = yaml_block + formatted_content

        output_path = config.FORMATTED_DIR / f"{meta['stem']}_yaml.md"
        output_path.write_text(final_content, encoding='utf-8')

        logger.info(f"✓ Success! YAML added. Output saved to: {output_path}")

        # Validation: Log first 20 lines
        logger.info("\n--- YAML Validation (First 20 lines) ---")
        with open(output_path, 'r', encoding='utf-8') as f:
            for _ in range(20):
                line = f.readline()
                if not line:
                    break
                logger.info(line.rstrip())
        logger.info("----------------------------------------\n")

        return True

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return False

# ============================================================================
# WEBPAGE GENERATION
# ============================================================================


def _extract_webpage_metadata(extracts_summary_file):
    """Extract topics, themes, key terms, and abstract from extracts-summary."""
    with open(extracts_summary_file, 'r', encoding='utf-8') as f:
        content = f.read()

    content = strip_yaml_frontmatter(content)
    content = re.sub(r'---\s*#\s*TERMINOLOGY EXTRACTION OUTPUT.*?---\s*#\s*Key Terms',
                     '# Key Terms', content, flags=re.DOTALL)

    metadata = {
        'topics': extract_section(content, 'Topics'),
        'themes': extract_section(content, 'Key Themes'),
        'abstract': extract_section(content, 'Abstract'),
        'key_terms': ', '.join(re.findall(r'^## ([A-Z][^\n#]+?)[\s]*\n+\*\*Definition Type:', content, re.MULTILINE))
    }
    return metadata


def _generate_html_page(base_name, formatted_content, metadata):
    """Generate complete HTML page with sidebar."""
    meta = parse_filename_metadata(base_name)
    topics_html = markdown_to_html(metadata['topics'])
    themes_html = markdown_to_html(metadata['themes'])
    abstract_html = markdown_to_html(metadata['abstract'])

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(meta['title'])}</title>
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
        <h1>{escape(meta['title'])}</h1>
        <div class="meta">
            <strong>{escape(meta['author'])}</strong> | {escape(meta['date'])}
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
    """Orchestrates the generation of the main webpage with a sidebar."""
    logger = setup_logging('generate_webpage')
    try:
        formatted_file = config.FORMATTED_DIR / f"{base_name} - formatted.md"
        extracts_summary_file = config.SUMMARIES_DIR / \
            f"{base_name} - extracts-summary.md"
        output_file = config.WEBPAGES_DIR / f"{base_name}.html"

        validate_input_file(formatted_file)
        validate_input_file(extracts_summary_file)

        formatted_content = formatted_file.read_text(encoding='utf-8')
        formatted_content = strip_yaml_frontmatter(formatted_content)

        logger.info("Loading extracts-summary materials...")
        bowen_refs = load_bowen_references(base_name)
        emphasis_items = load_emphasis_items(base_name)
        metadata = _extract_webpage_metadata(extracts_summary_file)
        logger.info(
            f"Found {len(bowen_refs)} Bowen references and {len(emphasis_items)} emphasis items.")

        logger.info("Highlighting transcript...")
        key_term_defs = _extract_key_term_definitions(extracts_summary_file)
        formatted_html = markdown_to_html(formatted_content)
        # Clean up unwanted headers before highlighting to ensure consistency with simple_webpage
        formatted_html = re.sub(
            r'<h1>Transcript Formatting[^<]*</h1>\s*', '', formatted_html, flags=re.IGNORECASE)
        formatted_html = re.sub(r'^<h1>[^<]+</h1>\s*', '', formatted_html)
        formatted_html = _highlight_html_content(
            formatted_html, bowen_refs, emphasis_items, key_term_defs)

        meta = parse_filename_metadata(base_name)
        formatted_html = f'<h1>{escape(meta["title"])}</h1>\n\n{formatted_html}'

        logger.info("Generating HTML page...")
        html = _generate_html_page(base_name, formatted_html, metadata)

        config.WEBPAGES_DIR.mkdir(parents=True, exist_ok=True)
        output_file.write_text(html, encoding='utf-8')

        logger.info(f"✓ Webpage generated successfully: {output_file}")
        return True

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return False

# ============================================================================
# SIMPLE WEBPAGE GENERATION
# ============================================================================


def _extract_abstract(extracts_summary_file):
    """Extract abstract from extracts-summary."""
    with open(extracts_summary_file, 'r', encoding='utf-8') as f:
        content = f.read()
    content = strip_yaml_frontmatter(content)
    abstract = extract_section(content, 'Abstract')
    return re.sub(r'^---\s*$', '', abstract, flags=re.MULTILINE).strip()


def _load_definitions_content(extracts_summary_file):
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


def _extract_key_terms(extracts_summary_file):
    """Extract key term names (without definitions) from archival document."""
    content = _load_definitions_content(extracts_summary_file)
    if content is None:
        with open(extracts_summary_file, 'r', encoding='utf-8') as f:
            content = f.read()

    content = strip_yaml_frontmatter(content)
    content = re.sub(r'---\s*#\s*TERMINOLOGY EXTRACTION OUTPUT.*?---\s*#\s*Key Terms',
                     '# Key Terms', content, flags=re.DOTALL)
    term_headings = re.findall(
        r'^## ([A-Z][^\n#]+?)[\s]*\n+\*\*Definition Type:', content, re.MULTILINE)
    return [term.strip() for term in term_headings]


def _extract_key_term_definitions(extracts_summary_file):
    """Extract key terms with their definitions and types from archival."""
    content = _load_definitions_content(extracts_summary_file)
    if content is None:
        with open(extracts_summary_file, 'r', encoding='utf-8') as f:
            content = f.read()
    content = strip_yaml_frontmatter(content)
    content = re.sub(r'---\s*#\s*TERMINOLOGY EXTRACTION OUTPUT.*?---\s*#\s*Key Terms',
                     '# Key Terms', content, flags=re.DOTALL)
    term_pattern = r'## ([A-Z][^\n#]+?)[\s]*\n+\*\*Definition Type:\*\*\s*(Explicit Definition|Implicit Definition|Not Explicitly Defined)[\s\S]*?\*\*Definition:\*\*\s*([^*]+?)(?=\n\*\*|\n##|\Z)'
    matches = re.findall(term_pattern, content, re.MULTILINE)
    return [{'name': name.strip(), 'type': def_type.strip(), 'definition': definition.strip()} for name, def_type, definition in matches]


def _highlight_html_content(formatted_html, bowen_refs, emphasis_items, key_term_defs):
    """Add HTML highlighting to HTML content for Bowen refs, emphasis, and term definitions."""
    def tokenize_html(html):
        return re.split(r'(<[^>]+>)', html)

    # Pre-process tokens to unescape HTML entities in text nodes
    # This ensures "It&apos;s" in HTML matches "It's" in the quote

    def build_search_text_and_map(tokens):
        search_chars = []
        char_map = []  # List of (token_index, start_idx, end_idx)

        in_strong = False

        for i, tok in enumerate(tokens):
            # Track strong tags for speaker detection
            if tok.lower() in ('<strong>', '<b>'):
                in_strong = True
                search_chars.append(' ')
                char_map.append(None)
                continue

            if tok.lower() in ('</strong>', '</b>'):
                in_strong = False
                search_chars.append(' ')
                char_map.append(None)
                continue

            if tok.startswith('<') or not tok.strip():
                search_chars.append(' ')
                char_map.append(None)
                continue

            # Detect and skip Speaker Labels
            if in_strong:
                # Case 1: Colon inside (e.g. "Speaker:")
                if re.fullmatch(r'[\w\s\.\(\)]+:', tok.strip(), flags=re.IGNORECASE):
                    search_chars.append(' ')
                    char_map.append(None)
                    continue

                # Case 2: Colon outside (e.g. "Speaker" followed by "</strong>" and ":")
                if i + 2 < len(tokens):
                    next_tag = tokens[i+1].lower()
                    next_text = tokens[i+2]
                    if next_tag in ('</strong>', '</b>') and next_text.strip().startswith(':'):
                        search_chars.append(' ')
                        char_map.append(None)
                        continue

            # Process text token character by character, handling entities
            j = 0
            while j < len(tok):
                if tok[j] == '&':
                    end_entity = tok.find(';', j, j + 10)
                    if end_entity != -1:
                        entity = tok[j:end_entity+1]
                        decoded = unescape(entity)
                        for char in decoded:
                            search_chars.append(char)
                            char_map.append((i, j, end_entity + 1))
                        j = end_entity + 1
                        continue

                search_chars.append(tok[j])
                char_map.append((i, j, j + 1))
                j += 1

        return ''.join(search_chars), char_map

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
            if text_words_norm[i:i+n_quote] == quote_words:
                start_char = text_positions[i].start()
                end_char = text_positions[i+n_quote-1].end()
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
            while left < right and (matching_blocks[right].a - matching_blocks[left].a) > window_limit:
                current_score -= matching_blocks[left].size
                left += 1

            if current_score > best_score:
                best_score = current_score
                best_cluster = matching_blocks[left: right+1]

        # Calculate match ratio based on the best cluster found
        match_ratio = best_score / len(quote_words) if quote_words else 0

        # Threshold: 70% of words must match (allows for some hallucination/correction in summary)
        if match_ratio >= 0.7:
            first_block = best_cluster[0]
            last_block = best_cluster[-1]

            start_char_idx = first_block.a
            end_char_idx = last_block.a + last_block.size - 1

            if start_char_idx < len(text_positions) and end_char_idx < len(text_positions):
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
        while end > start and (end-1 >= len(char_map) or char_map[end-1] is None):
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
            tokens[start_tok] = text[:start_off] + open_tag + \
                text[start_off:end_off] + close_tag + text[end_off:]
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
        labels = [l.strip() for l in existing[3].split(';') if l.strip()]
        if label not in labels:
            labels.append(label)
            existing[3] = '; '.join(labels)

    tokens = tokenize_html(formatted_html)
    search_text, char_map = build_search_text_and_map(tokens)
    highlights = []
    emphasis_entries = {}

    for label, quote in emphasis_items:
        quote_snippet = ' '.join(quote.split()[:75])
        start, end = find_word_span(quote_snippet, search_text)
        span = map_search_span_to_tokens(char_map, start, end)
        if span:
            entry = [span, 'emphasis', label, None]
            highlights.append(entry)
            emphasis_entries[label] = entry

    for concept, quote in bowen_refs:
        quote_snippet = ' '.join(quote.split()[:75])
        start, end = find_word_span(quote_snippet, search_text)
        if start is None:
            start, end = find_word_span(quote, search_text)
        span = map_search_span_to_tokens(char_map, start, end)
        if span:
            highlights.append([span, 'bowen', concept, None])
            continue
        bowen_norm = normalize_text(quote, aggressive=True)
        for emphasis_label, emphasis_quote in emphasis_items:
            if bowen_norm in normalize_text(emphasis_quote, aggressive=True):
                entry = emphasis_entries.get(emphasis_label)
                if entry:
                    add_bowen_label(entry, concept)
                break

    highlights.sort(key=lambda x: (x[0][0], x[0][1]), reverse=True)

    priority = {'emphasis': 3, 'bowen': 2,
                'def-explicit': 1, 'def-implicit': 1}

    def spans_overlap(a, b):
        return not (a[2] < b[0] or a[0] > b[2] or (a[2] == b[0] and a[3] <= b[1]) or (b[2] == a[0] and b[3] <= a[1]))

    filtered_highlights = []
    for h in highlights:
        should_skip = False
        remove_indices = []
        for i, existing in enumerate(filtered_highlights):
            if spans_overlap(h[0], existing[0]):
                if {h[1], existing[1]} == {'emphasis', 'bowen'}:
                    if h[1] == 'emphasis':
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
        if htype == 'bowen':
            insert_mark(
                tokens, span, f'<mark class="bowen-ref" title="Bowen Reference: {escape(label)}">', '</mark>')
        elif htype == 'emphasis':
            bowen_title = f' | Bowen Reference: {escape(extra_label)}' if extra_label else ''
            bowen_class = ' bowen-ref' if extra_label else ''
            insert_mark(
                tokens, span, f'<mark class="emphasis{bowen_class}" title="Emphasized: {escape(label)}{bowen_title}">', '</mark>')
        elif htype in ['def-explicit', 'def-implicit']:
            def_type = 'Explicit Definition' if htype == 'def-explicit' else 'Implicit Definition'
            insert_mark(
                tokens, span, f'<span class="{htype}" title="{def_type}: {escape(label)}">', '</span>')

    return "".join(tokens)


def _generate_simple_html_page(base_name, formatted_content, abstract='', key_terms=[]):
    """Generate simple HTML page without sidebar."""
    meta = parse_filename_metadata(base_name)
    abstract_html = f'<section class="abstract"><h2>Abstract</h2>{markdown_to_html(abstract)}</section>' if abstract else ''
    key_terms_html = f'<section class="key-terms"><h2>Key Terms</h2><p>{", ".join(f"<strong>{escape(term)}</strong>" for term in key_terms)}</p></section>' if key_terms else ''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(meta['title'])}</title>
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
            <h1>{escape(meta['title'])}</h1>
            <div class="meta">
                <div class="author">{escape(meta['author'])}</div>
                <div class="date">{escape(meta['date'])}</div>
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
    """Orchestrates the generation of the simple, single-column webpage."""
    logger = setup_logging('generate_simple_webpage')
    try:
        formatted_file = config.FORMATTED_DIR / f"{base_name} - formatted.md"
        extracts_summary_file = config.SUMMARIES_DIR / \
            f"{base_name} - extracts-summary.md"
        output_file = config.WEBPAGES_DIR / f"{base_name} - simple.html"

        validate_input_file(formatted_file)
        validate_input_file(extracts_summary_file)

        formatted_content = formatted_file.read_text(encoding='utf-8')
        formatted_content = strip_yaml_frontmatter(formatted_content)

        logger.info("Loading extracts-summary materials for simple webpage...")
        abstract = _extract_abstract(extracts_summary_file)
        key_terms = _extract_key_terms(extracts_summary_file)
        bowen_refs = load_bowen_references(base_name)
        emphasis_items = load_emphasis_items(base_name)
        key_term_defs = _extract_key_term_definitions(extracts_summary_file)

        logger.info("Highlighting transcript for simple webpage...")
        formatted_html = markdown_to_html(formatted_content)
        # Clean up HTML before highlighting
        formatted_html = re.sub(
            r'<h1>Transcript Formatting[^<]*</h1>\s*', '', formatted_html, flags=re.IGNORECASE)
        formatted_html = re.sub(r'^<h1>[^<]+</h1>\s*', '', formatted_html)

        highlighted_html = _highlight_html_content(
            formatted_html, bowen_refs, emphasis_items, key_term_defs)

        logger.info("Generating simple HTML page...")
        html = _generate_simple_html_page(
            base_name, highlighted_html, abstract, key_terms)

        config.WEBPAGES_DIR.mkdir(parents=True, exist_ok=True)
        output_file.write_text(html, encoding='utf-8')

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
        if line.startswith('## '):
            if current:
                sections.append(current)
            current = {'title': line[3:].strip(), 'lines': [line]}
        else:
            if current is None:
                continue
            current['lines'].append(line)
    if current:
        sections.append(current)

    if not sections:
        return content

    sections.sort(key=lambda s: s['title'].lower())
    return '\n'.join('\n'.join(section['lines']) for section in sections).strip()


def _extract_pdf_metadata(extracts_summary_file):
    """Extract metadata for PDF generation."""
    with open(extracts_summary_file, 'r', encoding='utf-8') as f:
        content = f.read()
    content = strip_yaml_frontmatter(content)
    content = re.sub(r'---\s*#\s*TERMINOLOGY EXTRACTION OUTPUT.*?---\s*#\s*Key Terms',
                     '# Key Terms', content, flags=re.DOTALL)

    metadata = {
        'topics': extract_section(content, 'Topics'),
        'themes': extract_section(content, 'Key Themes'),
        'abstract': extract_section(content, 'Abstract'),
        'key_terms': extract_section(content, 'Key Terms')
    }

    definitions_content = _load_definitions_content(extracts_summary_file)
    if definitions_content:
        definitions_content = strip_yaml_frontmatter(definitions_content)
        definitions_content = re.sub(
            r'```yaml.*?```', '', definitions_content, flags=re.DOTALL | re.IGNORECASE)
        definitions_content = re.sub(r'^## (Part 2: Key Term Definitions|Key Terms)\s*',
                                     '', definitions_content, flags=re.MULTILINE).strip()
        if definitions_content:
            metadata['key_terms'] = _sort_key_term_sections(
                definitions_content)

    return metadata


def _generate_html_for_pdf(base_name, formatted_content, metadata):
    """Generate complete HTML for PDF conversion."""
    meta = parse_filename_metadata(base_name)
    topics_html = markdown_to_html(metadata['topics'])
    themes_html = markdown_to_html(metadata['themes'])
    abstract_html = markdown_to_html(metadata['abstract'])
    key_terms_html = markdown_to_html(metadata['key_terms'])

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{escape(meta['title'])}</title>
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
        <h1>{escape(meta['title'])}</h1>
        <div class="meta">
            <p><strong>{escape(meta['author'])}</strong></p>
            <p>{escape(meta['date'])}</p>
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
    """Orchestrates the generation of the PDF."""
    logger = setup_logging('generate_pdf')
    try:
        from weasyprint import HTML
    except ImportError:
        logger.error(
            "WeasyPrint library not found. Install with: pip install weasyprint")
        return False

    try:
        formatted_file = config.FORMATTED_DIR / f"{base_name} - formatted.md"
        extracts_summary_file = config.SUMMARIES_DIR / \
            f"{base_name} - extracts-summary.md"
        output_file = config.PDFS_DIR / f"{base_name}.pdf"

        validate_input_file(formatted_file)
        validate_input_file(extracts_summary_file)

        formatted_content = formatted_file.read_text(encoding='utf-8')
        formatted_content = strip_yaml_frontmatter(formatted_content)

        logger.info("Loading extracts-summary materials for PDF...")
        bowen_refs = load_bowen_references(base_name)
        emphasis_items = load_emphasis_items(base_name)
        metadata = _extract_pdf_metadata(extracts_summary_file)

        logger.info("Highlighting transcript for PDF...")
        formatted_html = markdown_to_html(formatted_content)
        formatted_html = re.sub(
            r'<h1>Transcript Formatting[^<]*</h1>\s*', '', formatted_html, flags=re.IGNORECASE)
        # Also remove the title header if present, to match simple_webpage logic
        formatted_html = re.sub(r'^<h1>[^<]+</h1>\s*', '', formatted_html)
        key_term_defs = _extract_key_term_definitions(extracts_summary_file)
        highlighted_html = _highlight_html_content(
            formatted_html, bowen_refs, emphasis_items, key_term_defs)

        logger.info("Generating HTML for PDF...")
        html_content = _generate_html_for_pdf(
            base_name, highlighted_html, metadata)

        config.PDFS_DIR.mkdir(parents=True, exist_ok=True)

        logger.info("Generating PDF...")
        HTML(string=html_content).write_pdf(output_file)
        logger.info(f"✓ PDF generated successfully: {output_file}")
        return True

    except Exception as e:
        logger.error(
            f"An error occurred during PDF generation: {e}", exc_info=True)
        return False

# ============================================================================
# FORMAT VALIDATION
# ============================================================================


def _normalize_word_for_validation(w: str) -> str:
    """Strips punctuation and lowercases for validation comparison."""
    # Explicitly remove markdown symbols before regex
    w = w.replace('#', '').replace('*', '').replace('_', '').replace('`', '')
    # Aggressively strip markdown markers and punctuation from start/end
    w = re.sub(r'^[\W_]+', '', w)
    w = re.sub(r'[\W_]+$', '', w)
    w = re.sub(r"[^\w']+$", "", w)
    return w.lower()


def _compare_transcripts(raw_text: str, formatted_text: str, skip_words: Set[str], max_lookahead: int, max_mismatch_ratio: float, max_mismatches: Optional[int]) -> Dict[str, Any]:
    """Compares raw to formatted transcript, word by word."""
    a_words: List[str] = raw_text.split()

    # Filter B words to only those that have content after normalization
    b_words_raw: List[str] = formatted_text.split()
    b_words: List[str] = []
    b_norm: List[str] = []
    for w in b_words_raw:
        norm = _normalize_word_for_validation(w)
        if norm:
            b_words.append(w)
            b_norm.append(norm)

    a_norm: List[str] = [_normalize_word_for_validation(w) for w in a_words]

    mismatches: List[Dict[str, Any]] = []
    checked = 0
    i = 0
    j = 0
    stopped_reason: Optional[str] = None

    while i < len(a_words):
        a_n = a_norm[i]

        if not a_n or a_n in skip_words:
            i += 1
            continue

        checked += 1

        if j >= len(b_words):
            mismatches.append(
                {"a_index": i, "a_word": a_words[i], "b_index": None, "b_word": None, "reason": "B exhausted"})
            stopped_reason = "B_exhausted"
            break

        if a_n == b_norm[j]:
            i += 1
            j += 1
        else:
            found = False
            for offset in range(1, max_lookahead + 1):
                jj = j + offset
                if jj < len(b_words) and a_n == b_norm[jj]:
                    i += 1
                    j = jj + 1
                    found = True
                    break
            if not found:
                mismatches.append(
                    {"a_index": i, "a_word": a_words[i], "b_index": j, "b_word": b_words[j], "reason": "Not found in lookahead"})
                i += 1

        if checked > 0:
            mismatch_count = len(mismatches)
            mismatch_ratio = mismatch_count / checked
            if max_mismatches is not None and mismatch_count >= max_mismatches:
                stopped_reason = "max_mismatches"
                break
            if mismatch_ratio > max_mismatch_ratio:
                stopped_reason = "mismatch_ratio"
                break

    return {
        "a_word_count": len(a_words),
        "b_word_count": len(b_words),
        "checked_words": checked,
        "mismatch_count": len(mismatches),
        "mismatch_ratio": mismatch_ratio if checked > 0 else 0.0,
        "mismatches": mismatches,
        "stopped_reason": stopped_reason,
    }


def validate_format(raw_filename: str, formatted_filename: Optional[str] = None, skip_words_file: Optional[str] = None, logger=None) -> bool:
    """Orchestrates the format validation process."""
    if logger is None:
        logger = setup_logging('validate_format')
    try:
        raw_file_path = config.SOURCE_DIR / raw_filename
        if formatted_filename:
            formatted_file_path = config.FORMATTED_DIR / formatted_filename
        else:
            stem = Path(raw_filename).stem
            formatted_file_path = config.FORMATTED_DIR / \
                f"{stem} - formatted.md"

        validate_input_file(raw_file_path)
        validate_input_file(formatted_file_path)

        # Use utf-8-sig to handle potential BOM
        raw_text = raw_file_path.read_text(encoding='utf-8-sig')
        formatted_text = formatted_file_path.read_text(encoding='utf-8-sig')

        # Strip YAML if present (in case validating a file that already has it)
        formatted_text = strip_yaml_frontmatter(formatted_text)

        raw_clean = re.sub(
            r'^\s*(\[[\d:.]+\]\s+[^:]+:|Unknown Speaker|Speaker \d+)\s+\d+:\d+', '', raw_text, flags=re.MULTILINE)
        raw_clean = re.sub(r"^\s*Transcribed by\b.*", '',
                           raw_clean, flags=re.MULTILINE)

        formatted_clean, _ = re.subn(
            r"\s+\[sic\](?: \([^)]+\))?", "", formatted_text)
        formatted_clean = re.sub(r'\*\*[^*]+:\*\*\s*', '', formatted_clean)

        # Aggressively remove Markdown headers (lines starting with #)
        formatted_clean = re.sub(
            r'^\s*#+.*$', '', formatted_clean, flags=re.MULTILINE)

        skip_words = set()
        if skip_words_file:
            skip_words = {normalize_text(word) for word in Path(
                skip_words_file).read_text().splitlines() if word and not word.startswith('#')}

        result = _compare_transcripts(
            raw_clean, formatted_clean, skip_words, 3, 0.02, None)

        logger.info("=== Comparison Summary ===")
        for key, value in result.items():
            if key != "mismatches":
                logger.info(f"{key}: {value}")

        if result["mismatch_count"] > 0:
            logger.error("Validation FAILED: Mismatches found.")
            for m in result["mismatches"][:20]:
                logger.error(
                    f"  Mismatch: A[{m['a_index']}]='{m['a_word']}' vs B[{m['b_index']}]='{m.get('b_word')}'")
            return False

        logger.info("Validation PASSED: No mismatches found.")
        return True

    except Exception as e:
        logger.error(
            f"An error occurred during format validation: {e}", exc_info=True)
        return False

# ============================================================================
# ABSTRACT VALIDATION
# ============================================================================


ABSTRACT_VALIDATION_PROMPT = "abstract_quality_assessment_prompt_v2.md"


def _load_extracts_summary_for_abstract(base_name: str) -> tuple[str, str]:
    """Load extracts-summary and extract the abstract."""
    summary_path = config.SUMMARIES_DIR / f"{base_name} - extracts-summary.md"
    validate_input_file(summary_path)
    content = summary_path.read_text(encoding='utf-8')
    abstract_match = re.search(
        r'## (?:\*\*)?Abstract(?:\*\*)?\s*\n\n(.*?)(?=\n---|\n## |\Z)', content, flags=re.DOTALL)
    if not abstract_match:
        raise ValueError(
            f"Could not find ## Abstract section in {summary_path}")
    return content, abstract_match.group(1).strip()


def _extract_scores_from_output(output: str) -> dict:
    """Extract assessment scores from the Claude output."""
    scores = {}

    # Strategy 1: Markdown Table
    # Matches: | Dimension | 4 |  OR  | Dimension | 4/5 |
    table_pattern = r'\|\s*(?:\*\*)?([^\*\|]+?)(?:\*\*)?\s*\|\s*(?:\*\*)?(\d+(?:\.\d+)?)(?:\*\*)?(?:\s*/\s*5)?\s*\|'
    matches = re.findall(table_pattern, output)
    for dimension, score in matches:
        dimension = dimension.strip()
        if dimension and dimension != "Dimension" and "---" not in dimension:
            scores[dimension] = float(score)

    # Strategy 2: List format (e.g. - **Accuracy**: 5/5)
    if not scores:
        list_pattern = r'[-*]\s*(?:\*\*)?([A-Za-z ]+?)(?:\*\*)?:?\s+(\d+(?:\.\d+)?)(?:/5)?'
        matches = re.findall(list_pattern, output)
        for dimension, score in matches:
            scores[dimension.strip()] = float(score)

    # Extract Overall Score (Table or Text)
    # Try table row first
    overall_match = re.search(
        r'\|\s*(?:\*\*)?Overall(?: Score)?(?:\*\*)?\s*\|\s*(?:\*\*)?(\d+(?:\.\d+)?)(?:\*\*)?(?:\s*/\s*5)?\s*\|', output, re.IGNORECASE)
    if overall_match:
        scores['Overall'] = float(overall_match.group(1))
    else:
        # Try text label (e.g. **Overall Score**: 4.5)
        overall_text_match = re.search(
            r'(?:Overall|Total)\s*(?:Score)?\s*[:|-]?\s*(?:\*\*)?\s*(\d+(?:\.\d+)?)', output, re.IGNORECASE)
        if overall_text_match:
            scores['Overall'] = float(overall_text_match.group(1))

    return scores


def _extract_extended_abstract(output: str) -> str:
    """Extract the extended abstract from the validation output."""
    # Try standard markdown header
    match = re.search(
        r'(?:^|\n)#+\s*(?:\*\*)?(?:EXTENDED|REVISED|IMPROVED)?\s*ABSTRACT(?:\*\*)?\s*\n+(.*?)(?=\n#|\Z)', output, flags=re.DOTALL | re.IGNORECASE)

    if not match:
        # Try bold label without header (e.g. **Revised Abstract**:)
        match = re.search(r'(?:\*\*)?(?:EXTENDED|REVISED|IMPROVED)\s*ABSTRACT(?:\*\*)?:?\s*\n+(.*?)(?=\n#|\Z)',
                          output, flags=re.DOTALL | re.IGNORECASE)

    return match.group(1).strip() if match else ""


def _save_abstracts(content: str, base_name: str) -> Path:
    """Save the abstracts validation output."""
    output_path = config.SUMMARIES_DIR / f"{base_name} - abstracts.md"
    config.SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding='utf-8')
    return output_path


def validate_abstract(base_name: str, model: str, target_score: float, max_iterations: int, auto_continue: bool, logger) -> bool:
    """Orchestrates the abstract validation and revision process."""
    if logger is None:
        logger = setup_logging('validate_abstract')

    try:
        logger.info(f"Loading files for: {base_name}")
        transcript = _load_formatted_transcript(f"{base_name} - formatted.md")
        transcript_tokens = estimate_token_count(transcript)
        logger.info(
            f"Transcript length: {len(transcript)} chars (~{transcript_tokens} tokens)")
        _, initial_abstract = _load_extracts_summary_for_abstract(base_name)
        prompt_template = _load_summary_prompt(ABSTRACT_VALIDATION_PROMPT)

        current_abstract = initial_abstract
        best_score = 0
        best_output = ""

        for i in range(max_iterations + 1):
            logger.info(f"--- Iteration {i} ---")
            abstract_tokens = estimate_token_count(current_abstract)
            logger.info(
                f"Current Abstract length: {len(current_abstract)} chars (~{abstract_tokens} tokens)")

            # Provide multiple common keys to ensure template replacement works
            # regardless of what placeholders the prompt file uses
            replacements = {
                "source_document": transcript,
                "transcript": transcript,
                "text": transcript,
                "abstract": current_abstract,
                "current_abstract": current_abstract,
                "Source Document": transcript,
                "Source_Document": transcript,
                "source document": transcript
            }
            prompt = _fill_prompt_template(
                prompt_template, replacements, transcript)

            # Robust fallback: If prompt is shorter than the transcript, replacement definitely failed.
            # We append the documents manually to ensure Claude receives them.
            if transcript not in prompt:
                logger.warning(
                    "Template replacement failed (transcript not found in prompt). Appending documents manually.")
                prompt += f"\n\n--- SOURCE DOCUMENT ---\n{transcript}\n\n--- ABSTRACT TO EVALUATE ---\n{current_abstract}"

            validation_output = _generate_summary_with_claude(
                prompt, model, 0.3, logger)
            scores = _extract_scores_from_output(validation_output)

            if scores:
                logger.info("Detailed Scores:")
                for dimension, score in scores.items():
                    logger.info(f"  - {dimension}: {score}")

            overall_score = scores.get('Overall', 0)
            logger.info(f"Iteration {i} score: {overall_score}")

            if overall_score == 0:
                logger.warning(
                    "⚠️ Failed to extract score. Raw output preview (first 1000 chars):")
                logger.warning(validation_output[:1000])
                logger.warning(
                    "---------------------------------------------------")

            if overall_score > best_score:
                best_score = overall_score
                best_output = validation_output

            if best_score >= target_score:
                logger.info(
                    f"Target score of {target_score} reached. Stopping.")
                break

            if not auto_continue and i < max_iterations:
                logger.info("Auto-continuing to next iteration.")

            current_abstract = _extract_extended_abstract(validation_output)
            if not current_abstract:
                logger.error(
                    "Could not extract extended abstract for next iteration.")
                break

        if best_score == 0:
            logger.error(
                "Validation failed: Could not extract valid scores from model output.")
            return False

        _save_abstracts(best_output, base_name)
        logger.info(
            f"✓ Abstract validation complete. Best score: {best_score}")
        return True

    except ValueError as e:
        # Re-raise configuration errors so they appear in the GUI
        logger.error(f"Configuration error: {e}")
        raise e
    except Exception as e:
        logger.error(
            f"An error occurred during abstract validation: {e}", exc_info=True)
        return False


# ============================================================================
# NEW ABSTRACT GENERATION & VALIDATION
# ============================================================================

def generate_structured_abstract(base_name: str, logger=None) -> bool:
    """
    Generate an abstract using the structured pipeline.
    """
    if logger is None:
        logger = setup_logging('generate_structured_abstract')
    
    try:
        formatted_file = config.FORMATTED_DIR / f"{base_name} - formatted.md"
        extracts_summary_file = config.SUMMARIES_DIR / f"{base_name} - extracts-summary.md"
        
        validate_input_file(formatted_file)
        validate_input_file(extracts_summary_file)
        
        transcript = formatted_file.read_text(encoding='utf-8')
        transcript = strip_yaml_frontmatter(transcript)
        
        extracts_content = extracts_summary_file.read_text(encoding='utf-8')
        extracts_content = strip_yaml_frontmatter(extracts_content)
        
        metadata = parse_filename_metadata(base_name)
        
        # We need to extract the raw markdown for Topics and Key Themes
        # extract_section usually returns the text under the header.
        topics_section = extract_section(extracts_content, 'Topics')
        themes_section = extract_section(extracts_content, 'Key Themes')
        
        if not topics_section or not themes_section:
             logger.error("Could not find Topics or Key Themes in extracts summary.")
             return False

        # Add headers back because abstract_pipeline regex expects them
        # (The regex in abstract_pipeline.py looks for ### Title etc. which might be preserved or not depending on extract_section)
        # Let's check abstract_pipeline.py regex:
        # pattern = r'###\s+(.+?)\n(.+?)\n\*_\(~(\d+)%[^;]+;\s*Sections?\s+([\d\-,\s]+)\)_\*'
        # If extract_section returns just the content, we might need to verify if the ### subheaders are there.
        # Usually extract_section returns everything until the next equal-level header.
        
        abstract_input = abstract_pipeline.prepare_abstract_input(
            metadata=metadata,
            topics_markdown=topics_section,
            themes_markdown=themes_section,
            transcript=transcript
        )
        
        if not abstract_input.topics:
             logger.error("Failed to parse any Topics from extracts summary. Check regex or input format.")
             return False
        
        if not abstract_input.themes:
             logger.warning("Failed to parse any Key Themes from extracts summary.")

        logger.info(f"Parsed {len(abstract_input.topics)} topics and {len(abstract_input.themes)} themes.")
        
        logger.info("Generating abstract via API...")
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
             raise ValueError("ANTHROPIC_API_KEY not set")
             
        client = anthropic.Anthropic(api_key=api_key)
        abstract_text = abstract_pipeline.generate_abstract(abstract_input, client)
        
        # Save abstract
        output_path = config.SUMMARIES_DIR / f"{base_name} - abstract-generated.md"
        output_path.write_text(abstract_text, encoding='utf-8')
        logger.info(f"Generated abstract saved to {output_path}")
        
        return True
    except Exception as e:
        logger.error(f"Error generating structured abstract: {e}", exc_info=True)
        return False


def validate_abstract_coverage(base_name: str, logger=None) -> bool:


    """


    Validate the abstract using the coverage validation module.


    """


    if logger is None:


        logger = setup_logging('validate_abstract_coverage')


        


    try:


        # Load Abstract Input (re-create it)


        formatted_file = config.FORMATTED_DIR / f"{base_name} - formatted.md"


        extracts_summary_file = config.SUMMARIES_DIR / f"{base_name} - extracts-summary.md"


        


        # We need the abstract to validate.


        # Prefer "abstract-generated.md" if exists, otherwise extract from "extracts-summary.md"


        generated_abstract_file = config.SUMMARIES_DIR / f"{base_name} - abstract-generated.md"


        


        if generated_abstract_file.exists():


            abstract_text = generated_abstract_file.read_text(encoding='utf-8')


            logger.info(f"Validating generated abstract from: {generated_abstract_file.name}")


        else:


            _, abstract_text = _load_extracts_summary_for_abstract(base_name)


            logger.info(f"Validating abstract from: {extracts_summary_file.name}")


            


        transcript = formatted_file.read_text(encoding='utf-8')


        transcript = strip_yaml_frontmatter(transcript)


        


        extracts_content = extracts_summary_file.read_text(encoding='utf-8')


        extracts_content = strip_yaml_frontmatter(extracts_content)


        


        metadata = parse_filename_metadata(base_name)


        topics_section = extract_section(extracts_content, 'Topics')


        themes_section = extract_section(extracts_content, 'Key Themes')


        


        abstract_input = abstract_pipeline.prepare_abstract_input(


            metadata=metadata,


            topics_markdown=topics_section,


            themes_markdown=themes_section,


            transcript=transcript


        )


        


        api_key = os.getenv("ANTHROPIC_API_KEY")


        client = anthropic.Anthropic(api_key=api_key) if api_key else None


        


        passed, report = abstract_validation.validate_and_report(


            abstract_text, abstract_input, api_client=client


        )


        


        report_path = config.SUMMARIES_DIR / f"{base_name} - abstract-validation.txt"


        report_path.write_text(report, encoding='utf-8')


        


        logger.info(f"Validation Report saved to {report_path}")


        logger.info(f"Validation Passed: {passed}")


        


        # Log the report content line by line for the GUI
        for line in report.splitlines():
            logger.info(line)
        
        return passed
        
    except Exception as e:
        logger.error(f"Error validating abstract coverage: {e}", exc_info=True)
        return False


def generate_abstract_with_structured_pipeline(base_name: str, logger=None) -> bool:
    """
    Generate an abstract using the structured pipeline. This is a wrapper for generate_structured_abstract.
    """
    return generate_structured_abstract(base_name=base_name, logger=logger)


def validate_abstract_with_structured_pipeline(base_name: str, logger=None) -> bool:
    """
    Validate the abstract using the coverage validation module. This is a wrapper for validate_abstract_coverage.
    """
    return validate_abstract_coverage(base_name=base_name, logger=logger)



# ============================================================================
# NEW SUMMARY GENERATION & VALIDATION
# ============================================================================

def generate_structured_summary(base_name: str, summary_target_word_count: int = 500, gen_summary_logger=None) -> bool:
    """
    Generate a structured summary using the pipeline.
    """
    if gen_summary_logger is None:
        gen_summary_logger = setup_logging('generate_structured_summary')
    
    try:
        # Explicitly cast to int right at the beginning of the function body
        # This will convert summary_target_word_count to int or raise TypeError/ValueError
        try:
            summary_target_word_count = int(summary_target_word_count)
        except (TypeError, ValueError) as e:
            gen_summary_logger.error(f"Error: summary_target_word_count expected to be an integer, but received type {type(summary_target_word_count)} with value '{summary_target_word_count}'. Original error: {e}", exc_info=True)
            return False

        formatted_file = config.FORMATTED_DIR / f"{base_name} - formatted.md"
        extracts_summary_file = config.SUMMARIES_DIR / f"{base_name} - extracts-summary.md"
        
        validate_input_file(formatted_file)
        validate_input_file(extracts_summary_file)
        
        transcript = formatted_file.read_text(encoding='utf-8')
        transcript = strip_yaml_frontmatter(transcript)
        
        extracts_content = extracts_summary_file.read_text(encoding='utf-8')
        extracts_content = strip_yaml_frontmatter(extracts_content)
        
        metadata = parse_filename_metadata(base_name)
        
        # Extract sections
        topics_section = extract_section(extracts_content, 'Topics')
        themes_section = extract_section(extracts_content, 'Key Themes')
        
        if not topics_section:
             gen_summary_logger.error("Could not find Topics in extracts summary.")
             return False
        
        # DEBUG statements to diagnose TypeError
        gen_summary_logger.info(f"DEBUG: In generate_structured_summary:")
        gen_summary_logger.info(f"DEBUG:   Type of summary_target_word_count (after cast): {type(summary_target_word_count)}")
        gen_summary_logger.info(f"DEBUG:   Value of summary_target_word_count (after cast): {summary_target_word_count}")
        gen_summary_logger.info(f"DEBUG:   Type of gen_summary_logger (param): {type(gen_summary_logger)}")
        gen_summary_logger.info(f"DEBUG:   Value of gen_summary_logger (param): {gen_summary_logger}")
             
        summary_input = summary_pipeline.prepare_summary_input(
            metadata=metadata,
            topics_markdown=topics_section,
            themes_markdown=themes_section,
            transcript=transcript,
            word_count_for_allocation=summary_target_word_count
        )
        
        # Logging for GUI feedback
        topic_count = len(summary_input.body.topics)
        theme_count = len(summary_input.themes)
        
        if not topic_count:
             gen_summary_logger.error("Failed to parse any Topics from extracts summary. Check regex or input format.")
             return False
             
        gen_summary_logger.info(f"Parsed {topic_count} topics and {theme_count} themes for summary.")
        if theme_count == 0:
            gen_summary_logger.warning("No themes parsed. Summary will lack thematic weaving.")
            
        gen_summary_logger.info("Generating summary via API...")
        
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
             raise ValueError("ANTHROPIC_API_KEY not set")
             
        client = anthropic.Anthropic(api_key=api_key)
        summary_text = summary_pipeline.generate_summary(summary_input, client)
        
        # Save summary
        output_path = config.SUMMARIES_DIR / f"{base_name} - summary-generated.md"
        output_path.write_text(summary_text, encoding='utf-8')
        gen_summary_logger.info(f"Generated summary saved to {output_path}")
        
        return True
    except Exception as e:
        gen_summary_logger.error(f"Error generating structured summary: {e}", exc_info=True)
        return False


def validate_summary_coverage(base_name: str, logger=None) -> bool:
    """
    Validate the summary using the coverage validation module.
    """
    if logger is None:
        logger = setup_logging('validate_summary_coverage')
        
    try:
        # Load inputs
        formatted_file = config.FORMATTED_DIR / f"{base_name} - formatted.md"
        extracts_summary_file = config.SUMMARIES_DIR / f"{base_name} - extracts-summary.md"
        generated_summary_file = config.SUMMARIES_DIR / f"{base_name} - summary-generated.md"
        
        if generated_summary_file.exists():
            summary_text = generated_summary_file.read_text(encoding='utf-8')
            logger.info(f"Validating generated summary from: {generated_summary_file.name}")
        else:
            logger.error("No generated summary found to validate. Run 'Gen Summary' first.")
            return False
            
        transcript = formatted_file.read_text(encoding='utf-8')
        transcript = strip_yaml_frontmatter(transcript)
        
        extracts_content = extracts_summary_file.read_text(encoding='utf-8')
        extracts_content = strip_yaml_frontmatter(extracts_content)
        
        metadata = parse_filename_metadata(base_name)
        topics_section = extract_section(extracts_content, 'Topics')
        themes_section = extract_section(extracts_content, 'Key Themes')
        
        # Re-prepare input to get the checklist
        summary_input = summary_pipeline.prepare_summary_input(
            metadata=metadata,
            topics_markdown=topics_section,
            themes_markdown=themes_section,
            transcript=transcript
        )
        
        # Log input stats to help debug validation failures
        logger.info(f"Validation Input: {len(summary_input.body.topics)} topics, {len(summary_input.themes)} themes parsed from source.")
        
        api_key = os.getenv("ANTHROPIC_API_KEY")
        client = anthropic.Anthropic(api_key=api_key) if api_key else None
        
        passed, report = summary_validation.validate_and_report(
            summary_text, summary_input, api_client=client
        )
        
        report_path = config.SUMMARIES_DIR / f"{base_name} - summary-validation.txt"
        report_path.write_text(report, encoding='utf-8')
        
        logger.info(f"Validation Report saved to {report_path}")
        logger.info(f"Validation Passed: {passed}")
        
        for line in report.splitlines():
            logger.info(line)
        
        return passed
        
    except Exception as e:
        logger.error(f"Error validating summary coverage: {e}", exc_info=True)
        return False
