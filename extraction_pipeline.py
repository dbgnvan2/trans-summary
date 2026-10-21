"Pipeline module for extracting insights, summaries, and emphasis items."

import json
import re
from pathlib import Path


import abstract_pipeline
import config
import flagged_removal
import removal_record
import transcript_utils
import summary_pipeline
from bowen_attribution import has_bowen_source_attribution as _has_bowen_source_attribution
from bowen_attribution import concept_has_bowen_attribution
from transcript_utils import (
    extract_lens_titles,
    get_anthropic_client,
    call_claude_with_retry,
    clean_project_name,
    create_system_message_with_cache,
    extract_bowen_references,
    extract_section,
    fill_prompt_template,
    placeholder_pattern,
    find_text_in_content,
    load_project_transcript,
    normalize_text,
    parse_filename_metadata,
    parse_scored_emphasis_output,
    setup_logging,
    strip_yaml_frontmatter,
    themes_for_prompt,
    validate_emphasis_item,
    validate_input_file,
)
from validation_pipeline import (
    quote_is_verbatim_for_gate,
    validate_emphasis_items,
    validate_key_terms_fidelity,
    validate_summary_coverage,
    validate_topics_lightweight,
    summary_coverage_message,
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
    client = get_anthropic_client()

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
    return transcript_utils.response_text(message)


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
        # N2 review: the format check's parser (artifact_contracts.topics_from_markdown
        # uses summary_pipeline.parse_topics_structure), not the abstract's three-
        # strategy parser. Same result on 19 real topics files.
        import summary_pipeline
        return bool(summary_pipeline.parse_topics_structure(text))
    if normalized in (
        "interpretive themes",
        "themes",
        "key themes",
        "structural themes",
    ):
        # N2: the same parser the format check uses (artifact_contracts.themes_from_
        # markdown), so the stage can't report valid themes the format check rejects.
        # A looser regex fallback accepted bold-numbered lines with no Description.
        # On 23 real theme files it changed no result.
        return bool(transcript_utils.parse_bold_numbered_theme_blocks(text))
    if normalized == "key terms":
        return bool(
            re.search(r"(?:^|\n)###\s+", text)
            or re.search(r"(?:^|\n)\*\*[^*\n]+\*\*\s*[:\-]", text)
        )
    return True


def _report_invalid_sections(logger, sections: dict) -> list:
    """Log an error for each loaded section whose content fails
    _is_valid_section_content. Before, a failing section was reloaded from the same
    file and used as is with no message (N2 review, P2). Later steps still run (the
    release gate's format check blocks publish); this makes the cause visible in the
    run log. Returns the names reported.

    Spec:  docs/plan_small_fixes_2026-10-12.md#N2
    Tests: tests/test_small_fixes_n.py::test_n2_invalid_section_is_reported
    """
    bad = [name for name, text in sections.items()
           if text and not _is_valid_section_content(name, text)]
    for name in bad:
        logger.error("%s: the saved file has no items its format check can read; later "
                     "steps use it as is and the release gate will block publish. "
                     "Re-run that step.", name)
    return bad


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


# Prompt placeholders that take a theme file's text (TP).
_THEME_PROMPT_KEYS = ("structural_themes", "interpretive_themes")


def _for_prompt(replacements: dict) -> dict:
    """Prompt values with each theme file reduced to its published themes
    (``themes_for_prompt``), leaving out the model's closing notes (TP)."""
    return {key: (themes_for_prompt(value) if key in _THEME_PROMPT_KEYS and isinstance(value, str)
                  else value)
            for key, value in replacements.items()}


def _generate_with_cached_transcript(
    prompt_filename: str,
    model: str,
    logger,
    transcript_system_message,
    min_length: int = 100,
    **replacements,
) -> str:
    """Generate an artifact using a prompt template and cached transcript context."""
    return _generate_summary_with_claude(
        _build_prompt(prompt_filename, replacements),
        model,
        config.TEMP_ANALYSIS,
        logger,
        min_length=min_length,
        timeout=config.TIMEOUT_SUMMARY,
        system=transcript_system_message,
    )


def _build_prompt(prompt_filename: str, replacements: dict) -> str:
    """The prompt text: the template with its placeholders filled; a value with no
    placeholder in the template is added under "## Provided Context"."""
    replacements = _for_prompt(replacements)
    template = _load_summary_prompt(prompt_filename)
    prompt = fill_prompt_template(template, {}, "", **replacements)
    # If prompts do not include placeholders, still provide dynamic context explicitly.
    unresolved = []
    for key, value in replacements.items():
        # Shared pattern: the old inline regex required a literal backslash and
        # never matched, so every value was sent twice (review B-05).
        if not placeholder_pattern(key).search(template):
            unresolved.append((key, value))
    if unresolved:
        context_lines = ["", "", "## Provided Context", ""]
        for key, value in unresolved:
            context_lines.append(f"### {key}")
            context_lines.append(str(value).strip())
            context_lines.append("")
        prompt = prompt.rstrip() + "\n" + "\n".join(context_lines).rstrip() + "\n"
    return prompt


_THEME_PROMPTS = {"structural": "PROMPT_STRUCTURAL_THEMES_FILENAME",
                  "interpretive": "PROMPT_INTERPRETIVE_THEMES_FILENAME"}


def _generate_structured_themes(kind: str, model: str, logger, transcript_system_message,
                                structural: dict | None = None) -> tuple:
    """Generate one theme set as JSON that must match the schema, and render its
    markdown. Returns ``(obj, markdown)``: ``obj`` the checked version-2 object (the
    source of truth, saved as the ``.json`` file), ``markdown`` the file the page,
    judge and later prompts read. ``structural``: the structural object, required for
    the interpretive kind; it is sent as rendered markdown and its theme count bounds
    ``nested_under``.

    A reply that is not JSON or fails ``check_structured_themes`` is retried by
    ``call_claude_with_retry``; after the last attempt the error is raised (fail
    closed), and the stage records the failure.

    Purpose: Theme files in one layout, whatever the model's formatting (ST).
    Spec:    docs/plan_structured_themes_2026-10-14.md#ST.3
    Tests:   tests/test_structured_themes_st.py::test_st3_invalid_reply_retried_then_fails
    """
    import artifact_contracts as ac

    replacements = {}
    structural_count = None
    if kind == "interpretive":
        if structural is None:
            raise ValueError("interpretive themes need the structural themes object")
        replacements["structural_themes"] = ac.themes_to_markdown(structural)
        structural_count = len(structural["items"])
    prompt = _build_prompt(getattr(config, _THEME_PROMPTS[kind]), replacements)
    message = call_claude_with_retry(
        client=get_anthropic_client(),
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=config.MAX_TOKENS_EXTRACTION,
        temperature=config.TEMP_ANALYSIS,
        stream=True,
        min_length=config.THEME_MIN_REPLY_CHARS[kind],
        timeout=config.TIMEOUT_SUMMARY,
        logger=logger,
        system=transcript_system_message,
        output_format={"type": "json_schema", "schema": ac.themes_model_schema(kind)},
        check_reply=lambda text: ac.structured_themes_from_reply(text, kind, structural_count),
    )
    obj = ac.structured_themes_from_reply(
        transcript_utils.response_text(message), kind, structural_count)
    logger.info("%s themes: %d, returned as checked JSON.", kind.capitalize(), len(obj["items"]))
    return obj, ac.themes_to_markdown(obj, structural)


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
    """(alias) See ``bowen_attribution.concept_has_bowen_attribution`` — single
    source of truth, shared with the Bowen parser's fallback so the two cannot
    drift."""
    return concept_has_bowen_attribution(concept)


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
            "| Concept | Names Bowen? | Match / coverage | Quote (excerpt) |",
            "|---|:--:|--:|---|",
        ]
        for concept, quote in parsed_refs:
            attr = _has_bowen_source_attribution(quote) or _concept_has_bowen_attribution(concept)
            # The same test grounding used (sweep): match and word coverage.
            _ok, ends, coverage = quote_is_verbatim_for_gate(quote, transcript_text)
            excerpt = re.sub(r"\s+", " ", quote).strip()[:120].replace("|", "\\|")
            lines.append(
                f"| {concept[:50]} | {'yes' if attr else 'no'} | "
                f"{ends:.2f} / {coverage:.2f} | {excerpt} |"
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


def _self_validate_saved_summary(output_path: Path, summary_type: str, run_logger=None,
                                 structured: dict | None = None) -> None:
    """M3.B producer self-check for codec-backed artifacts: re-read the just-saved
    file through the schema codec and, on success, write the JSON sidecar. On
    drift, LEAVE the file on disk for the release gate to BLOCK on (deleting would
    invert a loud, publish-blocking gate ERROR into a silent drop — see LEARNINGS),
    invalidate any stale sidecar so the two can't disagree, and log loudly. Never
    raises — the gate is the single blocker; this only surfaces + records.

    ``structured``: the theme stage's checked version-2 object (ST), saved as the JSON
    file instead of the object read back from the markdown. ``_save_themes`` checks
    that the markdown reads back to its themes before anything is written."""
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
        ac.write_json_sidecar(output_path, key, structured if structured is not None else obj)
    except ac.SchemaError as e:
        logger.error(
            "%s artifact failed schema self-check — leaving it on disk for the "
            "release gate to BLOCK (P19/U4); invalidating stale sidecar. %s", key, e
        )
        if run_logger is not None:
            # T3: say it in the run's own log too, not only the artifact_contracts
            # log file, so the problem is seen when it happens, not at the gate.
            run_logger.error(
                "❌ %s failed its format check: %s The release gate will block "
                "publication until it is regenerated.", summary_type, e)
        ac.json_sidecar_path(output_path).unlink(missing_ok=True)


def _summary_stem(original_filename: str) -> str:
    """The project base name for a formatted / YAML transcript filename."""
    stem = clean_project_name(Path(original_filename).stem)
    if stem.endswith(config.SUFFIX_FORMATTED.replace(".md", "")):
        stem = stem.replace(config.SUFFIX_FORMATTED.replace(".md", ""), "")
    if stem.endswith("_yaml"):
        stem = stem[:-5]
    if stem.endswith(config.SUFFIX_YAML.replace(".md", "")):
        stem = stem.replace(config.SUFFIX_YAML.replace(".md", ""), "")
    return stem


def _set_aside_stale_emphasis(formatted_filename: str, logger) -> None:
    """When emphasis extraction saves nothing, rename an emphasis file (and its JSON
    sidecar) left by an earlier run to ``….stale``, so it is not published as this
    run's result (P8). Renamed, not deleted, so it can still be inspected.

    Spec:  docs/plan_todo_triage_2026-10-11.md#Q3
    Tests: tests/test_emphasis_save_q3.py::test_q3_failed_run_sets_aside_older_emphasis_file
    """
    import artifact_contracts as ac
    stem = _summary_stem(formatted_filename)
    md_path = config.PROJECTS_DIR / stem / f"{stem}{config.SUFFIX_EMPHASIS_SCORED}"
    for path in (md_path, ac.json_sidecar_path(md_path)):
        if path.exists():
            stale = path.with_name(f"{path.name}.stale")
            path.replace(stale)
            logger.warning("Emphasis file from an earlier run set aside: %s", stale)


def _save_summary(content: str, original_filename: str, summary_type: str,
                  logger=None, structured: dict | None = None) -> Path:
    """Save summary output. ``logger``: the run's logger, which also reports a
    failed format self-check (T3). ``structured``: for a theme file, the version-2
    object ``content`` was rendered from, saved as the JSON file (ST)."""
    stem = _summary_stem(original_filename)

    if summary_type == "emphasis-scored":
        suffix = config.SUFFIX_EMPHASIS_SCORED
        output_filename = f"{stem}{suffix}"
        project_dir = config.PROJECTS_DIR / stem
        project_dir.mkdir(parents=True, exist_ok=True)
        output_path = project_dir / output_filename
        output_path.write_text(content, encoding="utf-8")
        _self_validate_saved_summary(output_path, summary_type, logger)
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
    _self_validate_saved_summary(output_path, summary_type, logger, structured)
    return output_path


def _save_themes(obj: dict, markdown: str, original_filename: str, logger) -> Path:
    """Save a theme set: the markdown file and, as its JSON file, the version-2
    object it was rendered from (ST.5). The markdown must read back to the object's
    themes in order; if not, the renderer is wrong, so this raises and writes nothing
    (the files from an earlier run stay as they were).

    Spec:  docs/plan_structured_themes_2026-10-14.md#ST.5
    Tests: tests/test_structured_themes_st.py::test_st5_all_producers_write_json_and_md
           tests/test_structured_themes_st.py::test_st5_markdown_that_does_not_read_back_is_not_saved
    """
    import artifact_contracts as ac

    ac.check_structured_themes(obj)
    read_back = [it["name"] for it in
                 ac.codec("themes").parse_markdown(markdown, obj["kind"])["items"]]
    if read_back != [it["title"] for it in obj["items"]]:
        raise ac.SchemaError(f"{obj['kind']} themes: the markdown reads back as {read_back}, "
                             f"not the generated themes; nothing saved")
    return _save_summary(markdown, original_filename, f"{obj['kind']}-themes",
                         logger=logger, structured=obj)


# Main Exported Functions


def extract_scored_emphasis(
    formatted_filename: str,
    model: str | None = None,
    logger=None,
    transcript_system_message=None,
    transcript_text: str | None = None,
) -> bool:
    """Run the scored emphasis extraction pipeline."""
    model = model or config.settings.DEFAULT_MODEL  # N3: resolved per call, not at import
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
            effort=config.EMPHASIS_EFFORT,  # fixed thinking level (measured; see config)
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
            output_path = _save_summary(response, formatted_filename, "emphasis-scored", logger=logger)
            logger.warning(
                "Parsed 0 scored emphasis items despite substantial response; saved raw "
                "response to %s — the release gate will BLOCK publish on this drift.",
                output_path,
            )
            return False
        if not items:
            # N1: a short response with no scored items (a refusal, "none found") was
            # saved raw and reported as success; the gate then returned ERROR on it.
            # Nothing is saved, and an earlier run's file is set aside (as Q3).
            logger.error("The model returned no emphasis items (%d characters: %.120r); "
                         "nothing saved. Re-run the extraction.", len(response), response)
            _set_aside_stale_emphasis(formatted_filename, logger)
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
        verbatim_dropped = []
        verbatim_checked = 0
        gate_text = _gate_source_text(formatted_filename, transcript_text)
        for item in items:
            is_valid, issues = validate_emphasis_item(item)
            if is_valid:
                # RF.K: the gate's own verbatim test, so a spliced or altered quote is
                # dropped here instead of blocking publication later (P19).
                verbatim_checked += 1
                ok, ends, coverage = quote_is_verbatim_for_gate(item["quote"], gate_text)
                if not ok:
                    verbatim_dropped.append(item)
                    logger.warning("Dropping emphasis item not verbatim in the transcript "
                                   "(match %.2f, coverage %.2f): %s", ends, coverage,
                                   item.get("concept", ""))
                    continue
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
        logger.info("Emphasis verbatim check: kept %d of %d.",
                    verbatim_checked - len(verbatim_dropped), verbatim_checked)
        if not validated_items and verbatim_dropped:
            # Saving the raw response here would put back exactly the quotes just
            # dropped, and report success (sweep, P2/P19).
            logger.error("No emphasis item is verbatim in the transcript (kept 0 of %d); "
                         "nothing saved. Re-run the extraction.", verbatim_checked)
            _set_aside_stale_emphasis(formatted_filename, logger)
            return False
        if items and not validated_items:
            # Q3: every parsed item failed item validation. Saving the raw response
            # would write the rejected items and report success (P2/P19).
            logger.error("No emphasis item passed validation (kept 0 of %d); "
                         "nothing saved. Re-run the extraction.", len(items))
            _set_aside_stale_emphasis(formatted_filename, logger)
            return False
        # Every branch with no validated items has returned above (Q3, N1).
        final_content = "\n\n".join(final_content_lines)
        output_path = _save_summary(
            final_content, formatted_filename, "emphasis-scored", logger=logger)
        logger.info("✓ Scored emphasis saved to: %s", output_path)

        return True

    except Exception as e:
        logger.error("Error in scored emphasis extraction: %s",
                     e, exc_info=True)
        # Q3 re-check: an API or parse failure must not leave an earlier run's file
        # to be published as this run's result (P8).
        try:
            _set_aside_stale_emphasis(formatted_filename, logger)
        except OSError as move_error:
            logger.error("Could not set aside the earlier emphasis file: %s", move_error)
        return False


def _run_emphasis_step(formatted_filename, model, logger, transcript_system_message) -> bool:
    """Run emphasis extraction inside the main pipeline and say so when it produced
    nothing: emphasis is optional, so the release gate does not block a run without
    it, and this warning is the signal (Q3 sweep).

    Spec:  docs/plan_todo_triage_2026-10-11.md#Q3
    Tests: tests/test_emphasis_save_q3.py::test_q3_pipeline_warns_when_emphasis_not_produced
    """
    ok = extract_scored_emphasis(formatted_filename, model, logger, transcript_system_message)
    if not ok:
        logger.warning("Emphasis items were not produced; the published pages will "
                       "have no emphasis items.")
    return ok


def _gate_source_text(formatted_filename: str, fallback: str) -> str:
    """The text the release gate checks quotes against for this project
    (formatted transcript, else YAML body), so an extractor's verbatim check and
    the gate's agree (sweep, P35). Falls back to ``fallback`` without front matter
    when the project has neither (e.g. a direct text file)."""
    import release_gate

    stem = clean_project_name(Path(formatted_filename).stem)
    for suffix in (config.SUFFIX_FORMATTED, config.SUFFIX_YAML):
        stem = stem.replace(suffix.replace(".md", ""), "")
    return release_gate._load_source_transcript(stem) or strip_yaml_frontmatter(fallback or "")


def _ground_bowen_refs(refs, transcript_text: str, logger) -> list:
    """Keep the Bowen references whose quote passes the release gate's verbatim
    test (``quote_is_verbatim_for_gate``); log each one dropped and "kept N of M".

    Purpose: Never save a Bowen quote the gate will reject (RF.K, P19).
    Spec:    docs/plan_run_fixes_2026-10-09.md#RF.K.2
    Tests:   tests/test_run_fixes_rf.py::test_rfk2_bowen_spliced_quote_dropped
    """
    grounded = []
    for concept, quote in refs:
        ok, ends, coverage = quote_is_verbatim_for_gate(quote, transcript_text)
        if ok:
            grounded.append((concept, quote))
        else:
            logger.warning("Dropping Bowen reference not verbatim in the transcript "
                           "(match %.2f, coverage %.2f): %s", ends, coverage, concept)
    if refs:
        logger.info("Bowen references verbatim check: kept %d of %d.", len(grounded), len(refs))
    return grounded


def extract_bowen_references_from_transcript(
    formatted_filename: str,
    model: str | None = None,
    logger=None,
    transcript_system_message=None,
    transcript_text: str | None = None,
) -> bool:
    """Extracts Bowen references from the transcript."""
    model = model or config.settings.DEFAULT_MODEL  # N3: resolved per call, not at import
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

        gate_text = _gate_source_text(formatted_filename, transcript_text)

        def _ground_refs(refs: list[tuple[str, str]]) -> list[tuple[str, str]]:
            return _ground_bowen_refs(refs, gate_text, logger)

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
                parsed_refs, gate_text, formatted_filename, logger
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
    model: str | None = None,
    logger=None,
) -> bool:
    """Run Bowen and emphasis extraction together using one cached transcript context."""
    model = model or config.settings.DEFAULT_MODEL  # N3: resolved per call, not at import
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
    model: str | None = None,
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
    model = model or config.settings.DEFAULT_MODEL  # N3: resolved per call, not at import
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
        _save_summary(topics_output, formatted_filename, "topics", logger=logger)
        return True
    except Exception as e:
        logger.error("Error generating topics: %s", e, exc_info=True)
        return False


def generate_structured_summary(
    base_name: str,
    summary_target_word_count: int = None,
    logger=None,
    transcript_system_message=None,
    model: str | None = None,
) -> bool:
    """Generate a structured summary, judge its faithfulness and regenerate with
    the rejected claims as feedback, up to config.GENERATION_FAITHFULNESS_ATTEMPTS
    (RF.J). The model defaults to the main model (settings.DEFAULT_MODEL).

    Tests: tests/test_run_fixes_rf.py::test_rfj2_summary_regenerates_with_feedback
    """
    if logger is None:
        logger = setup_logging("generate_structured_summary")
    model = model or config.settings.DEFAULT_MODEL

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
        client = get_anthropic_client()
        output_path = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_SUMMARY_GEN}"
        )

        def _write(text):
            output_path.write_text(text, encoding="utf-8")

        lo, hi = config.summary_word_bounds(summary_input.target_word_count)
        def _generate(feedback):
            text = summary_pipeline.generate_summary(
                summary_input, client, model=model, system=transcript_system_message,
                feedback_claims=feedback)
            _note_length("summary", text, lo, hi, logger)
            return text

        ok = _generate_until_faithful(
            "summary", base_name, config.SUFFIX_SUMMARY_GEN, logger, _generate, _write,
            revise=lambda draft, claims: _revise_flagged(
                "summary", draft, claims, model=model, system=transcript_system_message,
                logger=logger, min_words=lo, max_words=hi, word_limits="soft"),
            guard=_coverage_guard(summary_input),
        )
        logger.info("Generated summary saved to %s", output_path)
        return ok
    except Exception as e:
        logger.error("Error generating structured summary: %s",
                     e, exc_info=True)
        return False


def _warn_not_quite_right(faith, what: str, logger) -> None:
    """Name the claims the severity step judged NOT QUITE RIGHT. They pass and are not
    revised (decision JS0.d), but they are listed in full, never dropped (P2).

    Spec:  docs/plan_judge_severity_2026-10-19.md#JS2.c
    Tests: tests/test_judge_severity_js.py::test_js2c_precheck_ignores_nqr
    """
    import release_gate as rg
    rg.log_not_quite_right(faith, what, logger)


def _faithfulness_precheck(base_name: str, suffix: str, logger=None):
    """Run the release gate's faithfulness AND entity-grounding checks on ONE
    artifact (``suffix``), as the abstract precheck does (both block at publish).

    Returns ("pass", []), ("fail", issues), ("unavailable", []) when the judge is
    off or errored (the gate then verifies at publish), or ("missing", []) when
    the artifact is not where the gate will look (a path bug, never a pass).
    ("partial", issues) when a check errored but the other found issues: the draft
    fails, but its count is not a full one, so it never beats a judged draft as the
    best draft (SC2 review).

    Claims the severity step judged NOT QUITE RIGHT are not issues: they are logged
    as a warning and the draft passes (JS2.c).

    Each issue is a ``flagged_removal.Flag``: the text fed back to the reviser, with
    the judge's label and reason, or the rejected name, for the removal step (RM2.h).

    Spec:  docs/plan_run_fixes_2026-10-09.md#RF.J.2,
           docs/plan_summary_closing_2026-10-18.md#SC2,
           docs/plan_judge_severity_2026-10-19.md#JS2.c,
           docs/plan_remove_flagged_2026-10-19.md#RM2.h
    Tests: tests/test_summary_closing_sc.py::test_sc2e_judge_error_with_names_is_partial,
           tests/test_judge_severity_js.py::test_js2c_precheck_ignores_nqr,
           tests/test_remove_flagged_rm.py::test_rm2h_record_has_judge_rationale
    """
    import release_gate as rg
    if not (config.PROJECTS_DIR / base_name / f"{base_name}{suffix}").exists():
        return "missing", []
    entity = rg.check_entity_grounding(base_name, logger, suffixes=[suffix])
    issues = _name_flags(entity)
    if not getattr(config, "FAITHFULNESS_JUDGE_ENABLED", False):
        # A disabled judge returns PASS ("judge disabled"); that is not a verdict.
        return ("fail", issues) if issues else ("unavailable", [])
    faith = rg.check_faithfulness(base_name, logger, suffixes=[suffix])
    _warn_not_quite_right(faith, suffix.strip(" -").removesuffix(".md"), logger)
    issues.extend(_claim_flags(faith))
    errored = rg.Status.ERROR in (faith.status, entity.status)
    if issues:
        return ("partial" if errored else "fail"), issues
    if errored:
        return "unavailable", []
    return "pass", []


def _name_flags(entity) -> list:
    """The entity check's rejected names as precheck issues (RM2.h)."""
    return [flagged_removal.Flag(f"the name '{n}' does not appear in the source",
                                 kind="name", name=n)
            for item in (entity.items or []) for n in item.get("names", [])]


def _claim_flags(faith) -> list:
    """The faithfulness check's flagged claims as precheck issues, each with the
    judge's record (label, reason, evidence) when the verdict has one (RM2.h)."""
    out = []
    for item in (faith.items or []):
        records = {r.get("claim"): r for r in item.get("wrong", []) if isinstance(r, dict)}
        out.extend(flagged_removal.Flag(c, record=records.get(c))
                   for c in item.get("unfaithful", []))
    return out


def _blog_precheck(base_name: str, suffix: str, logger=None):
    """Generation-time blog check: the gate's two-stage blog test (RF.N.1).
    A judge error with name hits is "partial", as in ``_faithfulness_precheck``."""
    import release_gate as rg
    status, ungrounded, _detail = rg.blog_ungrounded_claims(base_name, logger)
    if status == "missing":
        return "missing", []
    if status == "error":
        # Only name hits are known to be wrong; unassessed claims are not fed back.
        return ("partial", ungrounded) if ungrounded else ("unavailable", [])
    return ("fail", ungrounded) if status == "warn" else ("pass", [])


def _revise_reply_check(draft: str):
    """A ``check_reply`` for a revision of ``draft``: the reply must be the text, not
    a comment on it (no opening line from config.REVISE_PREAMBLE_STARTS the draft did
    not have), must not repeat the revise instructions, and, when the draft opens with
    front matter (``---`` or a fenced yaml block), must open with front matter the
    claim extractor still recognizes. Run 9: after a revision the overview's metadata
    ("target_audience: ...") was judged as a claim, so the block no longer counted as
    front matter. A changed title or a different front-matter form is allowed: a
    flagged title must be fixable (RS.6 review)."""
    from abstract_validation import _strip_fenced_block, _strip_front_matter
    template = _load_summary_prompt(config.PROMPT_REVISE_FLAGGED_FILENAME)
    instructions = [line.strip() for line in template.split("\n---\n")[0].splitlines()
                    if len(line.strip()) >= 40 and "{{" not in line]
    first = next((ln.strip() for ln in draft.splitlines() if ln.strip()), "")

    def _comment(line: str) -> bool:
        return line.lower().startswith(config.REVISE_PREAMBLE_STARTS)

    def _opens_with_metadata(text: str) -> bool:
        whole = text.strip()
        return _strip_fenced_block(_strip_front_matter(whole)) != whole

    draft_has_metadata = _opens_with_metadata(draft)

    def check(text: str) -> None:
        head = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        if any(line in text for line in instructions):
            raise ValueError("the revision repeats the revise instructions")
        if _comment(head) and not _comment(first):
            raise ValueError(f"the revision starts with a comment: {head[:60]!r}")
        if draft_has_metadata and not _opens_with_metadata(text):
            raise ValueError("the revision no longer opens with the draft's front matter")
    return check


def _revise_flagged(what: str, draft: str, claims: list, *, model: str, system,
                    logger, **limits) -> str:
    """Ask the model to change only the sentences of ``draft`` that make the flagged
    ``claims`` (say what the transcript supports, or drop the sentence) and keep the
    rest word for word. ``system`` carries the cached transcript; ``limits`` are the
    artifact's length settings (min_words, max_words, word_limits, min_length).

    Purpose: A retry fixes the flagged sentences instead of writing a new draft
             with new problems (run 8, Why Families overview).
    Spec:    docs/plan_run_safe_2026-10-14.md#RS.6
    Tests:   tests/test_run_safe_rs.py::test_rs6b_revise_prompt_has_draft_claims_and_keep_rule
    """
    template = _load_summary_prompt(config.PROMPT_REVISE_FLAGGED_FILENAME)
    # The draft goes in last, so nothing in it is read as a placeholder.
    prompt = (template.replace("{{artifact}}", what)
              .replace("{{claims}}", "\n".join(f"- {c}" for c in claims))
              .replace("{{draft}}", draft))
    return _generate_summary_with_claude(prompt, model, config.TEMP_BALANCED, logger,
                                         system=system,
                                         check_reply=_revise_reply_check(draft), **limits)


def _note_length(what: str, text: str, min_words: int, max_words: int, logger) -> None:
    """Say in the stage log when a kept draft is outside its word range. The soft
    limit's own warning goes to the pipeline module's logger, which the GUI does not
    show (RS.1 review)."""
    words = len(text.split())
    if (min_words and words < min_words) or (max_words and words > max_words):
        wanted = (f"{min_words}-{max_words}" if min_words and max_words
                  else f"at least {min_words}" if min_words else f"at most {max_words}")
        logger.warning("%s is %d words (wanted %s); kept, as the closest of the tries.",
                       what.capitalize(), words, wanted)


def _entity_blocks_after_retries(base_name: str, suffix: str, logger=None):
    """The gate's entity check on a kept draft, when it would block publication (a
    name not in the source, or the check could not run), else None. Faithfulness
    flags never block (user decision 2026-10-19), but the entity check still does, so
    a kept draft with a rejected name still fails its stage.

    Spec:  docs/plan_warn_only_2026-10-19.md#WO4
    Tests: tests/test_faithfulness_warn_only_wo.py::test_wo4_summary_kept_with_flags_stage_succeeds,
           tests/test_faithfulness_warn_only_wo.py::test_wo4_summary_kept_with_name_stage_fails
    """
    import release_gate as rg
    entity = rg.check_entity_grounding(base_name, logger, suffixes=[suffix])
    return entity if rg._is_blocking(entity) else None


def _coverage_guard(summary_input):
    """A ``guard`` for removal from the summary: the required coverage items
    (``summary_validation.generate_coverage_items``) a removal would leave at low
    keyword confidence. ``summary_coverage`` blocks publication, so a removed sentence
    that was in fact fine must not make it fail (RM2.e). An item already at low
    confidence before the removal is decided at the gate by the LLM check, which may
    rest on any sentence; it is returned too, so no removal is made (cold sweep
    2026-10-19, correctness #3 / learning-qa #2).

    Spec:  docs/plan_remove_flagged_2026-10-19.md#RM2.e
    Tests: tests/test_remove_flagged_rm.py::test_rm2e_only_mention_of_required_item_kept
    """
    import summary_validation as sv
    items = []

    def guard(before: str, after: str) -> list:
        # Built on first use, inside the removal step: an error here keeps the draft
        # as it is instead of failing the summary stage.
        if not items:
            items.extend(i for i in sv.generate_coverage_items(summary_input) if i.required)
        return [(i.label, i.keywords) for i in items
                if sv.check_keyword_coverage(after, i)[1] == "low"]
    return guard


def _remove_still_flagged(what: str, base_name: str, suffix: str, text: str, issues: list,
                          logger, write, guard=None) -> tuple:
    """Remove from the kept draft the sentences still flagged after the last attempt,
    record them, save the result, and log each one. Returns (text, number of flagged
    items not removed). Nothing changes when removal is off for ``what``, when nothing
    can be removed, when the record cannot be written, when removal itself fails, or
    when the result cannot be saved: removal is never a reason for a stage to fail.
    When flags were left in, the record lists them, so the end-of-run list shows them.

    Purpose: Take a flagged sentence out instead of publishing it with a warning.
    Spec:    docs/plan_remove_flagged_2026-10-19.md#RM2.a, #RM2.b, #RM3.b, #RM3.c
    Tests:   tests/test_remove_flagged_rm.py::test_rm2a_summary_last_attempt_sentence_removed_and_saved,
             tests/test_remove_flagged_rm.py::test_rm3b_record_write_fails_nothing_removed,
             tests/test_remove_flagged_rm.py::test_rm3c_refused_removal_recorded_and_listed,
             tests/test_remove_flagged_rm.py::test_rm3b_artifact_save_fails_stage_goes_on
    """
    if (not issues or not config.FAITHFULNESS_REMOVE_FLAGGED
            or what not in config.FAITHFULNESS_REMOVE_ARTIFACTS):
        return text, len(issues)
    label = what.capitalize()

    def record_kept(kept):
        # Nothing removed: the record still lists the flags left in, so the end-of-run
        # list does not say "none" when removal was refused (learning-qa F3).
        try:
            removal_record.write_entry(base_name, what, suffix, draft_before=text,
                                       final_text=text, removed=[], kept=kept, logger=logger)
        except OSError as e:
            logger.warning("%s: the removed-sentences record could not be written (%s).",
                           label, e)

    try:
        new_text, removed, kept = flagged_removal.remove_flagged_sentences(
            text, issues, max_share=config.FAITHFULNESS_REMOVE_MAX_SHARE, guard=guard)
    except Exception as e:  # noqa: BLE001 — a removal bug must not fail the stage
        logger.error("%s: removing the flagged sentences failed (%s); kept the draft as it "
                     "is.", label, e, exc_info=True)
        record_kept([flagged_removal.Kept(f, f"removal failed: {e}")
                     for f in dict.fromkeys(issues)])
        return text, len(issues)
    not_removed = "; ".join(f"{str(k.claim)[:120]!r} ({k.reason})" for k in kept)
    if not removed:
        logger.warning("%s: none of the %d flagged item(s) could be removed: %s",
                       label, len(issues), not_removed)
        record_kept(kept)
        return text, len(issues)
    try:
        path = removal_record.write_entry(base_name, what, suffix, draft_before=text,
                                          final_text=new_text, removed=removed, kept=kept,
                                          logger=logger)
    except OSError as e:
        logger.warning("%s: the removed-sentences record could not be written (%s); "
                       "nothing was removed.", label, e)
        return text, len(issues)
    try:
        write(new_text)
    except Exception as e:  # noqa: BLE001 — a failed save must not fail the stage
        logger.warning("%s: saving the draft with the sentences removed failed (%s); the "
                       "removal was not applied.", label, e)
        try:
            write(text)
        except Exception as e2:
            # The file may now hold neither draft: that fails the stage like any
            # other failed save of the artifact (cold sweep, learning-qa #3).
            logger.error("%s: the kept draft could not be saved again either (%s); the "
                         "file on disk may be incomplete.", label, e2)
            raise
        # The flags are still in the saved draft: the list must say so (F3).
        record_kept([flagged_removal.Kept(f, f"saving the cleaned draft failed: {e}")
                     for f in dict.fromkeys(issues)])
        return text, len(issues)
    left = len({str(k.claim) for k in kept})
    logger.warning("⚠️ %s: removed %d sentence(s) still flagged after the last attempt; "
                   "%d of %d flagged item(s) left in. Record: %s. Removed: %s",
                   label, len(removed), left, len(issues), path.name,
                   "; ".join(repr(r.sentence) for r in removed))
    if kept:
        logger.warning("%s: not removed: %s", label, not_removed)
    return new_text, left


def _all_removed_message(label: str, attempts: int, flags: list, judge_errored: bool,
                         cause: str = "") -> str:
    """The warning when nothing flagged is left after removal. It says which checks the
    removed flags came from: with names only, no claim was removed, and when the judge
    errored ("partial") the draft's faithfulness was not checked at all.

    With the faithfulness judge off (config.FAITHFULNESS_JUDGE_ENABLED false), it says
    no claim was checked, not that none was flagged (RM2.a.1).

    Purpose: Never report "every flagged sentence removed" for a check that did not run.
    Spec:    docs/plan_remove_flagged_2026-10-19.md#RM2.a;
             docs/plan_removal_open_items_2026-10-20.md#RM2.a.1
    Tests:   tests/test_remove_flagged_rm.py::test_rm2_partial_check_message_says_not_checked,
             tests/test_remove_flagged_rm.py::test_rm2_names_only_message,
             tests/test_remove_flagged_rm.py::test_rm2a1_names_only_message_says_judge_off
    """
    lead = f"⚠️ {label}: " + (f"{cause}; " if cause else "")
    names_only = bool(flags) and all(getattr(f, "kind", "claim") == "name" for f in flags)
    if names_only and judge_errored:
        return (lead + "the sentences with the flagged names were removed, but the "
                "faithfulness check could not run on this draft; the release gate will "
                "check it at publish. Removals are listed at the end of the run.")
    if names_only and not config.FAITHFULNESS_JUDGE_ENABLED:
        return (lead + "the sentences with the flagged names were removed; the "
                "faithfulness judge is off, so no claim was checked. Removals are listed "
                "at the end of the run.")
    if names_only:
        return (lead + "the sentences with the flagged names were removed; no claim was "
                "flagged. Removals are listed at the end of the run.")
    return (lead + f"every sentence still flagged after {attempts} attempt(s) was removed; "
            "they are listed at the end of the run.")


def _generate_until_faithful(what: str, base_name: str, suffix: str, logger,
                             generate, write, precheck=None, advisory=False,
                             revise=None, guard=None) -> bool:
    """Generate ``what``, save it, judge it; on rejected claims try again, up to
    config.GENERATION_FAITHFULNESS_ATTEMPTS. With ``revise(draft, claims)`` a retry
    fixes the flagged sentences of the previous draft (RS.6); without it, it
    regenerates with the claims as feedback. If every attempt fails, keep the draft
    with the fewest rejected claims (on a tie the later one, which has had more of its
    flagged sentences fixed, SC2) and warn: faithfulness flags never fail the stage
    (WO4). The sentences still flagged in the kept draft are then removed when
    config.FAITHFULNESS_REMOVE_ARTIFACTS names ``what`` (RM2; ``guard`` protects the
    summary's coverage). It returns False only when the kept draft has a name the
    gate's entity check rejects, which still blocks publication.

    Purpose: Catch unfaithful summary/blog claims at generation, not at publish.
    Spec:    docs/plan_run_fixes_2026-10-09.md#RF.J.2,
             docs/plan_run_safe_2026-10-14.md#RS.6,
             docs/plan_summary_closing_2026-10-18.md#SC2, #SC3
    Tests:   tests/test_run_fixes_rf.py::test_rfj2_summary_all_fail_keeps_best_and_warns,
             tests/test_faithfulness_warn_only_wo.py::test_wo4_summary_kept_with_flags_stage_succeeds,
             tests/test_run_safe_rs.py::test_rs6a_second_try_revises_previous_draft,
             tests/test_summary_closing_sc.py::test_sc2a_tie_keeps_the_later_draft,
             tests/test_summary_closing_sc.py::test_sc3a_last_try_does_not_say_it_will_revise,
             tests/test_remove_flagged_rm.py::test_rm2a_summary_last_attempt_sentence_removed_and_saved
    """
    attempts = max(1, int(config.GENERATION_FAITHFULNESS_ATTEMPTS))
    feedback, best_text, best_rank, last_text = None, None, None, None
    best_issues = []
    for attempt in range(1, attempts + 1):
        try:
            if revise is not None and feedback and last_text is not None:
                text = revise(last_text, feedback)
            else:
                text = generate(feedback)
        except Exception as e:  # e.g. the API failed on every retry (SL review)
            if best_text is None:
                raise
            logger.error("%s attempt %d/%d failed (%s); keeping the best earlier draft.",
                         what.capitalize(), attempt, attempts, e)
            break
        if last_text is None:
            # A new draft replaces the file, so an earlier removal no longer applies (RM3.c).
            removal_record.clear_entry(base_name, what, logger)
        write(text)
        last_text = text
        # A draft that echoes the correction instructions or the rejected claims
        # is not accepted, whatever the judge says (sweep, P19).
        echoed = [c for c in (feedback or []) if c and c in text]
        # "CORRECTION REQUIRED" is the regenerate fallback's instruction (no revise).
        unjudged = bool(feedback and ("CORRECTION REQUIRED" in text or echoed))
        if unjudged:
            status, issues = "fail", echoed or ["the draft repeats the correction instructions"]
        else:
            status, issues = (precheck or _faithfulness_precheck)(base_name, suffix, logger)
        if status == "missing":
            logger.error("%s was not saved where the release gate reads it (%s%s); "
                         "cannot verify it.", what.capitalize(), base_name, suffix)
            return False
        if status == "pass":
            logger.info("✓ %s passed faithfulness on attempt %d/%d.",
                        what.capitalize(), attempt, attempts)
            return True
        if status == "unavailable":
            logger.warning("Faithfulness check unavailable at generation; keeping the "
                           "%s — the release gate will verify it at publish.", what)
            return True
        # Only a judged draft can be kept: an echo-rejected one was never judged, so
        # its count is not its real one (RS.6 review). A "partial" one (a check
        # errored) ranks after every fully judged draft. On a tie the later draft
        # wins (SC2).
        rank = (status == "partial", len(issues))
        if not unjudged and (best_rank is None or rank <= best_rank):
            best_text, best_rank, best_issues = text, rank, list(issues)
        feedback = issues
        logger.warning("%s attempt %d/%d not faithful (%d claim(s)); %s. Claims: %s",
                       what.capitalize(), attempt, attempts, len(issues),
                       "no attempts left" if attempt == attempts  # SC3
                       else "revising the flagged sentences" if revise is not None
                       else "regenerating with corrective feedback",
                       "; ".join(issues))  # JS2.d: every claim, in full
    write(best_text)
    best_count = best_rank[1]
    if advisory:
        # RF.N: a warning, not a failure — the run continues.
        logger.warning("⚠️ %s still has %d claim(s) not grounded in the source after %d "
                       "attempt(s); kept the best draft. This is a warning only — review "
                       "the claims above before publishing it.", what.capitalize(),
                       best_count, attempts)
        return True
    best_text, best_count = _remove_still_flagged(what, base_name, suffix, best_text,
                                                  best_issues, logger, write, guard)
    blocking = _entity_blocks_after_retries(base_name, suffix, logger)
    if blocking is not None:
        logger.error("⚠️ Could not produce a %s free of rejected names after %d attempt(s); "
                     "kept the best draft (%d flagged item(s)). The release gate will BLOCK "
                     "publication until it is regenerated or edited: %s",
                     what, attempts, best_count, blocking.detail)
        return False
    if best_count == 0:
        logger.warning("%s", _all_removed_message(what.capitalize(), attempts, best_issues,
                                                  judge_errored=best_rank[0]))
        return True
    logger.warning("⚠️ %s still has %d flagged claim(s) after %d attempt(s); kept the best "
                   "draft. Faithfulness flags are warnings: the run goes on, and the release "
                   "gate lists them with the %% score.", what.capitalize(), best_count, attempts)
    return True


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
    # multi-artifact faithfulness sweep stays at the publish gate. The entity check is
    # scoped the same way: a name in the summary is not the abstract's to remove (WO4).
    faith = rg.check_faithfulness(base_name, logger, suffixes=[config.SUFFIX_ABSTRACT_GEN])
    _warn_not_quite_right(faith, "abstract", logger)  # JS2.c
    entity = rg.check_entity_grounding(base_name, logger, suffixes=[config.SUFFIX_ABSTRACT_GEN])
    if rg.Status.ERROR in (faith.status, entity.status):
        return "unavailable", []
    # Faithfulness flags arrive as a WARN since WO2; the flagged claims are in items.
    issues = _claim_flags(faith)
    if entity.status is rg.Status.FAIL:
        issues.extend(_name_flags(entity))
    if issues:
        return "fail", issues
    return "pass", []


def generate_structured_abstract(
    base_name: str, logger=None, transcript_system_message=None, model: str | None = None
) -> bool:
    """
    Generate an abstract using the structured pipeline.
    Note: Uses Sonnet for detailed content generation (was AUX_MODEL/Haiku).

    Purpose: Generate the abstract, revising flagged sentences until it passes the
             gate's faithfulness and name checks; if no try passes, keep the draft
             with the fewest issues (on a tie the later one), remove the sentences
             still flagged (RM2.b), and fail only on a rejected name (WO4).
    Spec:    docs/plan_summary_closing_2026-10-18.md#SC2, #SC3,
             docs/plan_remove_flagged_2026-10-19.md#RM2.b
    Tests:   tests/test_abstract_faithful_retry.py::test_sc2d_abstract_tie_keeps_the_later_draft,
             tests/test_abstract_faithful_retry.py::test_sc3b_abstract_last_try_wording,
             tests/test_remove_flagged_rm.py::test_rm2b_abstract_sentence_removed_and_saved
    """
    model = model or config.settings.AUX_MODEL  # N3: resolved per call, not at import
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

        client = get_anthropic_client()
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
        best_text, best_issue_count, last_text = None, None, None
        best_issues = []
        generation_error = None
        for attempt in range(1, max_attempts + 1):
            logger.info("Generating abstract via API (attempt %d/%d)...", attempt, max_attempts)
            try:
                if feedback and last_text is not None:
                    # Fix the flagged sentences of the last draft, keep the rest (RS.6).
                    abstract_text = _revise_flagged(
                        "abstract", last_text, feedback, model=model,
                        system=transcript_system_message, logger=logger, min_length=150,
                        max_words=config.ABSTRACT_HARD_MAX_WORDS - 1,
                        word_limits="soft").strip()
                else:
                    abstract_text = abstract_pipeline.generate_abstract(
                        abstract_input, client, model=model,
                        system=transcript_system_message, feedback_claims=feedback,
                    )
                    _note_length("abstract", abstract_text, 0,
                                 config.ABSTRACT_HARD_MAX_WORDS - 1, logger)
            except Exception as e:  # noqa: BLE001
                # A later attempt that fails outright (e.g. every retry over the word
                # limit, AQ) keeps the best earlier draft, as the summary does (SL2).
                # On the first attempt there is no draft: the stage fails.
                if best_text is None:
                    raise
                logger.error("Abstract attempt %d/%d failed: %s", attempt, max_attempts, e)
                generation_error = (attempt, e)
                break
            if last_text is None:
                removal_record.clear_entry(base_name, "abstract", logger)  # RM3.c
            output_path.write_text(abstract_text, encoding="utf-8")
            last_text = abstract_text

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
            # status == "fail": remember the least-bad draft (on a tie the later one,
            # SC2), feed the issues back.
            if best_text is None or len(issues) <= best_issue_count:
                best_text, best_issue_count, best_issues = abstract_text, len(issues), list(issues)
            feedback = issues
            logger.warning("Abstract attempt %d/%d not faithful (%d issue(s)); %s. "
                           "Issues: %s", attempt, max_attempts, len(issues),
                           "no attempts left" if attempt == max_attempts  # SC3
                           else "revising the flagged sentences",
                           "; ".join(issues))  # JS2.d: every claim, in full

        # All attempts failed — keep the least-bad draft; honest, loud status.
        if best_text is not None:
            output_path.write_text(best_text, encoding="utf-8")
            # RM2.b: the sentences still flagged are removed from the kept draft.
            best_text, best_issue_count = _remove_still_flagged(
                "abstract", base_name, config.SUFFIX_ABSTRACT_GEN, best_text, best_issues,
                logger, lambda t: output_path.write_text(t, encoding="utf-8"))
        if generation_error:
            attempt, e = generation_error
            cause = f"attempt {attempt}/{max_attempts} could not be generated ({e})"
        else:
            cause = f"no fully faithful abstract after {max_attempts} attempt(s)"
        # WO4: faithfulness flags warn and the run goes on; a name the gate's entity
        # check rejects still blocks, so that case still fails the stage (plan R11).
        blocking = _entity_blocks_after_retries(base_name, config.SUFFIX_ABSTRACT_GEN, logger)
        if blocking is not None:
            logger.error("⚠️ Abstract: %s; kept the best draft (%s unresolved issue(s)). "
                         "The release gate will BLOCK publication until it is regenerated "
                         "or edited: %s", cause, best_issue_count, blocking.detail)
            return False
        if best_issue_count == 0:
            logger.warning("%s", _all_removed_message("Abstract", max_attempts, best_issues,
                                                      judge_errored=False, cause=cause))
            return True
        logger.warning("⚠️ Abstract: %s; kept the best draft (%s flagged claim(s)). "
                       "Faithfulness flags are warnings: the run goes on, and the release "
                       "gate lists them with the %% score.", cause, best_issue_count)
        return True
    except Exception as e:
        logger.error("Error generating structured abstract: %s",
                     e, exc_info=True)
        return False


# Shared with release_gate's blog check (RF.N); defined in transcript_utils.
_extract_lens_titles = extract_lens_titles


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
            "parse_error": True,
        }
    return parsed


def _select_blog_lens(
    model: str,
    logger,
    transcript_system_message,
    structural_themes: str,
    interpretive_themes: str,
    lenses: str,
) -> tuple:
    """Validate the on-disk themes/lenses and return a top lens that is grounded
    in ``lenses``, retrying up to ``config.THEME_LENS_VALIDATION_ATTEMPTS`` times.

    Used by the Blog-only stage, where themes and lenses come from an earlier Core
    run and are not regenerated here. Returns ``(top_lens, reasons)``: the lens
    (``{}`` if none qualified) and one reason per failed attempt.

    Purpose: Give the Blog-only stage the same retry and lens check as Core.
    Spec:    docs/plan_run_fixes_2026-10-09.md#RF.C.2
    Tests:   tests/test_run_fixes_rf.py::test_rfc2_blog_retries_until_grounded_lens
    """
    attempts = config.THEME_LENS_VALIDATION_ATTEMPTS
    reasons = []
    for attempt in range(attempts):
        validation = _validate_themes_and_lenses(
            model, logger, transcript_system_message,
            structural_themes, interpretive_themes, lenses,
        )
        top_lens = validation.get("top_lens", {}) or {}
        denied = [name for key, name in (
            ("structural_themes_valid", "structural"),
            ("interpretive_themes_valid", "interpretive"))
            if not validation.get(key)]
        if validation.get("parse_error"):
            reason = "validator output was not JSON"
        elif denied:
            # Core accepts a lens only with both theme sets valid; so does this.
            reason = f"validator denied the {' and '.join(denied)} themes on disk (re-run Core)"
        elif not top_lens:
            reason = "validator returned no top lens"
        elif not _top_lens_is_grounded(top_lens, lenses):
            reason = (f"top lens '{top_lens.get('title', '')}' is not among the "
                      "generated lenses")
        else:
            logger.info("✓ Top-ranked lens validated: %s", top_lens.get("title", ""))
            return top_lens, reasons
        reasons.append(f"attempt {attempt + 1}/{attempts}: {reason}")
        logger.warning("Blog lens not validated (%s).", reasons[-1])
    return {}, reasons


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
        lens_reasons: list = []
        overview_failed = False
        abstract_output = ""
        structural_output = ""
        interpretive_output = ""
        topics_output = ""
        key_terms_output = ""
        lenses_output = ""

        if not skip_extracts_summary:
            # ST: the theme stages return checked JSON; the markdown is rendered from it.
            # Both sets are saved only when both were generated: interpretive themes
            # name structural themes, so a new structural file must not sit next to
            # an earlier run's interpretive file (ST review).
            logger.info("PART 1: Generating Structural Themes...")
            structural_obj, structural_output = _generate_structured_themes(
                "structural", model, logger, transcript_system_message)

            logger.info("PART 2: Generating Interpretive Themes...")
            interpretive_obj, interpretive_output = _generate_structured_themes(
                "interpretive", model, logger, transcript_system_message,
                structural=structural_obj)
            _save_themes(structural_obj, structural_output, formatted_filename, logger)
            _save_themes(interpretive_obj, interpretive_output, formatted_filename, logger)

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
            _save_summary(topics_output, formatted_filename, "topics", logger=logger)

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
            _save_summary(key_terms_output, formatted_filename, "key-terms", logger=logger)

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
            client = get_anthropic_client()
            # An intermediate draft (the Gen Abstract stage writes the published one,
            # which is length-checked), so no hard limit: a long draft must not fail
            # Core after the themes, topics and key terms are paid for (AQ review).
            abstract_output = abstract_pipeline.generate_abstract(
                abstract_input, client, model=model, system=transcript_system_message,
                max_words=0,
            )
            _save_summary(abstract_output, formatted_filename, "abstract-initial", logger=logger)

            if not skip_emphasis:
                logger.info("\n--- PART 6: Extracting Emphasis Items ---")
                _run_emphasis_step(formatted_filename, model, logger, transcript_system_message)
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
            max_attempts = config.THEME_LENS_VALIDATION_ATTEMPTS
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
                    structural_obj, structural_output = _generate_structured_themes(
                        "structural", model, logger, transcript_system_message)
                if not interpretive_valid or not structural_valid:
                    # ST.5: interpretive themes name structural themes by number, so new
                    # structural themes need new interpretive themes as well.
                    logger.warning(
                        "Interpretive themes denied by validator; regenerating..."
                        if not interpretive_valid else
                        "Regenerating interpretive themes for the new structural themes...")
                    interpretive_obj, interpretive_output = _generate_structured_themes(
                        "interpretive", model, logger, transcript_system_message,
                        structural=structural_obj)
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

            _save_themes(structural_obj, structural_output, formatted_filename, logger)
            _save_themes(interpretive_obj, interpretive_output, formatted_filename, logger)
            _save_summary(lenses_output, formatted_filename, "lenses-ranked", logger=logger)
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
            _report_invalid_sections(logger, {
                "Structural Themes": structural_output,
                "Interpretive Themes": interpretive_output,
                "Topics": topics_output,
                "Key Terms": key_terms_output,
            })

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
                _save_summary(lenses_output, formatted_filename, "lenses-ranked", logger=logger)

            if not skip_blog:
                missing = [name for name, text in (
                    ("structural themes", structural_output),
                    ("interpretive themes", interpretive_output),
                    ("ranked lenses", lenses_output)) if not text]
                if missing:
                    lens_reasons = [f"missing on disk: {', '.join(missing)} (run Core)"]
                else:
                    top_lens, lens_reasons = _select_blog_lens(
                        model,
                        logger,
                        transcript_system_message,
                        structural_output,
                        interpretive_output,
                        lenses_output,
                    )

        if not skip_blog:
            if not top_lens:
                logger.error(
                    "No validated top-ranked lens available; blog generation aborted "
                    "by policy. %s", "; ".join(lens_reasons)
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
            blog_paths = []

            def _write_blog(text):
                blog_paths.append(_save_summary(text, formatted_filename, "blog", logger=logger))

            # RF.N: the blog is judged as interpretation and only ever warns.
            blog_saved_ok = _generate_until_faithful(
                "blog", metadata["stem"], config.SUFFIX_BLOG, logger,
                lambda feedback: _generate_summary_with_claude(
                    prompt + (summary_pipeline.correction_feedback("blog post", feedback)
                              if feedback else ""),
                    model,
                    config.TEMP_BALANCED,
                    logger,
                    min_length=config.MIN_BLOG_CHARS,
                    system=transcript_system_message,
                ),
                _write_blog,
                precheck=_blog_precheck,
                advisory=True,
                revise=lambda draft, claims: _revise_flagged(
                    "blog post", draft, claims, model=model,
                    system=transcript_system_message, logger=logger,
                    min_length=config.MIN_BLOG_CHARS),
            )
            if blog_saved_ok:
                logger.info("✓ Blog post saved to: %s", blog_paths[-1])
            else:
                return False  # not saved where the gate reads it (logged above)
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
                **_for_prompt(dict(
                    focus_keyword=focus_keyword,
                    target_audience=target_audience,
                    target_word_count=config.OVERVIEW_MIN_WORDS,
                    title=metadata.get("title", ""),
                    presenter=metadata.get("presenter", metadata.get("author", "")),
                    date=metadata.get("date", ""),
                    abstract=abstract_output,
                    structural_themes=structural_output,  # closing notes left out (TP)
                    topics=topics_output,
                    key_terms=key_terms_output,
                )),
            )
            overview_paths = []

            def _write_overview(text):
                overview_paths.append(_save_summary(text, formatted_filename, "overview", logger=logger))

            # Same check-and-regenerate loop as the summary and blog (sweep, P5).
            overview_ok = _generate_until_faithful(
                "overview", metadata["stem"], config.SUFFIX_OVERVIEW, logger,
                lambda feedback: _generate_summary_with_claude(
                    prompt + (summary_pipeline.correction_feedback("overview post", feedback)
                              if feedback else ""),
                    model,
                    config.TEMP_BALANCED,
                    logger,
                    min_words=config.OVERVIEW_MIN_WORDS,
                    word_limits="soft",  # a short overview is kept with a warning (RS.1)
                    system=transcript_system_message,
                ),
                _write_overview,
                revise=lambda draft, claims: _revise_flagged(
                    "overview post", draft, claims, model=model,
                    system=transcript_system_message, logger=logger,
                    min_words=config.OVERVIEW_MIN_WORDS, word_limits="soft"),
            )
            logger.info("✓ Overview post saved to: %s", overview_paths[-1])
            if not overview_ok:
                overview_failed = True  # reported at the end
        else:
            logger.info("Overview generation skipped (skip_overview=True).")

        logger.info("✓ Transcript processing complete!")

        if not skip_extracts_summary:
            logger.info("VALIDATION: Checking Emphasis Items...")
            stem = metadata["stem"]
            formatted_path = (
                config.PROJECTS_DIR / stem / f"{stem}{config.SUFFIX_FORMATTED}"
            )
            if not formatted_path.exists():
                logger.error("VALIDATION: formatted transcript not found at %s — "
                             "extracted items cannot be validated.", formatted_path)
                return False
            # Validation results do not fail this stage (author decisions 2026-10-05 /
            # 2026-10-09): emphasis and topics block PUBLICATION through the release
            # gate (verbatim_quotes, topics_grounding); key terms are advisory. A
            # failure is reported here so it is visible during the run.
            failed_checks = []
            if not validate_emphasis_items(formatted_path, formatted_path, logger):
                failed_checks.append("emphasis quotes (blocks publication)")
            logger.info("VALIDATION: Checking Topics (lightweight)...")
            if not validate_topics_lightweight(formatted_path, stem, logger):
                failed_checks.append("topics (blocks publication)")
            logger.info("VALIDATION: Checking Key Terms...")
            if not validate_key_terms_fidelity(formatted_path, stem, logger):
                failed_checks.append("key terms (advisory)")
            if failed_checks:
                logger.warning("VALIDATION: %s did not pass — see the validation "
                               "reports.", ", ".join(failed_checks))

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
                message = summary_coverage_message(stem)  # as the release gate sees it
                if message:
                    logger.warning(message.removeprefix("⚠️ "))
            else:
                logger.error("Structured summary generation failed.")
                return False

        if overview_failed:
            logger.error("Overview did not pass faithfulness — see the warnings above.")
            return False
        return True

    except Exception as e:
        logger.error("An error occurred: %s", e, exc_info=True)
        return False
