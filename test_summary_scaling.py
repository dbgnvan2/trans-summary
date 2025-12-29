
import config
import summary_pipeline
import summary_validation
import transcript_utils
import pipeline
from pathlib import Path
import anthropic
import os

# Setup
config.set_transcripts_base("/Users/davemini2/transcripts")
base_name = "This is a test - Dave Galloway - 2025-12-07"
api_key = os.getenv("ANTHROPIC_API_KEY")

if not api_key:
    print("Error: ANTHROPIC_API_KEY not set")
    exit(1)

client = anthropic.Anthropic(api_key=api_key)


def run_test(target_words):
    print(f"\n--- Testing Target: {target_words} words ---")

    try:
        # Load data
        formatted_file = config.FORMATTED_DIR / f"{base_name} - formatted.md"
        extracts_file = config.SUMMARIES_DIR / \
            f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"

        if not formatted_file.exists():
            print(f"File not found: {formatted_file}")
            return

        transcript = formatted_file.read_text(encoding='utf-8')
        transcript = transcript_utils.strip_yaml_frontmatter(transcript)

        extracts_content = extracts_file.read_text(encoding='utf-8')
        extracts_content = transcript_utils.strip_yaml_frontmatter(
            extracts_content)

        metadata = transcript_utils.parse_filename_metadata(base_name)

        # Use extract_section from transcript_utils directly
        topics = transcript_utils.extract_section(extracts_content, 'Topics')
        themes = transcript_utils.extract_section(
            extracts_content, 'Key Themes')

        # Generate
        input_data = summary_pipeline.prepare_summary_input(
            metadata, topics, themes, transcript, target_word_count=target_words
        )

        print(f"Target Closing: {input_data.closing.word_allocation} words")

        print("Generating...")
        summary = summary_pipeline.generate_summary(input_data, client)

        # Validate
        res = summary_validation.check_proportionality(summary, input_data)

        closing_res = next(
            s for s in res['sections'] if s['name'] == 'Closing')
        print(f"Actual Closing: {closing_res['actual']} words")
        print(f"Deviation: {closing_res['deviation']*100:.1f}%")
        print(f"Pass: {closing_res['within_tolerance']}")

    except Exception as e:
        print(f"Test failed: {e}")


if __name__ == "__main__":
    # run_test(500) # We know this fails
    run_test(600)
    run_test(750)
