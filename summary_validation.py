"""
Summary Validation Module
Validates generated summaries for semantic coverage and proportionality.

Four-tier validation:
1. Structural checks (word count, prohibited elements)
2. Section presence (opening, body paragraphs, Q&A, closing)
3. Topic coverage (keyword matching per topic)
4. Proportionality verification (word allocation adherence)

Usage:
    from summary_validation import validate_summary_coverage, generate_review_checklist
    
    checklist = generate_review_checklist(summary_input)
    validation = validate_summary_coverage(summary, summary_input)
    
    if not validation["passed"]:
        print(validation["human_review_checklist"])
"""

import re
from dataclasses import dataclass
from typing import Optional
import config


@dataclass
class CoverageItem:
    """Single item to verify in summary."""
    category: str          # "metadata", "topic", "qa", "opening", "closing"
    label: str             # Human-readable label
    required: bool         # Must be present
    keywords: list[str]    # Terms that indicate coverage
    source_text: str       # Original text for reference
    expected_words: int    # Expected word count for this item
    covered: Optional[bool] = None
    confidence: Optional[str] = None
    actual_words: Optional[int] = None


def extract_keywords(text: str, min_length: int = 4) -> list[str]:
    """Extract significant keywords from text."""
    stopwords = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
        'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'must', 'that', 'this', 'these',
        'those', 'it', 'its', 'they', 'their', 'them', 'he', 'she', 'his',
        'her', 'we', 'our', 'you', 'your', 'what', 'which', 'who', 'whom',
        'how', 'when', 'where', 'why', 'about', 'into', 'through', 'during',
        'before', 'after', 'above', 'below', 'between', 'under', 'again',
        'further', 'then', 'once', 'here', 'there', 'all', 'each', 'few',
        'more', 'most', 'other', 'some', 'such', 'only', 'own', 'same',
        'than', 'too', 'very', 'just', 'also', 'now', 'being', 'think',
        'said', 'says', 'going', 'really', 'thing', 'things', 'something'
    }

    words = re.findall(r'\b[a-zA-Z]+\b', text.lower())

    keywords = []
    seen = set()
    for word in words:
        if len(word) >= min_length and word not in stopwords and word not in seen:
            keywords.append(word)
            seen.add(word)

    return keywords


def generate_coverage_items(summary_input) -> list[CoverageItem]:
    """
    Generate checklist items from SummaryInput.
    """
    items = []

    # Speaker/metadata
    speaker = summary_input.metadata.get("speaker", "")
    if speaker:
        name_parts = speaker.replace("Dr.", "").replace(".", "").split()
        name_keywords = [n.lower() for n in name_parts if len(n) > 2]

        items.append(CoverageItem(
            category="metadata",
            label=f"Speaker identified: {speaker}",
            required=True,
            keywords=name_keywords,
            source_text=speaker,
            expected_words=0  # Part of opening
        ))

    # Opening section
    if summary_input.opening.stated_purpose and "not explicitly stated" not in summary_input.opening.stated_purpose.lower():
        items.append(CoverageItem(
            category="opening",
            label="Opening: stated purpose",
            required=True,
            keywords=extract_keywords(
                summary_input.opening.stated_purpose)[:6],
            source_text=summary_input.opening.stated_purpose,
            expected_words=summary_input.opening.word_allocation
        ))

    # Each topic in body
    for topic in summary_input.body.topics:
        topic_keywords = extract_keywords(topic.name)

        # Add keywords from key points
        for point in topic.key_points[:3]:
            topic_keywords.extend(extract_keywords(point)[:2])

        items.append(CoverageItem(
            category="topic",
            label=f"Topic ({topic.percentage}%): {topic.name[:50]}",
            required=topic.percentage >= 10,  # Required if significant topic
            keywords=list(dict.fromkeys(topic_keywords))[:10],  # Dedupe, limit
            source_text=topic.name,
            expected_words=topic.word_allocation
        ))

    # Q&A section
    if summary_input.qa.include:
        qa_keywords = []
        for qt in summary_input.qa.question_types:
            qa_keywords.extend(extract_keywords(qt))

        items.append(CoverageItem(
            category="qa",
            label=f"Q&A content ({summary_input.qa.percentage}%)",
            required=True,
            keywords=qa_keywords[:8],
            source_text=", ".join(summary_input.qa.question_types),
            expected_words=summary_input.qa.word_allocation
        ))

    # Closing section
    if summary_input.closing.conclusion and "no explicit conclusion" not in summary_input.closing.conclusion.lower():
        items.append(CoverageItem(
            category="closing",
            label="Closing: conclusion",
            required=True,
            keywords=extract_keywords(summary_input.closing.conclusion)[:6],
            source_text=summary_input.closing.conclusion,
            expected_words=summary_input.closing.word_allocation
        ))

    return items


def segment_summary(summary: str) -> dict:
    """
    Attempt to segment summary into structural sections.

    Returns dict with paragraph texts and estimated word counts.
    """
    # Remove markdown headers before splitting to avoid counting them as paragraphs
    summary_clean = re.sub(r'(?:^|\n)#+\s*.*?(?=\n|$)', '', summary)

    # Split into paragraphs
    paragraphs = [p.strip() for p in summary_clean.split('\n\n') if p.strip()]

    # Filter out potential title paragraphs (very short, at start) that survived regex
    if paragraphs and len(paragraphs[0].split()) < 5:
        # Check if it looks like a title (no terminal punctuation or just a label)
        if not paragraphs[0].endswith('.') or paragraphs[0].lower() in ['summary', 'abstract', 'introduction']:
            paragraphs = paragraphs[1:]

    if not paragraphs:
        paragraphs = [summary]

    segments = {
        "paragraphs": paragraphs,
        "paragraph_words": [len(p.split()) for p in paragraphs],
        "total_words": len(summary.split()),
        "paragraph_count": len(paragraphs)
    }

    # Heuristic section identification
    if len(paragraphs) >= 3:
        segments["opening"] = paragraphs[0]
        segments["opening_words"] = len(paragraphs[0].split())

        segments["closing"] = paragraphs[-1]
        segments["closing_words"] = len(paragraphs[-1].split())

        segments["body"] = paragraphs[1:-1]
        segments["body_words"] = sum(len(p.split()) for p in paragraphs[1:-1])

    return segments


def check_keyword_coverage(
    text: str,
    item: CoverageItem,
    threshold: int = 2
) -> tuple[bool, str]:
    """Check if text contains sufficient keywords for coverage item."""
    text_lower = text.lower()

    matches = [kw for kw in item.keywords if kw in text_lower]
    match_count = len(matches)
    total_keywords = len(item.keywords)

    if total_keywords == 0:
        return True, "high"

    match_ratio = match_count / total_keywords

    if match_count >= threshold or match_ratio >= 0.4:
        return True, "high"
    elif match_count >= 1 or match_ratio >= 0.2:
        return True, "medium"
    else:
        return False, "low"


def check_proportionality(
    summary: str,
    summary_input,
    tolerance: float = 0.3
) -> dict:
    """
    Check if summary respects word allocation proportions.

    Args:
        summary: Generated summary text
        summary_input: SummaryInput with allocations
        tolerance: Acceptable deviation (0.3 = 30%)

    Returns:
        Dict with proportionality analysis
    """
    segments = segment_summary(summary)
    total_words = segments["total_words"]
    target_words = summary_input.target_word_count

    results = {
        "total_words": total_words,
        "target_words": target_words,
        "total_deviation": abs(total_words - target_words) / target_words,
        "sections": []
    }

    # Helper for dynamic tolerance
    def get_tolerance(expected_count, section_name=""):
        if section_name == "Closing" and expected_count < 50:
            return 2.5  # 250% tolerance for short closing sections
        elif expected_count < 100:
            return 0.5  # 50% for very small sections
        if expected_count < 200:
            return 0.4  # 40% for small sections
        return tolerance

    # Check opening
    if "opening_words" in segments:
        expected = summary_input.opening.word_allocation
        actual = segments["opening_words"]
        deviation = abs(actual - expected) / expected if expected > 0 else 0
        local_tol = get_tolerance(expected, "Opening")

        results["sections"].append({
            "name": "Opening",
            "expected": expected,
            "actual": actual,
            "deviation": deviation,
            "within_tolerance": deviation <= local_tol
        })

    # Check closing
    if "closing_words" in segments:
        expected = summary_input.closing.word_allocation
        actual = segments["closing_words"]
        deviation = abs(actual - expected) / expected if expected > 0 else 0
        local_tol = get_tolerance(expected, "Closing")

        results["sections"].append({
            "name": "Closing",
            "expected": expected,
            "actual": actual,
            "deviation": deviation,
            "within_tolerance": deviation <= local_tol
        })

    # Check body total
    if "body_words" in segments:
        expected = summary_input.body.word_allocation
        actual = segments["body_words"]
        deviation = abs(actual - expected) / expected if expected > 0 else 0
        local_tol = get_tolerance(expected, "Body (total)")

        results["sections"].append({
            "name": "Body (total)",
            "expected": expected,
            "actual": actual,
            "deviation": deviation,
            "within_tolerance": deviation <= local_tol
        })

    # Overall assessment
    results["proportionality_ok"] = (
        results["total_deviation"] <= tolerance and
        all(s["within_tolerance"] for s in results["sections"])
    )

    return results


def validate_summary_coverage(
    summary: str,
    summary_input,
    use_llm_verification: bool = False,
    api_client=None
) -> dict:
    """
    Validate summary covers required content with appropriate proportions.

    Args:
        summary: Generated summary text
        summary_input: SummaryInput used for generation
        use_llm_verification: Whether to use LLM for low-confidence items
        api_client: Anthropic client (required if use_llm_verification=True)

    Returns:
        Validation results dict
    """
    items = generate_coverage_items(summary_input)

    # Keyword coverage check
    for item in items:
        covered, confidence = check_keyword_coverage(summary, item)
        item.covered = covered
        item.confidence = confidence

    # LLM verification for low-confidence required items
    if use_llm_verification and api_client:
        low_confidence_required = [
            item for item in items
            if item.required and item.confidence == "low"
        ]

        if low_confidence_required:
            llm_results = verify_with_llm(
                summary, low_confidence_required, api_client)
            for item, result in zip(low_confidence_required, llm_results):
                item.covered = result
                item.confidence = "llm_verified"

    # Proportionality check
    proportionality = check_proportionality(summary, summary_input)

    # Compile results
    required_items = [item for item in items if item.required]
    optional_items = [item for item in items if not item.required]

    required_covered = sum(1 for item in required_items if item.covered)
    optional_covered = sum(1 for item in optional_items if item.covered)

    coverage_passed = all(item.covered for item in required_items)

    # Overall pass requires both coverage and proportionality
    passed = coverage_passed and proportionality["proportionality_ok"]

    # Generate human review checklist
    needs_review = [
        item for item in items
        if not item.covered or item.confidence in ("low", "medium")
    ]

    # Add proportionality issues to review
    proportion_issues = [
        s for s in proportionality["sections"]
        if not s["within_tolerance"]
    ]

    return {
        "passed": passed,
        "coverage_passed": coverage_passed,
        "proportionality_passed": proportionality["proportionality_ok"],
        "required_coverage": f"{required_covered}/{len(required_items)}",
        "optional_coverage": f"{optional_covered}/{len(optional_items)}",
        "word_count": {
            "actual": proportionality["total_words"],
            "target": proportionality["target_words"],
            "deviation": f"{proportionality['total_deviation']*100:.1f}%"
        },
        "items": [
            {
                "category": item.category,
                "label": item.label,
                "required": item.required,
                "covered": item.covered,
                "confidence": item.confidence,
                "expected_words": item.expected_words,
                "keywords_checked": item.keywords[:5]
            }
            for item in items
        ],
        "proportionality": proportionality,
        "human_review_checklist": format_review_checklist(
            needs_review, proportion_issues
        ) if needs_review or proportion_issues else None,
        "summary": generate_validation_summary(
            items, passed, coverage_passed, proportionality["proportionality_ok"]
        )
    }


def verify_with_llm(
    summary: str,
    items: list[CoverageItem],
    api_client
) -> list[bool]:
    """Use LLM to verify coverage of specific items."""
    items_text = "\n".join([
        f"{i+1}. {item.label}: \"{item.source_text[:100]}\""
        for i, item in enumerate(items)
    ])

    prompt_path = config.PROMPTS_DIR / config.PROMPT_VALIDATION_COVERAGE_FILENAME
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path}\n"
            f"Expected location: {config.PROMPTS_DIR}/{config.PROMPT_VALIDATION_COVERAGE_FILENAME}"
        )
    template = prompt_path.read_text(encoding='utf-8')

    prompt = template.replace("{{content_type}}", "summary") \
                     .replace("{{content_type_upper}}", "SUMMARY") \
                     .replace("{{content}}", summary) \
                     .replace("{{items_text}}", items_text)

    response = api_client.messages.create(
        model=config.AUX_MODEL,
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = response.content[0].text.strip()
    lines = response_text.upper().split('\n')

    results = []
    for line in lines:
        if 'YES' in line:
            results.append(True)
        elif 'NO' in line:
            results.append(False)

    while len(results) < len(items):
        results.append(False)

    return results[:len(items)]


def format_review_checklist(
    coverage_items: list[CoverageItem],
    proportion_issues: list[dict]
) -> str:
    """Format items needing review as human-readable checklist."""
    lines = ["## Human Review Checklist", ""]

    if coverage_items:
        lines.append("### Coverage Issues\n")

        for item in coverage_items:
            status = "❌ MISSING" if not item.covered else "⚠️ UNCERTAIN"
            required_tag = "[REQUIRED]" if item.required else "[optional]"

            lines.append(f"- {status} {required_tag} {item.label}")
            source_display = item.source_text[:80] + "..." if len(
                item.source_text) > 80 else item.source_text
            lines.append(f"  Source: \"{source_display}\"")
            lines.append(f"  Expected ~{item.expected_words} words")
            lines.append(f"  Keywords: {', '.join(item.keywords[:5])}")
            lines.append("")

    if proportion_issues:
        lines.append("### Proportionality Issues\n")

        for issue in proportion_issues:
            deviation_pct = issue["deviation"] * 100
            direction = "over" if issue["actual"] > issue["expected"] else "under"

            lines.append(
                f"- ⚠️ {issue['name']}: {direction} by {deviation_pct:.0f}%")
            lines.append(
                f"  Expected: ~{issue['expected']} words, Actual: {issue['actual']} words")
            lines.append("")

    return "\n".join(lines)


def generate_validation_summary(
    items: list[CoverageItem],
    passed: bool,
    coverage_passed: bool,
    proportionality_passed: bool
) -> str:
    """Generate one-line summary of validation results."""
    if passed:
        low_confidence = sum(
            1 for i in items if i.confidence in ("low", "medium"))
        if low_confidence > 0:
            return f"PASSED with {low_confidence} low-confidence items - human review recommended"
        return "PASSED - all requirements met"

    issues = []
    if not coverage_passed:
        required = [i for i in items if i.required]
        missing = [i.label for i in required if not i.covered]
        issues.append(f"missing: {', '.join(missing[:2])}")

    if not proportionality_passed:
        issues.append("word allocation issues")

    return f"FAILED - {'; '.join(issues)}"


def generate_review_checklist(summary_input) -> str:
    """
    Generate a pre-review checklist for human validators.
    """
    items = generate_coverage_items(summary_input)

    lines = [
        "# Summary Coverage Checklist",
        "",
        f"**Target word count:** {summary_input.target_word_count}",
        "",
        "## Required Items",
        ""
    ]

    required = [i for i in items if i.required]
    for item in required:
        lines.append(f"- [ ] {item.label} (~{item.expected_words} words)")

    lines.extend(["", "## Optional Items", ""])

    optional = [i for i in items if not i.required]
    for item in optional:
        lines.append(f"- [ ] {item.label} (~{item.expected_words} words)")

    lines.extend([
        "",
        "## Word Allocation",
        "",
        f"- Opening: {summary_input.opening.word_allocation} words",
        f"- Body: {summary_input.body.word_allocation} words",
    ])

    for topic in summary_input.body.topics:
        lines.append(
            f"  - {topic.name[:40]}...: {topic.word_allocation} words")

    if summary_input.qa.include:
        lines.append(f"- Q&A: {summary_input.qa.word_allocation} words")

    lines.append(f"- Closing: {summary_input.closing.word_allocation} words")

    lines.extend([
        "",
        "## Structural Requirements",
        "",
        "- [ ] Opens with speaker identification",
        "- [ ] States thesis/purpose clearly",
        "- [ ] Topics covered in chronological order",
        "- [ ] Transitions between topics",
        f"- [ ] Q&A section included: {summary_input.qa.include}",
        "- [ ] Closes with conclusion",
        "",
        "## Constraints",
        "",
        f"- [ ] Word count: {summary_input.target_word_count} ± 15%",
        "- [ ] Third person, present tense",
        "- [ ] No citations or section references",
        "- [ ] No evaluative language",
        "- [ ] No bullet points",
        "- [ ] Chronological order maintained"
    ])

    return "\n".join(lines)


# === Structural Validation ===

def validate_structural(summary: str, target_word_count: int) -> dict:
    """Structural validation for summary."""
    issues = []
    word_count = len(summary.split())

    # Word count check (±20% tolerance)
    min_words = int(target_word_count * 0.80)
    max_words = int(target_word_count * 1.20)

    if word_count < min_words:
        issues.append(f"Too short: {word_count} words (minimum {min_words})")
    elif word_count > max_words:
        issues.append(f"Too long: {word_count} words (maximum {max_words})")

    # Paragraph check
    paragraphs = [p for p in summary.split('\n\n') if p.strip()]
    if len(paragraphs) < 3:
        issues.append(f"Too few paragraphs: {len(paragraphs)} (minimum 3)")

    # Prohibited elements
    if re.search(r'Section \d+', summary):
        issues.append("Contains section references")

    if re.search(r'^\s*[-•*]\s', summary, re.MULTILINE):
        issues.append("Contains bullet points")

    # Removed 'important', 'significant', 'crucial' as they often reflect speaker's emphasis
    evaluative_terms = config.EVALUATIVE_TERMS
    found_evaluative = [
        t for t in evaluative_terms if t.lower() in summary.lower()]
    if found_evaluative:
        issues.append(f"Contains evaluative language: {found_evaluative}")

    return {
        "valid": len(issues) == 0,
        "word_count": word_count,
        "paragraph_count": len(paragraphs),
        "issues": issues
    }


# === Convenience Function ===

def validate_and_report(
    summary: str,
    summary_input,
    api_client=None
) -> tuple[bool, str]:
    """
    Validate summary and return pass/fail with report.
    """
    # Structural validation
    structural = validate_structural(summary, summary_input.target_word_count)

    if not structural["valid"]:
        report = f"Structural validation failed:\n" + \
            "\n".join(f"  - {i}" for i in structural["issues"])
        return False, report

    # Coverage validation
    coverage = validate_summary_coverage(
        summary,
        summary_input,
        use_llm_verification=api_client is not None,
        api_client=api_client
    )

    report_lines = [
        f"Validation: {coverage['summary']}",
        f"Required coverage: {coverage['required_coverage']}",
        f"Optional coverage: {coverage['optional_coverage']}",
        f"Word count: {coverage['word_count']['actual']}/{coverage['word_count']['target']} ({coverage['word_count']['deviation']} deviation)",
        f"Proportionality: {'OK' if coverage['proportionality_passed'] else 'ISSUES'}"
    ]

    if coverage["human_review_checklist"]:
        report_lines.extend(["", coverage["human_review_checklist"]])

    return coverage["passed"], "\n".join(report_lines)


# === Example Usage ===

if __name__ == "__main__":
    # Mock SummaryInput for testing
    class MockTopic:
        def __init__(self, name, percentage, word_allocation, key_points):
            self.name = name
            self.percentage = percentage
            self.word_allocation = word_allocation
            self.sections = "1-5"
            self.key_points = key_points

    class MockOpening:
        def __init__(self):
            self.word_allocation = 70
            self.stated_purpose = "To explore where the roots of Bowen theory reside"
            self.content_preview = ["astronomy", "biology", "neuroscience"]

    class MockBody:
        def __init__(self):
            self.word_allocation = 300
            self.topics = [
                MockTopic("Paradigm shifts in astronomy", 28, 100,
                          ["2000-year journey", "Aristarchus to Einstein"]),
                MockTopic("Physical to biological carryover", 22, 80,
                          ["Frank Wilczek", "universal laws"]),
                MockTopic("Cancer research parallels", 18, 60,
                          ["Marta Bertolaso", "blocked ontogeny"]),
            ]

    class MockQA:
        def __init__(self):
            self.include = True
            self.word_allocation = 50
            self.percentage = 32
            self.question_types = ["chronic anxiety", "determination"]
            self.notable_exchanges = ["Amy Post on adaptive capacity"]

    class MockClosing:
        def __init__(self):
            self.word_allocation = 50
            self.conclusion = "Answers extend beyond our species"
            self.open_questions = "Whether life forces have physical roots"
            self.future_direction = "Cross-disciplinary investigation"

    class MockInput:
        def __init__(self):
            self.metadata = {"speaker": "Dr. Michael Kerr"}
            self.target_word_count = 500
            self.opening = MockOpening()
            self.body = MockBody()
            self.qa = MockQA()
            self.closing = MockClosing()

    mock_input = MockInput()

    # Good summary
    good_summary = """
    Dr. Michael Kerr presents a webinar exploring the historical and scientific foundations of Bowen family systems theory. Drawing on over fifty years of clinical experience, Kerr examines where the roots of this theory reside, tracing connections from physical sciences through biology to human behavior. The presentation spans paradigm shifts in astronomy, the carryover from physics to biological understanding, and contemporary cancer research.

    The first major section traces the 2,000-year journey from Aristotle's geocentric model through Aristarchus, Copernicus, and ultimately Einstein. Kerr emphasizes how paradigm shifts can take extraordinarily long to achieve acceptance, drawing explicit parallels to the reception of systems thinking in psychology. Newton's introduction of forces as explanatory mechanisms receives particular attention, as forces figure prominently in Bowen theory but remain underutilized in mainstream biology.

    Kerr then examines how principles from physics have been preserved in biological systems. Referencing Frank Wilczek's work on fundamental particles, he notes that physical laws are universal and precise, while biology introduces new capacities like self-reproduction and variation. The concept of complementarity from Niels Bohr provides a framework for understanding how different analytical perspectives can coexist.

    The presentation draws parallels between cancer research and Bowen theory, particularly through Marta Bertolaso's work characterizing cancer as blocked ontogeny rather than mere cell multiplication. Kerr identifies counterbalancing forces in cellular systems that mirror the individuality and togetherness dynamics central to Bowen's framework.

    Audience questions explored chronic anxiety as a retained adaptive capacity rather than simply a problem to solve, and examined determination's role in recovery outcomes. Several participants connected the neuroscience material to their clinical practice.

    Kerr concludes that while definitive answers about Bowen theory's roots remain elusive, the evidence suggests answers extend beyond the boundaries of our species. Cross-disciplinary investigation spanning physics, biology, and neuroscience offers the most promising path forward.
    """

    # Bad summary (missing topics, wrong proportions)
    bad_summary = """
    Dr. Kerr gave a presentation about theory. He discussed various scientific topics and made some observations. The audience asked questions.
    
    In conclusion, more research is needed.
    """

    print("=== Pre-Review Checklist ===")
    print(generate_review_checklist(mock_input))
    print("\n" + "="*50 + "\n")

    print("=== Testing Good Summary ===")
    passed, report = validate_and_report(good_summary, mock_input)
    print(f"Passed: {passed}")
    print(report)

    print("\n" + "="*50 + "\n")

    print("=== Testing Bad Summary ===")
    passed, report = validate_and_report(bad_summary, mock_input)
    print(f"Passed: {passed}")
    print(report)
