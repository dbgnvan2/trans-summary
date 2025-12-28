"""
Core pipeline logic for the transcript processing application.
This module consolidates the business logic for each step of the pipeline,
making it reusable by both the GUI and the CLI scripts.
"""

import summary_validation
import summary_pipeline
import abstract_validation
import abstract_pipeline
import html_generator
from transcript_utils import (
    call_claude_with_retry,
    validate_input_file,
    setup_logging,
    normalize_text,
    extract_emphasis_items,
    strip_yaml_frontmatter,
    parse_filename_metadata,
    load_emphasis_items,
    find_text_in_content,
    extract_section,
    extract_bowen_references,
    estimate_token_count,
    check_token_budget,  # <--- Added this import
)
import anthropic
import os
import re
import threading
import time
from pathlib import Path
from difflib import SequenceMatcher
from typing import Set, Dict, List, Optional, Any

import config
from dotenv import load_dotenv
load_dotenv()


def strip_sic_annotations(text: str) -> tuple[str, int]:
    """Removes [sic] annotations and returns the cleaned text and count."""
    # This pattern handles [sic] optionally followed by a parenthetical correction,
    # surrounded by any whitespace. It replaces the entire annotation with a single space
    # to prevent accidentally joining words.
    pattern = r"\s*\[sic\](?:\s*\([^)]*\))?\s*"
    cleaned_text, count = re.subn(pattern, " ", text)
    return cleaned_text, count


def load_prompt() -> str:
    """Load the formatting prompt template."""
    prompts_dir = config.TRANSCRIPTS_BASE / "prompts"
    prompt_path = prompts_dir / config.PROMPT_FORMATTING_FILENAME

    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path}\n"
            f"Expected location: {prompts_dir}/{config.PROMPT_FORMATTING_FILENAME}"
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
        max_tokens=config.MAX_TOKENS_FORMATTING,
        stream=True,
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

        # Construct full prompt to check token budget before API call
        full_prompt_for_budget_check = f"{prompt_template}\n\n---\n\nRAW TRANSCRIPT:\n\n{raw_transcript}"
        # This should match max_tokens in format_transcript_with_claude
        MAX_TOKENS_FOR_FORMATTING = config.MAX_TOKENS_FORMATTING

        if not check_token_budget(full_prompt_for_budget_check, MAX_TOKENS_FOR_FORMATTING, logger):
            logger.error(
                "Token budget exceeded for formatting. Aborting API call.")
            return False

        formatted_content = format_transcript_with_claude(
            raw_transcript, prompt_template, model=model, logger=logger)

        # Strip [sic] annotations from the formatted content before saving.
        formatted_content, sic_count = strip_sic_annotations(formatted_content)
        if sic_count > 0 and logger:
            logger.info(f"Removed {sic_count} [sic] annotation(s).")

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


def _extract_emphasis_quotes(topics_themes_file):
    """Extract all quoted text from Emphasized Items section."""
    extracts_path = Path(topics_themes_file)
    stem = extracts_path.stem.replace(' - topics-themes', '')
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


def _generate_summary_with_claude(prompt: str, model: str, temperature: float, logger, min_length: int = 50, min_words: int = 0) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set.")
    client = anthropic.Anthropic(api_key=api_key)

    message = call_claude_with_retry(
        client=client,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=32000,
        temperature=temperature,
        stream=True,
        min_length=min_length,
        min_words=min_words,
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
    if stem.endswith(' - yaml'):
        stem = stem[:-7]
    output_filename = f"{stem} - {summary_type}.md"
    output_path = config.SUMMARIES_DIR / output_filename
    config.SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding='utf-8')
    return output_path


def _split_topics_themes(topics_themes_path: Path, logger):
    """Split topics-themes into focused extract files."""
    logger.info("Processing generated Key Items...")
    content = topics_themes_path.read_text(encoding='utf-8')
    clean_content = strip_yaml_frontmatter(content)
    stem = topics_themes_path.stem.replace(' - topics-themes', '')

    bowen_refs = extract_bowen_references(clean_content)
    if bowen_refs:
        bowen_output = "## Bowen References\n\n" + \
            "\n\n".join(
                [f'> **{label}:** "{quote}"' for label, quote in bowen_refs])
        bowen_path = config.SUMMARIES_DIR / f"{stem} - bowen-references.md"
        bowen_path.write_text(bowen_output, encoding='utf-8')
        logger.info(
            f"  ✓ {len(bowen_refs)} Bowen references → {bowen_path.name}")

    emphasis_items = extract_emphasis_items(clean_content)
    if emphasis_items:
        emphasis_output = "## Emphasized Items\n\n" + \
            "\n\n".join(
                [f'> **{label}:** "{quote}"' for label, quote in emphasis_items])
        emphasis_path = config.SUMMARIES_DIR / f"{stem} - emphasis-items.md"
        emphasis_path.write_text(emphasis_output, encoding='utf-8')
        logger.info(
            f"  ✓ {len(emphasis_items)} emphasis items → {emphasis_path.name}")


def summarize_transcript(formatted_filename: str, model: str, focus_keyword: str, target_audience: str,
                         skip_extracts_summary: bool, skip_terms: bool, skip_blog: bool,
                         generate_structured: bool = False, structured_word_count: int = config.DEFAULT_SUMMARY_WORD_COUNT, logger=None) -> bool:
    """Orchestrates the transcript summarization process."""
    if logger is None:
        logger = setup_logging('summarize_transcript')

    try:
        # Explicitly cast to int right at the beginning of the function body
        # This will convert structured_word_count to int or raise TypeError/ValueError
        try:
            structured_word_count = int(structured_word_count)
        except (TypeError, ValueError) as e:
            logger.error(
                f"Error: structured_word_count expected to be an integer or a string representing an integer, but received type {type(structured_word_count)} with value '{structured_word_count}'. Original error: {e}", exc_info=True)
            return False

        if not config.SOURCE_DIR.exists():
            raise FileNotFoundError(
                f"Source directory not found: {config.SOURCE_DIR}")

        logger.info(
            f"Loading formatted transcript: {formatted_filename}")
        transcript = _load_formatted_transcript(formatted_filename)
        transcript_word_count = len(transcript.split())
        metadata = parse_filename_metadata(formatted_filename)
        logger.info(f"Transcript metadata: {metadata}")

        topics_themes_path = None

        if not skip_extracts_summary:
            logger.info(
                "PART 1: Generating Key Items (Topics, Themes, Emphasis)...")
            prompt_template = _load_summary_prompt(
                config.PROMPT_EXTRACTS_FILENAME)
            prompt = _fill_prompt_template(
                prompt_template, metadata, transcript, target_audience=target_audience)

            # Calculate target length to guide the model
            target_words = int(transcript_word_count *
                               config.TARGET_EXTRACTS_PERCENT)
            if target_words < 200:
                target_words = 200
            prompt += f"\n\nIMPORTANT: Please ensure your response is concise and approximately {target_words} words in length. Focus on extracting only the most critical information."

            # Extracts summary should be substantial, about 7% of transcript word count.
            # We set a validation floor of 4% to allow for concise but valid summaries.
            min_expected_words = int(
                transcript_word_count * config.MIN_EXTRACTS_PERCENT)
            # Ensure reasonable bounds (at least 150 words unless transcript is tiny)
            min_expected_words = max(
                min_expected_words, config.MIN_EXTRACTS_WORDS_FLOOR) if transcript_word_count > config.MIN_TRANSCRIPT_WORDS_FOR_FLOOR else config.MIN_EXTRACTS_WORDS_ABSOLUTE

            output = _generate_summary_with_claude(
                prompt, model, 0.2, logger, min_length=config.MIN_EXTRACTS_CHARS, min_words=min_expected_words)

            topics_themes_path = _save_summary(
                output, formatted_filename, "topics-themes")
            output_words = len(output.split())
            logger.info(
                f"✓ Topics-Themes analysis saved ({output_words:,} words) to: {topics_themes_path}")
            _split_topics_themes(
                topics_themes_path, logger)
        else:
            base_name_from_formatted = Path(
                formatted_filename).stem.replace(' - formatted', '')
            potential_topics_themes_path = config.SUMMARIES_DIR / \
                f"{base_name_from_formatted} - topics-themes.md"
            if potential_topics_themes_path.exists():
                topics_themes_path = potential_topics_themes_path
                logger.info(
                    f"Skipping topics-themes generation, using existing file: {topics_themes_path}")

        if not skip_terms:
            logger.info("PART 2: Extracting Key Terms...")
            prompt_template = _load_summary_prompt(
                config.PROMPT_KEY_TERMS_FILENAME)
            prompt = _fill_prompt_template(
                prompt_template, metadata, transcript)
            output = _generate_summary_with_claude(
                prompt, model, 0.4, logger, min_length=config.MIN_KEY_TERMS_CHARS)
            key_terms_path = _save_summary(
                output, formatted_filename, "key-terms")
            logger.info(
                f"✓ Key terms document saved to: {key_terms_path}")

        if not skip_blog:
            logger.info("PART 3: Generating Blog Post...")
            prompt_template = _load_summary_prompt(config.PROMPT_BLOG_FILENAME)
            prompt = _fill_prompt_template(
                prompt_template, metadata, transcript, focus_keyword=focus_keyword, target_audience=target_audience)
            output = _generate_summary_with_claude(
                prompt, model, 0.3, logger, min_length=config.MIN_BLOG_CHARS)
            blog_path = _save_summary(output, formatted_filename, "blog")
            logger.info(f"✓ Blog post saved to: {blog_path}")

        logger.info("✓ Transcript processing complete!")

        if not skip_extracts_summary:  # Only validate emphasis if extracts were generated or explicitly not skipped
            logger.info("VALIDATION: Checking Emphasis Items...")
            formatted_path = config.FORMATTED_DIR / formatted_filename
            if topics_themes_path:
                _validate_emphasis_items(
                    formatted_path, topics_themes_path, logger)

        if generate_structured:
            if topics_themes_path:
                logger.info("Generating structured summary...")
                # The generate_structured_summary function expects base_name
                base_name = Path(formatted_filename).stem.replace(
                    ' - formatted', '')

                # word_count_for_generation = int(structured_word_count) # Removed explicit cast here

                structured_success = generate_structured_summary(
                    base_name=base_name,
                    summary_target_word_count=structured_word_count,  # Use the directly cast variable
                    logger=logger
                )
                if structured_success:
                    logger.info(
                        "Structured summary generation complete. Validating structured summary...")
                    validate_summary_coverage(
                        base_name=base_name, logger=logger)
                else:
                    logger.error(
                        "Structured summary generation failed.")
                    return False
            else:
                logger.warning(
                    "Cannot generate structured summary: topics-themes was skipped or not found.")

        return True

    except ValueError as e:
        # Re-raise configuration errors so they appear in the GUI
        logger.error(f"Configuration error: {e}")
        raise e
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
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

        output_path = config.FORMATTED_DIR / f"{meta['stem']} - yaml.md"
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

from html_generator import generate_webpage
# ============================================================================
# SIMPLE WEBPAGE GENERATION
# ============================================================================


from html_generator import generate_simple_webpage
# PDF GENERATION
# ============================================================================


from html_generator import generate_pdf
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
            # Bidirectional Lookahead Strategy to handle insertions/deletions robustly

            # 1. Lookahead in B (Insertion in B / Deletion in A)
            b_match_offset = None
            for offset in range(1, max_lookahead + 1):
                if j + offset < len(b_words) and a_n == b_norm[j + offset]:
                    b_match_offset = offset
                    break

            # 2. Lookahead in A (Insertion in A / Deletion in B)
            a_match_offset = None
            for offset in range(1, max_lookahead + 1):
                if i + offset < len(a_norm) and b_norm[j] == a_norm[i + offset]:
                    a_match_offset = offset
                    break

            action = "mismatch"

            if b_match_offset is not None and a_match_offset is None:
                action = "skip_b"
            elif a_match_offset is not None and b_match_offset is None:
                action = "skip_a"
            elif b_match_offset is not None and a_match_offset is not None:
                # Both found. Use next-word match as tie-breaker.
                # Path 1: Skip B. Next comparison: A[i+1] vs B[j+b_off+1]
                path1_score = 0
                if i + 1 < len(a_norm) and j + b_match_offset + 1 < len(b_words):
                    if a_norm[i+1] == b_norm[j + b_match_offset + 1]:
                        path1_score = 1

                # Path 2: Skip A. Next comparison: A[i+a_off+1] vs B[j+1]
                path2_score = 0
                if i + a_match_offset + 1 < len(a_norm) and j + 1 < len(b_words):
                    if a_norm[i + a_match_offset + 1] == b_norm[j+1]:
                        path2_score = 1

                if path1_score > path2_score:
                    action = "skip_b"
                elif path2_score > path1_score:
                    action = "skip_a"
                else:
                    # Secondary tie-breaker: prefer smaller offset
                    if b_match_offset <= a_match_offset:
                        action = "skip_b"
                    else:
                        action = "skip_a"

            # Execute action
            if action == "skip_b":
                # B has extra words (insertions). Advance J to skip them.
                j += b_match_offset
                # Next iteration will match A[i] == B[j]
            elif action == "skip_a":
                # A has extra words (deletions in B). Record mismatches and advance I.
                for k in range(a_match_offset):
                    mismatches.append(
                        {"a_index": i+k, "a_word": a_words[i+k], "b_index": j, "b_word": b_words[j], "reason": "Skipped in A (deletion in B)"})
                i += a_match_offset
                # Next iteration will match A[i] == B[j]
            else:
                # True mismatch
                mismatches.append(
                    {"a_index": i, "a_word": a_words[i], "b_index": j, "b_word": b_words[j], "reason": "Mismatch"})
                i += 1

        if checked > 0:
            mismatch_count = len(mismatches)
            mismatch_ratio = mismatch_count / checked
            if max_mismatches is not None and mismatch_count >= max_mismatches:
                stopped_reason = "max_mismatches"
                break
            # Only enforce ratio check after checking at least 20% of the source text
            if checked > len(a_words) * 0.2 and mismatch_ratio > max_mismatch_ratio:
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
            r'^\s*(\[[\d:.]+\]\s+[^:]+:|Unknown Speaker|Speaker \d+)\s+\d+:\d+(?::\d+)?', '', raw_text, flags=re.MULTILINE)
        raw_clean = re.sub(r"^\s*Transcribed by\b.*", '',
                           raw_clean, flags=re.MULTILINE)

        # Aggressively remove timestamps
        # Matches 10:00, 1:00:00, 0:00 with optional brackets/parens and optional am/pm
        raw_clean = re.sub(
            r'[\[\(]?\b\d+:\d{2}(?::\d{2})?(?:[ap]m)?[\]\)]?', ' ', raw_clean, flags=re.IGNORECASE)
        # Remove headless timestamps (e.g., :00, :02) often found in artifacts
        raw_clean = re.sub(r'(?:^|\s)[\[\(]?:\d{2}\b[\]\)]?', ' ', raw_clean)

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

        # Increased lookahead to handle longer deleted phrases/duplicates
        result = _compare_transcripts(
            raw_clean, formatted_clean, skip_words, config.VALIDATION_LOOKAHEAD_WINDOW, 0.05, None)

        logger.info("=== Comparison Summary ===")
        for key, value in result.items():
            if key != "mismatches":
                logger.info(f"{key}: {value}")

        # Allow small mismatch ratio for passing (defined in config)
        if result["mismatch_ratio"] > config.VALIDATION_MISMATCH_RATIO:
            logger.error(
                f"Validation FAILED: Mismatch ratio {result['mismatch_ratio']:.2%} exceeds limit ({config.VALIDATION_MISMATCH_RATIO:.1%}).")
            for m in result["mismatches"][:20]:
                logger.error(
                    f"  Mismatch ({m.get('reason', 'Unknown')}): A[{m['a_index']}]='{m['a_word']}' vs B[{m['b_index']}]='{m.get('b_word')}'")
            return False

        if result["mismatch_count"] > 0:
            logger.warning(
                f"Validation PASSED with warnings: {result['mismatch_count']} mismatches ({result['mismatch_ratio']:.2%}).")
            for m in result["mismatches"][:10]:
                logger.warning(
                    f"  Ignored Mismatch ({m.get('reason', 'Unknown')}): A[{m['a_index']}]='{m['a_word']}' vs B[{m['b_index']}]='{m.get('b_word')}'")
        else:
            logger.info("Validation PASSED: No mismatches found.")

        return True

    except Exception as e:
        logger.error(
            f"An error occurred during format validation: {e}", exc_info=True)
        return False

# ============================================================================
# ABSTRACT VALIDATION
# ============================================================================


def _load_extracts_summary_for_abstract(base_name: str) -> tuple[str, str]:
    """Load topics-themes and extract the abstract."""
    summary_path = config.SUMMARIES_DIR / f"{base_name} - topics-themes.md"
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
        prompt_template = _load_summary_prompt(
            config.PROMPT_ABSTRACT_VALIDATION_FILENAME)

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
                prompt, model, 0.3, logger, min_length=config.MIN_ABSTRACT_VALIDATION_CHARS)
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
        topics_themes_file = config.SUMMARIES_DIR / \
            f"{base_name} - topics-themes.md"

        validate_input_file(formatted_file)
        validate_input_file(topics_themes_file)

        transcript = formatted_file.read_text(encoding='utf-8')
        transcript = strip_yaml_frontmatter(transcript)

        extracts_content = topics_themes_file.read_text(encoding='utf-8')
        extracts_content = strip_yaml_frontmatter(extracts_content)

        metadata = parse_filename_metadata(base_name)

        # We need to extract the raw markdown for Topics and Key Themes
        # extract_section usually returns the text under the header.
        topics_section = extract_section(extracts_content, 'Topics')
        themes_section = extract_section(extracts_content, 'Key Themes')

        if not topics_section or not themes_section:
            logger.error(
                "Could not find Topics or Key Themes in topics-themes.")
            return False

        # Add headers back because abstract_pipeline regex expects them
        # (The regex in abstract_pipeline.py looks for ### Title etc. which might be preserved or not depending on extract_section)
        # Let's check abstract_pipeline.py regex:
        # pattern = r'###\s+(.+?)\n(.+?)\n\*_\(~(\d+)%[^;]+;\s*Sections?\s+([\d\-,\s]+)\)_\*'
        # If extract_section returns just the content, we might need to verify if the ### subheaders are there.
        # Usually extract_section returns everything until the next equal-level header.

        # Calculate target word count (3% of transcript, min 150)
        transcript_words = len(transcript.split())
        target_word_count = max(
            int(transcript_words * config.ABSTRACT_TARGET_PERCENT), config.ABSTRACT_MIN_WORDS)

        abstract_input = abstract_pipeline.prepare_abstract_input(
            metadata=metadata,
            topics_markdown=topics_section,
            themes_markdown=themes_section,
            transcript=transcript,
            target_word_count=target_word_count
        )

        if not abstract_input.topics:
            logger.error(
                "Failed to parse any Topics from topics-themes. Check regex or input format.")
            return False

        if not abstract_input.themes:
            logger.warning(
                "Failed to parse any Key Themes from topics-themes.")

        logger.info(
            f"Parsed {len(abstract_input.topics)} topics and {len(abstract_input.themes)} themes.")

        logger.info("Generating abstract via API...")
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        client = anthropic.Anthropic(api_key=api_key)
        abstract_text = abstract_pipeline.generate_abstract(
            abstract_input, client)

        # Save abstract
        output_path = config.SUMMARIES_DIR / \
            f"{base_name} - abstract-generated.md"
        output_path.write_text(abstract_text, encoding='utf-8')
        logger.info(f"Generated abstract saved to {output_path}")

        return True
    except Exception as e:
        logger.error(
            f"Error generating structured abstract: {e}", exc_info=True)
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

        topics_themes_file = config.SUMMARIES_DIR / \
            f"{base_name} - topics-themes.md"

        # We need the abstract to validate.

        # Prefer "abstract-generated.md" if exists, otherwise extract from "extracts-summary.md"

        generated_abstract_file = config.SUMMARIES_DIR / \
            f"{base_name} - abstract-generated.md"

        if generated_abstract_file.exists():

            abstract_text = generated_abstract_file.read_text(encoding='utf-8')

            logger.info(
                f"Validating generated abstract from: {generated_abstract_file.name}")

        else:

            _, abstract_text = _load_extracts_summary_for_abstract(base_name)

            logger.info(
                f"Validating abstract from: {topics_themes_file.name}")

        transcript = formatted_file.read_text(encoding='utf-8')

        transcript = strip_yaml_frontmatter(transcript)

        extracts_content = topics_themes_file.read_text(encoding='utf-8')

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

        report_path = config.SUMMARIES_DIR / \
            f"{base_name} - abstract-validation.txt"

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

def generate_structured_summary(base_name: str, summary_target_word_count: int = config.DEFAULT_SUMMARY_WORD_COUNT, logger=None) -> bool:
    """
    Generate a structured summary using the pipeline.
    """
    if logger is None:
        logger = setup_logging('generate_structured_summary')

    try:
        # Explicitly cast to int right at the beginning of the function body
        # This will convert summary_target_word_count to int or raise TypeError/ValueError
        try:
            summary_target_word_count = int(summary_target_word_count)
        except (TypeError, ValueError) as e:
            logger.error(
                f"Error: summary_target_word_count expected to be an integer, but received type {type(summary_target_word_count)} with value '{summary_target_word_count}'. Original error: {e}", exc_info=True)
            return False

        formatted_file = config.FORMATTED_DIR / f"{base_name} - formatted.md"
        topics_themes_file = config.SUMMARIES_DIR / \
            f"{base_name} - topics-themes.md"

        validate_input_file(formatted_file)
        validate_input_file(topics_themes_file)

        transcript = formatted_file.read_text(encoding='utf-8')
        transcript = strip_yaml_frontmatter(transcript)

        extracts_content = topics_themes_file.read_text(encoding='utf-8')
        extracts_content = strip_yaml_frontmatter(extracts_content)

        metadata = parse_filename_metadata(base_name)

        # Extract sections
        topics_section = extract_section(extracts_content, 'Topics')
        themes_section = extract_section(extracts_content, 'Key Themes')

        if not topics_section:
            logger.error(
                "Could not find Topics in topics-themes.")
            return False

        # DEBUG statements to diagnose TypeError
        logger.info(f"DEBUG: In generate_structured_summary:")
        logger.info(
            f"DEBUG:   Type of summary_target_word_count (after cast): {type(summary_target_word_count)}")
        logger.info(
            f"DEBUG:   Value of summary_target_word_count (after cast): {summary_target_word_count}")
        logger.info(
            f"DEBUG:   Type of logger (param): {type(logger)}")
        logger.info(
            f"DEBUG:   Value of logger (param): {logger}")

        summary_input = summary_pipeline.prepare_summary_input(
            metadata=metadata,
            topics_markdown=topics_section,
            themes_markdown=themes_section,
            transcript=transcript,
            target_word_count=summary_target_word_count
        )

        # Logging for GUI feedback
        topic_count = len(summary_input.body.topics)
        theme_count = len(summary_input.themes)

        if not topic_count:
            logger.error(
                "Failed to parse any Topics from topics-themes. Check regex or input format.")
            return False

        logger.info(
            f"Parsed {topic_count} topics and {theme_count} themes for summary.")
        if theme_count == 0:
            logger.warning(
                "No themes parsed. Summary will lack thematic weaving.")

        logger.info("Generating summary via API...")

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        client = anthropic.Anthropic(api_key=api_key)
        summary_text = summary_pipeline.generate_summary(summary_input, client)

        # Save summary
        output_path = config.SUMMARIES_DIR / \
            f"{base_name} - summary-generated.md"
        output_path.write_text(summary_text, encoding='utf-8')
        logger.info(f"Generated summary saved to {output_path}")

        return True
    except Exception as e:
        logger.error(
            f"Error generating structured summary: {e}", exc_info=True)
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
        topics_themes_file = config.SUMMARIES_DIR / \
            f"{base_name} - topics-themes.md"
        generated_summary_file = config.SUMMARIES_DIR / \
            f"{base_name} - summary-generated.md"

        if generated_summary_file.exists():
            summary_text = generated_summary_file.read_text(encoding='utf-8')
            logger.info(
                f"Validating generated summary from: {generated_summary_file.name}")
        else:
            logger.error(
                "No generated summary found to validate. Run 'Gen Summary' first.")
            return False

        transcript = formatted_file.read_text(encoding='utf-8')
        transcript = strip_yaml_frontmatter(transcript)

        extracts_content = topics_themes_file.read_text(encoding='utf-8')
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
        logger.info(
            f"Validation Input: {len(summary_input.body.topics)} topics, {len(summary_input.themes)} themes parsed from source.")

        api_key = os.getenv("ANTHROPIC_API_KEY")
        client = anthropic.Anthropic(api_key=api_key) if api_key else None

        passed, report = summary_validation.validate_and_report(
            summary_text, summary_input, api_client=client
        )

        report_path = config.SUMMARIES_DIR / \
            f"{base_name} - summary-validation.txt"
        report_path.write_text(report, encoding='utf-8')

        logger.info(f"Validation Report saved to {report_path}")
        logger.info(f"Validation Passed: {passed}")

        for line in report.splitlines():
            logger.info(line)

        return passed

    except Exception as e:
        logger.error(f"Error validating summary coverage: {e}", exc_info=True)
        return False
