"""
Pipeline module for validation tasks (headers, abstracts, emphasis).
"""

import functools
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional


import abstract_pipeline
import abstract_validation
import config
import transcript_utils
import summary_pipeline
import summary_validation
from transcript_utils import (
    CURLY_QUOTE_MAP,
    get_anthropic_client_or_none,
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


_KEY_TERM_STOPWORDS = frozenset({"with", "from", "into", "about", "their", "within"})


def _initials(text: str) -> str:
    return "".join(w[0] for w in re.split(r"[\s-]+", text) if w and w[0].isalpha()).upper()


_VERSUS_RE = re.compile(r"\s+(?:versus|vs\.?)\s+", re.IGNORECASE)


def _key_term_alternatives(term: str) -> list:
    """Forms of a key-term label to ground against the transcript: the label, a
    trailing parenthetical and the text before it, each side of "X / Y", and a
    "versus" -> "and" variant. Never splits into single words, so a generic word
    alone cannot ground a term.

    Purpose: Ground terms whose label adds an expansion or alias (decision 2a).
    Spec:    docs/plan_review_fixes_2026-10-04.md#R15
    Tests:   tests/test_validator_gating_r15.py::test_r15_key_term_alternatives
    """
    candidates = [term]
    paren = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", term)
    if paren:
        main, inner = paren.group(1).strip(), paren.group(2).strip()
        candidates.append(main)
        # The parenthetical counts only when it is an expansion or acronym of the
        # main part, or has 2+ significant words of its own — "(Bowen)" or "(in
        # families)" must not ground a term (sweep finding, P7).
        if (_initials(inner) == main.replace(".", "").upper()
                or _initials(main) == inner.replace(".", "").upper()
                or len([w for w in re.findall(r"[A-Za-z]+", inner)
                        if len(w) >= 4 and w.lower() not in _KEY_TERM_STOPWORDS]) >= 2):
            candidates.append(inner)
    out: list = []
    for cand in candidates:
        for part in re.split(r"\s*/\s*", cand):
            part = part.strip()
            if not part:
                continue
            for form in (part, _VERSUS_RE.sub(" and ", part)):
                if form not in out:
                    out.append(form)
    return out or [term]


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
        # A term label often names alternatives that never appear verbatim as one
        # string, though one of them does: "Symbiosis / Symbiotic Relationship",
        # "OCD (Obsessive-Compulsive Disorder)", "Wanting versus Liking" (spoken as
        # "wanting and liking"). Ground on the best-matching alternative.
        term_ratio, best_part = max(
            (find_text_in_content(part, transcript, aggressive_normalization=True)[2], part)
            for part in _key_term_alternatives(term)
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
        def_local = _best_local_grounding(definition, best_part, transcript)
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


def _grade_topics(topics: list, transcript: str, sections_map: dict) -> list:
    """Grade each topic against the transcript. Returns
    ``(name, title_ratio, desc_ratio, section_ratio, result, has_sections)`` rows,
    result in EXACT / PARTIAL / WEAK / FAIL. Pure (no report written), so the
    release gate can run it too (plan R15)."""
    rows = []
    for topic in topics:
        name = topic.get("name", "").strip()
        description = topic.get("description", "").strip()
        sections_str = topic.get("sections", "").strip()
        if not name:
            continue

        # Each ratio is max(keyword grounding, fuzzy match). The fuzzy scan is
        # O(transcript) per call (20-50 s per real project) and can only RAISE the
        # ratio, so skip it once keyword grounding already reaches the top tier:
        # the tier is identical (plan R15 — the gate runs this on every publish).
        title_ratio = _keyword_grounding_ratio(name, transcript)
        if title_ratio < 0.65:
            title_ratio = max(title_ratio, find_text_in_content(
                name, transcript, aggressive_normalization=True)[2])

        desc_probe = " ".join(description.split()[:40])
        desc_ratio = _keyword_grounding_ratio(desc_probe, transcript) if desc_probe else 0.0
        if desc_probe and desc_ratio < 0.55:
            desc_ratio = max(desc_ratio, find_text_in_content(
                desc_probe, transcript, aggressive_normalization=True)[2])

        section_ratio = 0.0
        if sections_str:
            nums = summary_pipeline.parse_section_range(sections_str)
            section_text = " ".join(sections_map.get(n, "") for n in nums).strip()
            if section_text:
                section_ratio = _keyword_grounding_ratio(
                    f"{name} {desc_probe}", section_text
                )

        if title_ratio >= 0.65 and desc_ratio >= 0.55:
            result = "EXACT"
        elif title_ratio >= 0.45 and desc_ratio >= 0.35:
            result = "PARTIAL"
        elif title_ratio >= 0.25 or desc_ratio >= 0.20:
            result = "WEAK"
        else:
            result = "FAIL"
        rows.append((name, title_ratio, desc_ratio, section_ratio, result, bool(sections_str)))
    return rows


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

    for name, title_ratio, desc_ratio, section_ratio, result, has_sections in _grade_topics(
            topics, transcript, sections_map):
        if result == "EXACT":
            exact += 1
        elif result == "PARTIAL":
            partial += 1
        elif result == "WEAK":
            weak += 1
        else:
            failed += 1
        if has_sections and section_ratio < 0.60:
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


# Typographic characters the model may emit where the transcript has ASCII (or
# vice versa); mapped before comparison so they don't count as altered words.
_QUOTE_CHAR_MAP = str.maketrans({
    **CURLY_QUOTE_MAP,
    "\u2013": " ", "\u2014": " ", "\u2026": " ", "\u00a0": " ",
})


@functools.lru_cache(maxsize=4)
def _normalized_word_tuple(text: str) -> tuple:
    """Aggressively normalized words of ``text`` (cached: the same transcript is
    searched once per quote)."""
    text = text.translate(_QUOTE_CHAR_MAP)
    text = normalize_text(text, aggressive=True)
    # Filler words and stutters are ignored on both sides (author decision 2a,
    # 2026-10-09): a quote that only tidied "my uh my my degrees" is verbatim.
    return tuple(_collapse_disfluencies(re.sub(r"[^\w\s]", " ", text).lower().split()))


@functools.lru_cache(maxsize=4)
def _transcript_matcher(transcript_words: tuple) -> SequenceMatcher:
    """SequenceMatcher with the transcript as seq2 (its index is built once and
    reused; only seq1 changes per quote)."""
    return SequenceMatcher(None, (), transcript_words, autojunk=False)


def _doubled_letter_typo(quote_word: str, transcript_word: str, counts) -> bool:
    """True when the transcript word is a one-off misspelling the quote corrected:
    the two differ only by a doubled letter ("birdd" / "bird"), both have 4+
    letters, and the transcript spelling occurs exactly once in the transcript.

    Narrow on purpose (sweep 2026-10-09): any one-letter difference also accepted
    real word changes — would/could, were/where, than/then — and a misquote passed
    the blocking verbatim_quotes check."""
    a, b = quote_word, transcript_word
    if min(len(a), len(b)) < 4 or abs(len(a) - len(b)) != 1 or counts.get(b, 0) != 1:
        return False
    longer, shorter = (a, b) if len(a) > len(b) else (b, a)
    return any(longer[:k] + longer[k + 1:] == shorter
               for k in range(1, len(longer)) if longer[k] == longer[k - 1])


@functools.lru_cache(maxsize=4)
def _word_counts(transcript_words: tuple) -> dict:
    counts: dict = {}
    for w in transcript_words:
        counts[w] = counts.get(w, 0) + 1
    return counts


@functools.lru_cache(maxsize=4)
def _plain_word_string(text: str) -> str:
    """`` w1 w2 ... `` — the words of ``text`` normalized as in
    ``_normalized_word_tuple`` (quote marks, punctuation, filler words removed)
    but with repeats NOT collapsed. Padded with spaces for whole-word search."""
    text = normalize_text(text.translate(_QUOTE_CHAR_MAP), aggressive=True)
    words = re.sub(r"[^\w\s]", " ", text).lower().split()
    return " " + " ".join(w for w in words if w not in config.QUOTE_FILLER_WORDS) + " "


def _quote_is_verbatim(quote: str, transcript: str) -> bool:
    """True when the quote's words occur in the transcript exactly, in order and
    contiguous (after the normalization above, before any repeat collapsing).

    Collapsing repeats is context-dependent: a quote that stops inside a repeat
    ("utterings and utterings and utterings") collapses differently from the
    source that goes on ("... and utterings and that"). A quote that is literally
    in the source is verbatim whatever the collapse does (RF.B). A changed last
    word ("do it, do it, do" for "do it, do it, don't") is not found and falls
    through to the normal checks.

    Purpose: Stop exact quotes failing on repeat-collapse boundaries.
    Spec:    docs/plan_run_fixes_2026-10-09.md#RF.B
    Tests:   tests/test_run_fixes_rf.py::test_rfb1_quote_ending_inside_a_repeat_is_verbatim
    """
    q = _plain_word_string(quote)
    return q.strip() != "" and q in _plain_word_string(transcript)


_ELLIPSIS_RE = re.compile(r"\.\.\.|…")


def _ellipsis_word_positions(quote: str) -> set:
    """Normalized-word indices at which the quote marks an omission with "..." or "…":
    the normalized length of the quote text before each marker. The whole prefix is
    normalized (not each part), so a word repeated across a marker, which the
    normalizer collapses, does not shift later positions; the uncached normalizer
    keeps the transcript's cache entry (SW review)."""
    normalize = _normalized_word_tuple.__wrapped__
    return {len(normalize(quote[:m.start()])) for m in _ELLIPSIS_RE.finditer(quote)}


def _stray_edge_words(quote: str, q, window, blocks) -> int:
    """Number of quote words in a stray lead or tail. The lead is the run of matched
    blocks at the start of the quote, up to the first skip of at least
    config.QUOTE_STRAY_BLOCK_MIN_GAP source words; the tail is the same from the end.
    It is stray when it has at most config.QUOTE_STRAY_BLOCK_MAX_WORDS words, its
    words are not among the source words just before (or after) the rest of the quote
    (config.QUOTE_STRAY_NEAR_WORDS plus its own length), and the quote does not mark
    the omission there with "..." or "…".

    Example: "I think the future is…" where the source says "…the way I see it
    happening, to me the future is…". "I think" matches an earlier "I think", so every
    word was found and the quote passed (D6 open item).

    Only the ends: the alignment keeps order, so a changed word inside a quote is
    already a mismatch, and a short block between two omissions inside a quote is the
    speaker's word in its place.

    Purpose: Catch a changed first or last word that also occurs nearby.
    Spec:    docs/plan_swapped_word_quotes_2026-10-12.md#SW1
    Tests:   tests/test_swapped_word_quotes_sw.py::test_sw1_changed_first_words_fail
    """
    blocks = [b for b in blocks if b.size]
    if len(blocks) < 2:
        return 0
    gap_min, size_max = config.QUOTE_STRAY_BLOCK_MIN_GAP, config.QUOTE_STRAY_BLOCK_MAX_WORDS
    marked = _ellipsis_word_positions(quote)
    candidates = []  # (size, number of blocks in the unit, first?)
    for ordered, first in ((blocks, True), (blocks[::-1], False)):
        unit = [ordered[0]]
        body = None
        for prev, nxt in zip(ordered, ordered[1:]):
            gap = (nxt.b - (prev.b + prev.size)) if first else (prev.b - (nxt.b + nxt.size))
            if gap >= gap_min:
                body = nxt
                break
            unit.append(nxt)
        size = sum(b.size for b in unit)
        if body is None or size > size_max:
            continue
        if first:
            words = q[unit[0].a:unit[-1].a + unit[-1].size]
            edge = unit[-1].a + unit[-1].size
            near = window[max(unit[-1].b + unit[-1].size,
                              body.b - (size + config.QUOTE_STRAY_NEAR_WORDS)):body.b]
        else:
            words = q[unit[-1].a:unit[0].a + unit[0].size]
            edge = unit[-1].a
            end = body.b + body.size
            near = window[end:min(unit[-1].b, end + size + config.QUOTE_STRAY_NEAR_WORDS)]
        if edge in marked:
            continue  # the quote marks the omission with an ellipsis
        if all(word in near for word in words):
            continue  # the same words sit beside the rest of the quote: an omission
        candidates.append((size, len(unit), first))
    if len(candidates) == 2 and candidates[0][1] + candidates[1][1] >= len(blocks):
        # One large gap: the lead and the tail are each other's "body". Only the
        # shorter side can be the changed one (SW review: both were subtracted).
        candidates = [min(candidates)]
    return sum(size for size, _n, _first in candidates)


def _quote_word_coverage(quote: str, transcript: str) -> float:
    """Fraction of the quote's words found, in order, at its location in the
    transcript.

    Locates the quote by its longest verbatim run of words, then aligns the whole
    quote against a window around that spot. Words the quote omits from the source
    (e.g. an ellipsis) do not lower the score; words the quote adds or changes do —
    except a corrected one-off doubled-letter typo (J8, ``_doubled_letter_typo``).
    One exception to the omission rule (SW, ``_stray_edge_words``): a lead or tail
    of up to 4 words matched only across a skipped span, and not found beside the
    rest of the quote, counts as changed unless the quote marks the omission there
    with "..." or "…".

    Spec:  docs/plan_swapped_word_quotes_2026-10-12.md#SW1
    Tests: tests/test_swapped_word_quotes_sw.py
    """
    q = list(_normalized_word_tuple(quote))
    if not q:
        return 0.0
    if _quote_is_verbatim(quote, transcript):
        return 1.0
    t = _normalized_word_tuple(transcript)
    locator = _transcript_matcher(t)
    locator.set_seq1(q)
    anchor = locator.find_longest_match(0, len(q), 0, len(t))
    if anchor.size == 0:
        return 0.0
    slack = len(q) // 2 + 5
    lo = max(0, anchor.b - anchor.a - slack)
    hi = min(len(t), anchor.b + (len(q) - anchor.a) + slack)
    window = t[lo:hi]
    matcher = SequenceMatcher(None, q, window, autojunk=False)
    # SW: an edge word matched far from the rest of the quote is a changed word.
    matched = -_stray_edge_words(quote, q, window, matcher.get_matching_blocks())
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            matched += i2 - i1
        elif op == "replace" and i2 - i1 == j2 - j1:
            # A transcription typo the quote corrected ("birdd" -> "bird") is not a
            # misquotation (decision 2026-10-09, J8; narrowed after the sweep).
            counts = _word_counts(t)
            matched += sum(1 for a, b in zip(q[i1:i2], window[j1:j2])
                           if _doubled_letter_typo(a, b, counts))
    return matched / len(q)


@functools.lru_cache(maxsize=8)
def _without_disfluencies(text: str) -> str:
    """Lower-cased word sequence with filler words (config.QUOTE_FILLER_WORDS)
    removed and immediate repeats of 1-3 words collapsed, so "my uh my my degrees"
    and "my degrees" compare equal. Applied to both quote and transcript.

    Quotation marks are not part of a word: a quote that writes the speaker's
    inner "He's smiling" as 'He's smiling' must not turn "he's" into "'he's"
    (RF.B). Apostrophes inside a word ("he's", "don't") are kept.

    Purpose: Stop a quote that only dropped disfluencies failing verbatim checks.
    Spec:    docs/plan_review_fixes_2026-10-04.md#R15 (decision 1a),
             docs/plan_run_fixes_2026-10-09.md#RF.B
    Tests:   tests/test_validator_gating_r15.py::test_r15_emphasis_ignores_disfluencies,
             tests/test_run_fixes_rf.py::test_rfb1_nested_single_quotes_are_verbatim
    """
    text = text.lower().translate(_QUOTE_CHAR_MAP)
    words = [w.strip("'") for w in re.findall(r"[a-z0-9']+", text)]
    return " ".join(_collapse_disfluencies([w for w in words if w]))


def _collapse_disfluencies(words) -> list:
    """Drop filler words (config.QUOTE_FILLER_WORDS) and collapse immediate
    repeats of 1-3 words in a lower-cased word sequence."""
    words = [w for w in words if w not in config.QUOTE_FILLER_WORDS]
    out: list = []
    i = 0
    while i < len(words):
        for n in (3, 2, 1):
            if len(out) >= n and words[i:i + n] == out[-n:]:
                i += n
                break
        else:
            out.append(words[i])
            i += 1
    return out


def _emphasis_quote_found_ratio(quote: str, formatted_content: str) -> float:
    """
    Grounding ratio for one emphasis quote against the transcript.

    Returns the WEAKEST of: the head match, the tail match (both fuzzy, for long
    quotes; the whole quote for short ones), and the whole-quote word coverage
    (``_quote_word_coverage``). Probing only the head and tail let a quote with a
    fabricated or negated middle score 1.0; the coverage term catches that.
    """
    if _quote_is_verbatim(quote, formatted_content):
        return 1.0
    quote = _without_disfluencies(quote)
    if not quote:
        return 0.0  # an empty or filler-only "quote" grounds nothing (sweep finding)
    formatted_content = _without_disfluencies(formatted_content)
    words = quote.split()
    n = config.EMPHASIS_HEADTAIL_WORDS
    if len(words) <= 2 * n:
        probes = [quote]
    else:
        probes = [" ".join(words[:n]), " ".join(words[-n:])]
    ends = min(
        find_text_in_content(p, formatted_content, aggressive_normalization=True)[2]
        for p in probes
    )
    return min(ends, _quote_word_coverage(quote, formatted_content))


def quote_is_verbatim_for_gate(quote: str, transcript: str) -> tuple:
    """The release gate's verbatim test for one Bowen/emphasis quote:
    ``(ok, ends, coverage)``, ok when the head/tail match reaches
    config.EMPHASIS_QUOTE_PARTIAL_RATIO and whole-quote word coverage reaches
    config.QUOTE_MIN_WORD_COVERAGE.

    Purpose: One test shared by the gate and the extractors, so an extractor never
             saves a quote the gate will reject (RF.K, P19).
    Spec:    docs/plan_run_fixes_2026-10-09.md#RF.K.1
    Tests:   tests/test_run_fixes_rf.py::test_rfk1_gate_uses_shared_predicate
    """
    ends = _emphasis_quote_found_ratio(quote, transcript)
    coverage = _quote_word_coverage(quote, transcript)
    ok = ends >= config.EMPHASIS_QUOTE_PARTIAL_RATIO and coverage >= config.QUOTE_MIN_WORD_COVERAGE
    return ok, ends, coverage


def validate_emphasis_items(
    formatted_file_path: Path, extracts_summary_path: Path, logger
) -> bool:
    """Validate all emphasis quotes exist verbatim in the formatted transcript.

    Returns True when every emphasis quote passes the release gate's verbatim test
    (``quote_is_verbatim_for_gate``) and there is no parse-drift. Spec:
    docs/plan_todo_triage_2026-10-11.md#D6; Tests:
    tests/test_emphasis_threshold_d6.py::test_d6_one_changed_word_fails_validator_like_the_gate. Previously matched only the first 15 words of each quote, so a
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
        # D6: the release gate's own test decides found / not found, so this check
        # cannot pass a quote the gate will block (a "partial" match used to pass).
        ok, ratio, coverage = quote_is_verbatim_for_gate(quote, formatted_content)

        if not ok:
            logger.error("NOT FOUND: %s (match %.2f, word coverage %.2f) - Quote: %s...",
                         label, ratio, coverage, quote[:100])
            invalid_count += 1
        elif ratio >= config.EMPHASIS_QUOTE_FOUND_RATIO:
            valid_count += 1
        else:
            partial_count += 1

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
    formatted_filename: str, model: str | None = None, logger=None
) -> bool:
    """Validate that the section headers in the formatted transcript make sense,
    using the batched HeaderValidator (the GUI's "Val Headers" step) so there is one
    implementation. Returns False when the key is missing or any batch failed.

    Before HV this sent the whole transcript in one call capped at 4096 output
    tokens, which was cut off on a real 10k-word talk (2026-10-12).

    Spec:  docs/plan_todo_triage_2026-10-11.md#HV
    Tests: tests/test_header_validation_hv.py::test_hv1_validate_headers_uses_batched_validator
    """
    model = model or config.settings.AUX_MODEL  # N3: resolved per call, not at import
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

        import transcript_utils
        import transcript_validate_headers
        api_key = transcript_utils.resolve_anthropic_key()
        if not api_key:
            logger.error("Header validation: no Anthropic API key found "
                         "(ANTHROPIC_API_KEY or ~/.config/llm/keys.json).")
            return False
        validator = transcript_validate_headers.HeaderValidator(api_key, logger)
        return bool(validator.run(formatted_path, model=model))

    except Exception as e:
        logger.error(
            "An error occurred during header validation: %s", e, exc_info=True)
        return False


# ============================================================================
# STRUCTURED VALIDATION (COVERAGE)
# ============================================================================


def validate_abstract_coverage(base_name: str, logger=None, model: str | None = None) -> bool:
    """Validate the abstract using the coverage validation module."""
    model = model or config.settings.DEFAULT_MODEL  # N3: resolved per call, not at import
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

        client = get_anthropic_client_or_none(logger)

        passed, report = abstract_validation.validate_and_report(
            abstract_text, abstract_input, api_client=client, model=model, logger=logger
        )

        # Advisory (P2): surface abstract proper-names absent from the source.
        # No gate previously checked this, and a real run shipped a fabricated
        # researcher name ("Luciano Malorni") into the published HTML. The
        # presenter/author is passed as a KNOWN name so a correct attribution to
        # the speaker (named in the filename, not spoken in their own talk) is not
        # flagged as a hallucination ("Michael Kerr" false-positive).
        known_names = [
            n for n in (metadata.get("presenter"), metadata.get("author")) if n
        ]
        ungrounded_names = abstract_validation.find_ungrounded_names(
            abstract_text, transcript, known_names=known_names
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


def _summary_coverage_logic_version() -> str:
    import inspect

    prompt = config.PROMPTS_DIR / config.PROMPT_VALIDATION_COVERAGE_FILENAME
    parts = [
        config.settings.AUX_MODEL,  # the model the GUI runs the check with (U5 sweep)
        repr(sorted(config.SUMMARY_COVERAGE_GATING_CATEGORIES)),
        # The target the summary is checked against and the length band (SL).
        repr((config.DEFAULT_SUMMARY_WORD_COUNT, config.SUMMARY_LENGTH_ACCEPT_MIN_RATIO,
              config.SUMMARY_LENGTH_MAX_RATIO)),
        prompt.read_text(encoding="utf-8") if prompt.exists() else "<no prompt>",
        *(inspect.getsource(fn) for fn in (
            summary_validation.generate_coverage_items,
            summary_validation.check_keyword_coverage,
            summary_validation.extract_keywords,
            summary_validation.validate_summary_coverage,
            summary_validation.validate_and_report_status,
            summary_validation.validate_structural,
            abstract_validation.coverage_status,
            abstract_validation.apply_llm_results,
            abstract_validation.verify_items_with_llm,
            summary_pipeline.prepare_summary_input,
        )),
    ]
    return "|".join(parts)


def summary_coverage_key(base_name: str) -> Optional[str]:
    """sha256 over the summary, topics, interpretive themes and transcript files —
    the inputs summary coverage is computed from. None when there is no summary.
    A stored verdict whose key differs from this is stale (P6)."""
    import hashlib

    proj = config.PROJECTS_DIR / base_name
    summary = proj / f"{base_name}{config.SUFFIX_SUMMARY_GEN}"
    if not summary.exists():
        return None
    h = hashlib.sha256()
    # The verdict also depends on the coverage logic, prompt, model and gating
    # policy, not only the input files (sweep finding, P6).
    h.update(_summary_coverage_logic_version().encode("utf-8"))
    for suffix in (config.SUFFIX_SUMMARY_GEN, config.SUFFIX_TOPICS,
                   config.SUFFIX_INTERPRETIVE_THEMES, config.SUFFIX_FORMATTED,
                   config.SUFFIX_YAML):
        path = proj / f"{base_name}{suffix}"
        h.update(suffix.encode("utf-8"))
        h.update(path.read_bytes() if path.exists() else b"<absent>")
    return h.hexdigest()


def _write_summary_coverage_verdict(base_name: str, status: str, detail: str,
                                    not_gated: str = "") -> None:
    """Store the gate verdict. ``not_gated``: what the full validation found missing
    when the gate still passes (items outside SUMMARY_COVERAGE_GATING_CATEGORIES)."""
    import json

    path = config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_SUMMARY_COVERAGE_VERDICT}"
    if status == "ERROR":
        # Never store a could-not-verify result (P1): the next gate run retries.
        path.unlink(missing_ok=True)
        return
    record = {"status": status, "key": summary_coverage_key(base_name), "detail": detail}
    if not_gated:
        record["not_gated"] = not_gated
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")


_MISSING_REQUIRED_RE = re.compile(r"^- ❌ MISSING \[REQUIRED\] (.+?)\s*$", re.MULTILINE)


def _summary_verdict_detail(status: str, passed: bool, report: str) -> tuple[str, str]:
    """(detail, not_gated) for the stored verdict, built from the report's
    "Gate status:" line (status and reason) and its checklist (every missing required
    item). The report's first line is the full validation and lists at most two
    missing items, so it is used only for a clean pass and for a structural failure.
    E2E run 4: a PASS verdict whose detail said "Validation: FAILED", and a GUI message
    saying publication would be blocked."""
    lines = [line.rstrip() for line in report.splitlines()]
    first = lines[0].strip() if lines else ""
    gate = next((line.strip() for line in lines if line.startswith("Gate status:")), "")
    missing = _MISSING_REQUIRED_RE.findall(report)
    if not gate:
        # Structural failure ("Structural validation failed:" + issue lines).
        issue = next((line.strip(" -") for line in lines[1:] if line.strip()), "")
        return (f"{first} {issue}".strip() if first.endswith(":") else first), ""
    if status == "PASS":
        if passed:
            return first, ""
        # The gate passed, so every missing required item is outside the gate.
        if missing:
            not_gated = "missing: " + "; ".join(missing)
        else:
            rest = first.split(" - ", 1)[1] if " - " in first else ""
            not_gated = rest if rest.strip(" :").lower() != "missing" and rest else \
                "some required items not confirmed"
        gated = ", ".join(sorted(config.SUMMARY_COVERAGE_GATING_CATEGORIES))
        return f"Gated items ({gated}) covered; not gated: {not_gated}", not_gated
    detail = gate
    if missing:
        detail += "; missing required items: " + "; ".join(missing)
    return detail, ""


def stored_summary_coverage_verdict(base_name: str) -> Optional[dict]:
    """The stored summary-coverage verdict when it matches the current inputs, else
    None. The release gate and the run messages read it the same way."""
    import json

    key = summary_coverage_key(base_name)
    if key is None:
        return None
    path = config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_SUMMARY_COVERAGE_VERDICT}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not (isinstance(data, dict) and data.get("key") == key):
        return None
    detail = str(data.get("detail") or "")
    if data.get("status") == "PASS" and not data.get("not_gated") and \
            detail.startswith("Validation: FAILED"):
        # Saved before E2E7: a gate PASS with the full validation's "FAILED" line as
        # its detail. Reword it; the verdict and its key are unchanged.
        rest = detail.split(" - ", 1)[1] if " - " in detail else "some required items not confirmed"
        gated = ", ".join(sorted(config.SUMMARY_COVERAGE_GATING_CATEGORIES))
        data = {**data, "not_gated": rest,
                "detail": f"Gated items ({gated}) covered; not gated: {rest}"}
    return data


def summary_coverage_message(base_name: str) -> Optional[str]:
    """What the summary coverage result means for publication, from the verdict the
    release gate uses — not from the full validation, which also checks items the
    gate does not (Q&A, opening). None when there is nothing to report."""
    verdict = stored_summary_coverage_verdict(base_name)
    report = f"{base_name}{config.SUFFIX_SUMMARY_VAL}"
    if verdict is None:
        return ("⚠️ Summary coverage could not be checked — the release gate will run it "
                f"again. See the log and '{report}'.")
    if verdict.get("status") == "FAIL":
        return ("⚠️ Summary coverage did not pass — publication will be blocked until it "
                f"does. See '{report}'.")
    if verdict.get("not_gated"):
        return (f"⚠️ Summary: {verdict['not_gated']} — not checked by the release gate, so "
                f"publication is not blocked. See '{report}'.")
    return None


def validate_summary_coverage(base_name: str, logger=None, model: Optional[str] = None) -> bool:
    """Validate the summary using the coverage validation module.

    Also stores the gate verdict (PASS / FAIL; ERROR is not stored) keyed to
    ``summary_coverage_key`` for ``release_gate.check_summary_coverage``.
    ``model`` defaults to the GUI-selected AUX model (config.settings), the same
    model the freshness key hashes (U5 sweep).
    Spec: docs/plan_review_fixes_2026-10-04.md#R15
    """
    model = model or config.settings.AUX_MODEL
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
            target_word_count=config.DEFAULT_SUMMARY_WORD_COUNT,  # the generation target (was 500)
        )

        client = get_anthropic_client_or_none(logger)

        status, passed, report = summary_validation.validate_and_report_status(
            summary_text, summary_input, api_client=client, model=model, logger=logger
        )

        report_path = (
            config.PROJECTS_DIR / base_name /
            f"{base_name}{config.SUFFIX_SUMMARY_VAL}"
        )
        report_path.write_text(report, encoding="utf-8")
        detail, not_gated = _summary_verdict_detail(status, passed, report)
        _write_summary_coverage_verdict(base_name, status, detail, not_gated)

        logger.info("Validation Report saved to %s", report_path)
        logger.info("Validation Passed: %s", passed)

        for line in report.splitlines():
            logger.info(line)

        return passed

    except Exception as e:
        logger.error("Error validating summary coverage: %s", e, exc_info=True)
        return False
