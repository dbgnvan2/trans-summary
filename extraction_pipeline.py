"Pipeline module for extracting insights, summaries, and emphasis items."

import json
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
    extract_bowen_references,
    extract_section,
    find_text_in_content,
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
    # Normalize Interpretive Themes (replaces legacy Key Themes)
    text = re.sub(r'^\s*(?:#+\s*)?(?:[\*\_]+)?(?:\d+\.?\s*)?(?:Key\s+Themes|Interpretive\s+Themes)\b.*$',
                  '## Interpretive Themes', text, flags=re.MULTILINE | re.IGNORECASE)
    # Normalize Key Terms
    text = re.sub(r'^\s*(?:#+\s*)?(?:[\*\_]+)?(?:\d+\.?\s*)?Key Terms\b.*$',
                  '## Key Terms', text, flags=re.MULTILINE | re.IGNORECASE)
    return text


def _extract_first_section(content: str, section_names: list[str]) -> str:
    """Extract the first matching section from markdown content."""
    if not content:
        return ""
    for name in section_names:
        extracted = extract_section(content, name)
        if extracted:
            return extracted
    return ""


def _load_section_from_project_file(
    stem: str,
    suffix: str,
    section_names: list[str] | None = None,
) -> str:
    """Load a section from a project file, optionally extracting by section header."""
    path = config.PROJECTS_DIR / stem / f"{stem}{suffix}"
    if not path.exists():
        return ""
    content = strip_yaml_frontmatter(path.read_text(encoding="utf-8"))
    if section_names:
        extracted = _extract_first_section(content, section_names)
        return extracted or content.strip()
    return content.strip()


def _extract_json_object(text: str) -> dict:
    """Best-effort extraction of a JSON object from model output."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(text[start: end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _extract_lens_count(transcript_word_count: int) -> int:
    """Adaptive lens count based on transcript size/density proxy."""
    if transcript_word_count < 4000:
        return 6
    if transcript_word_count < 8000:
        return 9
    return 12


def _generate_with_cached_transcript(
    prompt_filename: str,
    model: str,
    logger,
    transcript_system_message,
    min_length: int = 100,
    **replacements,
) -> str:
    """Generate an artifact using a prompt template and cached transcript context."""
    template = _load_summary_prompt(prompt_filename)
    prompt = _fill_prompt_template(template, {}, "", **replacements)
    return _generate_summary_with_claude(
        prompt,
        model,
        config.TEMP_ANALYSIS,
        logger,
        min_length=min_length,
        timeout=config.TIMEOUT_SUMMARY,
        system=transcript_system_message,
    )


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


def _format_bowen_refs(refs: list[tuple[str, str]]) -> str:
    """Format Bowen references as blockquote lines."""
    lines = []
    for concept, quote in refs:
        concept = " ".join(str(concept).split()).strip()
        quote = " ".join(str(quote).split()).strip()
        if not concept or not quote:
            continue
        # Avoid breaking the quote wrapper
        quote = quote.replace('"', "'")
        lines.append(f'> **Bowen Reference - {concept}:** "{quote}"')
    return "\n".join(lines)


def _filter_bowen_references_semantically(
    refs: list[tuple[str, str]],
    model: str,
    logger,
) -> list[tuple[str, str]]:
    """Use LLM to keep only explicit Murray Bowen attributions."""
    if not refs:
        return refs

    try:
        prompt_template = _load_summary_prompt(
            config.PROMPT_BOWEN_FILTER_FILENAME
        )
        items_text = "\n".join(
            [f'- Label: {label}\n  Quote: {quote}' for label, quote in refs]
        )
        prompt = _fill_prompt_template(prompt_template, {}, "", items=items_text)

        logger.info("Filtering Bowen references semantically...")
        response = _generate_summary_with_claude(
            prompt,
            model,
            config.TEMP_ANALYSIS,
            logger,
            min_length=20,
            timeout=config.TIMEOUT_SUMMARY,
        )

        cleaned = _clean_bowen_output(response)
        if not cleaned.strip():
            return []

        parsed = extract_bowen_references(
            "## Bowen References\n\n" + cleaned
        )

        # Drop placeholder outputs like "None Found"
        filtered = [
            (c, q) for c, q in parsed
            if c.strip().lower() != "none found"
        ]
        return filtered
    except Exception as e:
        logger.warning(
            "Bowen semantic filter failed; keeping original refs. Error: %s", e
        )
        return refs


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
    elif summary_type == "topics":
        suffix = config.SUFFIX_TOPICS
    elif summary_type == "structural-themes":
        suffix = config.SUFFIX_STRUCTURAL_THEMES
    elif summary_type == "interpretive-themes":
        suffix = config.SUFFIX_INTERPRETIVE_THEMES
    elif summary_type == "lenses-ranked":
        suffix = config.SUFFIX_LENSES
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
    structural_themes = extract_section(clean_content, "Structural Themes")
    interpretive_themes = extract_section(clean_content, "Interpretive Themes")
    key_terms = extract_section(clean_content, "Key Terms")

    if topics or structural_themes or interpretive_themes or key_terms:
        combined_output = ""
        if topics:
            combined_output += f"## Key Topics\n\n{topics}\n\n"
        if structural_themes:
            combined_output += f"## Structural Themes\n\n{structural_themes}\n\n"
        if interpretive_themes:
            combined_output += f"## Interpretive Themes\n\n{interpretive_themes}\n\n"
        if key_terms:
            combined_output += f"## Key Terms\n\n{key_terms}\n\n"

        combined_path = project_dir / f"{stem}{config.SUFFIX_KEY_ITEMS_CLEAN}"
        combined_path.write_text(combined_output, encoding="utf-8")
        logger.info("  ✓ Topics, Structural/Interpretive Themes, Terms → %s", combined_path.name)


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
        transcript_text = strip_yaml_frontmatter(
            _load_formatted_transcript(formatted_filename)
        )
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

        # Semantic filter: keep only explicit Murray Bowen attributions
        parsed_refs = extract_bowen_references(
            "## Bowen References\n\n" + final_content
        )
        filtered_refs = _filter_bowen_references_semantically(
            parsed_refs, model, logger
        )

        def _ground_refs(refs: list[tuple[str, str]]) -> list[tuple[str, str]]:
            grounded = []
            for concept, quote in refs:
                _, _, ratio = find_text_in_content(
                    quote, transcript_text, aggressive_normalization=True
                )
                if ratio >= 0.90:
                    grounded.append((concept, quote))
                else:
                    logger.warning(
                        "Dropping ungrounded Bowen reference (match %.2f): %s",
                        ratio,
                        concept,
                    )
            return grounded

        grounded_semantic = _ground_refs(filtered_refs)
        if not grounded_semantic and parsed_refs:
            logger.warning(
                "Semantic filter produced no grounded Bowen references; falling back to grounded primary extraction output."
            )
            grounded_semantic = _ground_refs(parsed_refs)

        filtered_refs = grounded_semantic
        final_content = _format_bowen_refs(filtered_refs)

        # Ensure header is present for standard parsing
        final_content = f"## Bowen References\n\n{final_content}".rstrip()

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
        themes_section = extract_section(extracts_content, "Interpretive Themes")

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

        transcript = formatted_file.read_text(encoding="utf-8")
        transcript = strip_yaml_frontmatter(transcript)

        extracts_content = ""
        if all_key_items_file.exists():
            extracts_content = strip_yaml_frontmatter(
                all_key_items_file.read_text(encoding="utf-8")
            )

        metadata = parse_filename_metadata(base_name)

        topics_section = _extract_first_section(
            extracts_content, ["Topics", "Key Topics"]
        )
        themes_section = _extract_first_section(
            extracts_content,
            ["Interpretive Themes", "Themes", "Key Themes"],
        )

        if not topics_section:
            topics_section = _load_section_from_project_file(
                base_name,
                config.SUFFIX_TOPICS,
                ["Topics", "Key Topics"],
            )
            if topics_section:
                logger.info("Loaded Topics from dedicated topics file fallback.")

        if not themes_section:
            themes_section = _load_section_from_project_file(
                base_name,
                config.SUFFIX_INTERPRETIVE_THEMES,
                ["Interpretive Themes", "Themes", "Key Themes"],
            )
            if themes_section:
                logger.info("Loaded Interpretive Themes from dedicated file fallback.")

        if not topics_section or not themes_section:
            logger.error(
                "Could not find Topics or Interpretive Themes in available extraction files."
            )
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


def _validate_themes_and_lenses(
    model: str,
    logger,
    transcript_system_message,
    structural_themes: str,
    interpretive_themes: str,
    lenses: str,
) -> dict:
    """Back-validate structural themes, interpretive themes, and ranked lenses."""
    response = _generate_with_cached_transcript(
        config.PROMPT_THEME_LENS_VALIDATION_FILENAME,
        model,
        logger,
        transcript_system_message,
        min_length=80,
        structural_themes=structural_themes,
        interpretive_themes=interpretive_themes,
        lenses=lenses,
    )
    parsed = _extract_json_object(response)
    if not parsed:
        logger.warning("Theme/lens validation output was not parseable JSON.")
        return {
            "structural_themes_valid": False,
            "interpretive_themes_valid": False,
            "confirmed_lenses": [],
            "top_lens": {},
        }
    return parsed


def _compose_all_key_items(
    abstract: str,
    structural_themes: str,
    interpretive_themes: str,
    topics: str,
    key_terms: str,
    lenses: str,
) -> str:
    """Build canonical All Key Items document."""
    return (
        "## Abstract\n\n"
        f"{(abstract or 'None found.').strip()}\n\n"
        "## Structural Themes\n\n"
        f"{(structural_themes or 'None found.').strip()}\n\n"
        "## Interpretive Themes\n\n"
        f"{(interpretive_themes or 'None found.').strip()}\n\n"
        "## Topics\n\n"
        f"{(topics or 'None found.').strip()}\n\n"
        "## Key Terms\n\n"
        f"{(key_terms or 'None found.').strip()}\n\n"
        "## Lenses (Ranked)\n\n"
        f"{(lenses or 'None found.').strip()}\n"
    )


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
        top_lens = {}
        abstract_output = ""
        structural_output = ""
        interpretive_output = ""
        topics_output = ""
        key_terms_output = ""
        lenses_output = ""

        if not skip_extracts_summary:
            logger.info("PART 1: Generating Structural Themes...")
            structural_output = _generate_with_cached_transcript(
                config.PROMPT_STRUCTURAL_THEMES_FILENAME,
                model,
                logger,
                transcript_system_message,
                min_length=180,
            )
            _save_summary(structural_output, formatted_filename, "structural-themes")

            logger.info("PART 2: Generating Interpretive Themes...")
            interpretive_output = _generate_with_cached_transcript(
                config.PROMPT_INTERPRETIVE_THEMES_FILENAME,
                model,
                logger,
                transcript_system_message,
                min_length=260,
                structural_themes=structural_output,
            )
            _save_summary(interpretive_output, formatted_filename, "interpretive-themes")

            logger.info("PART 3: Generating Topics...")
            topics_output = _generate_with_cached_transcript(
                config.PROMPT_TOPICS_FILENAME,
                model,
                logger,
                transcript_system_message,
                min_length=220,
            )
            topics_output = re.sub(
                r"^\s*(?:#+\s*)?(?:[\*\_]+)?(?:\d+\.?\s*)?Topics\b.*$",
                "## Topics",
                topics_output,
                flags=re.MULTILINE | re.IGNORECASE,
            )
            _save_summary(topics_output, formatted_filename, "topics")

            logger.info("PART 4: Generating Key Terms...")
            key_terms_output = _generate_with_cached_transcript(
                config.PROMPT_KEY_TERMS_FILENAME,
                model,
                logger,
                transcript_system_message,
                min_length=160,
                author=metadata.get("presenter", metadata.get("author", "")),
                presenter=metadata.get("presenter", ""),
                date=metadata.get("date", ""),
                title=metadata.get("title", ""),
                filename=formatted_filename,
            )
            key_terms_output = re.sub(
                r"^\s*(?:#+\s*)?(?:[\*\_]+)?(?:\d+\.?\s*)?Key Terms\b.*$",
                "## Key Terms",
                key_terms_output,
                flags=re.MULTILINE | re.IGNORECASE,
            )
            _save_summary(key_terms_output, formatted_filename, "key-terms")

            logger.info("PART 5: Generating Abstract...")
            target_word_count = max(
                int(transcript_word_count * config.ABSTRACT_TARGET_PERCENT),
                config.ABSTRACT_MIN_WORDS,
            )
            abstract_input = abstract_pipeline.prepare_abstract_input(
                metadata=metadata,
                topics_markdown=topics_output,
                themes_markdown=interpretive_output,
                transcript=transcript,
                target_word_count=target_word_count,
            )
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not set")
            client = anthropic.Anthropic(api_key=api_key)
            abstract_output = abstract_pipeline.generate_abstract(
                abstract_input, client, model=model, system=transcript_system_message
            )
            _save_summary(abstract_output, formatted_filename, "abstract-initial")

            if not skip_emphasis:
                logger.info("\n--- PART 6: Extracting Emphasis Items ---")
                extract_scored_emphasis(
                    formatted_filename, model, logger, transcript_system_message
                )

            logger.info("\n--- PART 7: Extracting Bowen References ---")
            extract_bowen_references_from_transcript(
                formatted_filename, model, logger, transcript_system_message
            )

            logger.info("\n--- PART 8a: Generating Ranked Lenses (Adaptive Count) ---")
            lens_count = _extract_lens_count(transcript_word_count)
            lenses_output = _generate_with_cached_transcript(
                config.PROMPT_LENS_GENERATION_FILENAME,
                model,
                logger,
                transcript_system_message,
                min_length=350,
                structural_themes=structural_output,
                interpretive_themes=interpretive_output,
                topics=topics_output,
                key_terms=key_terms_output,
                lens_count_guidance=f"Generate exactly {lens_count} lenses in ranked order.",
            )

            logger.info(
                "--- PART 8b: Validating Structural/Interpretive Themes and Top Lens ---"
            )
            # Back-validation and regeneration loop: ensure lens #1 is valid.
            max_attempts = 3
            for attempt in range(max_attempts):
                logger.info(
                    "Theme/lens validation attempt %d/%d...",
                    attempt + 1,
                    max_attempts,
                )
                validation = _validate_themes_and_lenses(
                    model,
                    logger,
                    transcript_system_message,
                    structural_output,
                    interpretive_output,
                    lenses_output,
                )
                structural_valid = bool(validation.get("structural_themes_valid"))
                interpretive_valid = bool(validation.get("interpretive_themes_valid"))
                top_lens = validation.get("top_lens", {}) or {}

                if not structural_valid:
                    logger.warning("Structural themes denied by validator; regenerating...")
                    structural_output = _generate_with_cached_transcript(
                        config.PROMPT_STRUCTURAL_THEMES_FILENAME,
                        model,
                        logger,
                        transcript_system_message,
                        min_length=180,
                    )
                if not interpretive_valid:
                    logger.warning("Interpretive themes denied by validator; regenerating...")
                    interpretive_output = _generate_with_cached_transcript(
                        config.PROMPT_INTERPRETIVE_THEMES_FILENAME,
                        model,
                        logger,
                        transcript_system_message,
                        min_length=260,
                        structural_themes=structural_output,
                    )
                if structural_valid and interpretive_valid and top_lens:
                    logger.info(
                        "✓ Top-ranked lens validated: %s",
                        top_lens.get("title", "(untitled lens)"),
                    )
                    break

                logger.warning(
                    "Top lens not validated yet (attempt %d/%d). Regenerating lenses...",
                    attempt + 1,
                    max_attempts,
                )
                lenses_output = _generate_with_cached_transcript(
                    config.PROMPT_LENS_GENERATION_FILENAME,
                    model,
                    logger,
                    transcript_system_message,
                    min_length=350,
                    structural_themes=structural_output,
                    interpretive_themes=interpretive_output,
                    topics=topics_output,
                    key_terms=key_terms_output,
                    lens_count_guidance=f"Generate exactly {lens_count} lenses in ranked order.",
                )

            if not top_lens:
                logger.error("Failed to produce a validated top-ranked lens after retries.")
                return False

            _save_summary(structural_output, formatted_filename, "structural-themes")
            _save_summary(interpretive_output, formatted_filename, "interpretive-themes")
            _save_summary(lenses_output, formatted_filename, "lenses-ranked")

            all_key_items_content = _compose_all_key_items(
                abstract_output,
                structural_output,
                interpretive_output,
                topics_output,
                key_terms_output,
                lenses_output,
            )
            all_key_items_path = _save_summary(
                all_key_items_content,
                formatted_filename,
                "All Key Items",
            )
            _process_key_items_output(all_key_items_path, logger)
        else:
            stem = metadata["stem"]
            potential_path = (
                config.PROJECTS_DIR / stem /
                f"{stem}{config.SUFFIX_KEY_ITEMS_ALL}"
            )
            if potential_path.exists():
                all_key_items_path = potential_path
                logger.info("Skipping Key Items generation, using existing file: %s",
                            all_key_items_path)
                existing_content = strip_yaml_frontmatter(
                    potential_path.read_text(encoding="utf-8")
                )
                structural_output = _extract_first_section(
                    existing_content, ["Structural Themes"]
                )
                interpretive_output = _extract_first_section(
                    existing_content, ["Interpretive Themes", "Themes", "Key Themes"]
                )
                topics_output = _extract_first_section(
                    existing_content, ["Topics", "Key Topics"]
                )
                key_terms_output = _extract_first_section(
                    existing_content, ["Key Terms"]
                )
                lenses_output = _extract_first_section(
                    existing_content, ["Lenses (Ranked)", "Lenses"]
                )
                abstract_output = _extract_first_section(existing_content, ["Abstract"])

                # Hydrate missing sections from dedicated files to handle stale legacy All Key Items.
                if not structural_output:
                    structural_output = _load_section_from_project_file(
                        stem, config.SUFFIX_STRUCTURAL_THEMES, ["Structural Themes"]
                    )
                if not interpretive_output:
                    interpretive_output = _load_section_from_project_file(
                        stem,
                        config.SUFFIX_INTERPRETIVE_THEMES,
                        ["Interpretive Themes", "Themes", "Key Themes"],
                    )
                if not topics_output:
                    topics_output = _load_section_from_project_file(
                        stem, config.SUFFIX_TOPICS, ["Topics", "Key Topics"]
                    )
                if not key_terms_output:
                    key_terms_output = _load_section_from_project_file(
                        stem, config.SUFFIX_KEY_TERMS, ["Key Terms"]
                    )
                if not lenses_output:
                    lenses_output = _load_section_from_project_file(
                        stem, config.SUFFIX_LENSES, ["Lenses (Ranked)", "Lenses"]
                    )

                # If lenses are missing but key components exist, regenerate lenses and validate top lens.
                if not lenses_output and structural_output and interpretive_output:
                    logger.warning(
                        "No ranked lenses found in existing artifacts; regenerating for blog."
                    )
                    lens_count = _extract_lens_count(transcript_word_count)
                    lenses_output = _generate_with_cached_transcript(
                        config.PROMPT_LENS_GENERATION_FILENAME,
                        model,
                        logger,
                        transcript_system_message,
                        min_length=350,
                        structural_themes=structural_output,
                        interpretive_themes=interpretive_output,
                        topics=topics_output,
                        key_terms=key_terms_output,
                        lens_count_guidance=f"Generate exactly {lens_count} lenses in ranked order.",
                    )
                    _save_summary(lenses_output, formatted_filename, "lenses-ranked")

                if structural_output and interpretive_output and lenses_output:
                    validation = _validate_themes_and_lenses(
                        model,
                        logger,
                        transcript_system_message,
                        structural_output,
                        interpretive_output,
                        lenses_output,
                    )
                    top_lens = validation.get("top_lens", {}) or {}

                # Keep All Key Items in sync with hydrated sections when available.
                if all([abstract_output, structural_output, interpretive_output, topics_output, key_terms_output, lenses_output]):
                    refreshed_all_key_items = _compose_all_key_items(
                        abstract_output,
                        structural_output,
                        interpretive_output,
                        topics_output,
                        key_terms_output,
                        lenses_output,
                    )
                    all_key_items_path.write_text(refreshed_all_key_items, encoding="utf-8")
                    _process_key_items_output(all_key_items_path, logger)

        if not skip_blog:
            if not top_lens:
                logger.error(
                    "No validated top-ranked lens available; blog generation aborted by policy."
                )
                return False
            logger.info("\n--- PART 8: Generating Blog Post from Lens #1 ---")
            prompt_template = _load_summary_prompt(config.PROMPT_BLOG_FILENAME)
            prompt = _fill_prompt_template(
                prompt_template,
                metadata,
                transcript="",
                focus_keyword=focus_keyword,
                target_audience=target_audience,
                top_lens_title=top_lens.get("title", ""),
                top_lens_description=top_lens.get("description", ""),
                top_lens_rationale=top_lens.get("rationale", ""),
                top_lens_evidence=top_lens.get("evidence", ""),
                top_lens_hooks="\n".join(top_lens.get("hooks", []))
                if isinstance(top_lens.get("hooks"), list)
                else str(top_lens.get("hooks", "")),
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
        else:
            logger.info("Blog generation skipped (skip_blog=True).")

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
