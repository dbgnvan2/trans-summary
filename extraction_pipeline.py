"Pipeline module for extracting insights, summaries, and emphasis items."

import os
import re
from pathlib import Path

import anthropic

import abstract_pipeline
import config

# We need imports for structured summary generation if summarize_transcript calls it
import summary_pipeline
from transcript_utils import (
    call_claude_with_retry,
    create_system_message_with_cache,
    extract_section,
    parse_filename_metadata,
    parse_scored_emphasis_output,
    setup_logging,
    strip_yaml_frontmatter,
    validate_emphasis_item,
    validate_input_file,
)
from validation_pipeline import validate_emphasis_items, validate_summary_coverage

# Helpers


def _load_summary_prompt(prompt_filename: str) -> str:
    """Load a summary prompt template."""
    prompt_path = config.PROMPTS_DIR / prompt_filename
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path}\nExpected location: {config.PROMPTS_DIR}/{prompt_filename}"
        )
    return prompt_path.read_text(encoding="utf-8")


def _load_formatted_transcript(filename: str) -> str:
    """Load the formatted transcript."""
    if Path(filename).is_file():
        return Path(filename).read_text(encoding="utf-8")

    meta = parse_filename_metadata(filename)
    stem = meta["stem"]
    transcript_path = config.PROJECTS_DIR / stem / filename
    if transcript_path.exists():
        return transcript_path.read_text(encoding="utf-8")

    legacy_path = config.TRANSCRIPTS_BASE / "formatted" / filename
    if legacy_path.exists():
        return legacy_path.read_text(encoding="utf-8")

    validate_input_file(transcript_path)
    return transcript_path.read_text(encoding="utf-8")


def _fill_prompt_template(
    template: str, metadata: dict, transcript: str, **kwargs
) -> str:
    """Fill in the prompt template."""
    placeholders = {**metadata, **kwargs}
    for key, value in placeholders.items():
        pattern = re.compile(
            r"{{{{\s*{}\\s*}}}}".format(re.escape(key)), re.IGNORECASE)
        template = pattern.sub(lambda m: str(value), template)
    template = template.replace("{{insert_transcript_text_here}}", transcript)
    return template


def _generate_summary_with_claude(
    prompt: str,
    model: str,
    temperature: float,
    logger,
    min_length: int = 50,
    min_words: int = 0,
    timeout: float = config.TIMEOUT_SUMMARY,
    **kwargs,
) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set.")
    client = anthropic.Anthropic(api_key=api_key)

    message = call_claude_with_retry(
        client=client,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=config.MAX_TOKENS_EXTRACTION,
        temperature=temperature,
        stream=True,
        min_length=min_length,
        min_words=min_words,
        timeout=timeout,
        logger=logger,
        **kwargs,
    )
    return message.content[0].text


def _normalize_headers(text: str) -> str:
    """Ensure standard headers for key sections."""
    # Matches lines that look like headers:
    # ^ (start), optional #, optional *, "Topics", optional *, optional :, space*, $ (end)

    # Normalize Topics
    text = re.sub(r'^\s*(?:#+\s*)?(?:[\*\_]+)?(?:\d+\.?\s*)?Topics\b.*$',
                  '## Topics', text, flags=re.MULTILINE | re.IGNORECASE)
    # Normalize Key Themes
    text = re.sub(r'^\s*(?:#+\s*)?(?:[\*\_]+)?(?:\d+\.?\s*)?Key Themes\b.*$',
                  '## Key Themes', text, flags=re.MULTILINE | re.IGNORECASE)
    # Normalize Key Terms
    text = re.sub(r'^\s*(?:#+\s*)?(?:[\*\_]+)?(?:\d+\.?\s*)?Key Terms\b.*$',
                  '## Key Terms', text, flags=re.MULTILINE | re.IGNORECASE)
    return text


def _clean_bowen_output(text: str) -> str:
    """
    Cleans the raw output from the LLM for Bowen references.
    Removes any leading heading like "## Bowen References" and ensures each
    reference starts with '> '.
    Also strips list markers (1., -, *) to ensure clean blockquote format.
    """
    lines = text.strip().split('\n')
    cleaned_lines = []

    # Remove leading heading if present
    if lines and re.match(r'^\s*#+\s*Bowen\s+References', lines[0], re.IGNORECASE):
        lines.pop(0)  # Remove the heading line
        # Also remove any potential blank lines or separator lines that might follow
        while lines and (not lines[0].strip() or lines[0].strip() == '---'):
            lines.pop(0)

    for line in lines:
        stripped_line = line.strip()
        if stripped_line:
            # Remove existing blockquote marker to clean up what follows
            if stripped_line.startswith('>'):
                content = stripped_line[1:].strip()
            else:
                content = stripped_line

            # Remove list markers (1., -, *)
            # Matches "1. ", "1) ", "- ", "* " at start of content
            content = re.sub(r'^(?:\d+[\.\)]|[-*])\s+', '', content)

            # Re-add blockquote marker
            cleaned_lines.append(f"> {content}")

    return "\n".join(cleaned_lines)


def _save_summary(content: str, original_filename: str, summary_type: str) -> Path:
    """Save summary output."""
    stem = Path(original_filename).stem
    if stem.endswith(config.SUFFIX_FORMATTED.replace(".md", "")):
        stem = stem.replace(config.SUFFIX_FORMATTED.replace(".md", ""), "")
    if stem.endswith("_yaml"):
        stem = stem[:-5]
    if stem.endswith(config.SUFFIX_YAML.replace(".md", "")):
        stem = stem.replace(config.SUFFIX_YAML.replace(".md", ""), "")

    if summary_type == "emphasis-scored":
        suffix = config.SUFFIX_EMPHASIS_SCORED
        output_filename = f"{stem}{suffix}"
        project_dir = config.PROJECTS_DIR / stem
        project_dir.mkdir(parents=True, exist_ok=True)
        output_path = project_dir / output_filename
        output_path.write_text(content, encoding="utf-8")
        return output_path

    suffix = f" - {summary_type}.md"
    if summary_type == "All Key Items":
        suffix = config.SUFFIX_KEY_ITEMS_ALL
    elif summary_type == "key-terms":
        suffix = config.SUFFIX_KEY_TERMS
    elif summary_type == "blog":
        suffix = config.SUFFIX_BLOG
    elif summary_type == "topics-themes":
        suffix = config.SUFFIX_KEY_ITEMS_RAW_LEGACY

    output_filename = f"{stem}{suffix}"
    project_dir = config.PROJECTS_DIR / stem
    project_dir.mkdir(parents=True, exist_ok=True)
    output_path = project_dir / output_filename
    output_path.write_text(content, encoding="utf-8")
    return output_path


def _process_key_items_output(all_key_items_path: Path, logger):
    """Split the raw Key Items output into focused extract files."""
    logger.info("Processing generated Key Items into separate files...")
    content = all_key_items_path.read_text(encoding="utf-8")
    clean_content = strip_yaml_frontmatter(content)
    stem = all_key_items_path.stem.replace(
        config.SUFFIX_KEY_ITEMS_ALL.replace(".md", ""), ""
    )

    project_dir = config.PROJECTS_DIR / stem
    project_dir.mkdir(parents=True, exist_ok=True)

    topics = extract_section(clean_content, "Topics")
    themes = extract_section(clean_content, "Key Themes")
    key_terms = extract_section(clean_content, "Key Terms")

    if topics or themes or key_terms:
        combined_output = ""
        if topics:
            combined_output += f"## Key Topics\n\n{topics}\n\n"
        if themes:
            combined_output += f"## Key Themes\n\n{themes}\n\n"
        if key_terms:
            combined_output += f"## Key Terms\n\n{key_terms}\n\n"

        combined_path = project_dir / f"{stem}{config.SUFFIX_KEY_ITEMS_CLEAN}"
        combined_path.write_text(combined_output, encoding="utf-8")
        logger.info("  ✓ Topics, Themes, Terms → %s", combined_path.name)


# Main Exported Functions


def extract_scored_emphasis(
    formatted_filename: str,
    model: str = config.DEFAULT_MODEL,
    logger=None,
    transcript_system_message=None,
) -> bool:
    """Run the scored emphasis extraction pipeline."""
    if logger is None:
        logger = setup_logging("extract_scored_emphasis")

    try:
        logger.info("Starting Scored Emphasis Extraction for: %s",
                    formatted_filename)
        prompt_template = _load_summary_prompt(
            config.PROMPT_EMPHASIS_SCORING_FILENAME)

        call_kwargs = {}
        if transcript_system_message:
            full_prompt = prompt_template
            call_kwargs["system"] = transcript_system_message
        else:
            transcript = _load_formatted_transcript(formatted_filename)
            full_prompt = f"{prompt_template}\n\n---\n\nTRANSCRIPT:\n\n{transcript}"

        logger.info("Sending request to Claude...")
        response = _generate_summary_with_claude(
            full_prompt,
            model,
            config.TEMP_STRICT,
            logger,
            min_length=100,
            timeout=config.TIMEOUT_SUMMARY,
            **call_kwargs,
        )

        items = parse_scored_emphasis_output(response)
        if not items and len(response) > 500:
            logger.warning("No items extracted despite substantial response.")
            _save_summary(response, formatted_filename, "emphasis-scored")
            return False

        logger.info("Extracted %d scored emphasis items.", len(items))

        validated_items = []
        final_content_lines = []
        for item in items:
            is_valid, issues = validate_emphasis_item(item)
            if is_valid:
                validated_items.append(item)
                final_content_lines.append(
                    f"[{item['type']} - {item['category']} - Rank: {item['score']}%] Concept: {item['concept']}"
                )
                final_content_lines.append(f'"{item["quote"]}"')
            else:
                logger.warning("Filtered out invalid emphasis item: %s",
                               ', '.join(issues))

        logger.info("Retained %d items after validation.",
                    len(validated_items))
        final_content = (
            "\n\n".join(final_content_lines) if validated_items else response
        )
        output_path = _save_summary(
            final_content, formatted_filename, "emphasis-scored"
        )
        logger.info("✓ Scored emphasis saved to: %s", output_path)

        return True

    except Exception as e:
        logger.error("Error in scored emphasis extraction: %s",
                     e, exc_info=True)
        return False


def extract_bowen_references_from_transcript(
    formatted_filename: str,
    model: str = config.DEFAULT_MODEL,
    logger=None,
    transcript_system_message=None,
) -> bool:
    """Extracts Bowen references from the transcript."""
    if logger is None:
        logger = setup_logging("extract_bowen_references")

    try:
        logger.info("Starting Bowen Reference Extraction for: %s",
                    formatted_filename)
        prompt_template = _load_summary_prompt(
            config.PROMPT_BOWEN_EXTRACTION_FILENAME)

        call_kwargs = {}
        if transcript_system_message:
            full_prompt = prompt_template.replace(
                "TRANSCRIPT:\n\n{{insert_transcript_text_here}}", ""
            ).strip()
            full_prompt = full_prompt.replace(
                "{{insert_transcript_text_here}}", "")
            call_kwargs["system"] = transcript_system_message
        else:
            transcript = _load_formatted_transcript(formatted_filename)
            full_prompt = prompt_template.replace(
                "{{insert_transcript_text_here}}", transcript
            )

        logger.info("Sending request to Claude for Bowen references...")
        response = _generate_summary_with_claude(
            full_prompt,
            model,
            config.TEMP_ANALYSIS,
            logger,
            min_length=50,
            timeout=config.TIMEOUT_SUMMARY,
            **call_kwargs,
        )

        final_content = _clean_bowen_output(response)
        # Ensure header is present for standard parsing
        final_content = f"## Bowen References\n\n{final_content}"

        stem = (
            Path(formatted_filename)
            .stem.replace(config.SUFFIX_FORMATTED.replace(".md", ""), "")
            .replace(config.SUFFIX_YAML.replace(".md", ""), "")
        )
        project_dir = config.PROJECTS_DIR / stem
        bowen_path = project_dir / f"{stem}{config.SUFFIX_BOWEN}"
        bowen_path.write_text(final_content, encoding="utf-8")

        num_found = len(re.findall(r"^\s*>\s*\*\*",
                        final_content, re.MULTILINE))
        logger.info("✓ Found %d Bowen references. Saved to: %s",
                    num_found, bowen_path.name)
        return True
    except Exception as e:
        logger.error("Error in Bowen reference extraction: %s",
                     e, exc_info=True)
        return False


def generate_structured_summary(
    base_name: str,
    summary_target_word_count: int = None,
    logger=None,
    transcript_system_message=None,
    model: str = config.DEFAULT_MODEL,  # Use Sonnet for detailed summaries (was AUX_MODEL/Haiku)
) -> bool:
    """Generate a structured summary using the pipeline."""
    if logger is None:
        logger = setup_logging("generate_structured_summary")

    if summary_target_word_count is None:
        summary_target_word_count = config.DEFAULT_SUMMARY_WORD_COUNT

    try:
        try:
            summary_target_word_count = int(summary_target_word_count)
        except (TypeError, ValueError):
            logger.error("Error: summary_target_word_count expected int, got %s",
                         summary_target_word_count)
            return False

        formatted_file = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_FORMATTED}"
        )
        all_key_items_file = (
            config.PROJECTS_DIR
            / base_name
            / f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"
        )

        validate_input_file(formatted_file)
        validate_input_file(all_key_items_file)

        transcript = formatted_file.read_text(encoding="utf-8")
        transcript = strip_yaml_frontmatter(transcript)

        extracts_content = all_key_items_file.read_text(encoding="utf-8")
        extracts_content = strip_yaml_frontmatter(extracts_content)

        metadata = parse_filename_metadata(base_name)
        topics_section = extract_section(extracts_content, "Topics")
        themes_section = extract_section(extracts_content, "Key Themes")

        if not topics_section:
            logger.error("Could not find Topics in All Key Items file.")
            return False

        summary_input = summary_pipeline.prepare_summary_input(
            metadata=metadata,
            topics_markdown=topics_section,
            themes_markdown=themes_section,
            transcript=transcript,
            target_word_count=summary_target_word_count,
        )

        logger.info("Parsed %d topics and %d themes.",
                    len(summary_input.body.topics), len(summary_input.themes))

        if not transcript_system_message:
            transcript_system_message = create_system_message_with_cache(
                transcript)

        logger.info("Generating summary via API (Target: %d words)...", summary_target_word_count)
        logger.info("Using model: %s", model)  # Log which model we're using
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        client = anthropic.Anthropic(api_key=api_key)
        summary_text = summary_pipeline.generate_summary(
            summary_input, client, model=model, system=transcript_system_message
        )

        output_path = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_SUMMARY_GEN}"
        )
        output_path.write_text(summary_text, encoding="utf-8")
        logger.info("Generated summary saved to %s", output_path)
        return True
    except Exception as e:
        logger.error("Error generating structured summary: %s",
                     e, exc_info=True)
        return False


def generate_structured_abstract(
    base_name: str, logger=None, transcript_system_message=None, model: str = config.DEFAULT_MODEL
) -> bool:
    """
    Generate an abstract using the structured pipeline.
    Note: Uses Sonnet for detailed content generation (was AUX_MODEL/Haiku).
    """
    if logger is None:
        logger = setup_logging("generate_structured_abstract")

    try:
        formatted_file = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_FORMATTED}"
        )
        all_key_items_file = (
            config.PROJECTS_DIR
            / base_name
            / f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"
        )

        validate_input_file(formatted_file)
        validate_input_file(all_key_items_file)

        transcript = formatted_file.read_text(encoding="utf-8")
        transcript = strip_yaml_frontmatter(transcript)

        extracts_content = all_key_items_file.read_text(encoding="utf-8")
        extracts_content = strip_yaml_frontmatter(extracts_content)

        metadata = parse_filename_metadata(base_name)

        topics_section = extract_section(extracts_content, "Topics")
        themes_section = extract_section(extracts_content, "Key Themes")

        if not topics_section or not themes_section:
            logger.error(
                "Could not find Topics or Key Themes in All Key Items file.")
            return False

        # Calculate target word count
        transcript_words = len(transcript.split())
        target_word_count = max(
            int(transcript_words * config.ABSTRACT_TARGET_PERCENT),
            config.ABSTRACT_MIN_WORDS,
        )

        abstract_input = abstract_pipeline.prepare_abstract_input(
            metadata=metadata,
            topics_markdown=topics_section,
            themes_markdown=themes_section,
            transcript=transcript,
            target_word_count=target_word_count,
        )

        if not abstract_input.topics:
            logger.error(
                "Failed to parse any Topics from topics-themes. Check regex or input format."
            )
            return False

        logger.info("Parsed %d topics and %d themes.",
                    len(abstract_input.topics), len(abstract_input.themes))

        if not transcript_system_message:
            transcript_system_message = create_system_message_with_cache(
                transcript)

        logger.info("Generating abstract via API...")
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        client = anthropic.Anthropic(api_key=api_key)
        abstract_text = abstract_pipeline.generate_abstract(
            abstract_input, client, model=model, system=transcript_system_message
        )

        output_path = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_ABSTRACT_GEN}"
        )
        output_path.write_text(abstract_text, encoding="utf-8")
        logger.info("Generated abstract saved to %s", output_path)

        return True
    except Exception as e:
        logger.error("Error generating structured abstract: %s",
                     e, exc_info=True)
        return False


def summarize_transcript(
    formatted_filename: str,
    model: str,
    focus_keyword: str,
    target_audience: str,
    skip_extracts_summary: bool,
    skip_emphasis: bool,
    skip_blog: bool,
    generate_structured: bool = False,
    structured_word_count: int = config.DEFAULT_SUMMARY_WORD_COUNT,
    logger=None,
) -> bool:
    """Orchestrates the transcript summarization process."""
    if logger is None:
        logger = setup_logging("summarize_transcript")

    try:
        if not config.SOURCE_DIR.exists():
            raise FileNotFoundError(
                f"Source directory not found: {config.SOURCE_DIR}")

        logger.info("Loading formatted transcript: %s", formatted_filename)
        transcript = _load_formatted_transcript(formatted_filename)
        transcript_word_count = len(transcript.split())
        metadata = parse_filename_metadata(formatted_filename)
        logger.info("Transcript metadata: %s", metadata)

        transcript_system_message = create_system_message_with_cache(
            transcript)

        all_key_items_path = None

        if not skip_extracts_summary:
            logger.info("PART 1: Generating Key Items...")
            prompt_template = _load_summary_prompt(
                config.PROMPT_EXTRACTS_FILENAME)
            prompt = _fill_prompt_template(
                prompt_template,
                metadata,
                transcript="",
                target_audience=target_audience,
            )

            min_expected_words = int(
                transcript_word_count * config.MIN_EXTRACTS_PERCENT
            )
            min_expected_words = (
                max(min_expected_words, config.MIN_EXTRACTS_WORDS_FLOOR)
                if transcript_word_count > config.MIN_TRANSCRIPT_WORDS_FOR_FLOOR
                else config.MIN_EXTRACTS_WORDS_ABSOLUTE
            )

            output = _generate_summary_with_claude(
                prompt,
                model,
                config.TEMP_ANALYSIS,
                logger,
                min_length=config.MIN_EXTRACTS_CHARS,
                min_words=min_expected_words,
                system=transcript_system_message,
            )

            # Enforce consistent headers
            output = _normalize_headers(output)

            all_key_items_path = _save_summary(
                output, formatted_filename, "All Key Items"
            )
            output_words = len(output.split())
            logger.info("✓ Key Items raw analysis saved (%d words) to: %s",
                        output_words, all_key_items_path)

            _process_key_items_output(all_key_items_path, logger)
        else:
            # handle if filename was already stemmed or yaml suffixed, better logic from _load_formatted_transcript
            # Reconstruct path based on project dir
            # Try to guess
            stem = metadata["stem"]
            potential_path = (
                config.PROJECTS_DIR / stem /
                f"{stem}{config.SUFFIX_KEY_ITEMS_ALL}"
            )
            if potential_path.exists():
                all_key_items_path = potential_path
                logger.info("Skipping Key Items generation, using existing file: %s",
                            all_key_items_path)

        if not skip_emphasis:
            logger.info("\n--- PART 2: Extracting Emphasis Items ---")
            extract_scored_emphasis(
                formatted_filename, model, logger, transcript_system_message
            )

        logger.info("\n--- PART 3: Extracting Bowen References ---")
        extract_bowen_references_from_transcript(
            formatted_filename, model, logger, transcript_system_message
        )

        if not skip_blog:
            logger.info("\n--- PART 4: Generating Blog Post ---")
            prompt_template = _load_summary_prompt(config.PROMPT_BLOG_FILENAME)
            prompt = _fill_prompt_template(
                prompt_template,
                metadata,
                transcript="",
                focus_keyword=focus_keyword,
                target_audience=target_audience,
            )
            output = _generate_summary_with_claude(
                prompt,
                model,
                config.TEMP_BALANCED,
                logger,
                min_length=config.MIN_BLOG_CHARS,
                system=transcript_system_message,
            )
            blog_path = _save_summary(output, formatted_filename, "blog")
            logger.info("✓ Blog post saved to: %s", blog_path)

        logger.info("✓ Transcript processing complete!")

        if not skip_extracts_summary and all_key_items_path:
            logger.info("VALIDATION: Checking Emphasis Items...")
            stem = metadata["stem"]
            formatted_path = (
                config.PROJECTS_DIR / stem / f"{stem}{config.SUFFIX_FORMATTED}"
            )
            if formatted_path.exists():
                validate_emphasis_items(
                    formatted_path, all_key_items_path, logger)

        if generate_structured:
            if all_key_items_path:
                logger.info("Generating structured summary...")
                stem = metadata["stem"]
                structured_success = generate_structured_summary(
                    base_name=stem,
                    summary_target_word_count=structured_word_count,
                    logger=logger,
                    transcript_system_message=transcript_system_message,
                )
                if structured_success:
                    logger.info("Validating structured summary...")
                    validate_summary_coverage(base_name=stem, logger=logger)
                else:
                    logger.error("Structured summary generation failed.")
                    return False
            else:
                logger.warning(
                    "Cannot generate structured summary: Key Items file was skipped or not found."
                )

        return True

    except Exception as e:
        logger.error("An error occurred: %s", e, exc_info=True)
        return False
