"""
Configuration for the transcript processing pipeline.
This module holds global variables for directory paths, which can be
updated by the GUI at runtime.
"""

from pathlib import Path
import os

# Default directories. By default, paths are relative to the project root.
TRANSCRIPTS_BASE = Path(os.getenv("TRANSCRIPTS_DIR", "."))
SOURCE_DIR = TRANSCRIPTS_BASE / "source"
FORMATTED_DIR = TRANSCRIPTS_BASE / "formatted"
SUMMARIES_DIR = TRANSCRIPTS_BASE / "summaries"
WEBPAGES_DIR = TRANSCRIPTS_BASE / "webpages"
PDFS_DIR = TRANSCRIPTS_BASE / "pdfs"
PROCESSED_DIR = TRANSCRIPTS_BASE / "processed"

# Default Model
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"


def set_transcripts_base(path: str | Path):
    """Update the base directory for transcripts and all related paths."""
    global TRANSCRIPTS_BASE, SOURCE_DIR, FORMATTED_DIR, SUMMARIES_DIR, WEBPAGES_DIR, PDFS_DIR, PROCESSED_DIR

    TRANSCRIPTS_BASE = Path(path)
    SOURCE_DIR = TRANSCRIPTS_BASE / "source"
    FORMATTED_DIR = TRANSCRIPTS_BASE / "formatted"
    SUMMARIES_DIR = TRANSCRIPTS_BASE / "summaries"
    WEBPAGES_DIR = TRANSCRIPTS_BASE / "webpages"
    PDFS_DIR = TRANSCRIPTS_BASE / "pdfs"
    PROCESSED_DIR = TRANSCRIPTS_BASE / "processed"
