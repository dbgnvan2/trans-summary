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
from typing import Optional

import config
from transcript_utils import call_claude_with_retry


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
    speaker_name = abstract_input.metadata.get("speaker", "")
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
    if (
        abstract_input.opening_purpose
        and abstract_input.opening_purpose != "Not explicitly stated"
    ):
        purpose_keywords = extract_keywords(abstract_input.opening_purpose)

        items.append(
            CoverageItem(
                category="purpose",
                label="Speaker's stated purpose",
                required=True,
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

    # Q&A coverage (if significant)
    if abstract_input.qa_percentage > 20 and abstract_input.qa_topics:
        qa_keywords = []
        for topic in abstract_input.qa_topics:
            qa_keywords.extend(extract_keywords(topic))

        items.append(
            CoverageItem(
                category="qa",
                label=f"Q&A content ({abstract_input.qa_percentage}%)",
                required=True,
                keywords=qa_keywords[:8],
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
        return True, "high"  # No keywords to check

    match_ratio = match_count / total_keywords

    if match_count >= threshold or match_ratio >= 0.5:
        return True, "high"
    elif match_count >= 1 or match_ratio >= 0.25:
        return True, "medium"
    else:
        return False, "low"


def validate_abstract_coverage(
    abstract: str, abstract_input, use_llm_verification: bool = False, api_client=None, model: str = config.AUX_MODEL
) -> dict:
    """
    Validate abstract covers required content from source.

    Args:
        abstract: Generated abstract text
        abstract_input: AbstractInput used to generate abstract
        use_llm_verification: Whether to use LLM for low-confidence items
        api_client: Anthropic client (required if use_llm_verification=True)
        model: Model to use for LLM verification

    Returns:
        Validation results dict
    """
    items = generate_coverage_items(abstract_input)

    # First pass: keyword matching
    for item in items:
        covered, confidence = check_keyword_coverage(abstract, item)
        item.covered = covered
        item.confidence = confidence

    # Second pass: LLM verification for low-confidence required items
    if use_llm_verification and api_client:
        low_confidence_required = [
            item for item in items if item.required and item.confidence == "low"
        ]

        if low_confidence_required:
            llm_results = verify_with_llm(
                abstract, low_confidence_required, api_client, model=model)
            for item, result in zip(low_confidence_required, llm_results):
                item.covered = result
                item.confidence = "llm_verified"

    # Compile results
    required_items = [item for item in items if item.required]
    optional_items = [item for item in items if not item.required]

    required_covered = sum(1 for item in required_items if item.covered)
    optional_covered = sum(1 for item in optional_items if item.covered)

    passed = all(item.covered for item in required_items)

    # Generate human review checklist for failures or low confidence
    needs_review = [
        item
        for item in items
        if not item.covered or item.confidence in ("low", "medium")
    ]

    return {
        "passed": passed,
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


def verify_with_llm(abstract: str, items: list[CoverageItem], api_client, model: str = config.AUX_MODEL) -> list[bool]:
    """
    Use LLM to verify coverage of specific items.

    Batches items into single API call for efficiency.
    """
    items_text = "\n".join(
        [f'{i + 1}. {item.label}: "{item.source_text}"' for i,
            item in enumerate(items)]
    )

    prompt_path = config.PROMPTS_DIR / config.PROMPT_VALIDATION_COVERAGE_FILENAME
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path}\n"
            f"Expected location: {config.PROMPTS_DIR}/{config.PROMPT_VALIDATION_COVERAGE_FILENAME}"
        )
    template = prompt_path.read_text(encoding="utf-8")

    prompt = (
        template.replace("{{content_type}}", "abstract")
        .replace("{{content_type_upper}}", "ABSTRACT")
        .replace("{{content}}", abstract)
        .replace("{{items_text}}", items_text)
    )

    # Use centralized call with retry
    response = call_claude_with_retry(
        client=api_client,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=100,
        temperature=0.0,  # Strict for validation
    )

    response_text = response.content[0].text.strip()
    lines = response_text.upper().split("\n")

    results = []
    for line in lines:
        if "YES" in line:
            results.append(True)
        elif "NO" in line:
            results.append(False)

    # Pad with False if response incomplete
    while len(results) < len(items):
        results.append(False)

    return results[: len(items)]


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
            f"- [ ] Q&A mentioned (required: {abstract_input.qa_percentage > 20})",
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
    abstract: str, abstract_input, api_client=None, model: str = config.AUX_MODEL
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
        use_llm_verification=api_client is not None,
        api_client=api_client,
        model=model,
    )

    report_lines = [
        f"Validation: {coverage['summary']}",
        f"Required coverage: {coverage['required_coverage']}",
        f"Optional coverage: {coverage['optional_coverage']}",
        f"Word count: {structural['word_count']}",
    ]

    # Add structural warnings to report
    if structural["warnings"]:
        report_lines.append("\nStructural Warnings:")
        report_lines.extend([f"  - {w}" for w in structural["warnings"]])

    if coverage["human_review_checklist"]:
        report_lines.extend(["", coverage["human_review_checklist"]])

    return coverage["passed"], "\n".join(report_lines)


def validate_structural(abstract: str, target_word_count: int = 250) -> dict:
    """
    Structural validation (from original validate_abstract).
    """
    issues = []
    warnings = []
    word_count = len(abstract.split())

    # Allow 20% tolerance - Now a WARNING
    min_words = int(target_word_count * 0.8)
    max_words = int(target_word_count * 1.2)

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
