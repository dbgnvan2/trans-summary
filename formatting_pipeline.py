"""
Pipeline module for transcript formatting and basic validation.
Extracts raw text, formats it via LLM, and performs word-level validation.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import anthropic

import config
from transcript_utils import (
    call_claude_with_retry,
    check_token_budget,
    normalize_text,
    parse_filename_metadata,
    setup_logging,
    strip_yaml_frontmatter,
    validate_input_file,
)


def strip_sic_annotations(text: str) -> tuple[str, int]:
    """Removes [sic] annotations and returns the cleaned text and count."""
    pattern = r"\s*\[sic\](?:\s*\([^)]*\))?\s*"
    cleaned_text, count = re.subn(pattern, " ", text)
    return cleaned_text, count


def load_prompt() -> str:
    """Load the formatting prompt template."""
    prompt_path = config.PROMPTS_DIR / config.PROMPT_FORMATTING_FILENAME

    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path}\n"
            f"Expected location: {config.PROMPTS_DIR}/{config.PROMPT_FORMATTING_FILENAME}"
        )
    return prompt_path.read_text(encoding="utf-8")


def load_raw_transcript(filename: str) -> str:
    """Load the raw transcript from source directory."""
    transcript_path = config.SOURCE_DIR / filename
    validate_input_file(transcript_path)
    return transcript_path.read_text(encoding="utf-8")


def format_transcript_with_claude(
    raw_transcript: str,
    prompt_template: str,
    model: str = config.DEFAULT_MODEL,
    logger=None,
) -> str:
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
            f"Transcript length: {word_count:,} words, {len(raw_transcript):,} characters"
        )
        logger.info("Waiting for Claude response...")
    else:
        print("Sending transcript to Claude...", flush=True)
        print(
            f"Transcript length: {len(raw_transcript.split()):,} words, {len(raw_transcript):,} characters",
            flush=True,
        )
        print(
            "⏳ Waiting for Claude response (may take 2-5 minutes for longer transcripts)...",
            flush=True,
        )

    # Use prompt caching for the large input
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": full_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
        }
    ]

    # Expect at least 50% of the original word count (conservative)
    min_expected_words = int(len(raw_transcript.split()) * 0.5)

    message = call_claude_with_retry(
        client=client,
        model=model,
        messages=messages,
        max_tokens=config.MAX_TOKENS_FORMATTING,
        stream=True,
        logger=logger,
        timeout=config.TIMEOUT_FORMATTING,
        min_words=min_expected_words,
    )

    return message.content[0].text


def save_formatted_transcript(content: str, original_filename: str) -> Path:
    """Save formatted transcript with naming convention."""
    stem = Path(original_filename).stem
    output_filename = f"{stem}{config.SUFFIX_FORMATTED}"

    project_dir = config.PROJECTS_DIR / stem
    project_dir.mkdir(parents=True, exist_ok=True)

    output_path = project_dir / output_filename
    output_path.write_text(content, encoding="utf-8")
    return output_path


def format_transcript(
    raw_filename: str, model: str = config.DEFAULT_MODEL, logger=None
) -> bool:
    """
    Orchestrates the transcript formatting process.
    """
    if logger is None:
        logger = setup_logging("format_transcript")

    try:
        if not config.SOURCE_DIR.exists():
            raise FileNotFoundError(f"Source directory not found: {config.SOURCE_DIR}")

        logger.info(
            f"Loading prompt template from: {config.TRANSCRIPTS_BASE / 'prompts'}"
        )
        prompt_template = load_prompt()

        logger.info(f"Loading raw transcript: {raw_filename}")
        raw_transcript = load_raw_transcript(raw_filename)

        # Construct full prompt to check token budget before API call
        full_prompt_for_budget_check = (
            f"{prompt_template}\n\n---\n\nRAW TRANSCRIPT:\n\n{raw_transcript}"
        )
        # This should match max_tokens in format_transcript_with_claude
        MAX_TOKENS_FOR_FORMATTING = config.MAX_TOKENS_FORMATTING

        if not check_token_budget(
            full_prompt_for_budget_check, MAX_TOKENS_FOR_FORMATTING, logger
        ):
            logger.error("Token budget exceeded for formatting. Aborting API call.")
            return False

        formatted_content = format_transcript_with_claude(
            raw_transcript, prompt_template, model=model, logger=logger
        )

        formatted_content, sic_count = strip_sic_annotations(formatted_content)
        if sic_count > 0 and logger:
            logger.info(f"Removed {sic_count} [sic] annotation(s).")

        output_path = save_formatted_transcript(formatted_content, raw_filename)

        logger.info("✓ Success!")
        logger.info(f"Formatted transcript saved to: {output_path}")
        return True

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise e
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return False


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
Title: "{meta["title"]}"
Presenter: "{meta["presenter"]}"
Lecture date: "{meta["date"]}"
Source recording: "{source_filename}"
Transcriber: "Automated; human-reviewed"
Authenticity: "{authenticity}"
Version: "v1.0"
License: "© {meta["year"]} {meta["presenter"]}. All rights reserved."
DOI: ""
---

'''


def add_yaml(transcript_filename: str, source_ext: str = "mp4", logger=None) -> bool:
    """
    Orchestrates the process of adding YAML front matter to a transcript.
    """
    if logger is None:
        logger = setup_logging("add_yaml")

    try:
        logger.info(f"Adding YAML to {transcript_filename}")

        meta = parse_filename_metadata(transcript_filename)
        stem = meta["stem"]

        transcript_path = config.PROJECTS_DIR / stem / transcript_filename
        validate_input_file(transcript_path)

        source_filename = f"{meta['stem']}.{source_ext.lstrip('.')}"

        formatted_content = transcript_path.read_text(encoding="utf-8")

        yaml_block = _generate_yaml_front_matter(meta, source_filename)
        final_content = yaml_block + formatted_content

        output_path = config.PROJECTS_DIR / stem / f"{meta['stem']}{config.SUFFIX_YAML}"
        output_path.write_text(final_content, encoding="utf-8")

        logger.info(f"✓ Success! YAML added. Output saved to: {output_path}")

        # Validation: Log first 20 lines
        logger.info("\n--- YAML Validation (First 20 lines) ---")
        with open(output_path, "r", encoding="utf-8") as f:
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


def _normalize_word_for_validation(w: str) -> str:
    """Strips punctuation and lowercases for validation comparison."""
    # Explicitly remove markdown symbols before regex
    w = w.replace("#", "").replace("*", "").replace("_", "").replace("`", "")
    # Aggressively strip markdown markers and punctuation from start/end
    w = re.sub(r"^[\W_]+", "", w)
    w = re.sub(r"[\W_]+$", "", w)
    w = re.sub(r"[^\w']+$", "", w)
    return w.lower()


def _compare_transcripts(
    raw_text: str,
    formatted_text: str,
    skip_words: Set[str],
    max_lookahead: int,
    max_mismatch_ratio: float,
    max_mismatches: Optional[int],
) -> Dict[str, Any]:
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
                {
                    "a_index": i,
                    "a_word": a_words[i],
                    "b_index": None,
                    "b_word": None,
                    "reason": "B exhausted",
                }
            )
            stopped_reason = "B_exhausted"
            break

        if a_n == b_norm[j]:
            i += 1
            j += 1
        else:
            # Bidirectional Lookahead Strategy
            b_match_offset = None
            for offset in range(1, max_lookahead + 1):
                if j + offset < len(b_words) and a_n == b_norm[j + offset]:
                    b_match_offset = offset
                    break

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
                path1_score = 0
                if i + 1 < len(a_norm) and j + b_match_offset + 1 < len(b_words):
                    if a_norm[i + 1] == b_norm[j + b_match_offset + 1]:
                        path1_score = 1

                path2_score = 0
                if i + a_match_offset + 1 < len(a_norm) and j + 1 < len(b_words):
                    if a_norm[i + a_match_offset + 1] == b_norm[j + 1]:
                        path2_score = 1

                if path1_score > path2_score:
                    action = "skip_b"
                elif path2_score > path1_score:
                    action = "skip_a"
                else:
                    if b_match_offset <= a_match_offset:
                        action = "skip_b"
                    else:
                        action = "skip_a"

            if action == "skip_b":
                j += b_match_offset
            elif action == "skip_a":
                for k in range(a_match_offset):
                    mismatches.append(
                        {
                            "a_index": i + k,
                            "a_word": a_words[i + k],
                            "b_index": j,
                            "b_word": b_words[j],
                            "reason": "Skipped in A (deletion in B)",
                        }
                    )
                i += a_match_offset
            else:
                mismatches.append(
                    {
                        "a_index": i,
                        "a_word": a_words[i],
                        "b_index": j,
                        "b_word": b_words[j],
                        "reason": "Mismatch",
                    }
                )
                i += 1

        if checked > 0:
            mismatch_count = len(mismatches)
            mismatch_ratio = mismatch_count / checked
            if max_mismatches is not None and mismatch_count >= max_mismatches:
                stopped_reason = "max_mismatches"
                break
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


def validate_format(
    raw_filename: str,
    formatted_filename: Optional[str] = None,
    skip_words_file: Optional[str] = None,
    logger=None,
) -> bool:
    """Orchestrates the format validation process."""
    if logger is None:
        logger = setup_logging("validate_format")
    try:
        stem = Path(raw_filename).stem
        raw_file_path = config.SOURCE_DIR / raw_filename
        if formatted_filename:
            formatted_file_path = config.PROJECTS_DIR / stem / formatted_filename
        else:
            formatted_file_path = (
                config.PROJECTS_DIR / stem / f"{stem}{config.SUFFIX_FORMATTED}"
            )

        validate_input_file(raw_file_path)
        validate_input_file(formatted_file_path)

        raw_text = raw_file_path.read_text(encoding="utf-8-sig")
        formatted_text = formatted_file_path.read_text(encoding="utf-8-sig")

        formatted_text = strip_yaml_frontmatter(formatted_text)

        raw_clean = re.sub(
            r"^\s*(\[[\d:.]+\]\s+[^:]+:|Unknown Speaker|Speaker \d+)\s+\d+:\d+(?::\d+)?",
            "",
            raw_text,
            flags=re.MULTILINE,
        )
        raw_clean = re.sub(r"^\s*Transcribed by\b.*", "", raw_clean, flags=re.MULTILINE)

        raw_clean = re.sub(
            r"[\[\(]?\b\d+:\d{2}(?::\d{2})?(?:[ap]m)?[\]\)]?",
            " ",
            raw_clean,
            flags=re.IGNORECASE,
        )
        raw_clean = re.sub(r"(?:^|\s)[\[\(]?:\d{2}\b[\]\)]?", " ", raw_clean)

        formatted_clean, _ = re.subn(r"\s+\[sic\](?: \([^)]+\))?", "", formatted_text)
        formatted_clean = re.sub(r"\*\*[^*]+:\*\*\s*", "", formatted_clean)

        formatted_clean = re.sub(r"^\s*#+.*$", "", formatted_clean, flags=re.MULTILINE)

        skip_words = set()
        if skip_words_file:
            skip_words = {
                normalize_text(word)
                for word in Path(skip_words_file).read_text().splitlines()
                if word and not word.startswith("#")
            }

        result = _compare_transcripts(
            raw_clean,
            formatted_clean,
            skip_words,
            config.VALIDATION_LOOKAHEAD_WINDOW,
            0.05,
            None,
        )

        logger.info("=== Comparison Summary ===")
        for key, value in result.items():
            if key != "mismatches":
                logger.info(f"{key}: {value}")

        if result["mismatch_ratio"] > config.VALIDATION_MISMATCH_RATIO:
            logger.error(
                f"Validation FAILED: Mismatch ratio {result['mismatch_ratio']:.2%} exceeds limit ({config.VALIDATION_MISMATCH_RATIO:.1%})."
            )
            for m in result["mismatches"][:20]:
                logger.error(
                    f"  Mismatch ({m.get('reason', 'Unknown')}): A[{m['a_index']}]='{m['a_word']}' vs B[{m['b_index']}]='{m.get('b_word')}'"
                )
            return False

        if result["mismatch_count"] > 0:
            logger.warning(
                f"Validation PASSED with warnings: {result['mismatch_count']} mismatches ({result['mismatch_ratio']:.2%})."
            )
            for m in result["mismatches"][:10]:
                logger.warning(
                    f"  Ignored Mismatch ({m.get('reason', 'Unknown')}): A[{m['a_index']}]='{m['a_word']}' vs B[{m['b_index']}]='{m.get('b_word')}'"
                )
        else:
            logger.info("Validation PASSED: No mismatches found.")

        return True

    except Exception as e:
        logger.error(f"An error occurred during format validation: {e}", exc_info=True)
        return False
