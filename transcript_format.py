#!/usr/bin/env python3
"""
Transcript Formatter using Claude API
Formats raw transcripts using the v10 prompt template.

Usage:
    python format_transcript.py "Title - Presenter - Date.txt"
    
Example:
    python format_transcript.py "Roots of Bowen Theory - Dr. Michael Kerr - 2019-11-15.txt"
"""

import argparse
import os
from pathlib import Path
import anthropic


# Directories (from environment variable)
TRANSCRIPTS_BASE = Path(
    os.getenv("TRANSCRIPTS_DIR", Path.home() / "transcripts"))
SOURCE_DIR = TRANSCRIPTS_BASE / "source"
FORMATTED_DIR = TRANSCRIPTS_BASE / "formatted"
PROMPTS_DIR = TRANSCRIPTS_BASE / "prompts"

# Prompt file name
PROMPT_FILENAME = "Transcript Formatting Prompt v10.md"


def load_prompt() -> str:
    """Load the formatting prompt template."""
    prompt_path = PROMPTS_DIR / PROMPT_FILENAME
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path}\n"
            f"Expected location: $TRANSCRIPTS_DIR/prompts/{PROMPT_FILENAME}"
        )
    return prompt_path.read_text(encoding='utf-8')


def load_raw_transcript(filename: str) -> str:
    """Load the raw transcript from source directory."""
    transcript_path = SOURCE_DIR / filename
    if not transcript_path.exists():
        raise FileNotFoundError(
            f"Raw transcript not found: {transcript_path}\n"
            f"Expected location: $TRANSCRIPTS_DIR/source/{filename}"
        )
    return transcript_path.read_text(encoding='utf-8')


def format_transcript_with_claude(raw_transcript: str, prompt_template: str, model: str = "claude-sonnet-4-20250514") -> str:
    """Send transcript to Claude for formatting."""
    import threading
    import time

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable not set.\n"
            "Set it with: export ANTHROPIC_API_KEY='your-api-key'"
        )

    client = anthropic.Anthropic(api_key=api_key)

    # Combine prompt template with transcript
    full_prompt = f"{prompt_template}\n\n---\n\nRAW TRANSCRIPT:\n\n{raw_transcript}"

    print("Sending transcript to Claude...", flush=True)
    print(f"Transcript length: {len(raw_transcript)} characters", flush=True)
    print("⏳ Waiting for Claude response (may take 2-5 minutes for longer transcripts)...", flush=True)

    # Progress indicator in background
    stop_progress = threading.Event()

    def show_progress():
        dots = 0
        while not stop_progress.is_set():
            time.sleep(30)
            if not stop_progress.is_set():
                dots = (dots + 1) % 4
                print(f"   Still processing{'.' * (dots + 1)}", flush=True)

    progress_thread = threading.Thread(target=show_progress, daemon=True)
    progress_thread.start()

    try:
        message = client.messages.create(
            model=model,
            max_tokens=16000,
            messages=[
                {"role": "user", "content": full_prompt}
            ]
        )

        # Display token usage
        print(f"\n✅ Formatting complete")
        print(f"   Tokens used: {message.usage.input_tokens:,} input + {message.usage.output_tokens:,} output = {message.usage.input_tokens + message.usage.output_tokens:,} total")

        # Check for truncation
        if message.stop_reason == "max_tokens":
            print("\n⚠️  WARNING: Output was truncated due to token limit!")
            print("   The transcript may be incomplete. Consider:")
            print("   - Increasing max_tokens")
            print("   - Processing in smaller chunks")
            raise RuntimeError("Output truncated at max_tokens limit")

        # Warn if close to limit
        if message.usage.output_tokens > 14400:  # 90% of 16000
            print(
                f"\n⚠️  Warning: Used {message.usage.output_tokens:,}/16,000 output tokens ({message.usage.output_tokens/160:.0f}%)")
            print("   Consider increasing max_tokens for longer transcripts")

        return message.content[0].text
    finally:
        stop_progress.set()
        progress_thread.join(timeout=1)


def save_formatted_transcript(content: str, original_filename: str) -> Path:
    """Save formatted transcript with naming convention."""
    stem = Path(original_filename).stem
    output_filename = f"{stem} - formatted.md"
    output_path = FORMATTED_DIR / output_filename

    # Create directory if it doesn't exist
    FORMATTED_DIR.mkdir(parents=True, exist_ok=True)

    output_path.write_text(content, encoding='utf-8')
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Format a raw transcript using Claude and the v10 prompt template."
    )
    parser.add_argument(
        "raw_filename",
        help="Filename of raw transcript in source directory (e.g., 'Title - Presenter - Date.txt')"
    )
    parser.add_argument(
        "--model",
        default="claude-3-5-sonnet-20241022",
        help="Claude model to use (default: claude-3-5-sonnet-20241022)"
    )

    args = parser.parse_args()

    try:
        # Validate directories
        if not SOURCE_DIR.exists():
            raise FileNotFoundError(
                f"Source directory not found: {SOURCE_DIR}\n"
                f"Please create it or check your TRANSCRIPTS_DIR environment variable."
            )

        # Load prompt template
        print(f"Loading prompt template from: {PROMPTS_DIR}", flush=True)
        prompt_template = load_prompt()

        # Load raw transcript
        print(f"Loading raw transcript: {args.raw_filename}", flush=True)
        raw_transcript = load_raw_transcript(args.raw_filename)

        # Format with Claude
        formatted_content = format_transcript_with_claude(
            raw_transcript, prompt_template)

        # Save output
        output_path = save_formatted_transcript(
            formatted_content, args.raw_filename)

        print("\n✓ Success!", flush=True)
        print(f"Formatted transcript saved to: {output_path}", flush=True)
        print("\nNext steps:", flush=True)
        print(
            f"1. Validate: python transcript_formatting_v10.py \"{args.raw_filename}\" \"{output_path.name}\"", flush=True)
        print(
            f"2. Add YAML: python yaml_injector.py \"{output_path.name}\"", flush=True)

        return 0

    except (OSError, IOError, anthropic.APIError) as e:
        print(f"Error: {e}", flush=True)
        return 1


if __name__ == "__main__":
    exit(main())
