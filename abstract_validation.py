"""
Abstract Validation Module
Validates generated abstracts for semantic coverage of source content.

Three-tier validation:
1. Structural checks (word count, prohibited elements)
2. Keyword coverage (fast, deterministic)
3. LLM verification (accurate, for failed keyword checks)

Usage:
    from abstract_validation import validate_abstract_coverage, generate_review_checklist

    checklist = generate_review_checklist(abstract_input)
    validation = validate_abstract_coverage(abstract, abstract_input)

    if not validation["passed"]:
        print(validation["human_review_checklist"])
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

import config
from transcript_utils import call_claude_with_retry, cap_max_tokens_for_model


def find_ungrounded_names(abstract: str, transcript: str,
                          known_names=None) -> list[str]:
    """
    Return multi-word proper names in the abstract that are NOT grounded in the
    source transcript.

    A name is grounded when at least one of its significant tokens (length >=
    ``config.ABSTRACT_NAME_TOKEN_MIN_LEN``) fuzzy-matches some token in the
    source. Fuzzy matching (ratio >= ``config.ABSTRACT_NAME_FUZZY_MIN``) spares
    ASR spelling normalizations (e.g. "Bertoloso" -> "Bertolaso") while still
    catching a fabricated name whose tokens appear nowhere in the source. Matches
    Latin-accented names ("José García") as well as ASCII.

    ``known_names`` is an optional iterable of names that are legitimately ABSENT
    from the transcript body (the presenter/author, who is named in the filename
    metadata but not spoken in their own talk). A name whose significant tokens
    are ALL covered by a known name is skipped — so a correct attribution to the
    presenter ("Michael Kerr") is not flagged as a hallucination, while a
    fabricated adjacent name ("Michael Kerrstone") still is (its stray token is
    not known).

    KNOWN GAPS (this is a lexical check — a real fix is the semantic judge, M2):
    it only detects a MULTI-WORD Title-Case shape, so a single-word surname
    ("Malorni" alone), an ALL-CAPS acronym/org ("ACME"), initials ("J. Ewing"),
    and non-Latin scripts slip through. It caught the shipped "Luciano Malorni"
    (multi-word); adjacent fabrication shapes remain uncovered. Markdown headings
    and bold concept/term labels are stripped from the prose scan, but the
    multi-word names inside them are collected by ``scaffolding_name_spans`` and
    grounded the same way (review F2), minus generic heading phrases
    (``config.SCAFFOLDING_HEADING_PHRASES``). A concept label ("Role Absorption")
    passes because its words are in the source; a fabricated name in a heading
    or label is flagged. The faithfulness judge receives the same ungrounded
    spans as claims (``faithfulness_judge.extract_claims(text, source=...)``).
    """
    # Strip ALL markdown scaffolding — leading YAML/headings AND mid-document
    # headings / bold labels — so a Title-Case heading or concept label in a
    # prose-and-heading artifact (blog/overview/summary) is never mistaken for a
    # fabricated proper name (the false-BLOCK class: "# Abstract" -> "Abstract In",
    # "## Key Takeaways" -> "Key Takeaways"). Pure-prose artifacts (the abstract)
    # carry no mid-document headings, so this is a no-op there.
    # Names inside the stripped headings/labels are still checked (review F2): they
    # are collected separately, minus generic heading phrases, then grounded below.
    scaffold_names = scaffolding_name_spans(abstract)
    abstract = _strip_scaffolding(abstract)
    source_tokens = {
        t for t in re.findall(r"[a-zà-öø-ÿ]+", transcript.lower())
        if len(t) >= config.ABSTRACT_NAME_TOKEN_MIN_LEN
    }
    # Presenter/author names (filename metadata) that are legitimately ABSENT from
    # the transcript body, so grounding them against the source is the wrong test.
    # Match the FULL normalized name (not a filtered token subset): a sub-4-char
    # fabricated surname ("Michael Li" vs presenter "Michael Kerr") must NOT be
    # hidden by dropping its only distinguishing token below the min length.
    known_full: set[str] = {
        " ".join(str(kn).lower().split()) for kn in (known_names or []) if kn
    }

    def _grounded(token: str) -> bool:
        low = token.lower()
        if low in source_tokens:
            return True
        return any(
            SequenceMatcher(None, low, s).ratio() >= config.ABSTRACT_NAME_FUZZY_MIN
            for s in source_tokens
            if abs(len(s) - len(low)) <= 2
        )

    def _known_name(name: str) -> bool:
        return " ".join(name.lower().split()) in known_full

    def _ungrounded_runs(span: str) -> list[str]:
        """Split a heading/label span at grounded words. A Title-Case heading is
        ALL capitalised, so "How Jane Doerfler Changed Family Therapy" is one span
        that one grounded word ("family") would clear; its ungrounded run "Jane
        Doerfler" is what must be checked (sweep finding, P7)."""
        min_len = config.ABSTRACT_NAME_TOKEN_MIN_LEN
        runs, cur = [], []
        for word in span.split():
            if len(word) >= min_len and _grounded(word):
                runs.append(cur)
                cur = []
            else:
                cur.append(word)
        runs.append(cur)
        out = []
        for run in runs:
            while run and len(run[0]) < min_len:
                run = run[1:]
            while run and len(run[-1]) < min_len:
                run = run[:-1]
            text = " ".join(run)
            if len(run) >= 2 and text.lower() not in config.SCAFFOLDING_HEADING_PHRASES:
                out.append(text)
        return out

    scaffold_names = [run for span in scaffold_names for run in _ungrounded_runs(span)]

    ungrounded: list[str] = []
    seen: set[str] = set()
    # Use [ \t]+ (not \s+) between name words: a real multi-word proper name is
    # on ONE line, so a match must never span a newline/paragraph break (that is
    # what produced the bogus "Abstract\n\nIn" name and a false publish BLOCK).
    for name in _NAME_SPAN.findall(abstract) + scaffold_names:
        if name in seen:
            continue
        seen.add(name)
        sig_tokens = [
            t for t in name.split()
            if len(t) >= config.ABSTRACT_NAME_TOKEN_MIN_LEN
        ]
        if sig_tokens and not any(_grounded(t) for t in sig_tokens) \
                and not _known_name(name):
            ungrounded.append(name)
    return ungrounded

QA_OPTIONAL_THRESHOLD = 15
QA_REQUIRED_THRESHOLD = 30


@dataclass
class CoverageItem:
    """Single item to verify in abstract."""

    category: str  # "topic", "theme", "purpose", "conclusion", "qa"
    label: str  # Human-readable label
    required: bool  # Must be present
    keywords: list[str]  # Terms that indicate coverage
    source_text: str  # Original text for LLM verification
    covered: Optional[bool] = None  # Result of validation
    confidence: Optional[str] = None  # "high", "medium", "low"


def extract_keywords(text: str, min_length: int = 4) -> list[str]:
    """
    Extract significant keywords from text.
    Filters out common words and short terms.
    """
    # Common words to exclude
    stopwords = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
        "are",
        "were",
        "been",
        "be",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "that",
        "this",
        "these",
        "those",
        "it",
        "its",
        "they",
        "their",
        "them",
        "he",
        "she",
        "his",
        "her",
        "we",
        "our",
        "you",
        "your",
        "i",
        "my",
        "me",
        "what",
        "which",
        "who",
        "whom",
        "how",
        "when",
        "where",
        "why",
        "about",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "all",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "only",
        "own",
        "same",
        "than",
        "too",
        "very",
        "just",
        "also",
        "now",
        "being",
        "think",
        "said",
        "says",
        "going",
        "really",
        "thing",
        "things",
        "something",
        "anything",
    }

    # Extract words
    words = re.findall(r"\b[a-zA-Z]+\b", text.lower())

    # Filter and deduplicate
    keywords = []
    seen = set()
    for word in words:
        if len(word) >= min_length and word not in stopwords and word not in seen:
            keywords.append(word)
            seen.add(word)

    return keywords


def generate_coverage_items(abstract_input) -> list[CoverageItem]:
    """
    Generate checklist items from AbstractInput.

    Args:
        abstract_input: AbstractInput object from abstract_pipeline

    Returns:
        List of CoverageItem objects to verify
    """
    items = []

    # Speaker/metadata coverage
    # Production metadata comes from parse_filename_metadata, which has no
    # "speaker" key — only "presenter" — so this item was never created (review G6).
    speaker_name = (abstract_input.metadata.get("speaker")
                    or abstract_input.metadata.get("presenter", ""))
    if speaker_name:
        # Extract last name for keyword matching
        name_parts = speaker_name.replace("Dr.", "").replace(".", "").split()
        name_keywords = [n.lower() for n in name_parts if len(n) > 2]

        items.append(
            CoverageItem(
                category="metadata",
                label=f"Speaker identified: {speaker_name}",
                required=True,
                keywords=name_keywords,
                source_text=speaker_name,
            )
        )

    # Topic coverage
    for topic in abstract_input.topics:
        topic_keywords = extract_keywords(topic.name)

        items.append(
            CoverageItem(
                category="topic",
                label=f"Topic ({topic.percentage}%): {topic.name}",
                required=topic.percentage >= 15,  # Required if major topic
                keywords=topic_keywords,
                source_text=topic.name,
            )
        )

    # Theme coverage
    for i, theme in enumerate(abstract_input.themes):
        theme_keywords = extract_keywords(theme.name) + extract_keywords(
            theme.description
        )

        items.append(
            CoverageItem(
                category="theme",
                label=f"Theme: {theme.name}",
                required=i == 0,  # First theme is required
                keywords=theme_keywords[:8],  # Limit keywords
                source_text=f"{theme.name}: {theme.description}",
            )
        )

    # Purpose coverage
    if abstract_input.opening_purpose == config.PURPOSE_EXTRACTION_FAILED:
        # A10/P1: purpose extraction failed transiently. We cannot confirm the
        # abstract covers the purpose, so keep the check REQUIRED and uncoverable
        # (no keywords) — validation must NOT silently pass on an unverified purpose.
        items.append(
            CoverageItem(
                category="purpose",
                label="Speaker's stated purpose (extraction FAILED - retry, unverified)",
                required=True,
                keywords=[],
                source_text=abstract_input.opening_purpose,
            )
        )
    elif (
        abstract_input.opening_purpose
        and abstract_input.opening_purpose != "Not explicitly stated"
    ):
        purpose_keywords = extract_keywords(abstract_input.opening_purpose)

        # A genuine "manually insert" absence (speaker stated no purpose) is optional.
        is_required = "manually insert" not in abstract_input.opening_purpose

        items.append(
            CoverageItem(
                category="purpose",
                label="Speaker's stated purpose",
                required=is_required,
                keywords=purpose_keywords[:6],
                source_text=abstract_input.opening_purpose,
            )
        )

    # Conclusion coverage
    if (
        abstract_input.closing_conclusion
        and abstract_input.closing_conclusion != "No explicit conclusion stated"
    ):
        conclusion_keywords = extract_keywords(
            abstract_input.closing_conclusion)

        items.append(
            CoverageItem(
                category="conclusion",
                label="Speaker's conclusion",
                required=True,
                keywords=conclusion_keywords[:6],
                source_text=abstract_input.closing_conclusion,
            )
        )

    # Q&A coverage (if significant and extractable). Q&A is only required when it
    # is a substantial share of the transcript and topics are high-signal.
    if abstract_input.qa_percentage >= QA_OPTIONAL_THRESHOLD and abstract_input.qa_topics:
        qa_keywords = []
        for topic in abstract_input.qa_topics:
            qa_keywords.extend(extract_keywords(topic))
        qa_keywords = list(dict.fromkeys(qa_keywords))[:8]

        if len(qa_keywords) >= 2:
            items.append(
                CoverageItem(
                    category="qa",
                    label=f"Q&A content ({abstract_input.qa_percentage}%)",
                    required=abstract_input.qa_percentage >= QA_REQUIRED_THRESHOLD,
                    keywords=qa_keywords,
                    source_text=", ".join(abstract_input.qa_topics),
                )
            )

    return items


def check_keyword_coverage(
    abstract: str, item: CoverageItem, threshold: int = 2
) -> tuple[bool, str]:
    """
    Check if abstract contains sufficient keywords for a coverage item.

    Args:
        abstract: Generated abstract text
        item: CoverageItem to verify
        threshold: Minimum keyword matches for "covered"

    Returns:
        (is_covered, confidence_level)
    """
    abstract_lower = abstract.lower()

    matches = [kw for kw in item.keywords if kw in abstract_lower]
    match_count = len(matches)
    total_keywords = len(item.keywords)

    if total_keywords == 0:
        # No keywords to ground on — DO NOT auto-pass (A11/P7). Return low
        # confidence (not covered) so the item is eligible for the LLM rescue pass
        # / human review rather than silently satisfied OR hard-failed with no
        # recovery (a short/stopword topic name legitimately yields no keywords).
        return False, "low"

    match_ratio = match_count / total_keywords

    if match_count >= threshold or match_ratio >= 0.5:
        return True, "high"
    elif match_count >= 1 or match_ratio >= 0.25:
        return True, "medium"
    else:
        return False, "low"


def validate_abstract_coverage(
    abstract: str, abstract_input, use_llm_verification: bool = False, api_client=None, model: str = config.AUX_MODEL, logger=None
) -> dict:
    """
    Validate abstract covers required content from source.

    Args:
        abstract: Generated abstract text
        abstract_input: AbstractInput used to generate abstract
        use_llm_verification: Whether to use LLM for low-confidence items
        api_client: Anthropic client (required if use_llm_verification=True)
        model: Model to use for LLM verification
        logger: Optional logger for warnings

    Returns:
        Validation results dict
    """
    items = generate_coverage_items(abstract_input)

    # A12: match keywords against the abstract BODY, not a leading `# Abstract`
    # header/label the model may have emitted.
    abstract = _strip_leading_scaffolding(abstract)

    # First pass: keyword matching
    for item in items:
        if item.source_text == config.PURPOSE_EXTRACTION_FAILED:
            # A10: purpose extraction failed transiently. Cannot verify coverage,
            # and the sentinel is meaningless to keyword/LLM checks. Mark
            # hard-uncovered with a DISTINCT confidence so it (a) never auto-passes
            # and (b) is excluded from the LLM rescue pass below (reserved for
            # genuinely low-confidence content items — A11).
            item.covered = False
            item.confidence = "extraction_failed"
            continue
        covered, confidence = check_keyword_coverage(abstract, item)
        item.covered = covered
        item.confidence = confidence

    # Second pass: LLM verification for low-confidence required items
    if use_llm_verification:
        low_confidence_required = [
            item for item in items if item.required and item.confidence == "low"
        ]
        if low_confidence_required and not api_client:
            # No client (no API key): these items could not be checked. Mark them
            # unverified so the status is ERROR (retry, never stored) rather than a
            # stored FAIL that outlives the missing key (sweep finding, P1).
            apply_llm_results(
                low_confidence_required, [None] * len(low_confidence_required))
            low_confidence_required = []

        if low_confidence_required:
            llm_results = verify_with_llm(
                abstract, low_confidence_required, api_client, model=model, logger=logger)
            apply_llm_results(low_confidence_required, llm_results)

    # Compile results
    required_items = [item for item in items if item.required]
    optional_items = [item for item in items if not item.required]

    required_covered = sum(1 for item in required_items if item.covered)
    optional_covered = sum(1 for item in optional_items if item.covered)

    if required_items:
        passed = all(item.covered for item in required_items)
    else:
        # No required coverage items could be derived — upstream topics/themes/
        # purpose/conclusion are missing or format-drifted. `all([]) == True` would
        # report a clean pass on a validation that checked NOTHING, so fail closed
        # (A9/P19). Sibling of the summary-coverage guard.
        passed = False
        if logger:
            logger.warning(
                "validate_abstract_coverage: zero required coverage items derived "
                "from abstract_input — upstream extraction missing/drifted; refusing "
                "to report PASS (A9)."
            )

    # Generate human review checklist for failures or low confidence
    needs_review = [
        item
        for item in items
        if not item.covered or item.confidence in ("low", "medium")
    ]

    return {
        "passed": passed,
        # Abstract coverage is advisory; zero required items is the A9 fail-closed case.
        "status": {"NONE": "FAIL"}.get(coverage_status(items), coverage_status(items)),
        "llm_unavailable": any(i.confidence == "llm_unavailable" for i in items),
        "required_coverage": f"{required_covered}/{len(required_items)}",
        "optional_coverage": f"{optional_covered}/{len(optional_items)}",
        "items": [
            {
                "category": item.category,
                "label": item.label,
                "required": item.required,
                "covered": item.covered,
                "confidence": item.confidence,
                "keywords_checked": item.keywords[:5],  # Show sample
            }
            for item in items
        ],
        "human_review_checklist": format_review_checklist(needs_review)
        if needs_review
        else None,
        "summary": generate_validation_summary(items, passed),
    }


# Item confidences meaning "could not be verified" (transient / upstream failure),
# as opposed to a verified miss. A required item left uncovered only for these
# reasons makes the coverage status ERROR (retry), not FAIL (review C-07 / P1).
UNVERIFIED_CONFIDENCES = ("llm_unavailable", "extraction_failed")


def verify_items_with_llm(content: str, items: list, api_client, content_type: str,
                          model: str = config.AUX_MODEL, logger=None,
                          source_text_limit: Optional[int] = None) -> list:
    """Ask the LLM whether ``content`` covers each item. Returns one entry per item:
    True / False, or None for every item when the call fails (API error, timeout,
    truncation), so the caller can report "could not verify" instead of "missing".

    Purpose: One LLM-rescue implementation for abstract and summary coverage
             (review F13 / STRUCT-04) that keeps a failed call distinct (C-07).
    Spec:    docs/plan_review_fixes_2026-10-04.md#R13 / #R14
    Tests:   tests/test_validator_gating_r15.py::test_r13a_short_yes_no_reply_accepted
    """
    items_text = "\n".join(
        f'{i + 1}. {item.label}: "{item.source_text[:source_text_limit]}"'
        for i, item in enumerate(items)
    )

    prompt_path = config.PROMPTS_DIR / config.PROMPT_VALIDATION_COVERAGE_FILENAME
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path}\n"
            f"Expected location: {config.PROMPTS_DIR}/{config.PROMPT_VALIDATION_COVERAGE_FILENAME}"
        )
    template = prompt_path.read_text(encoding="utf-8")

    prompt = (
        template.replace("{{content_type}}", content_type)
        .replace("{{content_type_upper}}", content_type.upper())
        .replace("{{content}}", content)
        .replace("{{items_text}}", items_text)
    )

    requested_max_tokens = max(512, 80 * len(items) + 64)
    max_tokens = cap_max_tokens_for_model(model, requested_max_tokens, logger=logger)

    try:
        response = call_claude_with_retry(
            client=api_client,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.0,  # Strict for validation
            logger=logger,
            min_length=2,  # a "YES\nNO" reply is legitimately short (review F13)
        )
    except Exception as e:  # noqa: BLE001 — reported as "could not verify", not a miss
        if logger:
            logger.warning("LLM coverage verification unavailable (%s); the affected "
                           "items are reported as unverified — retry.", e)
        return [None] * len(items)

    # One YES/NO answer per line, matched as whole words ("NOTE"/"NONE" in a
    # preamble must not count). If the number of answers doesn't match the number
    # of items, the mapping is unknown: every item is unverified, never a padded
    # False that would read as a checked miss (sweep finding, P1/P2).
    results: list = []
    for line in response.content[0].text.strip().upper().split("\n"):
        m = re.search(r"\b(YES|NO)\b", line)
        if m:
            results.append(m.group(1) == "YES")
    if len(results) != len(items):
        if logger:
            logger.warning("LLM coverage reply had %d answers for %d items; treating "
                           "them as unverified.", len(results), len(items))
        return [None] * len(items)
    return results


def verify_with_llm(abstract: str, items: list[CoverageItem], api_client, model: str = config.AUX_MODEL, logger=None) -> list:
    """Abstract LLM coverage rescue (see ``verify_items_with_llm``)."""
    return verify_items_with_llm(abstract, items, api_client, "abstract",
                                 model=model, logger=logger)


def apply_llm_results(items: list, llm_results: list) -> None:
    """Record LLM rescue results on the items: None -> "llm_unavailable" (the
    keyword result stands, marked unverified); True/False -> "llm_verified"."""
    for item, result in zip(items, llm_results):
        if result is None:
            item.confidence = "llm_unavailable"
        else:
            item.covered = result
            item.confidence = "llm_verified"


def coverage_status(items: list, gating_categories=None) -> str:
    """PASS / FAIL / ERROR over the required items (restricted to
    ``gating_categories`` when given).

    FAIL needs at least one required item that was checked and found missing;
    when every missing item is unverified (``UNVERIFIED_CONFIDENCES``) the status
    is ERROR (retryable). No required items at all is NONE — a deterministic
    condition the caller turns into PASS or FAIL with a reason (an ERROR here
    would re-run and block forever; sweep finding).

    Purpose: A gate-readable verdict for coverage validation (plan R14/R15).
    Spec:    docs/plan_review_fixes_2026-10-04.md#R15
    Tests:   tests/test_validator_gating_r15.py::test_r14b_unavailable_is_error
    """
    required = [i for i in items if i.required
                and (gating_categories is None or i.category in gating_categories)]
    if not required:
        return "NONE"
    missing = [i for i in required if not i.covered]
    if not missing:
        return "PASS"
    if any(i.confidence not in UNVERIFIED_CONFIDENCES for i in missing):
        return "FAIL"
    return "ERROR"


def format_review_checklist(items: list[CoverageItem]) -> str:
    """
    Format items needing review as human-readable checklist.
    """
    lines = ["## Human Review Checklist", ""]
    lines.append("The following items need manual verification:\n")

    for item in items:
        status = "❌ MISSING" if not item.covered else "⚠️ UNCERTAIN"
        required_tag = "[REQUIRED]" if item.required else "[optional]"

        lines.append(f"- {status} {required_tag} {item.label}")
        lines.append(
            f'  Source: "{item.source_text[:100]}..."'
            if len(item.source_text) > 100
            else f'  Source: "{item.source_text}"'
        )
        lines.append(f"  Keywords checked: {', '.join(item.keywords[:5])}")
        lines.append("")

    return "\n".join(lines)


def generate_validation_summary(items: list[CoverageItem], passed: bool) -> str:
    """Generate one-line summary of validation results."""
    required = [i for i in items if i.required]
    # required_pass = sum(1 for i in required if i.covered)

    if passed:
        low_confidence = sum(
            1 for i in items if i.confidence in ("low", "medium"))
        if low_confidence > 0:
            return f"PASSED with {low_confidence} low-confidence items - human review recommended"
        return "PASSED - all required items covered"
    else:
        missing = [i.label for i in required if not i.covered]
        return f"FAILED - missing required: {', '.join(missing[:3])}"


def generate_review_checklist(abstract_input) -> str:
    """
    Generate a pre-review checklist for human validators.

    Use this before abstract generation to understand what should be covered,
    or provide to human reviewer alongside the abstract.
    """
    items = generate_coverage_items(abstract_input)

    lines = [
        "# Abstract Coverage Checklist",
        "",
        "## Required Items (must be mentioned)",
        "",
    ]

    required = [i for i in items if i.required]
    for item in required:
        lines.append(f"- [ ] {item.label}")

    lines.extend(
        ["", "## Optional Items (should be mentioned if space permits)", ""])

    optional = [i for i in items if not i.required]
    for item in optional:
        lines.append(f"- [ ] {item.label}")

    lines.extend(
        [
            "",
            "## Structural Requirements",
            "",
            "- [ ] Opens with speaker identification and context",
            "- [ ] States central argument/purpose",
            "- [ ] Mentions key topics in presentation order",
            "- [ ] Includes conclusion or implications",
            (
                "- [ ] Q&A mentioned (required: "
                f"{abstract_input.qa_percentage >= QA_REQUIRED_THRESHOLD})"
            ),
            "",
            "## Constraints",
            "",
            "- [ ] Word count: 150-250 words",
            "- [ ] Third person, present tense",
            "- [ ] No citations or section references",
            "- [ ] No evaluative language",
            "- [ ] No bullet points",
        ]
    )

    return "\n".join(lines)


# === Integration with abstract_pipeline ===


def validate_and_report(
    abstract: str, abstract_input, api_client=None, model: str = config.AUX_MODEL, logger=None
) -> tuple[bool, str]:
    """
    Convenience function: validate and return pass/fail with report.

    Args:
        abstract: Generated abstract
        abstract_input: Input used for generation
        api_client: Optional, for LLM verification of uncertain items
        model: Model to use for LLM verification

    Returns:
        (passed: bool, report: str)
    """
    # Structural validation first
    target_word_count = getattr(abstract_input, "target_word_count", 250)
    structural = validate_structural(abstract, target_word_count)
    
    # Fail only on fatal issues
    if not structural["valid"]:
        return False, f"Structural validation failed: {structural['issues']}"

    # Coverage validation
    coverage = validate_abstract_coverage(
        abstract,
        abstract_input,
        use_llm_verification=True,  # no client -> items reported unverified
        api_client=api_client,
        model=model,
        logger=logger,
    )

    report_lines = [
        f"Validation: {coverage['summary']}",
        f"Required coverage: {coverage['required_coverage']}",
        f"Optional coverage: {coverage['optional_coverage']}",
        f"Word count: {structural['word_count']}",
    ]
    if coverage["llm_unavailable"]:
        report_lines.append("LLM verification unavailable — some items are unverified; retry.")

    # Add structural warnings to report
    if structural["warnings"]:
        report_lines.append("\nStructural Warnings:")
        report_lines.extend([f"  - {w}" for w in structural["warnings"]])

    if coverage["human_review_checklist"]:
        report_lines.extend(["", coverage["human_review_checklist"]])

    return coverage["passed"], "\n".join(report_lines)


# Title-case word incl. common Latin accents (À-Ö,Ø-Þ upper / à-ö,ø-ÿ lower).
_NAME_WORD = r"[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+"
# Use [ \t]+ (not \s+) between name words: a real multi-word proper name is on
# ONE line, so a match must never span a newline/paragraph break.
_NAME_SPAN = re.compile(rf"\b{_NAME_WORD}(?:[ \t]+{_NAME_WORD})+\b")

# Inline leading bold label with an optional bullet: "**Term** — def",
# "**Term:** def", "- **Topic.** desc". The separator must be present EITHER as
# trailing punctuation INSIDE the bold (colon/period/dash) OR after the closing
# "**" (em/en-dash, colon, hyphen) — a bare "**bold** prose" with no separator is
# NOT a label and is left intact.
_INLINE_BOLD_LABEL = re.compile(
    r"^\s*(?:[-*•]\s+)?\*\*(?P<label>[^*\n]+?)(?:[.:—–-]\*\*|\*\*[ \t]*[:—–-])[ \t]*(?P<rest>.*)$"
)
_YAML_LINE = re.compile(r"^(?:[A-Za-z_][\w -]*:(?:\s|$)|\s*-\s|\s+\S|#)")


def _strip_front_matter(text: str) -> str:
    """Strip a leading ``---`` … ``---`` block only when every non-blank line in it
    is YAML-shaped (``key: value``, a list item, an indented continuation, or a
    comment). A ``---`` horizontal rule followed by prose is NOT front matter;
    stripping it hid that prose from both blockers (review F2, plan R6.c)."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    body = [ln for ln in text[3:end].split("\n") if ln.strip()]
    if all(_YAML_LINE.match(ln) for ln in body):
        return text[end + 4:].lstrip()
    return text


def scaffolding_name_spans(text: str) -> list[str]:
    """Multi-word Title-Case spans inside the lines ``_strip_scaffolding`` removes
    (headings, bold-only lines, inline bold labels), excluding generic heading
    phrases. The entity check and the faithfulness judge ground these the same way
    as prose names, so a name in a heading or label is not invisible.

    Purpose: Close the scaffolding blind spot of both hard blockers (review F2).
    Spec:    docs/plan_review_fixes_2026-10-04.md#R6
    Tests:   tests/test_faithfulness_scaffolding_r6.py::test_r6b_entity_grounding_flags_name_in_scaffolding
    """
    t = _strip_fenced_block(_strip_front_matter((text or "").strip()))
    exclude = config.SCAFFOLDING_HEADING_PHRASES
    spans: list[str] = []
    for line in t.split("\n"):
        s = line.strip()
        heading = re.match(r"^#{1,6}\s+(.*)$", s)
        if heading:
            removed = heading.group(1)
        elif re.match(r"^\*\*[^*\n]+\*\*\s*$", s):
            removed = s
        else:
            label = _INLINE_BOLD_LABEL.match(s)
            removed = label.group("label") if label else None
        if removed is None:
            continue
        for name in _NAME_SPAN.findall(removed.replace("**", "")):
            if name.lower() not in exclude and name not in spans:
                spans.append(name)
    return spans


def _strip_fenced_block(text: str) -> str:
    """Strip a LEADING fenced code block (```yaml … ``` or ``` … ```).

    The overview/blog artifacts front-load their SEO/Q&A metadata in a fenced
    ```yaml block rather than a ``---`` front-matter block. A fenced block is
    metadata, not artifact content — its ``slug:``/``focus_keyword:``/``q:``/``a:``
    lines are not claims and not proper names. Stripping it here (single source of
    truth) keeps every downstream consumer from re-flagging it.
    """
    m = re.match(r"^\s*```[^\n]*\n.*?\n```[ \t]*\n?", text, re.DOTALL)
    return text[m.end():] if m else text


def _strip_leading_scaffolding(text: str) -> str:
    """Remove leading YAML front matter and markdown heading/bold-label lines the
    model sometimes emits despite the prompt's "no headers" instruction (e.g. a
    leading ``# Abstract``), so they aren't counted as abstract body (A12).
    """
    t = _strip_front_matter((text or "").strip())
    t = _strip_fenced_block(t)
    lines = t.split("\n")
    while lines and (
        not lines[0].strip()
        or re.match(r"^\s*#{1,6}\s+", lines[0])          # markdown heading
        or re.match(r"^\s*\*\*[^*\n]+\*\*\s*$", lines[0])  # bold-only label line
    ):
        lines.pop(0)
    return "\n".join(lines).strip()


def _strip_scaffolding(text: str) -> str:
    """Remove YAML front matter and ALL markdown structural lines the model emits
    in prose-and-heading artifacts (blog/overview/summary) — every ``#`` heading,
    every bold-only label line, and inline leading bold labels (definition-list /
    topic-list style) — so the name detector scans prose only and never treats a
    Title-Case heading or concept label ("Key Takeaways", "Role Absorption") as a
    fabricated proper name.

    A superset of ``_strip_leading_scaffolding`` (which strips only LEADING
    scaffolding, for word-count purposes). Pure-prose artifacts contain no
    mid-document headings, so this is a no-op there and the abstract's calibrated
    0-false-positive behaviour is unchanged.
    """
    t = _strip_front_matter((text or "").strip())
    t = _strip_fenced_block(t)
    # Inline bold labels keep only their definition/description (see
    # _INLINE_BOLD_LABEL); the label's names are checked via scaffolding_name_spans.
    kept: list[str] = []
    for line in t.split("\n"):
        s = line.strip()
        if not s:
            kept.append(line)
            continue
        if re.match(r"^#{1,6}\s+", s):            # markdown heading line
            continue
        if re.match(r"^\*\*[^*\n]+\*\*\s*$", s):   # bold-only label line
            continue
        m = _INLINE_BOLD_LABEL.match(s)
        kept.append(m.group("rest") if m else line)
    return "\n".join(kept).strip()


def validate_structural(abstract: str, target_word_count: int = 250) -> dict:
    """
    Structural validation (from original validate_abstract).
    """
    issues = []
    warnings = []
    # A12: count the abstract BODY, not a forbidden leading `# Abstract` header.
    word_count = len(_strip_leading_scaffolding(abstract).split())

    # Allow 20% tolerance - Now a WARNING. The upper bound is also hard-capped
    # below ABSTRACT_HARD_MAX_WORDS so an abstract of >= 250 words is always
    # flagged as too long, independent of the target.
    min_words = int(target_word_count * 0.8)
    max_words = min(int(target_word_count * 1.2), config.ABSTRACT_HARD_MAX_WORDS - 1)

    if word_count < min_words:
        warnings.append(f"Length check: Too short ({word_count} words, minimum {min_words})")
    elif word_count > max_words:
        warnings.append(f"Length check: Too long ({word_count} words, maximum {max_words})")

    if re.search(r"Section \d+", abstract):
        issues.append("Contains section references")

    if re.search(r"^\s*[-•*]\s", abstract, re.MULTILINE):
        issues.append("Contains bullet points")

    # Evaluative language - Now a WARNING
    evaluative_terms = ["important", "valuable",
                        "insightful", "excellent", "crucial"]
    found_evaluative = [
        t for t in evaluative_terms if t.lower() in abstract.lower()]
    if found_evaluative:
        warnings.append(f"Evaluative language check: Contains {found_evaluative}")

    return {
        "valid": len(issues) == 0, 
        "word_count": word_count, 
        "issues": issues,
        "warnings": warnings
    }


# === Example Usage ===

if __name__ == "__main__":
    # Mock AbstractInput for testing
    class MockTopic:
        def __init__(self, name, percentage):
            self.name = name
            self.percentage = percentage

    class MockTheme:
        def __init__(self, name, description):
            self.name = name
            self.description = description

    class MockInput:
        def __init__(self):
            self.metadata = {"speaker": "Dr. Michael Kerr"}
            self.topics = [
                MockTopic("Paradigm shifts in astronomy", 28),
                MockTopic("Physical to biological carryover", 22),
                MockTopic("Cancer research parallels", 18),
            ]
            self.themes = [
                MockTheme(
                    "Cross-disciplinary foundations",
                    "Physical sciences inform biological understanding",
                )
            ]
            self.opening_purpose = "To explore where the roots of Bowen theory reside"
            self.closing_conclusion = "Answers extend beyond our species"
            self.qa_percentage = 32
            self.qa_topics = ["chronic anxiety", "determination"]

    mock_input = MockInput()

    # Good abstract (covers content)
    good_abstract = """
    Dr. Michael Kerr presents a webinar exploring the historical and scientific 
    foundations of Bowen family systems theory. Kerr examines where the roots of 
    this theory reside, arguing that cross-disciplinary investigation offers the 
    most promising path. The presentation traces paradigm shifts in astronomy from 
    geocentric to heliocentric models, then examines the carryover from physical 
    to biological systems, with particular attention to cancer research parallels. 
    Kerr concludes that answers extend beyond the boundaries of our species. 
    Audience questions explored chronic anxiety and determination in recovery.
    """

    # Bad abstract (missing key content)
    bad_abstract = """
    Dr. Kerr gives an interesting presentation about science and theory. He 
    discusses various historical topics and makes some observations about 
    biology. The audience asked questions at the end.
    """

    print("=== Testing Good Abstract ===")
    checklist = generate_review_checklist(mock_input)
    print(checklist)
    print("\n" + "=" * 50 + "\n")

    result = validate_abstract_coverage(good_abstract, mock_input)
    print(f"Passed: {result['passed']}")
    print(f"Summary: {result['summary']}")
    print(f"Required: {result['required_coverage']}")

    print("\n=== Testing Bad Abstract ===")
    result = validate_abstract_coverage(bad_abstract, mock_input)
    print(f"Passed: {result['passed']}")
    print(f"Summary: {result['summary']}")
    if result["human_review_checklist"]:
        print(result["human_review_checklist"])
