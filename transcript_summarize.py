#!/usr/bin/env python3
"""
Transcript Summarizer using Claude API
Generates three types of outputs from formatted transcripts:
1. Archival Analysis (Abstract, Key Items, Academic Summary)
2. Key Terms (Domain terminology and definitions)
3. Blog Post (SEO-optimized content)

Each uses a separate API call for fresh context.

Usage:
    python transcript_summaries.py "Title - Presenter - Date - formatted.md"
    
Example:
    python transcript_summaries.py "Roots of Bowen Theory - Dr Michael Kerr - 2019-11-15 - formatted.md"
"""

import argparse
import os
from pathlib import Path
import anthropic
import re
from difflib import SequenceMatcher


# Directories (from environment variable)
TRANSCRIPTS_BASE = Path(
    os.getenv("TRANSCRIPTS_DIR", Path.home() / "transcripts"))
FORMATTED_DIR = TRANSCRIPTS_BASE / "formatted"
SUMMARIES_DIR = TRANSCRIPTS_BASE / "summaries"
PROMPTS_DIR = TRANSCRIPTS_BASE / "prompts"

# Prompt file names
EXTRACTS_SUMMARY_PROMPT = "Transcript Summary Abstract Key Items v1.md"
KEY_TERMS_PROMPT = "Transcript Summary Key Terms v1.md"
BLOG_PROMPT = "Transcript Summary Blog Post v1.md"


def normalize_text(text):
    """Normalize text for comparison by removing [sic] markers, extra whitespace, and punctuation variations."""
    # Remove [sic] and its variations
    text = re.sub(r'\[sic\]\s*\([^)]+\)', '', text)
    text = re.sub(r'\[sic\]', '', text)

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)

    # Remove leading/trailing whitespace
    text = text.strip()

    return text.lower()


def extract_emphasis_quotes(extracts_summary_file):
    """Extract all quoted text from Emphasized Items section."""
    with open(extracts_summary_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the Emphasized Items section
    match = re.search(
        r'## \*\*Emphasized Items\*\*(.*?)(?=---|\Z)', content, re.DOTALL)
    if not match:
        return []

    emphasis_section = match.group(1)

    # Extract all quotes (text between quotes after >)
    # Pattern: > **[Label]:** "quote text" - **[Type]**
    quote_pattern = r'>\s*\*\*([^*]+):\*\*\s*"([^"]+)"'
    quotes = re.findall(quote_pattern, emphasis_section)

    return [(label.strip(), quote.strip()) for label, quote in quotes]


def find_best_match(needle, haystack, threshold=0.85):
    """Find the best matching substring in haystack for needle.
    Returns (match_ratio, matched_text) or (0, None) if no good match."""

    needle_normalized = normalize_text(needle)
    haystack_normalized = normalize_text(haystack)

    # Try exact match first
    if needle_normalized in haystack_normalized:
        return (1.0, needle)

    # Try fuzzy matching on sliding windows
    needle_words = needle_normalized.split()
    needle_len = len(needle_words)

    # Use word-level matching for better handling of small differences
    haystack_words = haystack_normalized.split()

    best_ratio = 0
    best_match = None

    # Slide a window across the haystack
    for i in range(len(haystack_words) - needle_len + 1):
        window = ' '.join(haystack_words[i:i + needle_len])
        ratio = SequenceMatcher(None, needle_normalized, window).ratio()

        if ratio > best_ratio:
            best_ratio = ratio
            best_match = window

    if best_ratio >= threshold:
        return (best_ratio, best_match)

    return (best_ratio, None)


def validate_emphasis_items(formatted_file, extracts_summary_file):
    """Validate all emphasis quotes exist in the formatted transcript."""

    # Read formatted transcript
    with open(formatted_file, 'r', encoding='utf-8') as f:
        formatted_content = f.read()

    # Extract emphasis quotes from archival
    quotes = extract_emphasis_quotes(extracts_summary_file)

    if not quotes:
        print("⚠️  No emphasis quotes found to validate")
        return

    valid_count = 0
    invalid_count = 0
    partial_count = 0

    for label, quote in quotes:
        # Use first 15 words for matching
        quote_core = ' '.join(quote.split()[:15])
        ratio, _match = find_best_match(
            quote_core, formatted_content, threshold=0.80)

        if ratio >= 0.95:
            valid_count += 1
        elif ratio >= 0.80:
            partial_count += 1
        else:
            print(f"   ❌ NOT FOUND: {label}")
            print(f"      Quote: {quote[:100]}...")
            invalid_count += 1

    print("\n  Emphasis Items Validation:")
    print(f"    ✅ Exact matches: {valid_count}")
    if partial_count > 0:
        print(f"    ⚠️  Partial matches: {partial_count}")
    if invalid_count > 0:
        print(f"    ❌ Not found: {invalid_count}")

    accuracy = (valid_count + partial_count) / \
        len(quotes) * 100 if quotes else 0
    print(f"    Overall accuracy: {accuracy:.1f}%")

    if invalid_count > 0:
        print(
            f"\n  ⚠️  WARNING: {invalid_count} quotes could not be validated!")


def extract_key_terms_quotes(key_terms_file):
    """Extract all quoted text from Key Terms definitions."""
    with open(key_terms_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find all Key Terms sections (## Term Name)
    # Extract quotes from Definition sections
    # Pattern: Quotes appear in Definition: field, between double quotes
    quote_pattern = r'\*\*Definition:\*\*\s*["\"]([^""]+)["\"]'
    quotes = re.findall(quote_pattern, content, re.DOTALL)

    # Also catch quotes that span multiple lines or have narrative around them
    # Look for content between quotation marks in definition sections
    definition_blocks = re.findall(
        r'\*\*Definition:\*\*(.*?)(?=\*\*Source Location:\*\*|\Z)', content, re.DOTALL)

    all_quotes = []
    for block in definition_blocks:
        # Find all quoted text in this definition block
        block_quotes = re.findall(r'"([^"]+)"', block)
        all_quotes.extend([(None, q.strip())
                          for q in block_quotes if len(q.strip()) > 20])

    return all_quotes


def validate_key_terms_definitions(formatted_file, key_terms_file):
    """Validate that key terms definitions quote actual transcript text."""

    # Read formatted transcript
    with open(formatted_file, 'r', encoding='utf-8') as f:
        formatted_content = f.read()

    # Extract quotes from key terms
    quotes = extract_key_terms_quotes(key_terms_file)

    if not quotes:
        print("⚠️  No definition quotes found to validate")
        return

    valid_count = 0
    invalid_count = 0
    partial_count = 0

    for _label, quote in quotes:
        # Use first 15 words for matching
        quote_words = quote.split()
        if len(quote_words) > 15:
            quote_core = ' '.join(quote_words[:15])
        else:
            quote_core = quote

        ratio, _match = find_best_match(
            quote_core, formatted_content, threshold=0.80)

        if ratio >= 0.95:
            valid_count += 1
        elif ratio >= 0.80:
            partial_count += 1
        else:
            invalid_count += 1
            if invalid_count <= 3:  # Only show first 3 failures
                print(f"   ❌ NOT FOUND: {quote[:80]}...")

    print("\n  Key Terms Definition Validation:")
    print(f"    ✅ Exact matches: {valid_count}")
    if partial_count > 0:
        print(f"    ⚠️  Partial matches: {partial_count}")
    if invalid_count > 0:
        print(f"    ❌ Not found: {invalid_count}")

    accuracy = (valid_count + partial_count) / \
        len(quotes) * 100 if quotes else 0
    print(f"    Overall accuracy: {accuracy:.1f}%")

    if invalid_count > 3:
        print(f"    (Showing first 3 of {invalid_count} validation failures)")


def load_prompt(prompt_filename: str) -> str:
    """Load a prompt template."""
    prompt_path = PROMPTS_DIR / prompt_filename
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path}\n"
            f"Expected location: $TRANSCRIPTS_DIR/prompts/{prompt_filename}"
        )
    return prompt_path.read_text(encoding='utf-8')


def load_formatted_transcript(filename: str) -> str:
    """Load the formatted transcript."""
    transcript_path = FORMATTED_DIR / filename
    if not transcript_path.exists():
        raise FileNotFoundError(
            f"Formatted transcript not found: {transcript_path}\n"
            f"Expected location: $TRANSCRIPTS_DIR/formatted/{filename}"
        )
    return transcript_path.read_text(encoding='utf-8')


def parse_metadata(filename: str) -> dict:
    """Extract metadata from filename pattern: 'Title - Presenter - Date - formatted.md'"""
    stem = Path(filename).stem
    # Remove ' - formatted' suffix if present
    if stem.endswith(' - formatted'):
        stem = stem[:-12]

    parts = [p.strip() for p in stem.split(' - ')]

    if len(parts) < 3:
        return {
            "title": stem,
            "author": "Unknown",
            "date": "Unknown",
            "filename": filename
        }

    return {
        "title": parts[0],
        "author": parts[1],
        "date": parts[2],
        "filename": filename
    }


def fill_prompt_template(template: str, metadata: dict, transcript: str,
                         focus_keyword: str = "Family Systems",
                         target_audience: str = "General public interested in psychology") -> str:
    """Fill in the prompt template with metadata and transcript."""
    # Replace template variables
    filled = template.replace("{{title}}", metadata["title"])
    filled = filled.replace("{{author}}", metadata["author"])
    filled = filled.replace("{{date}}", metadata["date"])
    filled = filled.replace("{{filename}}", metadata["filename"])
    filled = filled.replace("{{focus_keyword}}", focus_keyword)
    filled = filled.replace("{{target_audience}}", target_audience)
    filled = filled.replace("{{doc_type}}", "Webinar Transcript")
    filled = filled.replace("{{insert_transcript_text_here}}", transcript)

    return filled


def generate_summary_with_claude(prompt: str, model: str = "claude-sonnet-4-5-20250929", temperature: float = 0.2) -> str:
    """Send prompt to Claude for summary generation."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable not set.\n"
            "Set it with: export ANTHROPIC_API_KEY='your-api-key'"
        )

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model=model,
        max_tokens=16000,
        temperature=temperature,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    # Display token usage
    print(f"   Tokens: {message.usage.input_tokens:,} input + {message.usage.output_tokens:,} output = {message.usage.input_tokens + message.usage.output_tokens:,} total")

    # Check for truncation
    if message.stop_reason == "max_tokens":
        print("\n⚠️  WARNING: Output was truncated due to token limit!")
        print("   The summary may be incomplete.")
        raise RuntimeError("Output truncated at max_tokens limit")

    # Warn if close to limit
    if message.usage.output_tokens > 14400:  # 90% of 16000
        print(
            f"   ⚠️  Warning: Used {message.usage.output_tokens:,}/16,000 output tokens ({message.usage.output_tokens/160:.0f}%)")

    return message.content[0].text


def save_summary(content: str, original_filename: str, summary_type: str) -> Path:
    """Save summary output."""
    stem = Path(original_filename).stem
    # Remove ' - formatted' if present
    if stem.endswith(' - formatted'):
        stem = stem[:-12]

    output_filename = f"{stem} - {summary_type}.md"
    output_path = SUMMARIES_DIR / output_filename

    # Create directory if it doesn't exist
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)

    output_path.write_text(content, encoding='utf-8')
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate summaries from a formatted transcript using Claude."
    )
    parser.add_argument(
        "formatted_filename",
        help="Filename of formatted transcript (e.g., 'Title - Presenter - Date - formatted.md')"
    )
    parser.add_argument(
        "--focus-keyword",
        default="Family Systems",
        help="Focus keyword for SEO (default: Family Systems)"
    )
    parser.add_argument(
        "--target-audience",
        default="General public interested in psychology",
        help="Target audience description"
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-5-20250929",
        help="Claude model to use (default: claude-sonnet-4-5-20250929)"
    )
    parser.add_argument(
        "--skip-extracts-summary",
        action="store_true",
        help="Skip extracts-summary analysis (Part 1)"
    )
    parser.add_argument(
        "--skip-terms",
        action="store_true",
        help="Skip key terms extraction (Part 2)"
    )
    parser.add_argument(
        "--skip-blog",
        action="store_true",
        help="Skip blog post generation (Part 3)"
    )

    args = parser.parse_args()

    try:
        # Load transcript
        print(f"Loading formatted transcript: {args.formatted_filename}")
        transcript = load_formatted_transcript(args.formatted_filename)
        metadata = parse_metadata(args.formatted_filename)

        print(f"Transcript metadata:")
        print(f"  Title: {metadata['title']}")
        print(f"  Author: {metadata['author']}")
        print(f"  Date: {metadata['date']}")
        print(f"  Length: {len(transcript)} characters")

        # Part 1: Extracts Summary Analysis
        if not args.skip_extracts_summary:
            print("\n" + "="*60)
            print("PART 1: Generating Extracts Summary Analysis...")
            print("="*60)

            extracts_summary_prompt_template = load_prompt(
                EXTRACTS_SUMMARY_PROMPT)
            extracts_summary_prompt = fill_prompt_template(
                extracts_summary_prompt_template,
                metadata,
                transcript,
                target_audience=args.target_audience
            )

            print(f"Sending to Claude (model: {args.model})...")
            extracts_summary_output = generate_summary_with_claude(
                extracts_summary_prompt, args.model)

            extracts_summary_path = save_summary(
                extracts_summary_output, args.formatted_filename, "extracts-summary")
            print(
                f"✓ Extracts summary analysis saved to: {extracts_summary_path}")

        # Part 2: Key Terms Extraction
        if not args.skip_terms:
            print("\n" + "="*60)
            print("PART 2: Extracting Key Terms...")
            print("="*60)

            key_terms_prompt_template = load_prompt(KEY_TERMS_PROMPT)
            key_terms_prompt = fill_prompt_template(
                key_terms_prompt_template,
                metadata,
                transcript
            )

            print(f"Sending to Claude (model: {args.model})...")
            # Use temperature 0.4 for balanced extraction/synthesis
            key_terms_output = generate_summary_with_claude(
                key_terms_prompt, args.model, temperature=0.4)

            key_terms_path = save_summary(
                key_terms_output, args.formatted_filename, "key-terms")
            print(f"✓ Key terms document saved to: {key_terms_path}")

        # Part 3: Blog Post
        if not args.skip_blog:
            print("\n" + "="*60)
            print("PART 3: Generating Blog Post...")
            print("="*60)

            blog_prompt_template = load_prompt(BLOG_PROMPT)
            blog_prompt = fill_prompt_template(
                blog_prompt_template,
                metadata,
                transcript,
                focus_keyword=args.focus_keyword,
                target_audience=args.target_audience
            )

            print(f"Sending to Claude (model: {args.model})...")
            blog_output = generate_summary_with_claude(blog_prompt, args.model)

            blog_path = save_summary(
                blog_output, args.formatted_filename, "blog")
            print(f"✓ Blog post saved to: {blog_path}")

        print("\n" + "="*60)
        print("✓ Summary generation complete!")
        print("="*60)

        # Validate emphasis items if extracts-summary was generated
        if not args.skip_extracts_summary:
            print("\n" + "="*60)
            print("VALIDATION: Checking Emphasis Items...")
            print("="*60)
            formatted_path = FORMATTED_DIR / args.formatted_filename
            validate_emphasis_items(formatted_path, extracts_summary_path)
            print("="*60)

        # Validate key terms definitions if key terms was generated
        if not args.skip_terms:
            print("\n" + "="*60)
            print("VALIDATION: Checking Key Terms Definitions...")
            print("="*60)
            formatted_path = FORMATTED_DIR / args.formatted_filename
            validate_key_terms_definitions(formatted_path, key_terms_path)
            print("="*60)

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
