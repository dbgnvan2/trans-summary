"""
Pipeline module for validation tasks (headers, abstracts, emphasis).
"""

import os
import re
from pathlib import Path
from typing import Optional

import anthropic

import abstract_pipeline
import abstract_validation
import config
import summary_pipeline
import summary_validation
from transcript_utils import (
    call_claude_with_retry,
    create_system_message_with_cache,
    extract_emphasis_items,
    extract_section,
    find_text_in_content,
    parse_filename_metadata,
    setup_logging,
    strip_yaml_frontmatter,
    validate_input_file,
)

# Reuse the helper from formatting pipeline or define here if private
# It was private in pipeline.py, let's redefine generic helper or import if possible.
# Ideally, we load generic prompts via a utility.
# For now, I'll reimplement a specific loader for validation prompts to avoid circular deps.


def _load_validation_prompt(prompt_filename: str) -> str:
    """Load a validation prompt template."""
    prompt_path = config.PROMPTS_DIR / prompt_filename
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path}\nExpected location: {config.PROMPTS_DIR}/{prompt_filename}"
        )
    return prompt_path.read_text(encoding="utf-8")


def _load_formatted_transcript(filename: str) -> str:
    """Load the formatted transcript."""
    # 1. Check if filename is a direct path to an existing file
    if Path(filename).is_file():
        return Path(filename).read_text(encoding="utf-8")

    meta = parse_filename_metadata(filename)
    stem = meta["stem"]

    # 2. Check project directory (Primary location)
    transcript_path = config.PROJECTS_DIR / stem / filename
    if transcript_path.exists():
        return transcript_path.read_text(encoding="utf-8")

    # 3. Fallback to legacy formatted directory
    legacy_path = config.TRANSCRIPTS_BASE / "formatted" / filename
    if legacy_path.exists():
        return legacy_path.read_text(encoding="utf-8")

    # If not found, validate_input_file will raise the appropriate error for the expected path
    validate_input_file(transcript_path)
    return transcript_path.read_text(encoding="utf-8")


def _fill_prompt_template(
    template: str, metadata: dict, transcript: str, **kwargs
) -> str:
    """Fill in the prompt template."""
    placeholders = {**metadata, **kwargs}
    for key, value in placeholders.items():
        pattern = re.compile(
            r"{{\s*" + re.escape(key) + r"\s*}}", re.IGNORECASE)
        template = pattern.sub(lambda m: str(value), template)
    template = template.replace("{{insert_transcript_text_here}}", transcript)
    return template


def _generate_validation_response(
    prompt: str,
    model: str,
    temperature: float,
    logger,
    min_length: int = 50,
    system: Optional[list] = None,
    **kwargs
) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set.")
    client = anthropic.Anthropic(api_key=api_key)

    if system:
        kwargs["system"] = system

    max_tokens = config.MAX_TOKENS_HEADER_VALIDATION
    # Cap output tokens for model-specific limits (e.g., haiku max 8192)
    if "haiku" in model.lower() and max_tokens > 8192:
        logger.warning(
            "Capping max_tokens from %d to 8192 for model %s", max_tokens, model
        )
        max_tokens = 8192

    message = call_claude_with_retry(
        client=client,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,  # Use ample tokens (capped per model)
        temperature=temperature,
        stream=True,
        min_length=min_length,
        logger=logger,
        **kwargs,
    )
    return message.content[0].text


# ============================================================================
# EMPHASIS VALIDATION
# ============================================================================


def _extract_emphasis_quotes_from_file(all_key_items_file):
    """Extract all quoted text from Emphasized Items section."""
    extracts_path = Path(all_key_items_file)
    stem = extracts_path.stem.replace(
        config.SUFFIX_KEY_ITEMS_ALL.replace(".md", ""), ""
    )
    emphasis_file = extracts_path.parent / f"{stem}{config.SUFFIX_EMPHASIS}"

    source_file = emphasis_file if emphasis_file.exists() else extracts_path
    content = source_file.read_text(encoding="utf-8")
    content = strip_yaml_frontmatter(content)

    return extract_emphasis_items(content)


def validate_emphasis_items(
    formatted_file_path: Path, extracts_summary_path: Path, logger
):
    """Validate all emphasis quotes exist in the formatted transcript."""
    formatted_content = formatted_file_path.read_text(encoding="utf-8")
    quotes = _extract_emphasis_quotes_from_file(extracts_summary_path)

    if not quotes:
        logger.warning("No emphasis quotes found to validate")
        return

    valid_count, partial_count, invalid_count = 0, 0, 0

    for label, quote in quotes:
        # Use only first 15 words for fuzzy matching to avoid issues with long quotes
        quote_core = " ".join(quote.split()[:15])

        # Use shared utility instead of local _find_best_match
        _, _, ratio = find_text_in_content(
            quote_core, formatted_content, aggressive_normalization=True
        )

        if ratio >= 0.95:
            valid_count += 1
        elif ratio >= 0.80:
            partial_count += 1
        else:
            logger.error("NOT FOUND: %s - Quote: %s...", label, quote[:100])
            invalid_count += 1

    logger.info("Emphasis Items Validation:")
    logger.info(f"  Exact matches: {valid_count}")
    if partial_count > 0:
        logger.warning(f"  Partial matches: {partial_count}")
    if invalid_count > 0:
        logger.error("  Not found: %d", invalid_count)

    accuracy = (valid_count + partial_count) / \
        len(quotes) * 100 if quotes else 0
    logger.info("  Overall accuracy: %.1f%%", accuracy)


# ============================================================================
# HEADER VALIDATION
# ============================================================================


def validate_headers(
    formatted_filename: str, model: str = config.AUX_MODEL, logger=None
) -> bool:
    """
    Validate that the section headers in the formatted transcript make sense.
    """
    if logger is None:
        logger = setup_logging("validate_headers")

    try:
        base_name = (
            Path(formatted_filename)
            .stem.replace(config.SUFFIX_FORMATTED.replace(".md", ""), "")
            .replace(config.SUFFIX_YAML.replace(".md", ""), "")
        )
        formatted_path = config.PROJECTS_DIR / base_name / formatted_filename
        validate_input_file(formatted_path)

        logger.info(f"Loading formatted transcript: {formatted_filename}")
        transcript = formatted_path.read_text(encoding="utf-8")

        # Create cached system message
        system_message = create_system_message_with_cache(transcript)

        prompt_template = _load_validation_prompt(
            config.PROMPT_FORMATTING_HEADER_VALIDATION_FILENAME
        )

        # Remove transcript placeholder or text from prompt
        full_prompt = prompt_template.replace(
            "{{batch_content}}", "(See transcript in system message)"
        )
        if "{{batch_content}}" not in prompt_template:
            # Fallback if the template doesn't use that variable, but usually it does.
            # The code previously appended the transcript. We just need the template.
            full_prompt = prompt_template

        logger.info("Sending transcript to Claude for header validation...")

        response = _generate_validation_response(
            full_prompt,
            model,
            config.TEMP_STRICT,
            logger,
            min_length=100,
            system=system_message,
            suppress_caching_warnings=True
        )

        report_path = (
            config.PROJECTS_DIR
            / base_name
            / f"{base_name}{config.SUFFIX_HEADER_VAL_REPORT}"
        )
        report_path.write_text(response, encoding="utf-8")

        logger.info("✓ Header validation report saved to: %s", report_path)
        return True

    except Exception as e:
        logger.error(
            "An error occurred during header validation: %s", e, exc_info=True)
        return False


# ============================================================================
# ABSTRACT VALIDATION (LEGACY)
# ============================================================================


def _extract_scores_from_output(output: str) -> dict:
    """Extract assessment scores from the Claude output."""
    scores = {}
    table_pattern = r"|\s*(?:\*\*)?([^\*\|]+?)(?:\*\*)?\s*|\s*(?:\*\*)?(\d+(?:\.\d+)?)(?:\*\*)?(?:\s*/\s*5)?\s*|"
    matches = re.findall(table_pattern, output)
    for dimension, score in matches:
        dimension = dimension.strip()
        if dimension and dimension != "Dimension" and "---" not in dimension:
            scores[dimension] = float(score)

    if not scores:
        list_pattern = (
            r"[-*]\s*(?:\*\*)?([A-Za-z ]+?)(?:\*\*)?:?\s+(\d+(?:\.\d+)?)(?:/5)?"
        )
        matches = re.findall(list_pattern, output)
        for dimension, score in matches:
            scores[dimension.strip()] = float(score)

    overall_match = re.search(
        r"|\s*(?:\*\*)?Overall(?: Score)?(?:\*\*)?\s*|\s*(?:\*\*)?(\d+(?:\.\d+)?)(?:\*\*)?(?:\s*/\s*5)?\s*|",
        output,
        re.IGNORECASE,
    )
    if overall_match:
        scores["Overall"] = float(overall_match.group(1))
    else:
        overall_text_match = re.search(
            r"(?:Overall|Total)\s*(?:Score)?\s*[:|-]?\s*(?:\*\*)?\s*(\d+(?:\.\d+)?)",
            output,
            re.IGNORECASE,
        )
        if overall_text_match:
            scores["Overall"] = float(overall_text_match.group(1))

    return scores


def _extract_extended_abstract(output: str) -> str:
    """Extract the extended abstract from the validation output."""
    match = re.search(
        r"(?:^|\n)#+\s*(?:\*\*)?(?:EXTENDED|REVISED|IMPROVED)?\s*ABSTRACT(?:\*\*)?\s*\n+(.*?)(?=\n#|\Z)",
        output,
        flags=re.DOTALL | re.IGNORECASE,
    )

    if not match:
        match = re.search(
            r"(?:\*\*)?(?:EXTENDED|REVISED|IMPROVED)\s*ABSTRACT(?:\*\*)?:?\s*\n+(.*?)(?=\n#|\Z)",
            output,
            flags=re.DOTALL | re.IGNORECASE,
        )

    return match.group(1).strip() if match else ""


def _save_abstracts(content: str, base_name: str) -> Path:
    """Save the abstracts validation output."""
    project_dir = config.PROJECTS_DIR / base_name
    project_dir.mkdir(parents=True, exist_ok=True)
    output_path = project_dir / f"{base_name}{config.SUFFIX_ABSTRACTS_LEGACY}"
    output_path.write_text(content, encoding="utf-8")
    return output_path


def _load_extracts_summary_for_abstract(base_name: str) -> tuple[str, str]:
    """Load All Key Items and extract the abstract."""
    summary_path = config.PROJECTS_DIR / base_name / \
        f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"
    validate_input_file(summary_path)
    content = summary_path.read_text(encoding="utf-8")
    abstract_match = re.search(
        r"## (?:\[\*\])?Abstract(?:\*\])?\s*\n\n(.*?)(?=\n---|\n## |\Z)",
        content,
        flags=re.DOTALL,
    )
    if not abstract_match:
        raise ValueError(
            f"Could not find ## Abstract section in {summary_path}")
    return content, abstract_match.group(1).strip()


def validate_abstract_legacy(
    base_name: str,
    model: str,
    target_score: float,
    max_iterations: int,
    auto_continue: bool,
    logger,
) -> bool:
    """Orchestrates the abstract validation and revision process (Legacy)."""
    if logger is None:
        logger = setup_logging("validate_abstract")

    try:
        logger.info("Loading files for: %s", base_name)
        transcript = _load_formatted_transcript(
            f"{base_name}{config.SUFFIX_FORMATTED}")

        # Create cached system message
        system_message = create_system_message_with_cache(transcript)

        _, initial_abstract = _load_extracts_summary_for_abstract(base_name)
        prompt_template = _load_validation_prompt(
            config.PROMPT_ABSTRACT_VALIDATION_FILENAME
        )

        current_abstract = initial_abstract
        best_score = 0
        best_output = ""

        for i in range(max_iterations + 1):
            logger.info("--- Iteration %d ---", i)

            replacements = {
                "source_document": "(See transcript in system message)",
                "transcript": "(See transcript in system message)",
                "text": "(See transcript in system message)",
                "abstract": current_abstract,
                "current_abstract": current_abstract,
            }
            # Use transcript length as proxy for empty check if needed, but not passing full text
            prompt = _fill_prompt_template(prompt_template, replacements, "")

            if "(See transcript in system message)" not in prompt:
                prompt += f"\n\n--- ABSTRACT TO EVALUATE ---\n{current_abstract}"

            validation_output = _generate_validation_response(
                prompt,
                model,
                config.TEMP_BALANCED,
                logger,
                min_length=config.MIN_ABSTRACT_VALIDATION_CHARS,
                system=system_message,
            )
            scores = _extract_scores_from_output(validation_output)

            overall_score = scores.get("Overall", 0)
            logger.info("Iteration %d score: %s", i, overall_score)

            if overall_score > best_score:
                best_score = overall_score
                best_output = validation_output

            if best_score >= target_score:
                break

            current_abstract = _extract_extended_abstract(validation_output)
            if not current_abstract:
                break

        if best_score == 0:
            return False

        _save_abstracts(best_output, base_name)
        return True

    except Exception as e:
        logger.error("An error occurred during abstract validation: %s",
                     e, exc_info=True)
        return False


# ============================================================================
# STRUCTURED VALIDATION (COVERAGE)
# ============================================================================


def validate_abstract_coverage(base_name: str, logger=None, model: str = config.AUX_MODEL) -> bool:
    """Validate the abstract using the coverage validation module."""
    if logger is None:
        logger = setup_logging("validate_abstract_coverage")

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

        generated_abstract_file = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_ABSTRACT_GEN}"
        )

        if generated_abstract_file.exists():
            abstract_text = generated_abstract_file.read_text(encoding="utf-8")
        else:
            logger.error(
                "No generated abstract found to validate. (Step 6 likely failed)")
            return False

        transcript = formatted_file.read_text(encoding="utf-8")
        transcript = strip_yaml_frontmatter(transcript)

        extracts_content = all_key_items_file.read_text(encoding="utf-8")
        extracts_content = strip_yaml_frontmatter(extracts_content)

        metadata = parse_filename_metadata(base_name)
        topics_section = extract_section(extracts_content, "Topics")
        themes_section = extract_section(extracts_content, "Key Themes")

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

        api_key = os.getenv("ANTHROPIC_API_KEY")
        client = anthropic.Anthropic(api_key=api_key) if api_key else None

        passed, report = abstract_validation.validate_and_report(
            abstract_text, abstract_input, api_client=client, model=model, logger=logger
        )

        report_path = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_ABSTRACT_VAL}"
        )
        report_path.write_text(report, encoding="utf-8")

        logger.info("Validation Report saved to %s", report_path)
        logger.info("Validation Passed: %s", passed)

        for line in report.splitlines():
            logger.info(line)

        return passed

    except Exception as e:
        logger.error("Error validating abstract coverage: %s",
                     e, exc_info=True)
        return False


def validate_summary_coverage(base_name: str, logger=None, model: str = config.AUX_MODEL) -> bool:
    """Validate the summary using the coverage validation module."""
    if logger is None:
        logger = setup_logging("validate_summary_coverage")

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
        generated_summary_file = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_SUMMARY_GEN}"
        )

        if generated_summary_file.exists():
            summary_text = generated_summary_file.read_text(encoding="utf-8")
        else:
            logger.error("No generated summary found to validate.")
            return False

        transcript = formatted_file.read_text(encoding="utf-8")
        transcript = strip_yaml_frontmatter(transcript)

        extracts_content = all_key_items_file.read_text(encoding="utf-8")
        extracts_content = strip_yaml_frontmatter(extracts_content)

        metadata = parse_filename_metadata(base_name)
        topics_section = extract_section(extracts_content, "Topics")
        themes_section = extract_section(extracts_content, "Key Themes")

        summary_input = summary_pipeline.prepare_summary_input(
            metadata=metadata,
            topics_markdown=topics_section,
            themes_markdown=themes_section,
            transcript=transcript,
        )

        api_key = os.getenv("ANTHROPIC_API_KEY")
        client = anthropic.Anthropic(api_key=api_key) if api_key else None

        passed, report = summary_validation.validate_and_report(
            summary_text, summary_input, api_client=client, model=model, logger=logger
        )

        report_path = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_SUMMARY_VAL}"
        )
        report_path.write_text(report, encoding="utf-8")

        logger.info("Validation Report saved to %s", report_path)
        logger.info("Validation Passed: %s", passed)

        for line in report.splitlines():
            logger.info(line)

        return passed

    except Exception as e:
        logger.error("Error validating summary coverage: %s", e, exc_info=True)
        return False
