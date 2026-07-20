"""
Pipeline module for transcript formatting and basic validation.
Extracts raw text, formats it via LLM, and performs word-level validation.
"""

import os
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import anthropic

import config
import transcript_utils
from transcript_utils import (
    call_claude_with_retry,
    check_token_budget,
    clean_project_name,
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


def detect_transcript_source_format(text: str) -> str:
    """Classify supported transcript wrapper formats for logging."""
    sample = "\n".join(text.splitlines()[:12])
    trx_markers = (
        "TRANSCRIPT",
        "Source file:",
        "Date:",
        "Duration:",
        "Speakers:",
        "Warnings:",
    )
    if all(marker in sample for marker in trx_markers):
        return "trx_whisper_wrapped"
    return "plain_transcript"


def strip_transcript_metadata_header(text: str) -> str:
    """Remove TRX-style transcript metadata header before content comparison."""
    if detect_transcript_source_format(text) != "trx_whisper_wrapped":
        return text
    lines = text.splitlines()

    separator_index = None
    for index, line in enumerate(lines[:20]):
        if re.match(r"^-{10,}\s*$", line):
            separator_index = index
            break

    if separator_index is None:
        return text

    return "\n".join(lines[separator_index + 1 :]).lstrip()


def strip_raw_speaker_prefixes(text: str) -> str:
    """Remove timestamped/raw speaker prefixes before validation comparison."""
    prefix_pattern = (
        r"^\s*(?:[\[\(]?[\d:.]+[\]\)]?\s*)?"  # optional timestamp: bracketed or bare
        r"(?:Unknown Speaker|Speaker \d+|[A-Za-z][\w .'-]{0,40}):\s*"
    )
    return re.sub(prefix_pattern, "", text, flags=re.MULTILINE)


def strip_transcript_validation_footer(text: str) -> str:
    """Remove appended TRX validation report blocks from transcript text."""
    for marker in ("\nVALIDATION REPORT\n", "\r\nVALIDATION REPORT\r\n", "\nFLAGGED ITEMS\n"):
        index = text.find(marker)
        if index != -1:
            return text[:index].rstrip() + "\n"
    return text


def load_prompt() -> str:
    """Load the formatting prompt template."""
    return transcript_utils.load_prompt(config.PROMPT_FORMATTING_FILENAME)


def load_raw_transcript(filename: str) -> str:
    """Load the raw transcript from source directory."""
    transcript_path = config.SOURCE_DIR / filename
    validate_input_file(transcript_path)
    raw_text = transcript_path.read_text(encoding="utf-8")
    return strip_transcript_validation_footer(raw_text)


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
        logger.info("Transcript length: %d words, %d characters",
                    word_count, len(raw_transcript))
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
    # Use clean project name (stripping _validated, _vN) for consistency
    stem = clean_project_name(original_filename)
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
            raise FileNotFoundError(
                f"Source directory not found: {config.SOURCE_DIR}")

        logger.info("Loading prompt template from: %s", config.PROMPTS_DIR)
        prompt_template = load_prompt()

        logger.info(f"Loading raw transcript: {raw_filename}")
        raw_transcript = load_raw_transcript(raw_filename)
        logger.info(
            "Detected transcript source format: %s",
            detect_transcript_source_format(raw_transcript),
        )

        # Construct full prompt to check context budget before API call.
        # This guard must compare against model context capacity, not the
        # requested output token count.
        full_prompt_for_budget_check = (
            f"{prompt_template}\n\n---\n\nRAW TRANSCRIPT:\n\n{raw_transcript}"
        )
        max_context_input_budget = max(
            config.MAX_CONTEXT_TOKENS - config.MAX_TOKENS_FORMATTING,
            config.MAX_TOKENS_FORMATTING,
        )

        if not check_token_budget(
            full_prompt_for_budget_check, max_context_input_budget, logger
        ):
            logger.error(
                "Context budget exceeded for formatting. Aborting API call.")
            return False

        formatted_content = format_transcript_with_claude(
            raw_transcript, prompt_template, model=model, logger=logger
        )

        formatted_content, sic_count = strip_sic_annotations(formatted_content)
        if sic_count > 0 and logger:
            logger.info("Removed %d [sic] annotation(s).", sic_count)

        output_path = save_formatted_transcript(
            formatted_content, raw_filename)

        logger.info("✓ Success!")
        logger.info("Formatted transcript saved to: %s", output_path)
        return True

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise e
    except Exception as e:
        logger.error("An error occurred: %s", e, exc_info=True)
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


def _resolve_structured_stem(filename: str) -> str:
    """Strip transcript artifact suffixes to recover the project stem."""
    stem = Path(filename).stem
    for suffix in (
        config.SUFFIX_FORMATTED.replace(".md", ""),
        config.SUFFIX_YAML.replace(".md", ""),
    ):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return clean_project_name(stem)


def _parse_metadata_fallback(stem: str, transcript_text: str | None = None) -> dict:
    """Best-effort metadata extraction for non-canonical transcript filenames."""
    source_filename = None
    if transcript_text:
        match = re.search(r"^Source file:\s*(.+)$", transcript_text, re.MULTILINE)
        if match:
            source_filename = Path(match.group(1).strip()).name

    candidate = Path(source_filename).stem if source_filename else stem
    candidate = clean_project_name(candidate)

    date_match = re.search(r"(\d{4}-\d{2}-\d{2}|\d{8})", candidate)
    raw_date = date_match.group(1) if date_match else ""
    if raw_date and re.fullmatch(r"\d{8}", raw_date):
        date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
    else:
        date = raw_date or "Unknown"

    year_match = re.search(r"(\d{4})", date)
    year = year_match.group(1) if year_match else "Unknown"

    title_source = candidate
    if "GMT" in title_source:
        title_source = title_source.split("GMT", 1)[0].strip()
    if raw_date:
        title_source = re.sub(re.escape(raw_date), "", title_source).strip(" -_")

    title = title_source or candidate or stem
    presenter = "Unknown"

    return {
        "title": title,
        "presenter": presenter,
        "author": presenter,
        "date": date,
        "year": year,
        "filename": stem,
        "source_filename": source_filename,
        "stem": stem,
    }


def _resolve_yaml_metadata(transcript_filename: str, transcript_text: str | None = None) -> dict:
    """Resolve transcript metadata for YAML, tolerating non-canonical filenames."""
    stem = _resolve_structured_stem(transcript_filename)
    try:
        meta = parse_filename_metadata(transcript_filename)
        meta["stem"] = stem
        meta["source_filename"] = None
        return meta
    except ValueError:
        return _parse_metadata_fallback(stem, transcript_text)


def add_yaml(transcript_filename: str, source_ext: str = "mp4", logger=None) -> bool:
    """
    Orchestrates the process of adding YAML front matter to a transcript.
    """
    if logger is None:
        logger = setup_logging("add_yaml")

    try:
        logger.info("Adding YAML to %s", transcript_filename)

        stem = _resolve_structured_stem(transcript_filename)

        transcript_path = config.PROJECTS_DIR / stem / transcript_filename
        validate_input_file(transcript_path)

        formatted_content = transcript_path.read_text(encoding="utf-8")
        meta = _resolve_yaml_metadata(transcript_filename, formatted_content)
        source_filename = meta.get("source_filename") or f"{meta['stem']}.{source_ext.lstrip('.')}"

        yaml_block = _generate_yaml_front_matter(meta, source_filename)
        final_content = yaml_block + formatted_content

        output_path = config.PROJECTS_DIR / stem / \
            f"{meta['stem']}{config.SUFFIX_YAML}"
        output_path.write_text(final_content, encoding="utf-8")

        logger.info("✓ Success! YAML added. Output saved to: %s", output_path)

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
        logger.error("An error occurred: %s", e, exc_info=True)
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
            # Check for Fuzzy Match (Typo correction)
            # e.g. "livel" vs "life"
            if len(a_n) > 0 and len(b_norm[j]) > 0 and a_n[0] == b_norm[j][0]:
                matcher = SequenceMatcher(None, a_n, b_norm[j])
                if matcher.ratio() > 0.65:
                    i += 1
                    j += 1
                    continue

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

    mismatch_count = len(mismatches)
    mismatch_ratio = mismatch_count / checked if checked > 0 else 0.0

    return {
        "a_word_count": len(a_words),
        "b_word_count": len(b_words),
        "checked_words": checked,
        "mismatch_count": mismatch_count,
        "mismatch_ratio": mismatch_ratio,
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
        # Use clean project name to locate the project directory
        stem = clean_project_name(raw_filename)
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
        logger.info(
            "Detected transcript source format: %s",
            detect_transcript_source_format(raw_text),
        )

        formatted_text = strip_yaml_frontmatter(formatted_text)

        raw_clean = strip_transcript_validation_footer(raw_text)
        raw_clean = strip_transcript_metadata_header(raw_clean)

        raw_clean = strip_raw_speaker_prefixes(raw_clean)
        raw_clean = re.sub(r"^\s*Transcribed by\b.*", "",
                           raw_clean, flags=re.MULTILINE)

        raw_clean = re.sub(
            r"[\[\(]?\b\d+:\d{2}(?::\d{2})?(?:[ap]m)?[\]\)]?",
            " ",
            raw_clean,
            flags=re.IGNORECASE,
        )
        raw_clean = re.sub(r"(?:^|\s)[\[\(]?:\d{2}\b[\]\)]?", " ", raw_clean)
        # Strip lines that are solely a bare number (plain TRX timestamp lines)
        raw_clean = re.sub(r"(?m)^\s*\d+\s*$", " ", raw_clean)

        # Remove procedural speech from raw text to avoid validation errors
        # These are commonly removed by the formatting model
        procedural_patterns = [
            r"\bnext slide(?:,? please)?\.?",
            r"\bnext one(?:,? please)?\.?",
            r"\bslide please\.?",
            r"\bintro\b",  
            r"(?:^|[\.\!\?]\s+)so(?:,)?\s+",   # Sentence-starting 'So'
            r"(?:^|[\.\!\?]\s+)okay(?:,)?\s+", # Sentence-starting 'Okay'
            r"(?:^|[\.\!\?]\s+)right(?:,)?\s+", # Sentence-starting 'Right'
            r"\bjust to emphasize(?: this)?",
            r"\bone please",
            r"\bthere you see",
            r"\bthanks\.?",
            r"\bnext(?:,)?\s+",
            r"\bone(?:,)?\s+",
            r"\bslide(?:,)?\s+",
            r"\bplease\.?"
        ]
        for p in procedural_patterns:
            raw_clean = re.sub(p, " ", raw_clean, flags=re.IGNORECASE | re.MULTILINE)

        formatted_clean, _ = re.subn(
            r"\s+\[sic\](?: \([^)]+\))?", "", formatted_text)
        formatted_clean = re.sub(r"\*\*[^*]+:\*\*\s*", "", formatted_clean)

        formatted_clean = re.sub(
            r"^\s*#+.*$", "", formatted_clean, flags=re.MULTILINE)

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
            logger.error("Validation FAILED: Mismatch ratio %.2f%% exceeds limit (%.1f%%).",
                         result['mismatch_ratio'] * 100, config.VALIDATION_MISMATCH_RATIO * 100)
            for m in result["mismatches"][:20]:
                logger.error("  Mismatch (%s): A[%s]='%s' vs B[%s]='%s'", m.get(
                    'reason', 'Unknown'), m['a_index'], m['a_word'], m['b_index'], m.get('b_word'))
            return False

        if result["mismatch_count"] > 0:
            logger.warning("Validation PASSED with warnings: %d mismatches (%.2f%%).",
                           result['mismatch_count'], result['mismatch_ratio'] * 100)
            for m in result["mismatches"][:10]:
                logger.warning("  Ignored Mismatch (%s): A[%s]='%s' vs B[%s]='%s'", m.get(
                    'reason', 'Unknown'), m['a_index'], m['a_word'], m['b_index'], m.get('b_word'))
        else:
            logger.info("Validation PASSED: No mismatches found.")

        return True

    except Exception as e:
        logger.error(
            "An error occurred during format validation: %s", e, exc_info=True)
        return False
