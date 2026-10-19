"""Read the transcription tool's header and say whether the transcript is complete.

The transcription tool (TRX) starts each raw transcript with a header::

    TRANSCRIPT
    ==========
    Source file:  ...
    Duration:     01:28:00
    Warnings:     Cloud transcription used chunked upload (12 part(s), 480s each).; Cloud
                  transcription incomplete: transcribed 5 of 12 chunks; missing time ranges
                  (approx.): 00:24:00-00:32:00, ...
    --------------------------------------------------

(the Warnings value is one line in the file). When the tool reports that it could not
transcribe part of the recording, every output covers only the transcribed parts. This
module finds that warning so the run can say so; it never stops a run.

Purpose: Detect an incomplete source transcript from the tool's own header.
Spec:    docs/plan_incomplete_transcript_2026-10-19.md#IT1
Tests:   tests/test_source_completeness_it.py::test_it1a_real_incomplete_header_is_parsed
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import config

_SEPARATOR = re.compile(r"^-{10,}\s*$")
# Without a separator, read no further than the window detect_transcript_source_format uses.
_HEADER_WINDOW = 12
_SEPARATOR_WINDOW = 20
# The tool joins warnings with "; ". A warning can itself contain "; " ("...WhisperX
# version; skipped."), so split only after a period, or before a capital letter: the
# incomplete warning ends with a time range, not a period, and the next warning
# starts with a capital ("...01:36:00; Dropped 6 of 650 segment(s)...").
_WARNING_SPLIT = re.compile(r"(?<=\.);\s*|;\s+(?=[A-Z])")
_CHUNKS = re.compile(r"transcribed\s+(\d+)\s+of\s+(\d+)\s+chunks", re.IGNORECASE)
_RANGE = re.compile(r"\b(\d{1,2}:\d{2}:\d{2})\s*-\s*(\d{1,2}:\d{2}:\d{2})\b")


@dataclass
class SourceCompleteness:
    has_header: bool = False
    warnings: list = field(default_factory=list)  # every warning, as written
    incomplete: bool = False
    incomplete_warning: Optional[str] = None  # the tool's incomplete warning, as written
    chunks_transcribed: Optional[int] = None
    chunks_total: Optional[int] = None
    missing_ranges: list = field(default_factory=list)  # [(start, end)], as written
    details_readable: bool = False


def _header_lines(text: str) -> Optional[list]:
    """The header's lines, or None when the text has no transcription-tool header.

    A header is one the first non-blank line of which is ``TRANSCRIPT``, or one that
    ``detect_transcript_source_format`` recognises: whatever the source-fidelity
    check strips as a header is read here too.
    """
    # Imported here: formatting_pipeline imports this module.
    from formatting_pipeline import detect_transcript_source_format

    if text.startswith("﻿"):
        text = text[1:]
    lines = text.splitlines()
    first = next((line.strip() for line in lines if line.strip()), "")
    if first != "TRANSCRIPT" and detect_transcript_source_format(text) != "trx_whisper_wrapped":
        return None
    for index, line in enumerate(lines[:_SEPARATOR_WINDOW]):
        if _SEPARATOR.match(line):
            return lines[:index]
    return lines[:_HEADER_WINDOW]


def read_header(text: str) -> SourceCompleteness:
    """Parse the header of a raw transcript. The body is never read.

    Purpose: Turn the tool's Warnings line into a completeness record.
    Spec:    docs/plan_incomplete_transcript_2026-10-19.md#IT1.a
    Tests:   tests/test_source_completeness_it.py::test_it1a_real_incomplete_header_is_parsed,
             ::test_it1c_malformed_header_still_flagged, ::test_it1e_body_text_and_near_miss_not_flagged
    """
    header = _header_lines(text)
    if header is None:
        return SourceCompleteness()
    result = SourceCompleteness(has_header=True)
    value = next((line.split(":", 1)[1].strip() for line in header
                  if line.strip().startswith("Warnings:")), "")
    result.warnings = [w.strip() for w in _WARNING_SPLIT.split(value) if w.strip()]
    markers = [m.lower() for m in config.SOURCE_INCOMPLETE_MARKERS]
    for warning in result.warnings:
        chunks = _CHUNKS.search(warning)
        if (any(marker in warning.lower() for marker in markers)
                or (chunks and int(chunks[1]) < int(chunks[2]))):
            result.incomplete = True
            result.incomplete_warning = warning
            break
    if not result.incomplete:
        return result
    chunks = _CHUNKS.search(result.incomplete_warning)
    if chunks:
        result.chunks_transcribed, result.chunks_total = int(chunks[1]), int(chunks[2])
    result.missing_ranges = _RANGE.findall(result.incomplete_warning)
    # The tool lists one range per missing chunk. If the numbers don't add up, the
    # details are not trusted and the tool's own words are quoted instead.
    result.details_readable = bool(
        chunks and result.missing_ranges
        and len(result.missing_ranges) == result.chunks_total - result.chunks_transcribed)
    return result


def read_file(path: Path) -> SourceCompleteness:
    """``read_header`` on a file. An unreadable file raises (callers report it)."""
    return read_header(Path(path).read_text(encoding="utf-8-sig", errors="replace"))


def join_ranges(ranges: list) -> list:
    """Join ranges where one ends exactly where the next starts, for display."""
    joined = []
    for start, end in ranges:
        if joined and joined[-1][1] == start:
            joined[-1] = (joined[-1][0], end)
        else:
            joined.append((start, end))
    return joined


def incomplete_message(c: SourceCompleteness, source_name: str) -> str:
    """One plain message for the log, the Confirm dialog and the gate detail.

    Purpose: Say what is missing, from the tool's own numbers, with no derived figure.
    Spec:    docs/plan_incomplete_transcript_2026-10-19.md#IT1.f
    Tests:   tests/test_source_completeness_it.py::test_it1f_message_joins_touching_ranges
    """
    if c.details_readable:
        ranges = ", ".join(f"{s}-{e}" for s, e in join_ranges(c.missing_ranges))
        what = (f"the transcription tool transcribed {c.chunks_transcribed} of "
                f"{c.chunks_total} chunks. Missing (approx.): {ranges}.")
    else:
        what = (f"the transcription tool says so, but its details could not be read: "
                f"\"{c.incomplete_warning}\".")
    return (f"The source transcript is incomplete: {what} The summary, abstract and other "
            f"outputs cover only the transcribed parts. Source: {source_name}.")


def notices(c: SourceCompleteness, source_name: str) -> list:
    """Lines to log for this transcript, as ``[(level, text)]``, level "info" or "warning".

    Every warning in the header goes in one info line, word for word (IT0.f); an
    incomplete transcript adds the warning message. A transcript with no header or
    no warnings gives nothing; callers say so in their own words if they need to.

    Spec:    docs/plan_incomplete_transcript_2026-10-19.md#IT2
    Tests:   tests/test_source_completeness_it.py::test_it1f_notices_levels
    """
    lines = []
    if c.warnings:
        lines.append(("info", f"Transcription tool warnings ({source_name}): "
                              + "; ".join(c.warnings)))
    if c.incomplete:
        lines.append(("warning", incomplete_message(c, source_name)))
    return lines


def gate_item(c: SourceCompleteness, source_name: str) -> dict:
    """The release-gate item for one incomplete source file (ranges as written)."""
    return {"file": source_name,
            "chunks_transcribed": c.chunks_transcribed,
            "chunks_total": c.chunks_total,
            "missing_ranges": [f"{s}-{e}" for s, e in c.missing_ranges],
            "warning": c.incomplete_warning}
