"""
Summary Generation Pipeline
Prepares structured input for LLM summary generation from transcript extractions.

Handles proportional word allocation based on topic coverage percentages.

Usage:
    from summary_pipeline import prepare_summary_input, generate_summary

    # From extraction outputs
    input_data = prepare_summary_input(
        metadata=yaml_metadata,
        topics_markdown=topics_section,
        themes_markdown=themes_section,
        transcript=full_transcript,
        target_word_count=500
    )

    summary = generate_summary(input_data, api_client)
"""

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Optional

import config
from emphasis_detector import EmphasisDetector
from transcript_utils import call_claude_with_retry


@dataclass
class TopicAllocation:
    """Topic with word allocation for summary."""

    name: str
    percentage: int
    word_allocation: int
    sections: str
    key_points: list[str] = field(default_factory=list)


@dataclass
class OpeningSection:
    word_allocation: int
    stated_purpose: str
    content_preview: list[str]


@dataclass
class BodySection:
    word_allocation: int
    topics: list[TopicAllocation]


@dataclass
class QASection:
    include: bool
    word_allocation: int
    percentage: int
    question_types: list[str]
    notable_exchanges: list[str]


@dataclass
class ClosingSection:
    word_allocation: int
    conclusion: str
    open_questions: str
    future_direction: str


@dataclass
class SummaryInput:
    metadata: dict
    target_word_count: int
    opening: OpeningSection
    body: BodySection
    qa: QASection
    closing: ClosingSection
    themes: list[dict] = field(default_factory=list)

    def to_json(self) -> str:
        """Serialize for API prompt injection."""
        data = {
            "metadata": self.metadata,
            "target_word_count": self.target_word_count,
            "themes": self.themes,
            "opening": asdict(self.opening),
            "body": {
                "word_allocation": self.body.word_allocation,
                "topics": [asdict(t) for t in self.body.topics],
            },
            "qa": asdict(self.qa),
            "closing": asdict(self.closing),
        }
        return json.dumps(data, indent=2)


# === Word Allocation Logic ===


def calculate_word_allocations(
    target_word_count: int, topic_percentages: list[int], qa_percentage: int
) -> dict:
    """Calculate word allocations for each section."""
    include_qa = qa_percentage > 5

    # Base allocations
    opening_pct = config.SUMMARY_OPENING_PCT
    closing_pct = config.SUMMARY_CLOSING_PCT
    qa_pct = config.SUMMARY_QA_PCT if include_qa else 0.0
    body_pct = 1.0 - opening_pct - closing_pct - qa_pct

    allocations = {
        "opening": int(target_word_count * opening_pct),
        "body_total": int(target_word_count * body_pct),
        "qa": int(target_word_count * qa_pct) if include_qa else 0,
        "closing": int(target_word_count * closing_pct),
        "include_qa": include_qa,
    }

    # Allocate body words to topics proportionally
    total_topic_pct = sum(topic_percentages)
    if total_topic_pct > 0:
        allocations["topic_allocations"] = [
            int(allocations["body_total"] * (pct / total_topic_pct))
            for pct in topic_percentages
        ]
    else:
        # Equal distribution if no percentages
        per_topic = (
            allocations["body_total"] // len(topic_percentages)
            if topic_percentages
            else 0
        )
        allocations["topic_allocations"] = [per_topic] * len(topic_percentages)

    return allocations


# === Extraction Parsing ===


def parse_topics_with_details(topics_markdown: str, transcript: str) -> list[dict]:
    """Parse Topics section and extract key points from transcript using robust block parsing."""
    topics = []

    # Regex matches: ### Name \n Description \n Metadata line
    # Matches format: *_(~25% of transcript; Sections 1-5)_*
    # Robust pattern handling spaces, brackets, and various separators
    pattern = r"###\s+([^\n]+)\s*\n\s*((?:(?!\n###).)+?)\s*\n\s*[\*_\-\s\[\(]+~?(\d+)%[^;\n]+;\s*Sections?\s+([\d\-,\s]+)(?:\)|\])?[\*_\-\s]*"

    matches = re.findall(pattern, topics_markdown, re.DOTALL)

    for match in matches:
        name = match[0].strip()
        description = match[1].strip()
        percentage = int(match[2])
        sections = match[3].strip()

        if percentage >= 5:
            # Clean up description if it has leading/trailing markdown wrapper lines that regex captured
            # (The regex is greedy on description, so it might capture trailing newlines/spacers)
            description = description.strip()

            # Extract key points from the description and transcript sections
            key_points = extract_key_points(description, sections, transcript)

            topics.append(
                {
                    "name": name,
                    "percentage": percentage,
                    "sections": sections,
                    "description": description,
                    "key_points": key_points,
                }
            )

    # Sort by percentage descending
    topics.sort(key=lambda t: t["percentage"], reverse=True)
    return topics


def extract_key_points(
    description: str, sections_str: str, transcript: str
) -> list[str]:
    """Extract 3-5 key points for a topic from its description and transcript sections."""
    key_points = []

    # Split description into sentences
    sentences = re.split(r"(?<=[.!?])\s+", description)

    for sentence in sentences:
        # Clean and validate
        sentence = sentence.strip()
        if len(sentence) > 20 and len(sentence) < 200:
            # Simplify to key point format
            point = simplify_to_key_point(sentence)
            if point and point not in key_points:
                key_points.append(point)

    # If we need more points, scan transcript sections
    if len(key_points) < 3:
        section_points = extract_points_from_sections(sections_str, transcript)
        for point in section_points:
            if point not in key_points:
                key_points.append(point)
                if len(key_points) >= 5:
                    break

    return key_points[:5]


def simplify_to_key_point(sentence: str) -> Optional[str]:
    """Convert a sentence to a concise key point."""
    # Remove common filler phrases
    fillers = [
        r"^The speaker\s+",
        r"^Kerr\s+",
        r"^He\s+",
        r"^She\s+",
        r"^This\s+",
        r"^It\s+",
        r"in this section,?\s*",
        r"here,?\s*",
    ]

    point = sentence
    for filler in fillers:
        point = re.sub(filler, "", point, flags=re.IGNORECASE)

    # Capitalize first letter
    if point:
        point = point[0].upper() + \
            point[1:] if len(point) > 1 else point.upper()

    # Remove trailing period for consistency
    point = point.rstrip(".")

    return point if len(point) > 15 else None


def extract_points_from_sections(sections_str: str, transcript: str) -> list[str]:
    """Extract key points from transcript sections using emphasis detection."""
    points = []

    # Parse section range (e.g., "6-14" or "6, 8, 10")
    section_nums = parse_section_range(sections_str)

    # Build pattern to match these sections
    for section_num in section_nums:
        pattern = rf"## Section {section_num}[^\n]*\n(.*?)(?=## Section|\Z)"
        match = re.search(pattern, transcript, re.DOTALL)

        if match:
            section_text = match.group(1)

            # Use robust EmphasisDetector
            detector = EmphasisDetector()
            matches = detector.detect(section_text)

            for m in matches:
                point = simplify_to_key_point(m.full_sentence)
                if point and point not in points:
                    points.append(point)

        if len(points) >= 5:
            break

    return points


def parse_section_range(sections_str: str) -> list[int]:
    """Parse section string like '6-14' or '6, 8, 10' into list of ints."""
    sections = []

    # Handle ranges like "6-14"
    range_match = re.match(r"(\d+)\s*-\s*(\d+)", sections_str)
    if range_match:
        start, end = int(range_match.group(1)), int(range_match.group(2))
        sections = list(range(start, end + 1))
    else:
        # Handle comma-separated like "6, 8, 10"
        nums = re.findall(r"\d+", sections_str)
        sections = [int(n) for n in nums]

    return sections


def parse_themes(themes_markdown: str) -> list[dict]:
    """
    Parse Interpretive Themes using a robust line-based approach.
    Supports both new header format (### Theme) and legacy numbered lists (1. **Theme**:).
    """
    themes = []

    # Strategy 1: Check for header-based structure (###)
    # This is the new standard as of Jan 2026
    if "###" in themes_markdown:
        # Split by level 3 headers
        blocks = [
            b.strip() for b in re.split(r"(?:^|\n)###\s+", themes_markdown) if b.strip()
        ]

        for block in blocks:
            lines = block.split("\n")
            if not lines:
                continue

            # First line is the theme name
            name = lines[0].strip()
            sections = ""
            description_lines = []

            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue

                 # Check for Source Sections indicator
                if "Source Section" in line:
                    # Extract sections if possible
                    sect_match = re.search(
                        r"Sections:?\s*([^*]+)", line, re.IGNORECASE)
                    if sect_match:
                        sections = sect_match.group(1).strip().rstrip("*_")
                    continue

                description_lines.append(line)

            description = " ".join(description_lines).strip()
            if name and description:
                themes.append(
                    {"name": name, "description": description, "sections": sections}
                )

        return themes

    # Strategy 2: Fallback to numbered list parsing (Legacy)
    # Supports both:
    #   1. **Theme**: Description
    #   *Source Sections: 1, 2*
    # and:
    #   2. **Theme Two**: Description only
    blocks = re.finditer(
        r"(?:^|\n)\s*\d+\.\s+(.*?)(?=(?:\n\s*\d+\.\s+)|\Z)",
        themes_markdown,
        re.DOTALL,
    )

    for block_match in blocks:
        block = block_match.group(1).strip()
        if not block:
            continue

        # First line is expected to carry "Name: Description"
        first_line, _, rest = block.partition("\n")
        line_match = re.match(
            r"(?:\*\*)?(.+?)(?:\*\*)?:\s*(.+)$",
            first_line.strip(),
        )
        if not line_match:
            continue

        name = line_match.group(1).strip()
        description = line_match.group(2).strip()
        sections = ""

        # Optional "Source Sections" may appear on following lines.
        combined_rest = rest.strip()
        if combined_rest:
            sect_match = re.search(
                r"Source Sections?:?\s*([^*_\n]+)",
                combined_rest,
                re.IGNORECASE,
            )
            if sect_match:
                sections = sect_match.group(1).strip().rstrip("*_")
            # Keep descriptive text that isn't source metadata.
            cleaned_rest = re.sub(
                r"[\*_ \-]*Source Sections?:?\s*[^*_\n]+[\*_ \-]*",
                "",
                combined_rest,
                flags=re.IGNORECASE,
            ).strip()
            if cleaned_rest:
                description = f"{description} {cleaned_rest}".strip()

        if name and description:
            themes.append({"name": name, "description": description, "sections": sections})

    return themes


# === Transcript Analysis ===


def extract_opening_content(transcript: str, section_count: int) -> dict:
    """Extract opening content: stated purpose and content preview."""
    opening_sections = max(section_count // 10, 2)

    # Get text from opening sections
    opening_text = ""
    for i in range(1, opening_sections + 1):
        pattern = rf"## Section {i}[^\n]*\n(.*?)(?=## Section|\Z)"
        match = re.search(pattern, transcript, re.DOTALL)
        if match:
            opening_text += match.group(1) + " "

    # Extract stated purpose
    purpose_patterns = [
        r"[Mm]y intent[^.]+\.",
        r"[Ii]'m going to[^.]+\.",
        r"[Tt]oday[^.]+(?:explore|discuss|examine|present)[^.]+\.",
        r"[Tt]he purpose[^.]+\.",
        r"[Ii] want to[^.]+\.",
        r"[Ww]hat are[^.]+\?",
    ]

    stated_purpose = "Not explicitly stated"
    for pattern in purpose_patterns:
        match = re.search(pattern, opening_text)
        if match:
            stated_purpose = match.group(0).strip()
            break

    # Extract content preview (topics mentioned in opening)
    preview_patterns = [
        r"going to (?:talk about|discuss|explore|present)[^.]+\.",
        r"two (?:presentations|parts|sections)[^.]+\.",
        r"first[^.]+second[^.]+\.",
    ]

    content_preview = []
    for pattern in preview_patterns:
        match = re.search(pattern, opening_text, re.IGNORECASE)
        if match:
            # Extract noun phrases as preview items
            text = match.group(0)
            nouns = re.findall(
                r"(?:the |a )?([a-z]+(?:\s+[a-z]+)?(?:\s+[a-z]+)?)", text.lower()
            )
            content_preview.extend([n for n in nouns if len(n) > 5][:3])

    return {"stated_purpose": stated_purpose, "content_preview": content_preview[:4]}


def extract_closing_content(transcript: str, section_count: int) -> dict:
    """Extract closing content: conclusion, open questions, future direction."""
    closing_start = max(
        section_count - (section_count // 10), section_count - 3)

    # Get text from closing sections
    closing_text = ""
    for i in range(closing_start, section_count + 1):
        pattern = rf"## Section {i}[^\n]*\n(.*?)(?=## Section|\Z)"
        match = re.search(pattern, transcript, re.DOTALL)
        if match:
            closing_text += match.group(1) + " "

    # Extract conclusion
    conclusion_patterns = [
        r"[Ii] think we can safely say[^.]+\.",
        r"[Ii]n conclusion[^.]+\.",
        r"[Tt]o conclude[^.]+\.",
        r"[Ss]o[,]? (?:the |my )?(?:answer|conclusion|point)[^.]+\.",
    ]

    conclusion = "No explicit conclusion stated"
    for pattern in conclusion_patterns:
        match = re.search(pattern, closing_text)
        if match:
            conclusion = match.group(0).strip()
            break

    # Extract open questions
    question_patterns = [
        r"[Qq]uestion[^.]+\?",
        r"[Ww]hether[^.]+\.",
        r"[Ii] don't know[^.]+\.",
        r"[Rr]emains to be seen[^.]+\.",
    ]

    open_questions = ""
    for pattern in question_patterns:
        match = re.search(pattern, closing_text)
        if match:
            open_questions = match.group(0).strip()
            break

    # Extract future direction
    future_patterns = [
        r"[Ff]uture[^.]+\.",
        r"[Nn]ext[^.]+\.",
        r"[Pp]ath forward[^.]+\.",
        r"[Ww]ill (?:ultimately |eventually )?[^.]+\.",
    ]

    future_direction = ""
    for pattern in future_patterns:
        match = re.search(pattern, closing_text)
        if match:
            future_direction = match.group(0).strip()
            break

    return {
        "conclusion": conclusion,
        "open_questions": open_questions,
        "future_direction": future_direction,
    }


def analyze_qa_content(transcript: str) -> dict:
    """Analyze Q&A sections for summary input."""
    # Identify Q&A sections
    qa_indicators = [
        r"\*\*[A-Z][a-z]+\s*:\*\*",  # **Name:** pattern
        r"\*\*Dr[.\s]+\w+:\*\*",
        r"\*\*Audience",
        r"question",
        r"comment",
    ]

    sections = re.split(r"(## Section \d+[^\n]+\n)", transcript)

    qa_sections = []
    total_sections = len([s for s in sections if s.startswith("## Section")])

    current_section = None
    for part in sections:
        if part.startswith("## Section"):
            current_section = part
        elif current_section:
            qa_count = sum(
                len(re.findall(p, part, re.IGNORECASE)) for p in qa_indicators
            )
            if qa_count >= 2:
                qa_sections.append(
                    {"header": current_section, "content": part})

    qa_percentage = (
        int((len(qa_sections) / total_sections)
            * 100) if total_sections > 0 else 0
    )

    # Extract question types and notable exchanges
    question_types = []
    notable_exchanges = []

    for qa in qa_sections:
        content = qa["content"]

        # Extract question topics
        topic_matches = re.findall(
            r"(?:about|on|regarding|thinking about)\s+([^.,?]+)", content, re.IGNORECASE
        )
        question_types.extend([t.strip()[:50] for t in topic_matches[:2]])

        # Look for notable exchanges (longer responses with insight)
        speaker_pattern = r"\*\*([^:]+):\*\*\s*([^*]+?)(?=\*\*|\Z)"
        speakers = re.findall(speaker_pattern, content, re.DOTALL)

        for speaker, text in speakers:
            # Audience member with substantial comment
            if len(text) > 200 and "Dr" not in speaker:
                # Extract first sentence as summary
                first_sentence = re.match(r"[^.!?]+[.!?]", text.strip())
                if first_sentence:
                    notable_exchanges.append(
                        f"{speaker.strip()}: {first_sentence.group(0)[:100]}"
                    )

    # Deduplicate
    question_types = list(dict.fromkeys(question_types))[:6]
    notable_exchanges = notable_exchanges[:3]

    return {
        "percentage": qa_percentage,
        "question_types": question_types,
        "notable_exchanges": notable_exchanges,
    }


def count_sections(transcript: str) -> int:
    """Count total sections in formatted transcript."""
    return len(re.findall(r"## Section \d+", transcript))


# === Main Preparation Function ===


def prepare_summary_input(
    metadata: dict,
    topics_markdown: str,
    themes_markdown: str,
    transcript: str,
    target_word_count: int = 500,
) -> SummaryInput:
    """
    Prepare structured input for summary generation API call.
    """
    section_count = count_sections(transcript)

    # Parse extractions
    topics = parse_topics_with_details(topics_markdown, transcript)
    themes = parse_themes(themes_markdown)

    # Analyze Q&A
    qa_analysis = analyze_qa_content(transcript)

    # Calculate word allocations
    # Use target_word_count directly without inflation
    # Model is instructed to aim for these word counts
    topic_percentages = [t["percentage"] for t in topics]
    allocations = calculate_word_allocations(
        target_word_count, topic_percentages, qa_analysis["percentage"]
    )

    # Extract opening and closing content
    opening_content = extract_opening_content(transcript, section_count)
    closing_content = extract_closing_content(transcript, section_count)

    # Build content preview from topic names
    content_preview = opening_content.get("content_preview", [])
    if not content_preview:
        content_preview = [t["name"][:40] for t in topics[:3]]

    # Build topic allocations
    topic_allocations = []
    for i, topic in enumerate(topics):
        word_alloc = (
            allocations["topic_allocations"][i]
            if i < len(allocations["topic_allocations"])
            else 50
        )
        topic_allocations.append(
            TopicAllocation(
                name=topic["name"],
                percentage=topic["percentage"],
                word_allocation=word_alloc,
                sections=topic["sections"],
                key_points=topic["key_points"],
            )
        )

    return SummaryInput(
        metadata=metadata,
        target_word_count=target_word_count,
        opening=OpeningSection(
            word_allocation=allocations["opening"],
            stated_purpose=opening_content["stated_purpose"],
            content_preview=content_preview,
        ),
        body=BodySection(
            word_allocation=allocations["body_total"], topics=topic_allocations
        ),
        qa=QASection(
            include=allocations["include_qa"],
            word_allocation=allocations["qa"],
            percentage=qa_analysis["percentage"],
            question_types=qa_analysis["question_types"],
            notable_exchanges=qa_analysis["notable_exchanges"],
        ),
        closing=ClosingSection(
            word_allocation=allocations["closing"],
            conclusion=closing_content["conclusion"],
            open_questions=closing_content["open_questions"],
            future_direction=closing_content["future_direction"],
        ),
        themes=themes,
    )


# === API Integration ===


def load_prompt() -> str:
    """Load the summary generation prompt template."""
    prompt_path = config.PROMPTS_DIR / config.PROMPT_STRUCTURED_SUMMARY_FILENAME
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path}\n"
            f"Expected location: {config.PROMPTS_DIR}/{config.PROMPT_STRUCTURED_SUMMARY_FILENAME}"
        )
    return prompt_path.read_text(encoding="utf-8")


def generate_summary(
    summary_input: SummaryInput,
    api_client,
    model: str = config.DEFAULT_MODEL,  # Use Sonnet for detailed summaries (was AUX_MODEL/Haiku)
    system: Optional[list] = None,
) -> str:
    """
    Generate summary via API call.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info("generate_summary called with model: %s", model)
    logger.info("Summary target_word_count: %d", summary_input.target_word_count)

    qa_instruction = (
        "include this section" if summary_input.qa.include else "skip this section"
    )

    prompt_template = load_prompt()

    # Log word allocations being sent to model
    logger.info("Word allocations - Opening: %d, Body: %d, QA: %d, Closing: %d, Total: %d",
                summary_input.opening.word_allocation,
                summary_input.body.word_allocation,
                summary_input.qa.word_allocation,
                summary_input.closing.word_allocation,
                summary_input.opening.word_allocation + summary_input.body.word_allocation +
                summary_input.qa.word_allocation + summary_input.closing.word_allocation)

    prompt = prompt_template.format(
        opening_words=summary_input.opening.word_allocation,
        body_words=summary_input.body.word_allocation,
        qa_words=summary_input.qa.word_allocation,
        qa_instruction=qa_instruction,
        closing_words=summary_input.closing.word_allocation,
        input_json=summary_input.to_json(),
    )

    kwargs = {}
    if system:
        kwargs["system"] = system

    # Use centralized call with retry and validation
    message = call_claude_with_retry(
        client=api_client,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4000,  # Allow for 750-word summaries (~3000 tokens)
        temperature=config.TEMP_BALANCED,
        min_length=2400,  # Ensure substantial summary (~600 words minimum)
        min_words=600,    # Enforce strict minimum of 600 words
        **kwargs,
    )

    return message.content[0].text.strip()


# === Example Usage ===

if __name__ == "__main__":
    sample_metadata = {
        "speaker": "Dr. Michael Kerr",
        "credentials": "50+ years practicing Bowen family systems theory",
        "event_type": "webinar",
        "title": "Roots of Bowen Theory",
        "domain": "Bowen family systems theory",
    }

    sample_topics = """
### Paradigm Shifts in Astronomy: Geocentric to Heliocentric Models

Kerr traces the 2,000-year journey from Aristotle's geocentric model through Aristarchus, 
Copernicus, Kepler, Galileo, and Newton, culminating in Einstein. He emphasizes that paradigm 
shifts can take extraordinarily long to achieve acceptance, drawing parallels to systems theory.

*_(~28% of transcript; Sections 6-14)_*

### Physical to Biological Carryover

The presentation examines how principles from physics—particularly forces and 
complementarity—have been preserved in biological systems. Kerr references Frank Wilczek's 
work on fundamental particles and physical laws as universal and precise.

*_(~22% of transcript; Sections 15-20)_*

### Cancer Research Parallels with Bowen Theory

Kerr discusses Marta Bertolaso's work on cancer as blocked ontogeny rather than mere cell 
multiplication. He draws parallels between counterbalancing forces in cellular systems 
and Bowen's individuality/togetherness concepts.

*_(~18% of transcript; Sections 21-28)_*
"""

    sample_themes = """
1. **Cross-disciplinary foundations**: Physical sciences provide essential context for 
understanding biological and behavioral phenomena, including Bowen theory concepts.
*Source Sections: 4, 13, 15, 29*

2. **Counterbalancing forces**: Differentiation and stability/togetherness operate as 
opposing forces at multiple levels—cellular, individual, and family.
*Source Sections: 3, 19, 25, 26, 28*
"""

    sample_transcript = """
## Section 1 – Introduction
My intent here today is to explore where the roots of Bowen theory reside.

## Section 32 – Amy's Question
**Amy:** I was thinking about chronic anxiety and this idea of regression.
**Dr. Kerr:** Yeah, I think something equivalent has got to be there.

## Section 60 – Conclusion
I think we can safely say the answers extend beyond the boundaries of our species.
"""

    # Prepare input
    summary_input = prepare_summary_input(
        metadata=sample_metadata,
        topics_markdown=sample_topics,
        themes_markdown=sample_themes,
        transcript=sample_transcript,
        target_word_count=500,
    )

    print("Prepared input:")
    print(summary_input.to_json())
    print("\n" + "=" * 50 + "\n")
    print("Word allocations:")
    print(f"  Opening: {summary_input.opening.word_allocation}")
    print(f"  Body: {summary_input.body.word_allocation}")
    for topic in summary_input.body.topics:
        print(f"    - {topic.name[:40]}...: {topic.word_allocation} words")
    print(
        f"  Q&A: {summary_input.qa.word_allocation} (include: {summary_input.qa.include})"
    )
    print(f"  Closing: {summary_input.closing.word_allocation}")
