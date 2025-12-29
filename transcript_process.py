#!/usr/bin/env python3
"""
Interactive Transcript Processing Pipeline

Guides user through complete transcript processing workflow:
1. Select source file from source directory
2. Format with Claude API
3. Validate word preservation
4. Add YAML front matter (with preview)
5. Generate summaries (archival + blog)
6. Validate emphasis items
7. Move source file to processed/ folder

Usage:
    python transcript_process.py
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional, Tuple
import config

# Script paths (in same directory as this script)
SCRIPT_DIR = Path(__file__).parent
FORMAT_SCRIPT = SCRIPT_DIR / "transcript_format.py"
VALIDATE_SCRIPT = SCRIPT_DIR / "transcript_validate_format.py"
ADD_YAML_SCRIPT = SCRIPT_DIR / "transcript_add_yaml.py"
SUMMARIZE_SCRIPT = SCRIPT_DIR / "transcript_summarize.py"

# Get Python executable
PYTHON = sys.executable


def setup_directories():
    """Ensure all required directories exist."""
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    config.SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    config.FORMATTED_DIR.mkdir(parents=True, exist_ok=True)


def list_source_files() -> list[Path]:
    """Get all .txt files in source directory."""
    if not config.SOURCE_DIR.exists():
        return []
    return sorted(config.SOURCE_DIR.glob("*.txt"))


def display_files(files: list[Path]) -> None:
    """Display numbered list of files."""
    print("\nAvailable source files:")
    print("-" * 80)
    for i, file in enumerate(files, 1):
        size_kb = file.stat().st_size / 1024
        print(f"  {i}. {file.name} ({size_kb:.1f} KB)")
    print("-" * 80)


def get_user_choice(prompt: str, max_value: Optional[int] = None) -> int:
    """Get numeric choice from user."""
    while True:
        try:
            choice = input(f"{prompt}: ").strip()
            if not choice:
                return 0
            value = int(choice)
            if max_value and (value < 1 or value > max_value):
                print(f"Please enter a number between 1 and {max_value}")
                continue
            return value
        except ValueError:
            print("Please enter a valid number")
        except KeyboardInterrupt:
            print("\n\nCancelled by user")
            sys.exit(0)


def confirm(prompt: str, default: bool = True) -> bool:
    """Ask yes/no question."""
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        try:
            response = input(f"{prompt}{suffix}: ").strip().lower()
            if not response:
                return default
            if response in ('y', 'yes'):
                return True
            if response in ('n', 'no'):
                return False
            print("Please enter 'y' or 'n'")
        except KeyboardInterrupt:
            print("\n\nCancelled by user")
            sys.exit(0)


def run_script(script: Path, args: list[str], description: str) -> Tuple[bool, int]:
    """Run a Python script and return success status and exit code."""
    print(f"\n{'='*80}")
    print(f"{description}")
    print('='*80)

    cmd = [PYTHON, str(script)] + args
    result = subprocess.run(cmd)

    success = result.returncode == 0
    if success:
        print(f"✅ {description} completed successfully")
    else:
        print(f"❌ {description} failed with exit code {result.returncode}")

    return success, result.returncode


def extract_metadata_from_filename(filename: str) -> Tuple[str, str, str]:
    """Extract title, author, date from filename pattern: 'Title - Author - Date.txt'"""
    # Remove .txt extension
    base = filename.replace('.txt', '')

    parts = [p.strip() for p in base.split(' - ')]

    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    elif len(parts) == 2:
        return parts[0], parts[1], ""
    else:
        return base, "", ""


def display_yaml_preview(formatted_file: Path) -> None:
    """Display the first 25 lines of the formatted file with YAML."""
    print("\n" + "="*80)
    print("YAML Front Matter Preview:")
    print("="*80)

    with open(formatted_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()[:25]
        for line in lines:
            print(line.rstrip())

    print("="*80)


def move_to_processed(source_file: Path) -> Path:
    """Move source file to processed/ folder and add 'Processed' to filename."""
    # Create new filename with 'Processed' suffix
    stem = source_file.stem
    new_name = f"{stem} - Processed{source_file.suffix}"
    dest_path = config.PROCESSED_DIR / new_name

    # Handle duplicate filenames
    counter = 1
    while dest_path.exists():
        new_name = f"{stem} - Processed ({counter}){source_file.suffix}"
        dest_path = config.PROCESSED_DIR / new_name
        counter += 1

    # Move file
    source_file.rename(dest_path)
    return dest_path


def main():
    """Main interactive processing loop."""
    print("\n" + "="*80)
    print("TRANSCRIPT PROCESSING PIPELINE")
    print("="*80)

    # Setup
    setup_directories()

    # List source files
    source_files = list_source_files()

    if not source_files:
        print(f"\n❌ No .txt files found in {config.SOURCE_DIR}")
        print("Please add transcript files to process.")
        return 1

    display_files(source_files)

    # Select file
    choice = get_user_choice(
        f"\nSelect file to process (1-{len(source_files)}, or 0 to exit)", len(source_files))
    if choice == 0:
        print("Exiting...")
        return 0

    source_file = source_files[choice - 1]
    print(f"\n📄 Selected: {source_file.name}")

    # Extract metadata for output filenames
    title, author, date = extract_metadata_from_filename(source_file.name)
    base_name = f"{title} - {author} - {date}"

    # Check existing files to determine starting point
    formatted_file = config.FORMATTED_DIR / f"{base_name} - formatted.md"
    has_formatted = formatted_file.exists()
    has_yaml = False

    # Check for YAML - either separate _yaml.md file or in formatted.md
    yaml_file = config.FORMATTED_DIR / f"{base_name} - yaml.md"
    if yaml_file.exists():
        has_yaml = True
    elif has_formatted:
        # Check if YAML exists by looking for "---" at start of formatted.md
        with open(formatted_file, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            has_yaml = (first_line == "---")

    # Show status
    print("\n" + "="*80)
    print("Current Status:")
    print(
        f"  📄 Source file: {'✅ Found' if source_file.exists() else '❌ Missing'}")
    print(
        f"  📝 Formatted file: {'✅ Found' if has_formatted else '❌ Not created'}")
    print(f"  📋 YAML front matter: {'✅ Added' if has_yaml else '❌ Not added'}")
    print("="*80)

    # Determine starting step
    start_step = 1

    if has_yaml:
        print("\n✨ File already formatted with YAML!")
        if confirm("Skip to summary generation?"):
            start_step = 4
        elif confirm("Re-run formatting from scratch?", default=False):
            start_step = 1
        else:
            print("Cancelled.")
            return 0
    elif has_formatted:
        print("\n✨ Formatted file exists!")
        if confirm("Skip formatting and start at validation?"):
            start_step = 2
        elif confirm("Re-run formatting from scratch?", default=False):
            start_step = 1
        else:
            print("Cancelled.")
            return 0
    else:
        if not confirm("\nProceed with formatting and validation?"):
            print("Cancelled.")
            return 0

    # Step 1: Format transcript (skip if starting later)
    if start_step <= 1:
        success, _ = run_script(
            FORMAT_SCRIPT,
            [str(source_file.name)],
            "STEP 1: Formatting Transcript"
        )

        if not success:
            print("\n❌ Formatting failed. Cannot continue.")
            return 1

    # Step 2: Validate transcript (skip if starting later)
    if start_step <= 2:
        success, _ = run_script(
            VALIDATE_SCRIPT,
            [str(source_file.name)],
            "STEP 2: Validating Word Preservation"
        )

        if not success:
            if not confirm("\n⚠️  Validation reported issues. Continue anyway?", default=False):
                print("Stopped at validation stage.")
                return 1

    # Step 3: Add YAML (skip if starting later)
    if start_step <= 3:
        if not confirm("\nProceed with adding YAML front matter?"):
            print("Stopped before YAML addition.")
            return 0

        success, _ = run_script(
            ADD_YAML_SCRIPT,
            [str(formatted_file.name)],
            "STEP 3: Adding YAML Front Matter"
        )

        if not success:
            print("\n❌ YAML addition failed.")
            return 1

        # Display YAML preview
        display_yaml_preview(formatted_file)

        if not confirm("\nDoes the YAML look correct?"):
            print("\n⚠️  Please manually edit the YAML in the formatted file.")
            if not confirm("Continue with summaries?", default=False):
                print("Stopped before summaries.")
                return 0

    # Step 4: Generate summaries
    if start_step <= 4:
        if not confirm("\nProceed with generating summaries?"):
            print("Stopped before summary generation.")
            return 0

    success, _ = run_script(
        SUMMARIZE_SCRIPT,
        [str(formatted_file.name)],
        "STEP 4: Generating Summaries (Archival + Blog)"
    )

    if not success:
        print("\n❌ Summary generation failed.")
        return 1

    # Step 5: Final confirmation
    print("\n" + "="*80)
    print("PROCESSING COMPLETE!")
    print("="*80)
    print(f"\n📁 Source file: {source_file}")
    print(f"📄 Formatted: {formatted_file}")
    print(
        f"📊 Summaries: {config.SUMMARIES_DIR / f'{base_name} - All Key Items.md'}")
    print(
        f"           : {config.SUMMARIES_DIR / f'{base_name} - blog.md'}")

    if confirm("\n✅ Everything looks good. Move source file to processed/?"):
        processed_path = move_to_processed(source_file)
        print(f"\n✅ Source file moved to: {processed_path}")
        print("\n🎉 Pipeline complete!")
    else:
        print("\n⚠️  Source file left in place for manual review.")
        print("You can process it again or manually move it to processed/ when ready.")

    return 0


if __name__ == "__main__":
    try:
        exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
