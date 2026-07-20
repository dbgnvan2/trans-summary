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
    cap_max_tokens_for_model,
    count_header_verdicts,
    create_system_message_with_cache,
    extract_emphasis_items,
    extract_section,
    find_text_in_content,
    load_project_transcript,
    normalize_text,
    parse_filename_metadata,
    parse_scored_emphasis_output,
    setup_logging,
    strip_yaml_frontmatter,
    validate_input_file,
    warn_if_empty_parse,
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

    max_tokens = cap_max_tokens_for_model(
        model, config.MAX_TOKENS_HEADER_VALIDATION, logger=logger
    )

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
    try:
        stem = parse_filename_metadata(extracts_path.name)["stem"]
    except Exception:
        stem = extracts_path.stem
        for suffix in (
            config.SUFFIX_FORMATTED,
            config.SUFFIX_YAML,
            config.SUFFIX_EMPHASIS,
            config.SUFFIX_EMPHASIS_SCORED,
        ):
            clean_suffix = suffix.replace(".md", "")
            if stem.endswith(clean_suffix):
                stem = stem[: -len(clean_suffix)]
                break
    scored_file = extracts_path.parent / f"{stem}{config.SUFFIX_EMPHASIS_SCORED}"
    emphasis_file = extracts_path.parent / f"{stem}{config.SUFFIX_EMPHASIS}"

    if scored_file.exists():
        scored_content = strip_yaml_frontmatter(scored_file.read_text(encoding="utf-8"))
        scored_items = parse_scored_emphasis_output(scored_content)
        if scored_items:
            return [
                (f"{item.get('concept', 'Item')} ({item.get('score', 0)}%)", item["quote"])
                for item in scored_items
                if item.get("quote")
            ]

    source_file = emphasis_file if emphasis_file.exists() else extracts_path
    content = source_file.read_text(encoding="utf-8")
    content = strip_yaml_frontmatter(content)

    return extract_emphasis_items(content)


def _parse_key_terms_section(content: str) -> list[tuple[str, str]]:
    """Parse key terms from markdown content into (term, definition) tuples."""
    # The canonical key-terms artifact is a dedicated file; the model often
    # emits the terms directly as `### Term` blocks with NO top-level
    # "Key Terms" heading. Fall back to the whole content so those files still
    # validate instead of reporting "No key terms found".
    section = extract_section(content, "Key Terms") or content
    if not section:
        return []

    terms: list[tuple[str, str]] = []

    # Format 1: ### Term Name\nDefinition...
    header_pattern = r'(?:^|\n)###\s+([^\n]+)\s*\n+(.+?)(?=\n###|\n\*\*|\Z)'
    for name, raw_def in re.findall(header_pattern, section, re.DOTALL):
        term = name.strip()
        definition = raw_def.strip()
        if term and definition:
            terms.append((term, definition))

    # Format 2: **Term**: Definition
    bold_pattern = r'\*\*([^\*]+?)\*\*\s*[:\-]\s*(.+?)(?=\n\*\*|\n\n|$)'
    existing = {t.lower() for t, _ in terms}
    for name, raw_def in re.findall(bold_pattern, section, re.DOTALL):
        term = name.strip()
        if not term or term.lower() in existing:
            continue
        definition = re.sub(r'\s+', ' ', raw_def.strip())
        if definition:
            terms.append((term, definition))

    return terms


def _load_key_terms_for_validation(base_name: str) -> list[tuple[str, str]]:
    """Load key terms from canonical key-terms artifact."""
    project_dir = config.PROJECTS_DIR / base_name
    key_terms_file = project_dir / f"{base_name}{config.SUFFIX_KEY_TERMS}"

    if key_terms_file.exists():
        content = strip_yaml_frontmatter(key_terms_file.read_text(encoding="utf-8"))
        parsed = _parse_key_terms_section(content)
        if parsed:
            return parsed

    return []


def _best_local_grounding(definition: str, term: str, transcript: str) -> Optional[float]:
    """
    Local grounding of a definition: the best keyword overlap of the definition
    over transcript windows centred on each occurrence of the term (or an alias
    part). Returns None when the term is not found in the transcript at all.

    Global overlap with the whole transcript barely discriminates — almost any
    on-topic text scores high — so a definition that describes the WRONG concept
    still passed (verified on a real run: a swapped, transcript-vocabulary
    definition scored 0.87 globally and validated EXACT). Local grounding drops
    sharply for a swapped/off-topic definition because its keywords are not near
    where the term is actually discussed (valid >=0.54 vs swapped <=0.13 on the
    calibration run).
    """
    window = config.KEY_TERMS_LOCAL_WINDOW_WORDS
    parts = [
        p.strip()
        for p in re.split(r"[/()]|\bversus\b|\bvs\b|\band\b", term)
        if len(p.strip()) > 3
    ] or [term]
    # Normalise the WHOLE transcript once, then split — so a hyphenated/compound
    # occurrence ("self-differentiation") tokenises the same way as the term
    # ("self differentiation") and the contiguous match can find it. (Per-word
    # normalisation kept "self differentiation" as one element and never matched.)
    norm_tokens = normalize_text(transcript, aggressive=True).split()
    best: Optional[float] = None
    for part in parts:
        part_norm = normalize_text(part, aggressive=True).split()
        if not part_norm:
            continue
        span = len(part_norm)
        for i in range(len(norm_tokens) - span + 1):
            if norm_tokens[i:i + span] == part_norm:
                lo = max(0, i - window)
                hi = min(len(norm_tokens), i + span + window)
                g = _keyword_grounding_ratio(definition, " ".join(norm_tokens[lo:hi]))
                best = g if best is None else max(best, g)
    return best


def validate_key_terms_fidelity(
    formatted_file_path: Path, base_name: str, logger
) -> bool:
    """
    Validate key terms against transcript text and save a markdown report.
    Uses deterministic grounding checks (no API call).
    """
    transcript = strip_yaml_frontmatter(formatted_file_path.read_text(encoding="utf-8"))
    terms = _load_key_terms_for_validation(base_name)

    report_path = (
        config.PROJECTS_DIR
        / base_name
        / f"{base_name}{config.SUFFIX_KEY_TERMS_VAL}"
    )

    if not terms:
        report_path.write_text(
            "# Key Terms Validation\n\nNo key terms found to validate.\n",
            encoding="utf-8",
        )
        key_terms_file = (
            config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_KEY_TERMS}"
        )
        if not warn_if_empty_parse(logger, "key terms", 0, source_path=key_terms_file):
            logger.info("No key terms to validate (no key-terms artifact present).")
        return False

    exact = 0
    partial = 0
    weak = 0
    failed = 0
    lines = [
        "# Key Terms Validation",
        "",
        f"Validated terms: {len(terms)}",
        "",
        "| Term | Term Match | Definition Support | Def Locality | Result |",
        "|---|---:|---:|---:|---|",
    ]

    for term, definition in terms:
        # A term is often a slash-joined alias pair ("Symbiosis / Symbiotic
        # Relationship") that never appears verbatim as one string, though each
        # alias does. Ground on the best-matching alias part.
        term_parts = [p.strip() for p in re.split(r"\s*/\s*", term) if p.strip()] or [term]
        term_ratio = max(
            find_text_in_content(part, transcript, aggressive_normalization=True)[2]
            for part in term_parts
        )
        # The definition is the model's synthesized paraphrase, NOT a transcript
        # quote — so grounding is driven by the TERM appearing in the transcript,
        # and the definition is checked for TOPICAL support (keyword overlap),
        # never verbatim. Requiring a verbatim definition match failed 100% of
        # valid terms (a false-negative that this validator previously produced).
        def_support = _keyword_grounding_ratio(definition, transcript)
        # def_support alone is a gameable proxy: overlap with the WHOLE transcript
        # is high for almost any on-topic text, so a definition describing the
        # wrong concept still scored EXACT (P7). Also require LOCAL grounding —
        # overlap in the window around where the term actually appears.
        def_local = _best_local_grounding(definition, term, transcript)
        # Benefit of the doubt when the term can't be localised at all: term_ratio
        # (fuzzy) may ground a term that the exact-sequence locator can't pin
        # (reordered/compound wording). Only DOWNGRADE when we DID locate the term
        # and the definition still fails the local floor — otherwise a legitimate
        # multi-word term would be silently demoted (P19 checklist #9).
        local_ok = def_local is None or def_local >= config.KEY_TERMS_DEF_LOCAL_MIN

        # The TERM must be grounded in the transcript to count at all; the
        # definition is a synthesized paraphrase and only refines the tier. An
        # ungrounded term FAILs even when its definition shares topical
        # vocabulary — otherwise a hallucinated term with a plausible on-topic
        # definition would sneak through as WEAK (P7).
        if term_ratio < config.KEY_TERMS_TERM_FAIL_BELOW:
            result = "FAIL"
            failed += 1
        elif (term_ratio >= config.KEY_TERMS_EXACT_TERM_MIN
              and def_support >= config.KEY_TERMS_EXACT_DEF_MIN and local_ok):
            result = "EXACT"
            exact += 1
        elif (term_ratio >= config.KEY_TERMS_PARTIAL_TERM_MIN
              and def_support >= config.KEY_TERMS_PARTIAL_DEF_MIN and local_ok):
            result = "PARTIAL"
            partial += 1
        else:
            result = "WEAK"
            weak += 1
            # Surface (P2) a grounded term whose definition failed the local
            # check — the likely cause is a definition that does not match its
            # term, not merely a thin paraphrase.
            if term_ratio >= config.KEY_TERMS_PARTIAL_TERM_MIN and not local_ok:
                logger.warning(
                    "Key term '%s' is grounded but its definition is weakly "
                    "localized (local=%.2f < %.2f) — the definition may not "
                    "describe this term.",
                    term, def_local or 0.0, config.KEY_TERMS_DEF_LOCAL_MIN,
                )

        lines.append(
            f"| {term} | {term_ratio:.2f} | {def_support:.2f} | "
            f"{'n/a' if def_local is None else f'{def_local:.2f}'} | {result} |"
        )

    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Exact: {exact}",
            f"- Partial: {partial}",
            f"- Weak: {weak}",
            f"- Fail: {failed}",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    logger.info(
        "Key Terms Validation: exact=%d partial=%d weak=%d fail=%d (report: %s)",
        exact,
        partial,
        weak,
        failed,
        report_path.name,
    )
    return failed == 0


def _load_topics_for_validation(base_name: str, transcript: str) -> list[dict]:
    """Load topics from canonical topics artifact."""
    project_dir = config.PROJECTS_DIR / base_name
    topics_file = project_dir / f"{base_name}{config.SUFFIX_TOPICS}"

    if topics_file.exists():
        content = strip_yaml_frontmatter(topics_file.read_text(encoding="utf-8"))
        topics_section = extract_section(content, "Topics") or extract_section(content, "Key Topics")
        if topics_section:
            parsed = summary_pipeline.parse_topics_with_details(topics_section, transcript)
            if parsed:
                return parsed
    return []


def _extract_transcript_sections(transcript: str) -> dict[int, str]:
    """Build map of section number -> section text."""
    sections: dict[int, str] = {}
    pattern = r"## Section (\d+)[^\n]*\n(.*?)(?=## Section \d+|\Z)"
    for num_str, body in re.findall(pattern, transcript, re.DOTALL):
        sections[int(num_str)] = body
    return sections


def _topic_keywords(text: str) -> list[str]:
    """Extract normalized topic keywords for lightweight lexical grounding."""
    stop = {
        "about", "also", "among", "analysis", "and", "are", "as", "at", "be", "by",
        "can", "discussion", "examining", "examination", "exploration", "explores",
        "for", "from", "how", "in", "including", "into", "is", "it", "its", "like",
        "models", "of", "on", "or", "presentation", "process", "research", "showing",
        "systems", "that", "the", "their", "these", "this", "to", "with",
    }
    words = re.findall(r"[a-zA-Z]+", text.lower())
    return [w for w in words if len(w) >= 4 and w not in stop]


def _keyword_grounding_ratio(probe: str, haystack: str) -> float:
    """
    Compute lexical grounding as overlap of meaningful probe keywords in haystack.
    Returns 0..1.
    """
    keywords = _topic_keywords(probe)
    if not keywords:
        return 0.0
    hay_words = set(_topic_keywords(haystack))
    matched = sum(1 for w in set(keywords) if w in hay_words)
    return matched / max(1, len(set(keywords)))


def validate_topics_lightweight(
    formatted_file_path: Path, base_name: str, logger
) -> bool:
    """
    Lightweight deterministic topic validation.
    Checks topic title grounding and optional section-reference consistency.
    """
    transcript = strip_yaml_frontmatter(formatted_file_path.read_text(encoding="utf-8"))
    topics = _load_topics_for_validation(base_name, transcript)
    sections_map = _extract_transcript_sections(transcript)

    report_path = (
        config.PROJECTS_DIR
        / base_name
        / f"{base_name}{config.SUFFIX_TOPICS_VAL}"
    )

    if not topics:
        report_path.write_text(
            "# Topics Validation\n\nNo topics found to validate.\n",
            encoding="utf-8",
        )
        topics_file = (
            config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_TOPICS}"
        )
        if not warn_if_empty_parse(logger, "topics", 0, source_path=topics_file):
            logger.info("No topics to validate (no topics artifact present).")
        return False

    exact = 0
    partial = 0
    weak = 0
    failed = 0
    section_mismatch = 0
    lines = [
        "# Topics Validation",
        "",
        f"Validated topics: {len(topics)}",
        "",
        "| Topic | Title Match | Description Match | Section Match | Result |",
        "|---|---:|---:|---:|---|",
    ]

    for topic in topics:
        name = topic.get("name", "").strip()
        description = topic.get("description", "").strip()
        sections_str = topic.get("sections", "").strip()
        if not name:
            continue

        title_fuzzy = find_text_in_content(
            name, transcript, aggressive_normalization=True
        )[2]
        title_ground = _keyword_grounding_ratio(name, transcript)
        title_ratio = max(title_fuzzy, title_ground)

        desc_probe = " ".join(description.split()[:40])
        desc_fuzzy = find_text_in_content(
            desc_probe, transcript, aggressive_normalization=True
        )[2] if desc_probe else 0.0
        desc_ground = _keyword_grounding_ratio(desc_probe, transcript) if desc_probe else 0.0
        desc_ratio = max(desc_fuzzy, desc_ground)

        section_ratio = 0.0
        if sections_str:
            nums = summary_pipeline.parse_section_range(sections_str)
            section_text = " ".join(sections_map.get(n, "") for n in nums).strip()
            if section_text:
                section_ratio = _keyword_grounding_ratio(
                    f"{name} {desc_probe}", section_text
                )
            else:
                section_ratio = 0.0

        if title_ratio >= 0.65 and desc_ratio >= 0.55:
            result = "EXACT"
            exact += 1
        elif title_ratio >= 0.45 and desc_ratio >= 0.35:
            result = "PARTIAL"
            partial += 1
        elif title_ratio >= 0.25 or desc_ratio >= 0.20:
            result = "WEAK"
            weak += 1
        else:
            result = "FAIL"
            failed += 1

        if sections_str and section_ratio < 0.60:
            section_mismatch += 1

        lines.append(
            f"| {name} | {title_ratio:.2f} | {desc_ratio:.2f} | {section_ratio:.2f} | {result} |"
        )

    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Exact: {exact}",
            f"- Partial: {partial}",
            f"- Weak: {weak}",
            f"- Fail: {failed}",
            f"- Section mismatches: {section_mismatch}",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    logger.info(
        "Topics Validation: exact=%d partial=%d weak=%d fail=%d section_mismatch=%d (report: %s)",
        exact,
        partial,
        weak,
        failed,
        section_mismatch,
        report_path.name,
    )
    # Allow section mismatches as warnings; hard-fail only for failed topics.
    return failed == 0


def _emphasis_quote_found_ratio(quote: str, formatted_content: str) -> float:
    """
    Grounding ratio for one emphasis quote against the transcript.

    Matches BOTH the head and the tail of the quote (not just the opening words)
    and returns the WEAKER of the two match ratios. A quote whose first words are
    verbatim but whose remainder is fabricated therefore scores low (the tail
    fails) instead of passing on its opening alone. Short quotes (<= 2x the
    head/tail window) are matched whole. Reflow across timestamp markers in the
    middle of a long quote is tolerated because only the ends are probed.
    """
    words = quote.split()
    n = config.EMPHASIS_HEADTAIL_WORDS
    if len(words) <= 2 * n:
        probes = [quote]
    else:
        probes = [" ".join(words[:n]), " ".join(words[-n:])]
    return min(
        find_text_in_content(p, formatted_content, aggressive_normalization=True)[2]
        for p in probes
    )


def validate_emphasis_items(
    formatted_file_path: Path, extracts_summary_path: Path, logger
) -> bool:
    """Validate all emphasis quotes exist verbatim in the formatted transcript.

    Returns True when every emphasis quote is grounded (no invalid quote and no
    parse-drift). Previously matched only the first 15 words of each quote, so a
    verbatim opening followed by a fabricated tail passed silently (P2/P9); it now
    probes both ends via ``_emphasis_quote_found_ratio``.
    """
    formatted_content = formatted_file_path.read_text(encoding="utf-8")
    quotes = _extract_emphasis_quotes_from_file(extracts_summary_path)

    if not quotes:
        # Resolve the scored-emphasis artifact so we can tell "no emphasis file"
        # from "file has content but parsed to nothing" (a format/parser drift).
        try:
            stem = parse_filename_metadata(Path(extracts_summary_path).name)["stem"]
        except Exception:
            stem = Path(extracts_summary_path).stem
        scored_path = Path(extracts_summary_path).parent / f"{stem}{config.SUFFIX_EMPHASIS_SCORED}"
        drift = warn_if_empty_parse(logger, "emphasis quotes", 0, source_path=scored_path)
        if not drift:
            logger.info("No emphasis items to validate (no emphasis artifact present).")
        # Content-present-but-parsed-to-nothing is a failure; genuinely absent is not.
        return not drift

    valid_count, partial_count, invalid_count = 0, 0, 0

    for label, quote in quotes:
        ratio = _emphasis_quote_found_ratio(quote, formatted_content)

        if ratio >= config.EMPHASIS_QUOTE_FOUND_RATIO:
            valid_count += 1
        elif ratio >= config.EMPHASIS_QUOTE_PARTIAL_RATIO:
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

    return invalid_count == 0


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

        # A5/P19: surface the AI verdicts so a real FAIL isn't hidden by the
        # "report written -> return True" success path (drift-tolerant counter).
        # ADVISORY BY DESIGN: the bool return means "report generated", not "all
        # sections passed" — consistent with the coverage validators, which also
        # produce a human-reviewed report rather than gating the pipeline. A content
        # FAIL is surfaced via this warning + the report's Verdict Summary, not the
        # return value; no caller aborts on it.
        verdicts = count_header_verdicts(response)
        if verdicts["FAIL"] > 0:
            logger.warning(
                "Header validation: %d section(s) reported STATUS: FAIL, %d WARN "
                "(%d PASS) — review %s",
                verdicts["FAIL"], verdicts["WARN"], verdicts["PASS"], report_path,
            )
        elif response.strip() and verdicts["total"] == 0:
            logger.warning(
                "Header validation: report has content but ZERO parseable STATUS "
                "verdicts — prompt/output format drift (A5/P19)."
            )

        logger.info("✓ Header validation report saved to: %s", report_path)
        return True

    except Exception as e:
        logger.error(
            "An error occurred during header validation: %s", e, exc_info=True)
        return False


# ============================================================================
# STRUCTURED VALIDATION (COVERAGE)
# ============================================================================


def validate_abstract_coverage(base_name: str, logger=None, model: str = config.DEFAULT_MODEL) -> bool:
    """Validate the abstract using the coverage validation module."""
    if logger is None:
        logger = setup_logging("validate_abstract_coverage")

    try:
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

        transcript = load_project_transcript(base_name, logger=logger)

        metadata = parse_filename_metadata(base_name)
        topics_file = config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_TOPICS}"
        themes_file = config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_INTERPRETIVE_THEMES}"
        topics_section = (
            strip_yaml_frontmatter(topics_file.read_text(encoding="utf-8"))
            if topics_file.exists()
            else ""
        )
        themes_section = (
            strip_yaml_frontmatter(themes_file.read_text(encoding="utf-8"))
            if themes_file.exists()
            else ""
        )

        transcript_words = len(transcript.split())
        target_word_count = config.abstract_target_word_count(transcript_words)

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

        # Advisory (P2): surface abstract proper-names absent from the source.
        # No gate previously checked this, and a real run shipped a fabricated
        # researcher name ("Luciano Malorni") into the published HTML.
        ungrounded_names = abstract_validation.find_ungrounded_names(
            abstract_text, transcript
        )
        if ungrounded_names:
            logger.warning(
                "Abstract contains %d proper name(s) not grounded in the source "
                "transcript (possible hallucination): %s",
                len(ungrounded_names), "; ".join(ungrounded_names),
            )
            report += (
                "\n\nUngrounded names (not found in source — verify): "
                + "; ".join(ungrounded_names)
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
        generated_summary_file = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_SUMMARY_GEN}"
        )

        if generated_summary_file.exists():
            summary_text = generated_summary_file.read_text(encoding="utf-8")
        else:
            logger.error("No generated summary found to validate.")
            return False

        transcript = load_project_transcript(base_name, logger=logger)

        metadata = parse_filename_metadata(base_name)
        topics_file = config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_TOPICS}"
        themes_file = config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_INTERPRETIVE_THEMES}"
        topics_section = (
            strip_yaml_frontmatter(topics_file.read_text(encoding="utf-8"))
            if topics_file.exists()
            else ""
        )
        themes_section = (
            strip_yaml_frontmatter(themes_file.read_text(encoding="utf-8"))
            if themes_file.exists()
            else ""
        )

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
