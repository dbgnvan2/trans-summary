"""
YAML Injector for Formatted Transcripts
Run after successful validation to prepend YAML front matter.

Uses environment variable TRANSCRIPTS_DIR to locate transcript files.
Set it to point to your Google Drive or other shared location.

Setup:
    export TRANSCRIPTS_DIR="/path/to/your/transcripts"
    # or for Google Drive:
    # export TRANSCRIPTS_DIR="$HOME/Google Drive/transcripts"

Usage:
    python yaml_injector.py "Title - Presenter - Date.txt"
    python yaml_injector.py "Title - Presenter - Date.txt" --source-ext mp3

Example:
    python yaml_injector.py "Roots of Bowen Theory - Dr. Michael Kerr - 2024-01-15.txt"
"""

import argparse
import os
import re
from pathlib import Path


# Default directories (from environment variable or fallback to home directory)
TRANSCRIPTS_BASE = Path(
    os.getenv("TRANSCRIPTS_DIR", Path.home() / "transcripts"))
DEFAULT_INPUT_DIR = TRANSCRIPTS_BASE / "formatted"
DEFAULT_OUTPUT_DIR = TRANSCRIPTS_BASE / "formatted"  # same dir


def parse_filename(filename: str) -> dict:
    """
    Extract metadata from filename pattern: 'Title - Presenter - Date.ext'

    Args:
        filename: Transcript filename

    Returns:
        dict with title, presenter, date, year keys
    """
    stem = Path(filename).stem
    parts = [p.strip() for p in stem.split(" - ")]

    if len(parts) < 3:
        raise ValueError(
            f"Filename must follow pattern 'Title - Presenter - Date.ext', got: {filename}"
        )

    meta = {
        "title": parts[0],
        "presenter": parts[1],
        "date": parts[2],
    }

    # Extract year from date (default to "unknown" if not found)
    year_match = re.search(r'(\d{4})', meta["date"])
    if year_match:
        meta["year"] = year_match.group(1)
    else:
        # Handle cases like "unknown", "TBD", or malformed dates
        meta["year"] = "unknown"

    return meta


def generate_yaml_front_matter(meta: dict, source_filename: str) -> str:
    """
    Generate YAML front matter block.

    Args:
        meta: Dictionary with title, presenter, date, year
        source_filename: Name of source recording file

    Returns:
        YAML front matter string with delimiters
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


def inject_yaml(
    transcript_filename: str,
    source_ext: str = "mp4",
    input_dir: str | Path | None = None,
    output_dir: str | Path | None = None
) -> Path:
    """
    Read formatted transcript, prepend YAML front matter, save output.

    Args:
        transcript_filename: Name of formatted transcript file
        source_ext: Extension of source recording (mp4, mp3, etc.)
        input_dir: Input directory (default: ./transcripts/formatted/new)
        output_dir: Output directory (default: same as input_dir)

    Returns:
        Path to saved output file
    """
    input_dir = Path(input_dir) if input_dir else DEFAULT_INPUT_DIR
    output_dir = Path(output_dir) if output_dir else input_dir

    # Paths
    transcript_path = input_dir / transcript_filename
    stem = Path(transcript_filename).stem

    # Parse metadata from filename
    meta = parse_filename(transcript_filename)

    # Construct source recording filename (same stem, different extension)
    source_filename = f"{stem}.{source_ext.lstrip('.')}"

    # Read formatted content
    formatted_content = transcript_path.read_text(encoding='utf-8')

    # Generate and prepend YAML
    yaml_block = generate_yaml_front_matter(meta, source_filename)
    final_content = yaml_block + formatted_content

    # Save output
    output_path = output_dir / f"{stem}_yaml.md"
    output_path.write_text(final_content, encoding='utf-8')

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Prepend YAML front matter to a formatted transcript."
    )
    parser.add_argument(
        "transcript_filename",
        help="Filename of the formatted transcript (e.g., 'Title - Presenter - Date.txt')"
    )
    parser.add_argument(
        "--source-ext",
        default="mp4",
        help="Extension of source recording file (default: mp4)"
    )
    parser.add_argument(
        "--input-dir",
        default=None,
        help=f"Input directory (default: $TRANSCRIPTS_DIR/formatted/new or {DEFAULT_INPUT_DIR})"
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: same as input-dir)"
    )

    args = parser.parse_args()

    try:
        output_path = inject_yaml(
            transcript_filename=args.transcript_filename,
            source_ext=args.source_ext,
            input_dir=args.input_dir,
            output_dir=args.output_dir
        )
        print(f"Success: {output_path}")

        # Show first 20 lines to confirm YAML was added
        print("\n=== First 20 lines of output file ===")
        with open(output_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f, 1):
                if i > 20:
                    break
                print(line.rstrip())

        return 0
    except (OSError, IOError, ValueError) as e:
        print(f"Error: {e}")
        return 1


# --- For agent integration ---

def inject_yaml_from_content(
    filename: str,
    formatted_content: str,
    source_ext: str = "mp4"
) -> str:
    """
    Agent-friendly function: inject YAML into content strinßg.

    Args:
        filename: Original filename for metadata parsing
        formatted_content: Validated formatted transcript content
        source_ext: Extension of source recording

    Returns:
        Final content with YAML prepended
    """
    meta = parse_filename(filename)
    stem = Path(filename).stem
    source_filename = f"{stem}.{source_ext.lstrip('.')}"
    yaml_block = generate_yaml_front_matter(meta, source_filename)
    return yaml_block + formatted_content


if __name__ == "__main__":
    exit(main())
