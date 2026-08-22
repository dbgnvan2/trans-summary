"Pipeline module for extracting insights, summaries, and emphasis items."

import json
import os
import re
from pathlib import Path

import anthropic

import abstract_pipeline
import config
import summary_pipeline
from bowen_attribution import has_bowen_source_attribution as _has_bowen_source_attribution
from transcript_utils import (
    call_claude_with_retry,
    clean_project_name,
    create_system_message_with_cache,
    extract_bowen_references,
    extract_section,
    fill_prompt_template,
    find_text_in_content,
    load_project_transcript,
    normalize_text,
    parse_filename_metadata,
    parse_scored_emphasis_output,
    setup_logging,
    strip_yaml_frontmatter,
    validate_emphasis_item,
    validate_input_file,
)
from validation_pipeline import (
    validate_emphasis_items,
    validate_key_terms_fidelity,
    validate_summary_coverage,
    validate_topics_lightweight,
)

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


def _contains_refusal_or_missing_context_text(text: str) -> bool:
    """Detect common non-answer patterns that should not be treated as valid artifacts."""
    if not text:
        return True
    lowered = text.lower()
    refusal_markers = [
        "i need to see the complete lecture document",
        "could you please provide the full document",
        "once i have this complete document",
        "please provide the full document",
        "i don't see any input items provided",
        "i need the complete document",
    ]
    return any(marker in lowered for marker in refusal_markers)


def _is_valid_section_content(section_name: str, text: str) -> bool:
    """Basic quality gates for extracted sections before downstream use."""
    if not text or not text.strip():
        return False
    if _contains_refusal_or_missing_context_text(text):
        return False

    normalized = section_name.lower()
    if normalized in ("topics", "key topics"):
        return bool(abstract_pipeline.parse_topics_from_extraction(text))
    if normalized in (
        "interpretive themes",
        "themes",
        "key themes",
        "structural themes",
    ):
        # Route through the format-aware parser so validity means "real themes
        # parsed", not "some scaffolding present". A bare `###`/number-outside-bold
        # check passed all-scaffolding structural files as valid (P19 sibling).
        if abstract_pipeline.parse_themes_from_extraction(text):
            return True
        # Fallback matches BOTH bold forms: `**1. Title**` (real, number inside
        # bold) and legacy `1. **Title**` (number outside bold).
        return bool(
            re.search(r"(?:^|\n)\s*(?:\*\*\d+\.\s+.+?\*\*|\d+\.\s+\*\*.+?\*\*)", text)
        )
    if normalized == "key terms":
        return bool(
            re.search(r"(?:^|\n)###\s+", text)
            or re.search(r"(?:^|\n)\*\*[^*\n]+\*\*\s*[:\-]", text)
        )
    return True


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
    prompt = fill_prompt_template(template, {}, "", **replacements)
    # If prompts do not include placeholders, still provide dynamic context explicitly.
    unresolved = []
    for key, value in replacements.items():
        pattern = re.compile(r"{{{{\s*{}\\s*}}}}".format(re.escape(key)), re.IGNORECASE)
        if not pattern.search(template):
            unresolved.append((key, value))
    if unresolved:
        context_lines = ["", "", "## Provided Context", ""]
        for key, value in unresolved:
            context_lines.append(f"### {key}")
            context_lines.append(str(value).strip())
            context_lines.append("")
        prompt = prompt.rstrip() + "\n" + "\n".join(context_lines).rstrip() + "\n"

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


def _format_bowen_refs(refs: list[tuple]) -> str:
    """Format Bowen references with optional timestamps."""
    lines = []
    for ref in refs:
        if len(ref) == 3:
            concept, quote, timestamp = ref
        else:
            concept, quote = ref
            timestamp = None
        
        concept = " ".join(str(concept).split()).strip()
        quote = " ".join(str(quote).split()).strip().replace('"', "'")
        
        if not concept or not quote:
            continue
            
        ts_str = f" [{timestamp}]" if timestamp else ""
        lines.append(f"### {concept}{ts_str}\n> \"{quote}\"")
    return "\n\n".join(lines)



def _compact_bowen_quote(quote: str, max_words: int = 140) -> str:
    """
    Keep quotes reasonably bounded while preserving attribution language.
    Prefer the sentence containing attribution plus adjacent context.
    """
    quote = " ".join(str(quote).split()).strip()
    if not quote:
        return quote

    words = quote.split()
    if len(words) <= max_words:
        return quote

    sentences = [
        s.strip()
        for s in re.split(r'(?<=[.!?])\s+', quote)
        if s and s.strip()
    ]
    if not sentences:
        return " ".join(words[:max_words]).rstrip(" ,;:") + "..."

    attr_pat = re.compile(
        r"\b(?:murray|dr\.?\s*bowen|bowen(?:'s)?|to\s+quote\s+bowen|he\s+said)\b",
        re.IGNORECASE,
    )
    idx = next((i for i, s in enumerate(sentences) if attr_pat.search(s)), 0)

    picked = [sentences[idx]]
    # Include one adjacent sentence if it fits.
    for j in (idx + 1, idx - 1):
        if 0 <= j < len(sentences):
            candidate = " ".join(picked + [sentences[j]])
            if len(candidate.split()) <= max_words:
                picked.append(sentences[j])
                break

    compact = " ".join(picked).strip()
    compact_words = compact.split()
    if len(compact_words) > max_words:
        compact = " ".join(compact_words[:max_words]).rstrip(" ,;:") + "..."

    return compact


def _concept_has_bowen_attribution(concept: str) -> bool:
    """Return True when the concept name itself names Bowen as the source.

    Handles cases like "Bowen's Timeline Prediction" or "Bowen's War on Cancer
    Comment" where the attribution is in the label, not the quote body.
    """
    if not concept:
        return False
    c = concept.lower().strip()
    # Possessive "Bowen's X" (exclude "Bowen theory" / "Bowen theorist")
    if re.search(r"\bbowen'?s\b", c) and not re.search(r"\bbowen\s+theor", c):
        return True
    # "Murray Bowen" or "Dr. Bowen" in the concept name
    if re.search(r"\b(?:murray\s+bowen|dr\.?\s*bowen)\b", c):
        return True
    return False


def _rule_filter_bowen_references(
    refs: list[tuple[str, str]],
    logger,
) -> list[tuple[str, str]]:
    """Drop refs that lack Bowen-source attribution in either the quote or the concept name."""
    filtered: list[tuple[str, str]] = []
    for concept, quote in refs:
        if _has_bowen_source_attribution(quote) or _concept_has_bowen_attribution(concept):
            filtered.append((concept, quote))
        else:
            logger.warning(
                "Dropping Bowen reference without Bowen-source attribution text: %s",
                concept,
            )
    return filtered


def _write_bowen_drop_diagnostic(parsed_refs, transcript_text, formatted_filename, logger):
    """Make a 0-reference Bowen result inspectable instead of silent.

    When extraction produced candidates but none survive attribution filtering +
    grounding, dump each candidate with WHY it dropped — whether its quote/concept
    names Bowen, and how well the quote grounds in the transcript. This answers
    "did the extraction miss the attribution, or did the filter over-drop it?"
    without which a 0 is opaque. Spec: run-log review (Bowen extraction).
    """
    try:
        stem = clean_project_name(Path(formatted_filename).stem)
        stem = stem.replace(config.SUFFIX_FORMATTED.replace(".md", ""), "")
        stem = stem.replace(config.SUFFIX_YAML.replace(".md", ""), "")
        project_dir = config.PROJECTS_DIR / stem
        project_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Bowen References — Drop Diagnostic",
            "",
            f"Extraction produced {len(parsed_refs)} candidate(s) but 0 survived "
            "attribution filtering + transcript grounding. If a candidate names "
            "Bowen but was dropped, the filter is over-dropping; if none name "
            "Bowen, the extraction captured concept applications rather than "
            "Bowen-attributed passages.",
            "",
            "| Concept | Names Bowen? | Grounding | Quote (excerpt) |",
            "|---|:--:|--:|---|",
        ]
        for concept, quote in parsed_refs:
            attr = _has_bowen_source_attribution(quote) or _concept_has_bowen_attribution(concept)
            _, _, ratio = find_text_in_content(
                quote, transcript_text, aggressive_normalization=True
            )
            excerpt = re.sub(r"\s+", " ", quote).strip()[:120].replace("|", "\\|")
            lines.append(
                f"| {concept[:50]} | {'yes' if attr else 'no'} | {ratio:.2f} | {excerpt} |"
            )
        debug_path = project_dir / f"{stem} - bowen-references-debug.md"
        debug_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.warning(
            "Bowen: 0 grounded refs from %d candidate(s). Drop diagnostic saved to: %s",
            len(parsed_refs),
            debug_path.name,
        )
    except Exception as e:  # diagnostics must never break the run
        logger.warning("Could not write Bowen drop diagnostic: %s", e)


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
        prompt = fill_prompt_template(prompt_template, {}, "", items=items_text)

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


# M3.B — codec-backed summary artifacts. summary_type -> (schema key, parse args).
# Types absent here (blog, overview) have no structured contract and are skipped.
_CODEC_FOR_SUMMARY_TYPE = {
    "emphasis-scored": ("emphasis", ()),
    "topics": ("topics", ()),
    "key-terms": ("key_terms", ()),
    "structural-themes": ("themes", ("structural",)),
    "interpretive-themes": ("themes", ("interpretive",)),
}


_ARTIFACT_CONTRACTS_LOGGER = None


def _artifact_contracts_logger():
    """One cached ``artifact_contracts`` logger per process.

    Self-validation runs on EVERY saved artifact, so calling ``setup_logging()``
    each time spawned a fresh timestamped log file and a console "Logging
    initialized" line per save — cluttering the terminal and the logs/ folder.
    Create it once and reuse it.
    """
    global _ARTIFACT_CONTRACTS_LOGGER
    if _ARTIFACT_CONTRACTS_LOGGER is None:
        _ARTIFACT_CONTRACTS_LOGGER = setup_logging("artifact_contracts")
    return _ARTIFACT_CONTRACTS_LOGGER


def _self_validate_saved_summary(output_path: Path, summary_type: str) -> None:
    """M3.B producer self-check for codec-backed artifacts: re-read the just-saved
    file through the schema codec and, on success, write the JSON sidecar. On
    drift, LEAVE the file on disk for the release gate to BLOCK on (deleting would
    invert a loud, publish-blocking gate ERROR into a silent drop — see LEARNINGS),
    invalidate any stale sidecar so the two can't disagree, and log loudly. Never
    raises — the gate is the single blocker; this only surfaces + records."""
    entry = _CODEC_FOR_SUMMARY_TYPE.get(summary_type)
    if entry is None:
        return
    import artifact_contracts as ac

    key, args = entry
    logger = _artifact_contracts_logger()  # cached: one log file per process, not per save
    try:
        obj = ac.codec(key).parse_markdown(
            output_path.read_text(encoding="utf-8"), *args
        )
        ac.write_json_sidecar(output_path, key, obj)
    except ac.SchemaError as e:
        logger.error(
            "%s artifact failed schema self-check — leaving it on disk for the "
            "release gate to BLOCK (P19/U4); invalidating stale sidecar. %s", key, e
        )
        ac.json_sidecar_path(output_path).unlink(missing_ok=True)


def _save_summary(content: str, original_filename: str, summary_type: str) -> Path:
    """Save summary output."""
    stem = clean_project_name(Path(original_filename).stem)
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
        _self_validate_saved_summary(output_path, summary_type)
        return output_path

    suffix = f" - {summary_type}.md"
    if summary_type == "topics":
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
    elif summary_type == "overview":
        suffix = config.SUFFIX_OVERVIEW
    output_filename = f"{stem}{suffix}"
    project_dir = config.PROJECTS_DIR / stem
    project_dir.mkdir(parents=True, exist_ok=True)
    output_path = project_dir / output_filename
    output_path.write_text(content, encoding="utf-8")
    _self_validate_saved_summary(output_path, summary_type)
    return output_path


# Main Exported Functions


def extract_scored_emphasis(
    formatted_filename: str,
    model: str = config.DEFAULT_MODEL,
    logger=None,
    transcript_system_message=None,
    transcript_text: str | None = None,
) -> bool:
    """Run the scored emphasis extraction pipeline."""
    if logger is None:
        logger = setup_logging("extract_scored_emphasis")

    try:
        logger.info("Starting Scored Emphasis Extraction for: %s",
                    formatted_filename)
        if transcript_text is None:
            transcript_text = _load_formatted_transcript(formatted_filename)
        
        prompt_template = _load_summary_prompt(
            config.PROMPT_EMPHASIS_SCORING_FILENAME)

        call_kwargs = {}
        if transcript_system_message:
            full_prompt = prompt_template
            call_kwargs["system"] = transcript_system_message
        else:
            full_prompt = f"{prompt_template}\n\n---\n\nTRANSCRIPT:\n\n{transcript_text}"

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
        logger.info("Parsed %d scored emphasis item(s) from model response.", len(items))
        if not items and len(response) > 500:
            # A >500-char response that parses to ZERO scored items is format drift
            # (the model emitted prose / a wrong shape), not a legitimate empty. We
            # save it under the canonical suffix ON PURPOSE: the M3 self-check +
            # release gate then see a non-conforming emphasis artifact and BLOCK the
            # publish (U4, deliberate) — better than a silent absence. The saved raw
            # is also the operator's inspection copy. (This return False already
            # failed the stage; the gate is the publish-level backstop.)
            output_path = _save_summary(response, formatted_filename, "emphasis-scored")
            logger.warning(
                "Parsed 0 scored emphasis items despite substantial response; saved raw "
                "response to %s — the release gate will BLOCK publish on this drift.",
                output_path,
            )
            return False
            
        # Find timestamps for each item
        for item in items:
            item['timestamp'] = None
            start_pos, _, ratio = find_text_in_content(item['quote'], transcript_text, aggressive_normalization=True)
            if start_pos is not None and ratio > 0.8:
                preceding_text = transcript_text[:start_pos]
                ts_matches = re.findall(r'\[(\d{2}:\d{2}:\d{2})\]', preceding_text)
                if ts_matches:
                    item['timestamp'] = ts_matches[-1]

        logger.info("Extracted %d scored emphasis items.", len(items))

        validated_items = []
        final_content_lines = []
        for item in items:
            is_valid, issues = validate_emphasis_item(item)
            if is_valid:
                validated_items.append(item)
                ts_str = f" | {item['timestamp']}" if item.get('timestamp') else ""
                # Keep the header and its quote in ONE block (single newline
                # between them); items are separated by a blank line below. This
                # matches what parse_scored_emphasis_output re-reads, so the
                # emphasis validator can round-trip the saved file.
                final_content_lines.append(
                    f"[{item['type']} - {item['category']} - Rank: {item['score']}%{ts_str}] "
                    f"Concept: {item['concept']}\n"
                    f'"{item["quote"]}"'
                )
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
    transcript_text: str | None = None,
) -> bool:
    """Extracts Bowen references from the transcript."""
    if logger is None:
        logger = setup_logging("extract_bowen_references")

    try:
        logger.info("Starting Bowen Reference Extraction for: %s",
                    formatted_filename)
        if transcript_text is None:
            transcript_text = _load_formatted_transcript(formatted_filename)
        transcript_text = strip_yaml_frontmatter(transcript_text)
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
        if final_content.strip() and not parsed_refs:
            # The extraction returned a non-empty response that parsed to 0 refs.
            # Either a "no references" prose response (legitimate empty) OR format
            # drift the parser could not read — surface it loudly rather than let a
            # dropped-format extraction read as a silent, indistinguishable 0.
            logger.warning(
                "Bowen extraction response was non-empty but parsed to 0 "
                "references (prose 'none found' or unrecognised format): %.120s",
                final_content,
            )
        filtered_refs = _filter_bowen_references_semantically(
            parsed_refs, model, logger
        )
        filtered_refs = _rule_filter_bowen_references(filtered_refs, logger)

        def _ground_refs(refs: list[tuple[str, str]]) -> list[tuple[str, str]]:
            grounded = []
            # Normalize the transcript ONCE, not per ref per call — the grounding loop
            # searches the same transcript 2x per ref (review M11 / P9).
            transcript_norm = normalize_text(transcript_text, aggressive=True)
            for concept, quote in refs:
                compact_quote = _compact_bowen_quote(quote, max_words=140)
                _, _, ratio_compact = find_text_in_content(
                    compact_quote, transcript_text, aggressive_normalization=True,
                    haystack_normalized=transcript_norm,
                )
                _, _, ratio_full = find_text_in_content(
                    quote, transcript_text, aggressive_normalization=True,
                    haystack_normalized=transcript_norm,
                )
                ratio = max(ratio_compact, ratio_full)
                if ratio >= 0.90:
                    # Keep full extracted quote in output to preserve complete attributed text.
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
            grounded_semantic = _ground_refs(
                _rule_filter_bowen_references(parsed_refs, logger)
            )

        # If we STILL have nothing but the extraction did find candidates, make
        # the zero-result inspectable rather than silently dropping everything.
        if not grounded_semantic and parsed_refs:
            _write_bowen_drop_diagnostic(
                parsed_refs, transcript_text, formatted_filename, logger
            )

        # Find timestamps for each grounded reference
        refs_with_timestamps = []
        for concept, quote in grounded_semantic:
            timestamp = None
            start_pos, _, ratio = find_text_in_content(quote, transcript_text, aggressive_normalization=True)
            if start_pos is not None and ratio > 0.8:
                # Search backwards from the start of the quote for the last timestamp
                preceding_text = transcript_text[:start_pos]
                ts_matches = re.findall(r'\[(\d{2}:\d{2}:\d{2})\]', preceding_text)
                if ts_matches:
                    timestamp = ts_matches[-1]
            refs_with_timestamps.append((concept, quote, timestamp))

        filtered_refs = refs_with_timestamps
        final_content = _format_bowen_refs(filtered_refs)

        # Ensure header is present for standard parsing
        final_content = f"## Bowen References\n\n{final_content}".rstrip()

        stem = clean_project_name(Path(formatted_filename).stem)
        stem = stem.replace(config.SUFFIX_FORMATTED.replace(".md", ""), "")
        stem = stem.replace(config.SUFFIX_YAML.replace(".md", ""), "")
        project_dir = config.PROJECTS_DIR / stem
        project_dir.mkdir(parents=True, exist_ok=True)
        bowen_path = project_dir / f"{stem}{config.SUFFIX_BOWEN}"
        bowen_path.write_text(final_content, encoding="utf-8")

        # M3.B — producer self-validation + JSON sidecar. Re-read the saved
        # artifact through the schema codec: if we extracted references but the
        # saved markdown does not parse back to them (or violates the schema),
        # that is producer/consumer format drift (P19). LEAVE the drifted file on
        # disk on purpose — deleting it would convert a loud, publish-blocking
        # gate ERROR (check_artifact_contracts, a hard blocker per U4) into a
        # silent absence with no signal, since no caller retries on the return
        # value and bowen is not a required artifact. Instead we remove any stale
        # (previously-valid) sidecar so the .json can't contradict the drifted
        # .md, log loudly, and return False. An empty-by-design run (zero refs)
        # skips the item check.
        import artifact_contracts as ac
        try:
            obj = ac.verify_saved_artifact(
                bowen_path, "bowen", expect_items=bool(refs_with_timestamps)
            )
            ac.write_json_sidecar(bowen_path, "bowen", obj)
        except ac.SchemaError as e:
            logger.error(
                "Bowen artifact FAILED contract self-check — the saved artifact "
                "drifts from its schema; leaving it on disk so the release gate "
                "BLOCKs publication (P19/U4). Invalidating any stale sidecar. %s", e
            )
            ac.json_sidecar_path(bowen_path).unlink(missing_ok=True)
            return False

        # Count one per reference. _format_bowen_refs emits "### Concept [ts]\n> \"quote\"",
        # so count the "### " concept headers (the previous "> **" pattern never
        # matched this format and reported 0 even when references were saved).
        num_found = len(re.findall(r"^###\s", final_content, re.MULTILINE))
        logger.info("✓ Found %d Bowen references. Saved to: %s",
                    num_found, bowen_path.name)
        return True
    except Exception as e:
        logger.error("Error in Bowen reference extraction: %s",
                     e, exc_info=True)
        return False


def extract_bowen_and_emphasis(
    formatted_filename: str,
    model: str = config.DEFAULT_MODEL,
    logger=None,
) -> bool:
    """Run Bowen and emphasis extraction together using one cached transcript context."""
    if logger is None:
        logger = setup_logging("extract_bowen_and_emphasis")

    try:
        logger.info(
            "Starting combined Bowen + Emphasis extraction for: %s",
            formatted_filename,
        )
        transcript = _load_formatted_transcript(formatted_filename)
        transcript_system_message = create_system_message_with_cache(transcript)

        emphasis_ok = extract_scored_emphasis(
            formatted_filename,
            model,
            logger,
            transcript_system_message,
        )
        bowen_ok = extract_bowen_references_from_transcript(
            formatted_filename,
            model,
            logger,
            transcript_system_message,
            transcript_text=transcript,
        )

        return emphasis_ok and bowen_ok
    except Exception as e:
        logger.error(
            "Error in combined Bowen + Emphasis extraction: %s",
            e,
            exc_info=True,
        )
        return False


def generate_topics(
    formatted_filename: str,
    model: str = config.DEFAULT_MODEL,
    logger=None,
    transcript_system_message=None,
) -> bool:
    """Generate ONLY the Topics artifact from the transcript (standalone).

    Purpose: Produce SUFFIX_TOPICS from the cached transcript alone, so a lean
             Topics -> Abstract path can skip the rest of Core (structural/
             interpretive themes, key terms, lenses). Mirrors PART 3 of
             summarize_transcript exactly (same prompt, min_length, header
             normalisation, and save target).
    Spec:    docs/spec_lean_abstract_2026-07-13.md#LA.1
    Tests:   tests/test_lean_abstract.py::test_la1_generate_topics_writes_topics_artifact
    """
    if logger is None:
        logger = setup_logging("generate_topics")

    try:
        transcript = _load_formatted_transcript(formatted_filename)
        if transcript_system_message is None:
            transcript_system_message = create_system_message_with_cache(transcript)

        logger.info("Generating Topics (standalone) for: %s", formatted_filename)
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
        return True
    except Exception as e:
        logger.error("Error generating topics: %s", e, exc_info=True)
        return False


def generate_structured_summary(
    base_name: str,
    summary_target_word_count: int = None,
    logger=None,
    transcript_system_message=None,
    model: str = config.AUX_MODEL,
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

        transcript = load_project_transcript(
            base_name, logger=logger
        )

        extracts_content = ""

        metadata = parse_filename_metadata(base_name)
        topics_section = _extract_first_section(
            extracts_content, ["Topics", "Key Topics"]
        )
        themes_section = _extract_first_section(
            extracts_content, ["Interpretive Themes", "Themes", "Key Themes"]
        )

        if not topics_section:
            topics_section = _load_section_from_project_file(
                base_name, config.SUFFIX_TOPICS, ["Topics", "Key Topics"]
            )
        if not themes_section:
            themes_section = _load_section_from_project_file(
                base_name,
                config.SUFFIX_INTERPRETIVE_THEMES,
                ["Interpretive Themes", "Themes", "Key Themes", "Interpretive / Process Themes"],
            )

        if not topics_section:
            logger.error("Could not find Topics in canonical topic artifacts.")
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


def _abstract_gate_precheck(base_name: str, logger=None):
    """Run the gate's faithfulness + entity-grounding checks on the just-saved
    abstract (the SAME functions the release gate uses, so they can't drift), and
    classify the result.

    Returns (status, issues):
      - "pass": both checks PASS -> the abstract is publishable.
      - "fail": at least one FAILed -> `issues` holds the specific unsupported
        claim(s) / ungrounded name(s) to feed back to the generator.
      - "unavailable": a check ERRORed or the judge is off (no API key / disabled)
        -> can't verify at generation time; accept and let the gate verify at
        publish (single attempt).
    """
    import release_gate as rg
    # Scope the GENERATION-time precheck to the abstract only — otherwise an unfaithful
    # claim in a sibling artifact (summary/overview/blog, already on disk) would be
    # blamed on the abstract, burning regeneration attempts on a claim the abstract
    # cannot remove and emitting a misleading BLOCK message (review M2). The full
    # multi-artifact faithfulness sweep stays at the publish gate.
    faith = rg.check_faithfulness(base_name, logger, suffixes=[config.SUFFIX_ABSTRACT_GEN])
    entity = rg.check_entity_grounding(base_name, logger)
    if rg.Status.ERROR in (faith.status, entity.status):
        return "unavailable", []
    if rg.Status.FAIL in (faith.status, entity.status):
        issues = []
        for item in (faith.items or []):
            issues.extend(item.get("unfaithful", []))
        for item in (entity.items or []):
            issues.extend(f"the name '{n}' does not appear in the source"
                          for n in item.get("names", []))
        return "fail", issues
    return "pass", []


def generate_structured_abstract(
    base_name: str, logger=None, transcript_system_message=None, model: str = config.AUX_MODEL
) -> bool:
    """
    Generate an abstract using the structured pipeline.
    Note: Uses Sonnet for detailed content generation (was AUX_MODEL/Haiku).
    """
    if logger is None:
        logger = setup_logging("generate_structured_abstract")

    try:
        transcript = load_project_transcript(
            base_name, logger=logger
        )

        metadata = parse_filename_metadata(base_name)

        topics_section = _load_section_from_project_file(
            base_name,
            config.SUFFIX_TOPICS,
            ["Topics", "Key Topics"],
        )
        # Interpretive Themes are optional: the abstract prompt
        # (prompts/Abstract Generation Prompt v1.md) builds Context / Central
        # Argument / Key Content / Conclusions / Q&A from metadata, topics and
        # transcript-derived opening/closing/Q&A only — it never references
        # themes. So a missing themes artifact is tolerated (parsed to []),
        # enabling a lean Topics-only abstract. Spec: docs/spec_lean_abstract_2026-07-13.md#LA.2
        themes_section = _load_section_from_project_file(
            base_name,
            config.SUFFIX_INTERPRETIVE_THEMES,
            ["Interpretive Themes", "Themes", "Key Themes", "Interpretive / Process Themes"],
        ) or ""

        parsed_topics_preview = (
            abstract_pipeline.parse_topics_from_extraction(topics_section)
            if topics_section
            else []
        )

        if topics_section and not parsed_topics_preview:
            logger.warning("Topics file present but unparseable; check topics format.")

        if not topics_section:
            logger.error(
                "Could not find Topics in canonical artifact files (required for the abstract)."
            )
            return False
        if not themes_section:
            logger.info(
                "No Interpretive Themes artifact found; generating abstract from Topics + transcript only."
            )

        # Calculate target word count (capped so abstracts stay < 250 words)
        transcript_words = len(transcript.split())
        target_word_count = config.abstract_target_word_count(transcript_words)

        abstract_input = abstract_pipeline.prepare_abstract_input(
            metadata=metadata,
            topics_markdown=topics_section,
            themes_markdown=themes_section,
            transcript=transcript,
            target_word_count=target_word_count,
        )

        if not parsed_topics_preview or not abstract_input.topics:
            logger.error(
                "Failed to parse any Topics from topics artifact. Check regex or input format."
            )
            return False

        logger.info("Parsed %d topics and %d themes.",
                    len(abstract_input.topics), len(abstract_input.themes))

        if not transcript_system_message:
            transcript_system_message = create_system_message_with_cache(
                transcript)

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        client = anthropic.Anthropic(api_key=api_key)
        output_path = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_ABSTRACT_GEN}"
        )

        # Check faithfulness/grounding AT GENERATION TIME and regenerate (with
        # corrective feedback) until it passes — so an unfaithful abstract is
        # caught + fixed here instead of only at publish. Reuses the gate's own
        # checks so they can't drift.
        max_attempts = max(1, int(getattr(config, "ABSTRACT_MAX_ATTEMPTS", 1)))
        feedback = None
        best_text, best_issue_count = None, None
        for attempt in range(1, max_attempts + 1):
            logger.info("Generating abstract via API (attempt %d/%d)...", attempt, max_attempts)
            abstract_text = abstract_pipeline.generate_abstract(
                abstract_input, client, model=model,
                system=transcript_system_message, feedback_claims=feedback,
            )
            output_path.write_text(abstract_text, encoding="utf-8")

            status, issues = _abstract_gate_precheck(base_name, logger)
            if status == "pass":
                logger.info("✓ Abstract passed faithfulness + grounding on attempt %d/%d. Saved to %s",
                            attempt, max_attempts, output_path)
                return True
            if status == "unavailable":
                logger.warning("Faithfulness/grounding check unavailable at generation "
                               "(judge off or no key); keeping abstract — the release gate "
                               "will verify it at publish. Saved to %s", output_path)
                return True
            # status == "fail": remember the least-bad draft, feed the issues back.
            if best_text is None or len(issues) < best_issue_count:
                best_text, best_issue_count = abstract_text, len(issues)
            feedback = issues
            logger.warning("Abstract attempt %d/%d not faithful (%d issue(s)); "
                           "regenerating with corrective feedback. Issues: %s",
                           attempt, max_attempts, len(issues), "; ".join(issues)[:300])

        # All attempts failed — keep the least-bad draft; honest, loud status.
        if best_text is not None:
            output_path.write_text(best_text, encoding="utf-8")
        logger.error("⚠️ Could not produce a fully faithful abstract after %d attempt(s); "
                     "kept the best draft (%s unresolved issue(s)). The release gate will "
                     "BLOCK publication until it is regenerated or edited.",
                     max_attempts, best_issue_count)
        return True
    except Exception as e:
        logger.error("Error generating structured abstract: %s",
                     e, exc_info=True)
        return False


def _extract_lens_titles(lenses_output: str) -> list[str]:
    """Pull the ranked-lens titles the producer actually wrote — the bold text of
    each `N. **Title**` line in the lenses artifact."""
    return [
        m.strip()
        for m in re.findall(r"(?m)^\s*\d+\.\s*\*\*(.+?)\*\*", lenses_output)
    ]


# Editorial vocabulary lives in config (review L7 / rule 9).
_LENS_STOPWORDS = config.LENS_STOPWORDS


def _top_lens_is_grounded(top_lens: dict, lenses_output: str) -> bool:
    """True only if the validator's `top_lens.title` corresponds to a lens that was
    actually generated (A8/P7). Without this, the top_lens was accepted on a
    truthy-dict gate alone, so a paraphrased or hallucinated lens rode through as
    "validated" and into the blog.

    Matching is on CONTENT tokens (stopwords + short tokens removed, punctuation
    stripped) so smart-quote/em-dash/case differences don't cause a false reject,
    while a title that merely reuses common filler words can't false-match (P7). No
    raw substring match — a short generic title being a substring of a long real
    lens was gameable.
    """
    title = (top_lens.get("title") or "").strip()
    if not title:
        return False
    candidates = _extract_lens_titles(lenses_output)
    if not candidates:
        return False

    def content_tokens(s: str) -> set:
        return {
            t
            for t in re.findall(r"[a-z0-9]+", s.lower())
            if len(t) > 2 and t not in _LENS_STOPWORDS
        }

    title_tokens = content_tokens(title)
    if not title_tokens:
        return False
    for cand in candidates:
        cand_tokens = content_tokens(cand)
        if not cand_tokens:
            continue
        # Fraction of the top_lens title's CONTENT words present in the candidate.
        if len(title_tokens & cand_tokens) / len(title_tokens) >= 0.6:
            return True
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


def summarize_transcript(
    formatted_filename: str,
    model: str,
    focus_keyword: str,
    target_audience: str,
    skip_extracts_summary: bool,
    skip_emphasis: bool,
    skip_bowen: bool,
    skip_blog: bool,
    skip_overview: bool = True,
    generate_structured: bool = False,
    structured_word_count: int = config.DEFAULT_SUMMARY_WORD_COUNT,
    logger=None,
) -> bool:
    """Orchestrates the transcript summarization process.

    Purpose: Run the configurable suite of summary/blog/overview generations.
    Spec:    docs/implementation_plan_2026-05-13.md#OV.3
    Tests:   tests/test_overview_post.py
    """
    if logger is None:
        logger = setup_logging("summarize_transcript")

    try:
        # SOURCE_DIR is only used by upstream extraction. Standalone runs
        # (skip_extracts_summary=True) read from PROJECTS_DIR instead, so
        # don't require SOURCE_DIR to exist.
        if not skip_extracts_summary and not config.SOURCE_DIR.exists():
            raise FileNotFoundError(
                f"Source directory not found: {config.SOURCE_DIR}")

        logger.info("Loading formatted transcript: %s", formatted_filename)
        transcript = _load_formatted_transcript(formatted_filename)
        transcript_word_count = len(transcript.split())
        metadata = parse_filename_metadata(formatted_filename)
        logger.info("Transcript metadata: %s", metadata)

        transcript_system_message = create_system_message_with_cache(
            transcript)

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
            # Capped so abstracts stay < 250 words (single source, P5).
            target_word_count = config.abstract_target_word_count(transcript_word_count)
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
            else:
                logger.info("\n--- PART 6: Emphasis Extraction Skipped ---")

            if not skip_bowen:
                logger.info("\n--- PART 7: Extracting Bowen References ---")
                extract_bowen_references_from_transcript(
                    formatted_filename, model, logger, transcript_system_message
                )
            else:
                logger.info("\n--- PART 7: Bowen Reference Extraction Skipped ---")

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
            validated = False  # A8: only ship if a grounded top lens was achieved.
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
                # A8/P7: the validator's top_lens must correspond to a lens actually
                # generated — otherwise a paraphrased/hallucinated lens is accepted.
                top_lens_grounded = _top_lens_is_grounded(top_lens, lenses_output)
                if top_lens and not top_lens_grounded:
                    logger.warning(
                        "Top lens '%s' is NOT grounded in the generated lenses — "
                        "treating as unvalidated and regenerating.",
                        top_lens.get("title", "(untitled lens)"),
                    )

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
                if structural_valid and interpretive_valid and top_lens and top_lens_grounded:
                    logger.info(
                        "✓ Top-ranked lens validated: %s",
                        top_lens.get("title", "(untitled lens)"),
                    )
                    validated = True
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

            if not validated:
                # A8/P7: retries exhausted without themes valid AND a top lens that
                # is grounded in the generated lenses. Do NOT ship an ungrounded/
                # unvalidated lens (the exhaustion-path fall-through the truthy-dict
                # gate allowed) — fail closed.
                logger.error(
                    "Failed to produce a validated + grounded top-ranked lens after "
                    "%d attempts; last top_lens=%r.",
                    max_attempts, top_lens.get("title", "(none)"),
                )
                return False

            _save_summary(structural_output, formatted_filename, "structural-themes")
            _save_summary(interpretive_output, formatted_filename, "interpretive-themes")
            _save_summary(lenses_output, formatted_filename, "lenses-ranked")
        else:
            stem = metadata["stem"]
            project_dir = config.PROJECTS_DIR / stem
            structural_output = _load_section_from_project_file(
                stem, config.SUFFIX_STRUCTURAL_THEMES, ["Structural Themes"]
            )
            interpretive_output = _load_section_from_project_file(
                stem,
                config.SUFFIX_INTERPRETIVE_THEMES,
                ["Interpretive Themes", "Themes", "Key Themes", "Interpretive / Process Themes"],
            )
            topics_output = _load_section_from_project_file(
                stem, config.SUFFIX_TOPICS, ["Topics", "Key Topics"]
            )
            key_terms_output = _load_section_from_project_file(
                stem, config.SUFFIX_KEY_TERMS, ["Key Terms"]
            )
            lenses_output = _load_section_from_project_file(
                stem, config.SUFFIX_LENSES, ["Lenses (Ranked)", "Lenses"]
            )
            abstract_generated = project_dir / f"{stem}{config.SUFFIX_ABSTRACT_GEN}"
            abstract_initial = project_dir / f"{stem}{config.SUFFIX_ABSTRACT_INIT}"
            if abstract_generated.exists():
                abstract_output = strip_yaml_frontmatter(
                    abstract_generated.read_text(encoding="utf-8")
                ).strip()
            elif abstract_initial.exists():
                abstract_output = strip_yaml_frontmatter(
                    abstract_initial.read_text(encoding="utf-8")
                ).strip()
            # Rehydrate/validate canonical artifacts.
            if (not structural_output) or (
                not _is_valid_section_content("Structural Themes", structural_output)
            ):
                structural_output = _load_section_from_project_file(
                    stem, config.SUFFIX_STRUCTURAL_THEMES, ["Structural Themes"]
                )
            if (not interpretive_output) or (
                not _is_valid_section_content("Interpretive Themes", interpretive_output)
            ):
                interpretive_output = _load_section_from_project_file(
                    stem,
                    config.SUFFIX_INTERPRETIVE_THEMES,
                    ["Interpretive Themes", "Themes", "Key Themes", "Interpretive / Process Themes"],
                )
            if (not topics_output) or (
                not _is_valid_section_content("Topics", topics_output)
            ):
                topics_output = _load_section_from_project_file(
                    stem, config.SUFFIX_TOPICS, ["Topics", "Key Topics"]
                )
            if (not key_terms_output) or (
                not _is_valid_section_content("Key Terms", key_terms_output)
            ):
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


        if not skip_blog:
            if not top_lens:
                logger.error(
                    "No validated top-ranked lens available; blog generation aborted by policy."
                )
                return False
            logger.info("\n--- PART 8: Generating Blog Post from Lens #1 ---")
            prompt_template = _load_summary_prompt(config.PROMPT_BLOG_FILENAME)
            prompt = fill_prompt_template(
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

        if not skip_overview:
            missing_inputs = [
                name for name, value in [
                    ("abstract", abstract_output),
                    ("structural_themes", structural_output),
                    ("topics", topics_output),
                    ("key_terms", key_terms_output),
                ]
                if not value
            ]
            if missing_inputs:
                logger.error(
                    "Overview generation aborted; missing required artifacts: %s",
                    ", ".join(missing_inputs),
                )
                return False
            logger.info("\n--- PART 9: Generating Overview Post (GEO) ---")
            prompt_template = _load_summary_prompt(config.PROMPT_OVERVIEW_FILENAME)
            prompt = fill_prompt_template(
                prompt_template,
                metadata,
                transcript="",
                focus_keyword=focus_keyword,
                target_audience=target_audience,
                target_word_count=config.OVERVIEW_MIN_WORDS,
                title=metadata.get("title", ""),
                presenter=metadata.get("presenter", metadata.get("author", "")),
                date=metadata.get("date", ""),
                abstract=abstract_output,
                structural_themes=structural_output,
                topics=topics_output,
                key_terms=key_terms_output,
            )
            overview_output = _generate_summary_with_claude(
                prompt,
                model,
                config.TEMP_BALANCED,
                logger,
                min_words=config.OVERVIEW_MIN_WORDS,
                system=transcript_system_message,
            )
            overview_path = _save_summary(overview_output, formatted_filename, "overview")
            logger.info("✓ Overview post saved to: %s", overview_path)
        else:
            logger.info("Overview generation skipped (skip_overview=True).")

        logger.info("✓ Transcript processing complete!")

        if not skip_extracts_summary:
            logger.info("VALIDATION: Checking Emphasis Items...")
            stem = metadata["stem"]
            formatted_path = (
                config.PROJECTS_DIR / stem / f"{stem}{config.SUFFIX_FORMATTED}"
            )
            if formatted_path.exists():
                validate_emphasis_items(
                    formatted_path, formatted_path, logger)
                logger.info("VALIDATION: Checking Topics (lightweight)...")
                validate_topics_lightweight(formatted_path, stem, logger)
                logger.info("VALIDATION: Checking Key Terms...")
                validate_key_terms_fidelity(formatted_path, stem, logger)

        if generate_structured:
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

        return True

    except Exception as e:
        logger.error("An error occurred: %s", e, exc_info=True)
        return False
