#!/usr/bin/env python3
"""
Sequential A → B transcript checker, raw to formatted file.
Usage:
    python validate_transcripts.py "Title - Presenter - Date.txt"
    (Will automatically look for the formatted file)

Purpose:
- Ensure every non-skipped word in the raw transcript (A) appears in the
  formatted transcript (B) in the same order.
- Tolerate:
  - Section headings in B (with or without timestamps).
  - Speaker/timestamp lines in A ("Unknown Speaker  0:06").
  - Otter footer lines ("Transcribed by https://otter.ai").
  - Markdown emphasis markers (*, **, _).
  - Trailing punctuation differences.
  - Inline corrections in B of the form: original [sic] (corrected text)


"""

import argparse
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

# Directories (from environment variable)
TRANSCRIPTS_BASE = Path(
    os.getenv("TRANSCRIPTS_DIR", Path.home() / "transcripts"))
SOURCE_DIR = TRANSCRIPTS_BASE / "source"
FORMATTED_DIR = TRANSCRIPTS_BASE / "formatted"


# ---------- Normalization & Utilities ----------

def normalize_word(w: str) -> str:
    """
    Normalize a word for comparison:

    1. Strip leading/trailing markdown emphasis markers (*, **, _)
       e.g. '**Dr.'  -> 'Dr.'
            '*Amy:*' -> 'Amy:'
    2. Strip trailing non-alphanumeric / non-underscore / non-apostrophe chars
       (commas, periods, colons, quotes, etc.).
    3. Lowercase.

    This makes "word,", "word.", "**word**" all normalize to "word".
    """
    # Strip leading markdown markers
    w = re.sub(r'^[*_]+', '', w)
    # Strip trailing markdown markers
    w = re.sub(r'[*_]+$', '', w)
    # Strip trailing punctuation etc. (anything not [0-9A-Za-z_'])
    w = re.sub(r"[^\w']+$", "", w)
    return w.lower()


def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_skip_words(path: Optional[str]) -> Set[str]:
    """
    Load skip words from a file (one per line), normalize them the same way
    as transcript words. Lines starting with '#' are treated as comments.
    """
    if path is None:
        return set()
    words: Set[str] = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            norm = normalize_word(raw)
            if norm:
                words.add(norm)
    return words


# ---------- Pre-processing: headings, speakers, footer, [sic] ----------

def strip_heading_lines(text: str, heading_regex: str, heading_ts_regex: str) -> (str, int):
    """
    Remove section heading lines from B.

    Logic:
      1) If a line starts with # (any markdown heading), drop it
      2) If a line matches the heading timestamp regex (e.g. ends with
         '([hh:mm:ss]).' or '([hh:mm:ss])'), treat it as a heading and drop it.
      3) Otherwise, if it matches the heading start regex (e.g.
         'Section 1 – ...' or '## Section 1 – ...'), also drop it.
      4) Otherwise, keep the line.

    Returns:
        (cleaned_text, removed_heading_count)
    """
    header_start = re.compile(heading_regex)
    header_ts = re.compile(heading_ts_regex)
    # Match any markdown heading (# or ## or ###, etc.)
    markdown_heading = re.compile(r'^\s*#+\s')

    lines = text.splitlines()
    kept: List[str] = []
    removed_count = 0

    for line in lines:
        # Check if line is a markdown heading (starts with #)
        if markdown_heading.match(line):
            removed_count += 1
            continue  # drop markdown heading

        # Check for timestamp-style heading first (e.g. '([00:01:23]).')
        if header_ts.search(line):
            removed_count += 1
            continue  # drop heading-with-timestamp line

        # Fallback: check for older heading style (no timestamp)
        if header_start.match(line.lstrip()):
            removed_count += 1
            continue  # drop heading line

        kept.append(line)

    return "\n".join(kept), removed_count


def strip_speaker_lines(text: str, speaker_regex: str) -> str:
    """
    Remove speaker/timestamp markers from A.

    Default matches patterns like:
        Unknown Speaker  0:06
        Unknown Speaker  1:44
        [00:00:56.70] Google Chrome:

    Works both for separate lines AND inline markers within text.
    """
    pattern = re.compile(speaker_regex)

    # First try line-by-line for files with proper line breaks
    lines = text.splitlines()
    if len(lines) > 10:  # If we have multiple lines, process line by line
        kept: List[str] = []
        for line in lines:
            if pattern.match(line):
                continue
            kept.append(line)
        return "\n".join(kept)

    # For files that are all on one line (or very few lines),
    # remove inline speaker markers
    # Pattern: [timestamp] Speaker Name:  or  Speaker N  timestamp
    inline_pattern = re.compile(r'\[[\d:.]+\]\s+[^:]+:\s*')
    text = inline_pattern.sub('', text)

    return text


def strip_speaker_labels(text: str) -> str:
    """
    Remove speaker labels from formatted transcript (B).

    Matches patterns like:
        **Dr. Kerr:**
        **Audience Member:**
        **Speaker 1:**

    These appear in formatted transcripts but should not be counted as words.
    """
    # Pattern: **[anything]:** at the start of a line or after whitespace
    pattern = re.compile(r'\*\*[^*]+:\*\*\s*')
    return pattern.sub('', text)


def strip_footer_lines(text: str, footer_regex: str) -> str:
    """
    Remove footer/meta lines from A, e.g.:
        Transcribed by https://otter.ai
    """
    pattern = re.compile(footer_regex)
    lines = text.splitlines()
    kept: List[str] = []

    for line in lines:
        if pattern.match(line):
            continue
        kept.append(line)

    return "\n".join(kept)


def strip_sic_corrections(text: str, sic_regex: str) -> (str, int):
    """
    Remove inline correction notations in B of the form:

        original [sic] (corrected words)

    Example:
        'Cobra [sic] (Tycho Brahe) said ...'
        -> 'Cobra said ...'

    The default regex removes the leading space before [sic] plus '[sic]' and the
    optional '(...)' group after it, but does NOT touch the original word.

    Returns:
        (cleaned_text, num_corrections_removed)
    """
    pattern = re.compile(sic_regex)
    new_text, num = pattern.subn("", text)
    return new_text, num


# ---------- Core comparison ----------

def compare_transcripts(
    raw_text: str,
    formatted_text: str,
    skip_words: Optional[Set[str]] = None,
    max_lookahead: int = 3,
    max_mismatch_ratio: float = 0.02,
    max_mismatches: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Compare transcript A (raw) to transcript B (formatted) sequentially.

    A is the reference. For each non-skip word in A, we try to align it to B
    in order.

    Matching logic (using normalized words):

      - If A[i] == B[j]         -> match; advance i and j.
      - Else look ahead in B[j+1..j+max_lookahead] for A[i]:
          * If found at j+offset: treat B[j..j+offset-1] as extra words,
            advance i, set j = j+offset+1, continue.
          * If not found: count a mismatch; advance i only.

      - Stop early if:
          * mismatch_count / checked_words > max_mismatch_ratio, or
          * mismatch_count >= max_mismatches (if provided).
    """

    skip_words = skip_words or set()

    # Remove trailing garbage patterns (e.g., repeated "you you you...")
    # Common transcription software artifacts at end of file
    raw_text = re.sub(r'(\byou\b\s*){10,}.*$',
                      '', raw_text, flags=re.IGNORECASE)
    raw_text = re.sub(r'(\b\w{1,3}\b\s*){20,}%?\s*$', '', raw_text)

    # Split on whitespace; keep original words for reporting.
    a_words: List[str] = raw_text.split()
    b_words: List[str] = formatted_text.split()

    # Normalized forms for comparison.
    a_norm: List[str] = [normalize_word(w) for w in a_words]
    b_norm: List[str] = [normalize_word(w) for w in b_words]

    mismatches: List[Dict[str, Any]] = []
    checked = 0
    i = 0  # index into A
    j = 0  # index into B
    stopped_reason: Optional[str] = None

    while i < len(a_words):
        a_n = a_norm[i]

        # Skip words in A: explicitly in skip_words or normalize to empty.
        if not a_n or a_n in skip_words:
            i += 1
            continue

        checked += 1

        # If B is exhausted, anything remaining in A is missing.
        if j >= len(b_words):
            mismatches.append(
                {
                    "a_index": i,
                    "a_word": a_words[i],
                    "b_index": None,
                    "b_word": None,
                    "reason": "B exhausted; remaining A words missing",
                }
            )
            stopped_reason = "B_exhausted"
            break

        # Direct match at current positions
        if a_n == b_norm[j]:
            i += 1
            j += 1
        else:
            # Look ahead in B for A[i]
            found = False
            for offset in range(1, max_lookahead + 1):
                jj = j + offset
                if jj >= len(b_words):
                    break
                if a_n == b_norm[jj]:
                    # Treat B[j..jj-1] as extra; align at jj.
                    i += 1
                    j = jj + 1
                    found = True
                    break

            if not found:
                mismatches.append(
                    {
                        "a_index": i,
                        "a_word": a_words[i],
                        "b_index": j,
                        "b_word": b_words[j],
                        "reason": "A word not found within lookahead window of B",
                    }
                )
                i += 1  # advance A only

        # Early stopping checks
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
        "mismatch_ratio": (len(mismatches) / checked) if checked else 0.0,
        "mismatches": mismatches,
        "stopped_reason": stopped_reason,
    }


# ---------- CLI entrypoint ----------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sequentially compare a raw transcript (A) to a formatted transcript (B)."
    )
    parser.add_argument(
        "raw_filename",
        help="Filename of raw transcript (e.g., 'Title - Presenter - Date.txt')"
    )
    parser.add_argument(
        "--formatted-file",
        default=None,
        help="Optional: specify formatted file name explicitly (otherwise auto-constructed)"
    )
    parser.add_argument(
        "--skip-words",
        help=(
            "Optional file with one skip word per line "
            "(applied to A only, normalized for comparison)"
        ),
        default=None,
    )
    parser.add_argument(
        "--max-lookahead",
        type=int,
        default=3,
        help="Max number of words to look ahead in B on mismatch (default: 3)",
    )
    parser.add_argument(
        "--max-mismatch-ratio",
        type=float,
        default=0.02,
        help="Stop if mismatches / checked_words exceeds this fraction (default: 0.02 = 2%%)",
    )
    parser.add_argument(
        "--max-mismatches",
        type=int,
        default=None,
        help="Optional absolute maximum number of mismatches before stopping",
    )
    parser.add_argument(
        "--show-first",
        type=int,
        default=20,
        help="Number of mismatches to show in detail (default: 20)",
    )
    parser.add_argument(
        "--heading-regex",
        # Start-of-line heading: optional '##', then 'Section <digits> – ...'
        default=r"^\s*(?:##\s*)?Section\s+\d+\s+[-–—]\s+",
        help=(
            "Regex for lines in B that should be treated as headings and skipped "
            "when no timestamp is present. Default matches lines like "
            "'Section 1 – Title' or '## Section 1 – Title'."
        ),
    )
    parser.add_argument(
        "--heading-ts-regex",
        # Timestamp-style heading marker at end of line: '([hh:mm:ss]).' or '([hh:mm:ss])'
        # Examples:
        #   'Section 1 – Title ([00:01:23]).'
        #   'Section 1 – Title ([00:01:23])'
        default=r"\(\[\d{1,2}:\d{2}:\d{2}\]\)\.?\s*$",
        help=(
            "Regex to detect headings that end with a timestamp like '([hh:mm:ss]).' "
            "or '([hh:mm:ss])'. If this matches anywhere in the line, the line is "
            "treated as a heading and skipped. Fallback is the --heading-regex "
            "if this does not match."
        ),
    )
    parser.add_argument(
        "--speaker-regex",
        default=r"^\s*(\[[\d:.]+\]\s+[^:]+:|Unknown Speaker|Speaker \d+|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+\d+:\d+",
        help=(
            "Regex for lines in A that are speaker/timestamp markers and should be skipped. "
            "Default matches lines like '[00:00:56.70] Google Chrome:' or 'Unknown Speaker  0:06' "
            "or 'Speaker 1  00:36' or 'Mike Kerr  1:07'."
        ),
    )
    parser.add_argument(
        "--raw-footer-regex",
        default=r"^\s*Transcribed by\b.*",
        help=(
            "Regex for lines in A that are transcript footer/meta (e.g. "
            "'Transcribed by https://otter.ai') and should be skipped."
        ),
    )
    parser.add_argument(
        "--sic-correction-regex",
        # Match " [sic]" and optionally " (corrected words)" after it, to remove
        # the entire correction notation but leave the original word intact.
        #
        # Example:
        #   "Cobra [sic] (Tycho Brahe) said"
        #   -> pattern matches " [sic] (Tycho Brahe)"
        #   -> result: "Cobra said"
        default=r"\s+\[sic\](?: \([^)]+\))?",
        help=(
            "Regex that matches inline correction notations in B of the form "
            "'[sic]' or '[sic] (corrected text)'. Matched spans are removed "
            "from B before comparison."
        ),
    )

    args = parser.parse_args()

    # Construct file paths
    raw_file_path = SOURCE_DIR / args.raw_filename

    # Auto-construct formatted filename if not provided
    if args.formatted_file:
        formatted_file_path = FORMATTED_DIR / args.formatted_file
    else:
        # Convert "Title - Presenter - Date.txt" to "Title - Presenter - Date - formatted.md"
        stem = Path(args.raw_filename).stem
        formatted_filename = f"{stem} - formatted.md"
        formatted_file_path = FORMATTED_DIR / formatted_filename

    # Validate that input files exist
    if not raw_file_path.exists():
        print(f"Error: Raw transcript file not found: '{raw_file_path}'")
        print(
            f"Expected location: $TRANSCRIPTS_DIR/source/{args.raw_filename}")
        return
    if not formatted_file_path.exists():
        print(
            f"Error: Formatted transcript file not found: '{formatted_file_path}'")
        print(f"Expected location: {formatted_file_path}")
        return

    raw_text_raw = load_text(str(raw_file_path))
    formatted_text_raw = load_text(str(formatted_file_path))

    # Clean A (raw): strip speaker lines + footer
    raw_no_speakers = strip_speaker_lines(raw_text_raw, args.speaker_regex)
    raw_clean = strip_footer_lines(raw_no_speakers, args.raw_footer_regex)

    # Clean B (formatted):
    #   1) strip inline [sic] corrections
    #   2) strip speaker labels (**Speaker:**)
    #   3) strip section headings (timestamp-style first, then plain)
    formatted_no_sic, sic_count = strip_sic_corrections(
        formatted_text_raw, args.sic_correction_regex
    )
    formatted_no_speakers = strip_speaker_labels(formatted_no_sic)
    formatted_clean, heading_count = strip_heading_lines(
        formatted_no_speakers,
        heading_regex=args.heading_regex,
        heading_ts_regex=args.heading_ts_regex,
    )

    skip_words = load_skip_words(args.skip_words)

    result = compare_transcripts(
        raw_text=raw_clean,
        formatted_text=formatted_clean,
        skip_words=skip_words,
        max_lookahead=args.max_lookahead,
        max_mismatch_ratio=args.max_mismatch_ratio,
        max_mismatches=args.max_mismatches,
    )

    # Attach preprocessing counts to result for convenience
    result["section_headings_removed"] = heading_count
    result["sic_corrections_removed"] = sic_count

    print("=== Comparison Summary ===")
    print(f"A words:                    {result['a_word_count']}")
    print(f"B words (after cleaning):   {result['b_word_count']}")
    print(f"Checked words (A):          {result['checked_words']}")
    print(f"Mismatches:                 {result['mismatch_count']}")
    print(f"Mismatch ratio:             {result['mismatch_ratio']:.4f}")
    print(f"Stopped reason:             {result['stopped_reason']}")
    print(f"Section headings removed:   {result['section_headings_removed']}")
    print(f"[sic] corrections removed:  {result['sic_corrections_removed']}")

    mismatches = result["mismatches"]
    if mismatches:
        print()
        n_show = min(args.show_first, len(mismatches))
        print(f"=== First {n_show} mismatches ===")
        for m in mismatches[:n_show]:
            print(
                f"A[{m['a_index']}]='{m['a_word']}' vs "
                f"B[{m['b_index']}]='{m['b_word'] if m['b_index'] is not None else None}' "
                f"--> {m['reason']}"
            )


if __name__ == "__main__":
    main()
