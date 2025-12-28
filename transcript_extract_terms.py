#!/usr/bin/env python3
"""
Transcript Key Terms Extractor using Claude API
Extracts domain-specific terminology and their definitions from formatted transcripts.

Usage:
    python transcript_extract_terms.py "Title - Presenter - Date - formatted.md"
    
Example:
    python transcript_extract_terms.py "Roots of Bowen Theory - Dr Michael Kerr - 2019-11-15 - formatted.md"
"""

import argparse
import os
from pathlib import Path
import anthropic
import config
from transcript_utils import parse_filename_metadata


def load_prompt() -> str:
    """Load the key terms extraction prompt template."""
    prompt_path = config.PROMPTS_DIR / config.PROMPT_KEY_TERMS_FILENAME
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path}\n"
            f"Expected location: {config.PROMPTS_DIR}/{config.PROMPT_KEY_TERMS_FILENAME}"
        )
    return prompt_path.read_text(encoding='utf-8')


def load_formatted_transcript(filename: str) -> str:
    """Load the formatted transcript."""
    # Allow - yaml.md as well
    if filename.endswith(" - yaml.md"):
        pass
    # Handle both with and without - formatted suffix
    elif not filename.endswith(" - formatted.md"):
        # Strip .txt or other extensions and add - formatted.md
        base = filename.replace(".txt", "").replace(".md", "")
        filename = f"{base} - formatted.md"

    transcript_path = config.FORMATTED_DIR / filename
    if not transcript_path.exists():
        raise FileNotFoundError(
            f"Formatted transcript not found: {transcript_path}\n"
            f"Expected location: {config.FORMATTED_DIR}/{filename}"
        )
    return transcript_path.read_text(encoding='utf-8')


def extract_key_terms_with_claude(transcript: str, metadata: dict, prompt_template: str) -> str:
    """Send transcript to Claude for key terms extraction."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable not set.\n"
            "Set it with: export ANTHROPIC_API_KEY='your-api-key'"
        )

    client = anthropic.Anthropic(api_key=api_key)

    # Replace template variables
    prompt = prompt_template.replace("{{author}}", metadata["author"])
    prompt = prompt.replace("{{date}}", metadata["date"])
    prompt = prompt.replace("{{title}}", metadata["title"])
    prompt = prompt.replace("{{filename}}", metadata["filename"])
    prompt = prompt.replace("{{insert_transcript_text_here}}", transcript)

    print("Extracting key terms with Claude...", flush=True)
    print(f"Transcript length: {len(transcript)} characters", flush=True)
    print("⏳ Waiting for Claude response (typically 1-2 minutes)...", flush=True)

    message = client.messages.create(
        model=config.DEFAULT_MODEL,
        max_tokens=config.MAX_TOKENS_EXTRACTION,
        temperature=0.4,  # Moderate temperature for balanced extraction/synthesis
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    # Display token usage
    print(f"\n✅ Key terms extracted")
    print(f"   Tokens used: {message.usage.input_tokens:,} input + {message.usage.output_tokens:,} output = {message.usage.input_tokens + message.usage.output_tokens:,} total")

    # Check for truncation
    if message.stop_reason == "max_tokens":
        print("\n⚠️  WARNING: Term extraction truncated!")
        raise RuntimeError("Output truncated at max_tokens limit")

    # Warn if close to limit
    if message.usage.output_tokens > 7200:  # ~90% of 8192
        print(
            f"   ⚠️  Warning: Used {message.usage.output_tokens:,}/8,192 output tokens ({message.usage.output_tokens/81.92:.0f}%)")

    return message.content[0].text


def save_key_terms(content: str, original_filename: str) -> Path:
    """Save the key terms document."""
    # Create output filename
    stem = Path(original_filename).stem
    stem = stem.replace(" - formatted", "")
    output_filename = f"{stem} - key-terms.md"
    output_path = config.SUMMARIES_DIR / output_filename

    # Ensure summaries directory exists
    config.SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)

    # Clean up any marker tags that might have appeared
    content = content.replace("<<<TERM_START>>>", "")
    content = content.replace("<<<TERM_END>>>", "")

    # Clean up any extra blank lines from marker removal
    import re
    content = re.sub(r'\n{3,}', '\n\n', content)

    # Save the content
    output_path.write_text(content, encoding='utf-8')

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Extract key terms and definitions from formatted transcripts"
    )
    parser.add_argument(
        "formatted_filename",
        help='Formatted transcript filename (e.g., "Title - Presenter - Date - formatted.md")'
    )

    args = parser.parse_args()

    try:
        # Load inputs
        print("Loading prompt template...", flush=True)
        prompt_template = load_prompt()

        print(
            f"Loading formatted transcript: {args.formatted_filename}", flush=True)
        transcript = load_formatted_transcript(args.formatted_filename)

        # Parse metadata
        metadata = parse_filename_metadata(args.formatted_filename)
        print("Transcript metadata:", flush=True)
        print(f"  Title: {metadata['title']}", flush=True)
        print(f"  Author: {metadata['author']}", flush=True)
        print(f"  Date: {metadata['date']}", flush=True)

        # Extract key terms
        key_terms_content = extract_key_terms_with_claude(
            transcript, metadata, prompt_template
        )

        # Save output
        output_path = save_key_terms(
            key_terms_content, args.formatted_filename)

        print("\n✓ Success!", flush=True)
        print(f"Key terms document saved to: {output_path}", flush=True)

        return 0

    except (OSError, IOError, anthropic.APIError) as e:
        print(f"\n✗ Error: {e}", flush=True)
        return 1


if __name__ == "__main__":
    exit(main())
