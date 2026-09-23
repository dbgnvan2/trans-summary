"""
Pipeline module for transcript formatting and basic validation.
Extracts raw text, formats it via LLM, and performs word-level validation.
"""

import datetime
import hashlib
import json
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

_TIMESTAMP_PATTERN_SRC = r"[\[\(]?\b\d+:\d{2}(?::\d{2})?(?:[ap]m)?[\]\)]?"


def strip_sic_annotations(text: str) -> tuple[str, int]:
    """Removes [sic] annotations and returns the cleaned text and count.

    Only horizontal whitespace (spaces/tabs) around the annotation is consumed.
    Line breaks are never removed: consuming them merged a paragraph ending in
    "[sic]" with the following "## Section" heading, which hid that heading
    from every line-anchored parser.
    """
    pattern = r"[ \t]*\[sic\](?:[ \t]*\([^)\n]*\))?"
    cleaned_text, count = re.subn(pattern, "", text)
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


def formatting_max_tokens(model: str) -> int:
    """Output token budget for the formatting call: the model's documented max
    output where known (config.MODEL_OUTPUT_TOKEN_LIMITS), else
    config.MAX_TOKENS_FORMATTING. The formatter reproduces the whole transcript,
    so its output is as long as its input."""
    return config.MODEL_OUTPUT_TOKEN_LIMITS.get(model.lower(), config.MAX_TOKENS_FORMATTING)


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
        max_tokens=formatting_max_tokens(model),
        stream=True,
        logger=logger,
        timeout=config.TIMEOUT_FORMATTING,
        min_words=min_expected_words,
    )

    return message.content[0].text


def strip_leading_title(text: str) -> tuple[str, List[str]]:
    """Remove heading-only lines before the first ``## Section`` heading (the
    model tends to echo the prompt's own title, e.g. ``# Transcript Formatting
    - Thematic Sections - v12-Lite``). Non-heading content before Section 1 is
    left in place so validation reports it."""
    match = re.search(r"^## Section ", text, flags=re.MULTILINE)
    if not match:
        return text, []
    before = text[:match.start()]
    lines = [ln.strip() for ln in before.splitlines() if ln.strip()]
    if not lines or not all(ln.startswith("#") for ln in lines):
        return text, []
    return text[match.start():], lines


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
    raw_filename: str, model: str = config.DEFAULT_MODEL, logger=None,
    pattern_set: Optional[str] = None,
) -> bool:
    """
    Orchestrates the transcript formatting process.

    ``pattern_set``: name of the pattern set to assign to this project before
    formatting ("" clears it; None keeps the project's current assignment).
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

        # Apply the project's pattern set (group-level fixes) to the raw text
        # before formatting; what was applied is recorded in the project.
        import pattern_sets
        stem = clean_project_name(raw_filename)
        if pattern_set is not None:
            pattern_sets.assign_to_project(stem, pattern_set or None)
        raw_transcript, pattern_record = pattern_sets.apply_to_raw_for_project(stem, raw_transcript)
        if pattern_record:
            total = sum(f["count"] for f in pattern_record["applied"])
            logger.info("Pattern set '%s': %d fix(es) applied to the raw transcript (%d occurrence(s)).",
                        pattern_record["name"], len(pattern_record["applied"]), total)
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
        max_output = formatting_max_tokens(model)
        expected_output = int(
            transcript_utils.estimate_token_count(raw_transcript)
            * config.FORMATTING_OUTPUT_EXPANSION
        )
        if expected_output > max_output:
            logger.error(
                "Transcript too long for single-pass formatting with %s: about %d "
                "output tokens needed, model limit %d. Use a model with a larger "
                "output limit (config FORMATTING_MODEL) or split the transcript.",
                model, expected_output, max_output,
            )
            return False
        max_context_input_budget = max(
            config.MAX_CONTEXT_TOKENS - max_output,
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
        formatted_content, removed = strip_leading_title(formatted_content)
        if removed:
            logger.info("Removed %d title line(s) before Section 1: %s", len(removed), removed[0])

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


def _generate_yaml_front_matter(
    meta: dict, source_filename: str, validation: Optional[dict] = None
) -> str:
    """
    Generate YAML front matter block.

    ``validation`` is the passing format-validation record for this exact text, or
    None. The Authenticity field states only what was actually checked: an
    automated word comparison against the source transcript (not the recording).
    """
    if validation:
        cmp = validation.get("comparison", {})
        review = cmp.get("review", {})
        reviewed = review.get("accept", 0) + review.get("edit", 0)
        reviewed_note = (
            f" {reviewed} difference(s) reviewed and approved by a person"
            f" ({review.get('edit', 0)} edited)." if reviewed else "")
        authenticity = (
            "Word-level comparison against the source transcript passed. Every\n"
            "  difference is a removed stutter or transcription tag, or was approved\n"
            f"  in review.{reviewed_note} Section headings added; timestamps removed."
        )
    else:
        authenticity = (
            "NOT VERIFIED: no passing comparison against the source transcript is\n"
            "  recorded for this text."
        )

    return f'''---
Title: "{meta["title"]}"
Presenter: "{meta["presenter"]}"
Lecture date: "{meta["date"]}"
Source recording: "{source_filename}"
Transcriber: "{config.YAML_TRANSCRIBER}"
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

        validation = None
        if format_validation_passed_for(meta["stem"], formatted_content):
            validation = load_format_validation_record(meta["stem"])
        else:
            logger.warning(
                "No passing format validation recorded for this formatted text; "
                "YAML Authenticity will state NOT VERIFIED."
            )
        yaml_block = _generate_yaml_front_matter(meta, source_filename, validation)
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


def _is_fuzzy_match(a_n: str, b_n: str) -> bool:
    """Accept likely transcription typos (e.g. 'livel' vs 'life')."""
    return (
        bool(a_n)
        and bool(b_n)
        and a_n[0] == b_n[0]
        and SequenceMatcher(None, a_n, b_n).ratio() > 0.65
    )


def _word_opcodes(a: List[str], b: List[str]) -> List[tuple]:
    """difflib opcodes for two word lists, with the common prefix and suffix
    trimmed first (O(n)). The trim makes identical or near-identical inputs fast
    and keeps SequenceMatcher's worst case (long runs of one repeated word) from
    being reached on realistic transcripts."""
    n_pre = 0
    limit = min(len(a), len(b))
    while n_pre < limit and a[n_pre] == b[n_pre]:
        n_pre += 1
    n_suf = 0
    while (n_suf < limit - n_pre
           and a[len(a) - 1 - n_suf] == b[len(b) - 1 - n_suf]):
        n_suf += 1
    ops: List[tuple] = []
    if n_pre:
        ops.append(("equal", 0, n_pre, 0, n_pre))
    mid_a = a[n_pre:len(a) - n_suf]
    mid_b = b[n_pre:len(b) - n_suf]
    if mid_a or mid_b:
        for tag, i1, i2, j1, j2 in SequenceMatcher(
                None, mid_a, mid_b, autojunk=False).get_opcodes():
            ops.append((tag, i1 + n_pre, i2 + n_pre, j1 + n_pre, j2 + n_pre))
    if n_suf:
        ops.append(("equal", len(a) - n_suf, len(a), len(b) - n_suf, len(b)))
    return ops


def _compare_transcripts(
    raw_text: str,
    formatted_text: str,
    skip_words: Set[str],
    max_lookahead: int,
    max_mismatch_ratio: float,
    max_mismatches: Optional[int],
) -> Dict[str, Any]:
    """Compares raw to formatted transcript, word by word.

    Uses a global alignment (difflib.SequenceMatcher over normalized words), so
    deletions, insertions and substitutions of any length are located and each
    word is counted once. The previous greedy aligner could only resynchronise
    within ``max_lookahead`` words, silently ignored inserted words, and counted
    a truncated output as a single mismatch.

    Mismatch reasons: "Mismatch" (substitution), "Skipped in A (deletion in B)",
    "Inserted in B", and "B exhausted" (raw words missing from the end of the
    formatted text, i.e. truncation).

    ``max_contiguous_run`` is the size of the largest single differing block.

    ``max_lookahead`` is retained for call compatibility and is unused.
    ``max_mismatch_ratio`` no longer stops the comparison early; exceeding it
    sets ``stopped_reason`` to "mismatch_ratio". ``max_mismatches`` caps the
    returned list and sets ``stopped_reason`` to "max_mismatches".
    """
    del max_lookahead  # unused; see docstring
    return _compare_words(raw_text.split(), formatted_text.split(), skip_words,
                          max_mismatch_ratio, max_mismatches)


_ARTIFACT_TAG_RE = re.compile(
    r"^[\[\(](?:crosstalk|inaudible|audio unclear|static)[\]\)][.,]?$", re.IGNORECASE)


def _compare_words(
    a_words: List[str],
    b_words: List[str],
    skip_words: Set[str],
    max_mismatch_ratio: float = 1.0,
    max_mismatches: Optional[int] = None,
) -> Dict[str, Any]:
    """Core of ``_compare_transcripts`` on pre-split word lists (surface forms).

    Besides per-word ``mismatches`` it returns ``blocks``: one entry per
    differing stretch, used by the review step. A block is auto-allowed only if
    it is a deleted immediate repetition (a stutter the prompt allows removing)
    or a deleted transcription-artifact tag such as ``[crosstalk]``.
    """

    def _checkable(words: List[str]) -> tuple[List[int], List[str]]:
        idx: List[int] = []
        norm: List[str] = []
        for pos, word in enumerate(words):
            n = _normalize_word_for_validation(word)
            if n and n not in skip_words:
                idx.append(pos)
                norm.append(n)
        return idx, norm

    a_idx, a_norm = _checkable(a_words)
    b_idx, b_norm = _checkable(b_words)
    b_vocab = set(b_norm)

    mismatches: List[Dict[str, Any]] = []
    corrections: List[Dict[str, Any]] = []

    def _deleted(k: int, reason: str) -> None:
        mismatches.append({
            "a_index": a_idx[k], "a_word": a_words[a_idx[k]],
            "b_index": None, "b_word": None, "reason": reason,
        })

    def _inserted(k: int) -> None:
        mismatches.append({
            "a_index": None, "a_word": None,
            "b_index": b_idx[k], "b_word": b_words[b_idx[k]],
            "reason": "Inserted in B",
        })

    b_exhausted = False
    max_run = 0
    max_run_a_index: Optional[int] = None
    blocks: List[Dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in _word_opcodes(a_norm, b_norm):
        if tag == "equal":
            continue
        before = len(mismatches)
        before_corr = len(corrections)
        # Raw words left over at the very end mean the formatted text stopped
        # early (truncation).
        at_end = i2 == len(a_norm) and j2 == len(b_norm) and (i2 - i1) > (j2 - j1)
        deletion_reason = "B exhausted" if at_end else "Skipped in A (deletion in B)"
        b_exhausted = b_exhausted or at_end
        paired = min(i2 - i1, j2 - j1) if tag == "replace" else 0
        for k in range(paired):
            a_n, b_n = a_norm[i1 + k], b_norm[j1 + k]
            # A near-identical replacement is accepted as a transcription
            # correction only if the raw word appears nowhere in the formatted
            # text (the formatter treated it as a mishearing throughout, e.g.
            # 'homostasis' -> 'homeostasis'). If the raw word is used elsewhere
            # in the formatted text it is a real word, so replacing it is an
            # edit (their/there, patient/parent) and counts as a mismatch.
            if _is_fuzzy_match(a_n, b_n) and a_n not in b_vocab:
                corrections.append({"a_index": a_idx[i1 + k], "a_word": a_words[a_idx[i1 + k]],
                                    "b_index": b_idx[j1 + k], "b_word": b_words[b_idx[j1 + k]]})
            else:
                mismatches.append({
                    "a_index": a_idx[i1 + k], "a_word": a_words[a_idx[i1 + k]],
                    "b_index": b_idx[j1 + k], "b_word": b_words[b_idx[j1 + k]],
                    "reason": "Mismatch",
                })
        for k in range(i1 + paired, i2):
            _deleted(k, deletion_reason)
        for k in range(j1 + paired, j2):
            _inserted(k)
        run = len(mismatches) - before
        if run > max_run:
            max_run = run
            max_run_a_index = a_idx[i1] if i1 < len(a_idx) else None

        seg = a_norm[i1:i2]
        span = i2 - i1
        auto = None
        if tag == "delete":
            if (i1 - span >= 0 and a_norm[i1 - span:i1] == seg) or a_norm[i2:i2 + span] == seg:
                auto = "stutter"
            elif _ARTIFACT_TAG_RE.match(" ".join(a_words[a_idx[k]] for k in range(i1, i2))):
                auto = "artifact tag"
        if tag == "delete":
            kind = "deleted"
        elif tag == "insert":
            kind = "inserted"
        elif len(corrections) - before_corr == span == (j2 - j1) and len(mismatches) == before:
            kind = "correction"
        else:
            kind = "changed"
        blocks.append({
            "mismatch_words": len(mismatches) - before,
            "key": f"{i1}:{i2}|{' '.join(b_norm[j1:j2])}",
            "kind": kind,
            "auto": auto,
            "raw_text": " ".join(a_words[a_idx[k]] for k in range(i1, i2)),
            "formatted_text": " ".join(b_words[b_idx[k]] for k in range(j1, j2)),
            "a_word_indices": [a_idx[k] for k in range(i1, i2)],
            "b_word_indices": [b_idx[k] for k in range(j1, j2)],
            # formatted word index before which raw words were dropped
            "b_insert_at": b_idx[j1] if j1 < len(b_idx) else len(b_words),
        })

    mismatches.sort(key=lambda m: (
        m["a_index"] if m["a_index"] is not None else float("inf"),
        m["b_index"] if m["b_index"] is not None else float("inf"),
    ))

    checked = len(a_norm)
    mismatch_count = len(mismatches)
    mismatch_ratio = mismatch_count / checked if checked > 0 else 0.0

    stopped_reason: Optional[str] = None
    if b_exhausted:
        stopped_reason = "B_exhausted"
    elif max_mismatches is not None and mismatch_count >= max_mismatches:
        stopped_reason = "max_mismatches"
        mismatches = mismatches[:max_mismatches]
    elif mismatch_ratio > max_mismatch_ratio:
        stopped_reason = "mismatch_ratio"

    return {
        "a_word_count": len(a_words),
        "b_word_count": len(b_words),
        "checked_words": checked,
        "mismatch_count": mismatch_count,
        "mismatch_ratio": mismatch_ratio,
        "mismatches": mismatches,
        "stopped_reason": stopped_reason,
        # Longest single block of differing words, and where it starts in the
        # raw text. A ratio alone lets a whole dropped paragraph pass on a long
        # transcript (e.g. 92 words = 0.9% of 10,000).
        "max_contiguous_run": max_run,
        "max_run_a_index": max_run_a_index,
        # Accepted near-identical replacements of words that never appear in the
        # formatted text (likely transcription errors the formatter corrected).
        "corrections": corrections,
        "blocks": blocks,
    }


_TIMESTAMP_PATTERN = _TIMESTAMP_PATTERN_SRC


def _strip_times(text: str) -> str:
    """Remove clock-like tokens (timestamps, times of day)."""
    text = re.sub(_TIMESTAMP_PATTERN, " ", text, flags=re.IGNORECASE)
    return re.sub(r"(?:^|\s)[\[\(]?:\d{2}\b[\]\)]?", " ", text)


def _prepare_raw_for_comparison(raw_text: str) -> str:
    """Raw transcript with wrapper header/footer, speaker prefixes and
    timestamps removed."""
    return _prepare_texts_for_comparison(raw_text, "")[0]


_FORMATTED_MASK_PATTERNS = [
    (re.compile(r"^[ \t]*#.*$", re.MULTILINE), 0),
    (re.compile(r"\*\*[^*\n]+:\*\*"), 0),
    (re.compile(r"[ \t]*\[sic\](?:[ \t]*\([^)\n]*\))?"), 0),
    (re.compile(_TIMESTAMP_PATTERN_SRC, re.IGNORECASE), 0),
    (re.compile(r"(?:^|\s)[\[\(]?:\d{2}\b[\]\)]?"), 0),
]


def formatted_tokens(formatted_text: str) -> List[tuple]:
    """Words of the formatted transcript that are compared with the raw text,
    as (surface, start, end) character offsets into ``formatted_text``.

    Excludes the same material as the comparison: heading lines, bold speaker
    labels, [sic] annotations and clock-like tokens. Offsets let the review step
    restore or edit exact stretches of the formatted file.
    """
    masked = bytearray(len(formatted_text))
    for pattern, _ in _FORMATTED_MASK_PATTERNS:
        for m in pattern.finditer(formatted_text):
            masked[m.start():m.end()] = b"\x01" * (m.end() - m.start())
    tokens: List[tuple] = []
    for m in re.finditer(r"\S+", formatted_text):
        start = None
        for pos in range(m.start(), m.end() + 1):
            inside = pos < m.end() and not masked[pos]
            if inside and start is None:
                start = pos
            elif not inside and start is not None:
                surface = formatted_text[start:pos]
                if _normalize_word_for_validation(surface):
                    tokens.append((surface, start, pos))
                start = None
    return tokens


def span_is_plain_text(formatted_text: str, start: int, end: int) -> bool:
    """True if [start, end) contains no masked material (headings, speaker
    labels, annotations) — i.e. it is safe to replace wholesale."""
    segment = formatted_text[start:end]
    return "\n#" not in segment and "**" not in segment and "[sic]" not in segment


def _prepare_texts_for_comparison(raw_text: str, formatted_text: str) -> tuple[str, str]:
    """Normalize raw and formatted transcripts before word comparison."""
    raw_clean = strip_transcript_validation_footer(raw_text)
    raw_clean = strip_transcript_metadata_header(raw_clean)
    raw_clean = strip_raw_speaker_prefixes(raw_clean)
    raw_clean = re.sub(r"^\s*Transcribed by\b.*", "", raw_clean, flags=re.MULTILINE)
    raw_clean = _strip_times(raw_clean)
    # Strip lines that are solely a bare number (plain TRX timestamp lines)
    raw_clean = re.sub(r"(?m)^\s*\d+\s*$", " ", raw_clean)

    formatted_clean, _ = strip_sic_annotations(formatted_text)
    formatted_clean = re.sub(r"\*\*[^*]+:\*\*\s*", "", formatted_clean)
    formatted_clean = re.sub(r"^\s*#+.*$", "", formatted_clean, flags=re.MULTILINE)
    formatted_clean = _strip_times(formatted_clean)

    return raw_clean, formatted_clean


# Output contract from the formatting prompt:
#   ## Section N – Heading Text ([hh:mm:ss]).
_HEADING_RE = re.compile(
    r"^## Section (\d+) – (.+?) \(\[(\d{2}):(\d{2}):(\d{2})\]\)\.[ \t]*$"
)
_RAW_TIME_RE = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?::(\d{2}))?(?![\d:])")


def _raw_timestamp_seconds(raw_text: str) -> Set[int]:
    """All clock-like values in the raw transcript, in seconds (h:mm:ss or m:ss)."""
    found: Set[int] = set()
    for first, second, third in _RAW_TIME_RE.findall(raw_text):
        if third:
            found.add(int(first) * 3600 + int(second) * 60 + int(third))
        else:
            found.add(int(first) * 60 + int(second))
    return found


def validate_section_headings(
    formatted_text: str, raw_text: Optional[str] = None
) -> tuple[List[str], List[str]]:
    """Deterministic check of the section-heading output contract.

    Returns (errors, warnings). ``formatted_text`` must have YAML front matter
    removed. If ``raw_text`` is given, each heading timestamp other than the
    prompt's 00:00:00 fallback must occur in the raw transcript.
    """
    errors: List[str] = []
    warnings: List[str] = []
    lines = formatted_text.splitlines()

    for line_no, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if "## Section" in line and not stripped.startswith("## Section"):
            errors.append(
                f"Line {line_no}: '## Section' heading is not at the start of a "
                "line (merged into text)"
            )

    heading_lines = [
        (line_no, line) for line_no, line in enumerate(lines, 1)
        if line.startswith("#")
    ]
    if not any(line.startswith("## Section") for _, line in heading_lines):
        errors.append("No '## Section' headings found")
        return errors, warnings

    first_heading_line = next(
        n for n, line in heading_lines if line.startswith("## Section")
    )
    preamble = [line.strip() for line in lines[: first_heading_line - 1] if line.strip()]
    if preamble:
        # Warning, not error: every fixture output checked so far starts with the
        # prompt's own H1 title echoed back ("# Transcript Formatting - ...").
        warnings.append(f"Content before the first '## Section' heading: {preamble[0]!r}")

    raw_seconds = _raw_timestamp_seconds(raw_text) if raw_text is not None else None

    sections = []
    for line_no, line in heading_lines:
        match = _HEADING_RE.match(line)
        if not match:
            if line.startswith("## "):
                errors.append(f"Line {line_no}: heading does not match contract: {line!r}")
            continue
        number = int(match.group(1))
        title = match.group(2)
        hh, mm, ss = (int(match.group(g)) for g in (3, 4, 5))
        if mm > 59 or ss > 59:
            errors.append(f"Section {number}: invalid timestamp {hh:02d}:{mm:02d}:{ss:02d}")
        seconds = hh * 3600 + mm * 60 + ss
        title_words = len(title.split())
        if not 3 <= title_words <= 12:
            warnings.append(f"Section {number}: heading has {title_words} words (contract: 3-12)")
        sections.append((line_no, number, seconds, f"{hh:02d}:{mm:02d}:{ss:02d}"))

    numbers = [n for _, n, _, _ in sections]
    if numbers != list(range(1, len(numbers) + 1)):
        errors.append(f"Section numbers are not sequential from 1: {numbers}")

    previous = None
    for line_no, number, seconds, ts in sections:
        if previous is not None and seconds < previous:
            errors.append(f"Section {number}: timestamp {ts} is earlier than the previous section")
        previous = seconds
        if raw_seconds is None or seconds == 0:
            if seconds == 0 and number > 1 and raw_seconds:
                warnings.append(
                    f"Section {number}: uses 00:00:00 fallback although the raw transcript has timestamps"
                )
            continue
        if seconds not in raw_seconds:
            errors.append(f"Section {number}: timestamp {ts} does not occur in the raw transcript")

    # Every section must contain transcript text.
    starts = [line_no for line_no, _, _, _ in sections] + [len(lines) + 1]
    for (line_no, number, _, _), next_start in zip(sections, starts[1:]):
        body = lines[line_no:next_start - 1]
        if not any(b.strip() and not b.startswith("#") for b in body):
            errors.append(f"Section {number}: no transcript text")

    return errors, warnings


_TIME_TOKEN_RE = re.compile(r"^[\[\(]?(\d{1,2}):(\d{2})(?::(\d{2}))?[\]\)]?[.,]?$")


def _raw_words_with_times(raw_text: str) -> tuple[List[str], List[Optional[int]]]:
    """Normalized raw words and, for each, the most recent raw timestamp (seconds)."""
    text = strip_transcript_metadata_header(strip_transcript_validation_footer(raw_text))
    words: List[str] = []
    times: List[Optional[int]] = []
    current: Optional[int] = None
    for token in text.split():
        m = _TIME_TOKEN_RE.match(token)
        if m:
            a, b, c = m.groups()
            current = int(a) * 3600 + int(b) * 60 + int(c) if c else int(a) * 60 + int(b)
            continue
        n = _normalize_word_for_validation(token)
        if n:
            words.append(n)
            times.append(current)
    return words, times


def check_heading_timestamp_positions(
    formatted_text: str, raw_text: str
) -> tuple[List[str], List[str]]:
    """Check each heading timestamp against where the section actually starts in
    the raw transcript.

    The section's opening words are located in the raw text by global alignment.
    The heading timestamp must be the raw timestamp of the segment the section
    starts in, or the next raw timestamp after that point (a section starting
    mid-segment takes the first timestamp inside it). Skipped when the raw text
    has no timestamps. ``formatted_text`` must have YAML front matter removed.
    """
    errors: List[str] = []
    warnings: List[str] = []
    raw_words, raw_times = _raw_words_with_times(raw_text)
    if not any(t is not None for t in raw_times):
        return errors, warnings

    fmt_words: List[str] = []
    section_starts: List[tuple[int, int, int]] = []  # (number, seconds, word index)
    for line in formatted_text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            secs = int(m.group(3)) * 3600 + int(m.group(4)) * 60 + int(m.group(5))
            section_starts.append((int(m.group(1)), secs, len(fmt_words)))
            continue
        if line.startswith("#"):
            continue
        body, _ = strip_sic_annotations(re.sub(r"\*\*[^*]+:\*\*", " ", line))
        for token in body.split():
            n = _normalize_word_for_validation(token)
            if n:
                fmt_words.append(n)

    fmt_to_raw = [-1] * len(fmt_words)
    for tag, i1, i2, j1, j2 in _word_opcodes(raw_words, fmt_words):
        if tag == "equal":
            for k in range(i2 - i1):
                fmt_to_raw[j1 + k] = i1 + k

    # next_time[i]: first raw timestamp value that starts strictly after word i.
    next_time: List[Optional[int]] = [None] * len(raw_words)
    upcoming: Optional[int] = None
    for i in range(len(raw_words) - 1, -1, -1):
        next_time[i] = upcoming
        if i > 0 and raw_times[i] != raw_times[i - 1]:
            upcoming = raw_times[i]
        elif i == 0 and raw_times[0] is not None:
            upcoming = raw_times[0]

    search = config.HEADING_TS_LOCATE_WINDOW
    for number, secs, start in section_starts:
        located = next(
            (k for k in range(start, min(start + search, len(fmt_words))) if fmt_to_raw[k] >= 0),
            None,
        )
        if located is None:
            warnings.append(f"Section {number}: opening words not found in raw transcript; "
                            "timestamp position not checked")
            continue
        r = fmt_to_raw[located]
        r0 = max(0, r - (located - start))
        allowed = {t if t is not None else 0 for t in raw_times[r0:r + 1]}
        if next_time[r] is not None:
            allowed.add(next_time[r])
        if secs not in allowed:
            shown = ", ".join(f"{a // 3600:02d}:{a % 3600 // 60:02d}:{a % 60:02d}" for a in sorted(allowed))
            errors.append(
                f"Section {number}: heading timestamp "
                f"{secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d} does not match "
                f"where the section starts in the raw transcript (expected one of: {shown})"
            )
    return errors, warnings


def difference_items(raw_text: str, formatted_text: str,
                     skip_words: Optional[Set[str]] = None) -> tuple:
    """Compare raw vs formatted and return (comparison_result, items).

    ``formatted_text`` must have YAML front matter removed. Each item is one
    differing stretch with: key (stable across edits to other parts of the
    text), kind, auto (reason it is allowed automatically, or None), raw_text,
    formatted_text, section number, raw/formatted context, and the character
    span in ``formatted_text`` (``span``; for a pure deletion an insertion
    point with start == end).
    """
    raw_words = _prepare_raw_for_comparison(raw_text).split()
    tokens = formatted_tokens(formatted_text)
    result = _compare_words(raw_words, [t[0] for t in tokens], skip_words or set())

    heading_offsets = [(m.start(), int(m.group(1))) for m in
                       re.finditer(r"^## Section (\d+)", formatted_text, flags=re.MULTILINE)]

    def _section_at(offset: int) -> Optional[int]:
        current = None
        for pos, number in heading_offsets:
            if pos <= offset:
                current = number
            else:
                break
        return current

    items = []
    for block in result["blocks"]:
        b_idx = block["b_word_indices"]
        if b_idx:
            start, end = tokens[b_idx[0]][1], tokens[b_idx[-1]][2]
        elif block["b_insert_at"] > 0:
            start = end = tokens[block["b_insert_at"] - 1][2]
        else:
            start = end = tokens[0][1] if tokens else 0
        a_idx = block["a_word_indices"]
        a_lo = a_idx[0] if a_idx else None
        b_lo = b_idx[0] if b_idx else block["b_insert_at"]
        raw_ctx = " ".join(raw_words[max(0, (a_lo or 0) - 8):(a_idx[-1] + 9) if a_idx else 0]) if a_idx else ""
        fmt_ctx = " ".join(t[0] for t in tokens[max(0, b_lo - 8):b_lo + len(b_idx) + 8])
        items.append({
            "key": block["key"],
            "kind": block["kind"],
            "auto": block["auto"],
            "raw_text": block["raw_text"],
            "formatted_text": block["formatted_text"],
            "section": _section_at(start),
            "raw_context": raw_ctx,
            "formatted_context": fmt_ctx,
            "span": [start, end],
            "mismatch_words": block["mismatch_words"],
        })
    return result, items


def verify_source_fidelity(
    raw_text: str,
    formatted_text: str,
    skip_words: Optional[Set[str]] = None,
    approvals: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """All deterministic checks of a formatted transcript against its raw source.

    Passes only if: the heading checks pass; the differences are within the
    gross limits (VALIDATION_MISMATCH_RATIO, VALIDATION_MAX_CONTIGUOUS_RUN —
    beyond them the output should be regenerated, not reviewed); and every
    difference is either auto-allowed (stutter / artifact tag) or has been
    approved in review (``approvals``: set of item keys).

    ``formatted_text`` may include YAML front matter (it is stripped). Returns
    ``passed``, ``errors``, ``warnings``, ``comparison`` (counts),
    ``items`` (all differences) and ``unresolved`` (items needing review).
    """
    formatted_text = strip_yaml_frontmatter(formatted_text)
    result, items = difference_items(raw_text, formatted_text, skip_words)
    approvals = approvals or set()
    errors, warnings = validate_section_headings(formatted_text, raw_text)
    pos_errors, pos_warnings = check_heading_timestamp_positions(formatted_text, raw_text)
    errors += pos_errors
    warnings += pos_warnings

    # Gross limits count only differences that are not auto-allowed: removed
    # stutters are expected and must not push a good transcript over the limit.
    reviewable = [i for i in items if not i["auto"]]
    review_words = sum(i["mismatch_words"] for i in reviewable)
    review_ratio = review_words / result["checked_words"] if result["checked_words"] else 0.0
    longest = max(reviewable, key=lambda i: i["mismatch_words"], default=None)
    gross = False
    if longest and longest["mismatch_words"] > config.VALIDATION_MAX_CONTIGUOUS_RUN:
        gross = True
        errors.append(
            f"{longest['mismatch_words']} consecutive differing words in section "
            f"{longest['section']} (limit {config.VALIDATION_MAX_CONTIGUOUS_RUN}) — re-run formatting"
        )
    if review_ratio > config.VALIDATION_MISMATCH_RATIO:
        gross = True
        errors.append(
            f"mismatch ratio {review_ratio * 100:.2f}% exceeds limit "
            f"{config.VALIDATION_MISMATCH_RATIO * 100:.1f}% — re-run formatting"
        )
    unresolved = [i for i in items if not i["auto"] and i["key"] not in approvals]
    if unresolved and not gross:
        errors.append(f"{len(unresolved)} difference(s) from the source need review")

    comparison = {k: v for k, v in result.items()
                  if k not in ("mismatches", "corrections", "blocks")}
    comparison["mismatch_sample"] = result["mismatches"][:20]
    comparison["corrections"] = [
        f"{c['a_word']} -> {c['b_word']}" for c in result["corrections"]]
    comparison["differences"] = len(items)
    comparison["auto_allowed"] = sum(1 for i in items if i["auto"])
    comparison["approved"] = sum(1 for i in items if not i["auto"] and i["key"] in approvals)
    return {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "comparison": comparison,
        "items": items,
        "unresolved": unresolved,
        "review_needed": bool(unresolved) and not gross,
    }


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def format_validation_record_path(stem: str) -> Path:
    return config.PROJECTS_DIR / stem / f"{stem}{config.SUFFIX_FORMAT_VALIDATION}"


def raw_source_copy_path(stem: str) -> Path:
    return config.PROJECTS_DIR / stem / f"{stem}{config.SUFFIX_RAW_SOURCE}"


def load_format_validation_record(stem: str) -> Optional[dict]:
    path = format_validation_record_path(stem)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def format_validation_passed_for(stem: str, formatted_text: str) -> bool:
    """True only if a PASS record exists for exactly this formatted text."""
    record = load_format_validation_record(stem)
    return bool(
        record
        and record.get("passed") is True
        and record.get("formatted_sha256") == _sha256_text(strip_yaml_frontmatter(formatted_text))
    )


def _write_format_validation_record(
    stem: str, raw_name: str, raw_text: str, formatted_text: str, outcome: Dict[str, Any]
) -> None:
    record = {
        "raw_file": raw_name,
        "raw_sha256": _sha256_text(raw_text),
        "formatted_sha256": _sha256_text(strip_yaml_frontmatter(formatted_text)),
        "passed": outcome["passed"],
        "errors": outcome["errors"],
        "warnings": outcome["warnings"],
        "comparison": outcome["comparison"],
        "validated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    path = format_validation_record_path(stem)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


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

        skip_words = set()
        if skip_words_file:
            skip_words = {
                normalize_text(word)
                for word in Path(skip_words_file).read_text().splitlines()
                if word and not word.startswith("#")
            }

        import format_review
        import pattern_sets
        # Compare against the text the formatter actually received: the raw with
        # this project's recorded pattern-set fixes applied.
        raw_text = pattern_sets.effective_raw(stem, raw_text)
        approvals = format_review.load_approvals(stem, raw_text)
        outcome = verify_source_fidelity(raw_text, formatted_text, skip_words, approvals)
        comparison = outcome["comparison"]
        comparison["review"] = format_review.review_counts(stem)

        # Keep a copy of the exact raw source just validated against, so the release
        # gate can re-verify later even after the source file is renamed or moved.
        # Always overwritten: the formatted text may have been regenerated from a
        # different raw version (e.g. a corrected _v2).
        raw_source_copy_path(stem).write_text(raw_text, encoding="utf-8")
        _write_format_validation_record(
            stem, raw_file_path.name, raw_text, formatted_text, outcome
        )

        logger.info("=== Comparison Summary ===")
        for key, value in comparison.items():
            if key != "mismatch_sample":
                logger.info(f"{key}: {value}")
        for warning in outcome["warnings"]:
            logger.warning("Check: %s", warning)

        if not outcome["passed"]:
            logger.error("Validation FAILED: %d error(s).", len(outcome["errors"]))
            for error in outcome["errors"][:20]:
                logger.error("  %s", error)
            if outcome["review_needed"]:
                logger.error("  Review the differences (GUI: Review Differences; CLI: "
                             "python transcript_review_format.py \"%s\").", stem)
                for item in outcome["unresolved"][:20]:
                    logger.error("    Section %s, %s: %r -> %r", item["section"], item["kind"],
                                 item["raw_text"], item["formatted_text"])
            for m in comparison["mismatch_sample"]:
                logger.error("  Mismatch (%s): A[%s]='%s' vs B[%s]='%s'", m.get(
                    'reason', 'Unknown'), m['a_index'], m['a_word'], m['b_index'], m.get('b_word'))
            return False

        if comparison["mismatch_count"] > 0:
            logger.warning("Validation PASSED with warnings: %d mismatches (%.2f%%).",
                           comparison['mismatch_count'], comparison['mismatch_ratio'] * 100)
            for m in comparison["mismatch_sample"][:10]:
                logger.warning("  Ignored Mismatch (%s): A[%s]='%s' vs B[%s]='%s'", m.get(
                    'reason', 'Unknown'), m['a_index'], m['a_word'], m['b_index'], m.get('b_word'))
        else:
            logger.info("Validation PASSED: No mismatches found.")

        return True

    except Exception as e:
        logger.error(
            "An error occurred during format validation: %s", e, exc_info=True)
        return False
