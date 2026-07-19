"""
Abstract Generation Pipeline
Prepares structured input for LLM abstract generation from transcript extractions.

Usage:
    from abstract_pipeline import prepare_abstract_input, generate_abstract

    # From extraction outputs
    input_data = prepare_abstract_input(
        metadata=yaml_metadata,
        topics=topics_list,
        themes=themes_list,
        transcript_text=full_transcript
    )

    abstract = generate_abstract(input_data, api_client)
"""

import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Optional

import anthropic

import logging

import config
from transcript_utils import (
    call_claude_with_retry,
    is_scaffolding_theme_name,
    parse_bold_numbered_theme_blocks,
)

logger = logging.getLogger(__name__)



@dataclass
class Topic:
    name: str
    percentage: int
    sections: str


@dataclass
class Theme:
    name: str
    description: str


@dataclass
class AbstractInput:
    metadata: dict
    topics: list[Topic]
    themes: list[Theme]
    opening_purpose: str
    closing_conclusion: str
    qa_percentage: int
    qa_topics: list[str]
    target_word_count: int

    def to_json(self) -> str:
        """Serialize for API prompt injection."""
        data = {
            "metadata": self.metadata,
            "topics": [asdict(t) for t in self.topics],
            "themes": [asdict(t) for t in self.themes],
            "opening_purpose": self.opening_purpose,
            "closing_conclusion": self.closing_conclusion,
            "qa_percentage": self.qa_percentage,
            "qa_topics": self.qa_topics,
            "target_word_count": self.target_word_count,
        }
        return json.dumps(data, indent=2)

    def to_contract_dict(self) -> dict:
        """Schema-shaped dict for the abstract_input boundary contract (M3).
        Same payload as ``to_json`` plus the ``version``/``artifact`` envelope
        the schema pins."""
        return {
            "version": "1",
            "artifact": "abstract_input",
            "metadata": self.metadata,
            "topics": [asdict(t) for t in self.topics],
            "themes": [asdict(t) for t in self.themes],
            "opening_purpose": self.opening_purpose,
            "closing_conclusion": self.closing_conclusion,
            "qa_percentage": self.qa_percentage,
            "qa_topics": self.qa_topics,
            "target_word_count": self.target_word_count,
        }


def parse_topics_from_extraction(topics_markdown: str) -> list[Topic]:
    """
    Parse Topics section using robust pattern matching.
    """
    topics = []

    # Strategy 1: Strict format with explicit percentage + sections metadata
    strict_pattern = r"###\s+([^\n]+)\s*\n\s*((?:(?!\n###).)+?)\s*\n\s*[\*_\-\s\[\(]+~?(\d+)%[^;\n]+;\s*Sections?\s+([\d\-,\s]+)(?:\)|\])?[\*_\-\s]*"

    matches = re.findall(strict_pattern, topics_markdown, re.DOTALL)

    for match in matches:
        name = match[0].strip()
        percentage = int(match[2])
        sections = match[3].strip()

        if percentage >= 5:
            topics.append(
                Topic(name=name, percentage=percentage, sections=sections))

    # Strategy 2: Header-based fallback (### Topic Name) even when metadata line is absent
    if not topics and "###" in topics_markdown:
        blocks = [
            b.strip() for b in re.split(r"(?:^|\n)###\s+", topics_markdown) if b.strip()
        ]
        for idx, block in enumerate(blocks):
            lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
            if not lines:
                continue
            name = lines[0]
            body = " ".join(lines[1:])
            pct_match = re.search(r"~?(\d+)%", body)
            percentage = int(pct_match.group(1)) if pct_match else max(5, 100 - idx * 10)
            sections_match = re.search(r"Sections?\s*([0-9,\-\s]+)", body, re.IGNORECASE)
            sections = sections_match.group(1).strip() if sections_match else ""
            topics.append(Topic(name=name, percentage=percentage, sections=sections))

    # Strategy 3: Numbered/bullet fallback (1. **Topic**: ... or - **Topic**: ...)
    if not topics:
        list_pattern = r"(?:^|\n)\s*(?:\d+\.\s+|[-*]\s+)(?:\*\*)?([^:\n*]+)(?:\*\*)?:"
        names = re.findall(list_pattern, topics_markdown)
        for idx, name in enumerate(names):
            clean_name = name.strip()
            if clean_name:
                topics.append(
                    Topic(
                        name=clean_name,
                        percentage=max(5, 100 - idx * 10),
                        sections="",
                    )
                )

    # Sort by percentage descending, take top 5
    topics.sort(key=lambda t: t.percentage, reverse=True)
    return topics[:5]


def parse_themes_from_extraction(themes_markdown: str) -> list[Theme]:
    """
    Parse structural/interpretive themes using robust pattern matching.

    Strategy order matters: the real extraction artifact writes bold-numbered
    ``**N. Title**`` blocks with ``###``/``##`` scaffolding headers around them
    (``### Structural Themes (3 total)``, ``### Summary Paragraph``). We MUST
    detect the bold-numbered format first; gating on ``###`` first captured the
    scaffolding header as the theme name and collapsed every real theme into one
    blob (P19 — TODO.md A1). ``###``-as-theme is a legacy fallback only.
    """
    themes = []

    # Strategy 1 (PREFERRED): real bold-numbered block format `**N. Title**`.
    for name, description in parse_bold_numbered_theme_blocks(themes_markdown):
        themes.append(Theme(name=name, description=description))

    # Strategy 2 (LEGACY): `### Theme Name` header blocks. Only when no
    # bold-numbered themes exist — in the real format `###` marks scaffolding.
    if not themes and "###" in themes_markdown:
        header_blocks = re.finditer(
            r"(?:^|\n)###\s+([^\n]+)\n(.*?)(?=(?:\n###\s+)|\Z)",
            themes_markdown,
            re.DOTALL,
        )
        for match in header_blocks:
            name = match.group(1).strip()
            description = " ".join(
                ln.strip() for ln in match.group(2).split("\n") if ln.strip()
            ).strip()
            if not is_scaffolding_theme_name(name) and description:
                themes.append(Theme(name=name, description=description))

    # Strategy 3: Numbered format
    if not themes:
        blocks = re.finditer(
            r"(?:^|\n)\s*\d+\.\s+(.*?)(?=(?:\n\s*\d+\.\s+)|\Z)",
            themes_markdown,
            re.DOTALL,
        )
        for block_match in blocks:
            block = block_match.group(1).strip()
            first_line, _, rest = block.partition("\n")
            line_match = re.match(
                r"(?:\*\*)?(.+?)(?:\*\*)?:\s*(.+)$",
                first_line.strip(),
            )
            if not line_match:
                continue
            name = line_match.group(1).strip()
            if is_scaffolding_theme_name(name):
                continue
            description = f"{line_match.group(2).strip()} {rest.strip()}".strip()
            description = re.sub(
                r"[\*_ \-]*Source Sections?:?\s*[^*_\n]+[\*_ \-]*",
                "",
                description,
                flags=re.IGNORECASE,
            ).strip()
            if name and description:
                themes.append(Theme(name=name, description=description))

    # P19 guard: non-empty input that parsed to nothing is contract drift, not a
    # benign empty — surface it loudly rather than silently returning [].
    if not themes and themes_markdown.strip():
        logger.warning(
            "parse_themes_from_extraction: non-empty themes input (%d chars) "
            "parsed to ZERO themes — producer/consumer format drift (P19).",
            len(themes_markdown.strip()),
        )

    # Take top 2 themes
    return themes[:2]


def extract_opening_purpose(transcript: str, section_count: int) -> str:
    """
    Extract speaker's stated purpose from opening sections using an LLM.
    """
    # 1. Isolate the opening 15% of the transcript's text, max 5 sections
    opening_section_count = min(max(1, section_count // 7), 5)
    
    section_pattern = r"## Section (\d+)"
    sections = re.split(section_pattern, transcript)
    
    opening_text = ""
    # The split results in ['pre-section1-text', '1', 'section1-text', '2', 'section2-text', ...]
    for i in range(1, opening_section_count * 2, 2):
        if i + 1 < len(sections):
            opening_text += f"## Section {sections[i]}\n{sections[i+1]}"

    if not opening_text.strip():
        return "Speakers purpose missing - manually insert"

    # 2. Load the prompt
    try:
        prompt_path = config.PROMPTS_DIR / "purpose_extraction_prompt.md"
        template = prompt_path.read_text(encoding="utf-8")
        prompt = template.replace("{{opening_text}}", opening_text)
    except FileNotFoundError:
        # Deployment/config problem, not "speaker said nothing" — retryable (A10/P1).
        return config.PURPOSE_EXTRACTION_FAILED

    # 3. Call the LLM
    try:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            # Config/transient — do NOT masquerade as genuine-absent (A10/P1).
            return config.PURPOSE_EXTRACTION_FAILED

        client = anthropic.Anthropic(api_key=api_key)
        
        message = call_claude_with_retry(
            client=client,
            model=config.settings.AUX_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,  # A single sentence should be short
            temperature=0.0,
            min_length=10, # Expect at least a short sentence
            logger=logger,  # named logger -> real script name in token-usage log
        )
        
        purpose = message.content[0].text.strip()

        # 4. Process the response
        if "Not explicitly stated" in purpose:
            return "Speakers purpose missing - manually insert"
        
        return purpose

    except Exception:
        # Transient API failure (timeout, rate-limit, 5xx) — retryable, not a
        # genuine absence; keep it distinct so the check isn't silently demoted (A10/P1).
        return config.PURPOSE_EXTRACTION_FAILED


def extract_closing_conclusion(transcript: str, section_count: int) -> str:
    """
    Extract speaker's conclusions from final sections.
    Looks for conclusion indicators in last 10% of sections.
    """
    closing_start = section_count - (section_count // 10) or section_count - 1

    # Conclusion-indicator phrases live in config (rule #9: editorial content).
    conclusion_patterns = config.ABSTRACT_CONCLUSION_PATTERNS

    # Search in last N sections. The alternation is NON-capturing: with a single
    # capturing group `re.findall` returns only the captured section NUMBERS and
    # discards the `[^#]+` body, so the conclusion search below ran against a string
    # of digits and always failed (A4/P19). `(?:...)` -> findall returns whole matches.
    section_pattern = (
        r"## Section (?:"
        + "|".join(str(i) for i in range(closing_start, section_count + 1))
        + r")[^#]+"
    )
    closing_text = " ".join(re.findall(section_pattern, transcript, re.DOTALL))

    for pattern in conclusion_patterns:
        match = re.search(pattern, closing_text, re.IGNORECASE)
        if match:
            return match.group(0).strip()

    return "No explicit conclusion stated"


def calculate_qa_percentage(transcript: str) -> tuple[int, list[str]]:
    """
    Estimate Q&A percentage and extract topic areas discussed.

    Returns:
        (percentage, list of topic keywords)
    """
    # Count total sections
    total_sections = len(re.findall(r"## Section \d+", transcript))

    # Identify Q&A sections by speaker label patterns
    qa_indicators = [
        r"\*\*[A-Z][a-z]+\s*:\*\*",  # **Name:** pattern (questioner)
        r"\*\*Dr[.\s]+\w+:\*\*",  # **Dr. Name:** pattern (response)
        r"\*\*Audience",  # **Audience Member:**
        r"question",
        r"comment",
    ]

    qa_sections = 0
    qa_topics = []

    sections = re.split(r"## Section \d+[^\n]+\n", transcript)

    for section in sections:
        qa_indicator_count = sum(
            len(re.findall(pattern, section, re.IGNORECASE))
            for pattern in qa_indicators
        )

        if qa_indicator_count >= 2:  # Likely Q&A section
            qa_sections += 1

            # Extract candidate topic phrases after question prepositions.
            topic_matches = re.findall(
                r"(?:about|on|regarding)\s+([A-Za-z][^.,;:!?\n]{2,80})",
                section,
                re.IGNORECASE,
            )
            qa_topics.extend(topic_matches[:3])

    percentage = int((qa_sections / total_sections) *
                     100) if total_sections > 0 else 0

    # Deduplicate, clean, and limit topics
    unique_topics = _clean_qa_topics(qa_topics)[:5]

    return percentage, unique_topics


def _clean_qa_topics(topics: list[str]) -> list[str]:
    """Normalize Q&A topic phrases and drop low-signal entries."""
    stopwords = {
        "a", "about", "an", "and", "as", "at", "be", "but", "by", "for", "from", "how",
        "i", "if", "in", "is", "it", "my", "of", "on", "or", "our", "so", "that",
        "regarding",
        "the", "their", "them", "there", "these", "they", "this", "those", "to",
        "we", "what", "when", "where", "which", "who", "why", "you", "your",
    }
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in topics:
        phrase = re.sub(r"\s+", " ", raw).strip(" -_:;,.!?()[]{}\"'").lower()
        if not phrase:
            continue
        words = [w for w in re.findall(r"[a-zA-Z]+", phrase) if w not in stopwords]
        # Keep only contentful topics with at least two meaningful tokens.
        if len(words) < 2 or max(len(w) for w in words) < 4:
            continue
        normalized = " ".join(words[:4])
        if normalized not in seen:
            seen.add(normalized)
            cleaned.append(normalized)
    return cleaned


def count_sections(transcript: str) -> int:
    """Count total sections in formatted transcript."""
    return len(re.findall(r"## Section \d+", transcript))


def prepare_abstract_input(
    metadata: dict,
    topics_markdown: str,
    themes_markdown: str,
    transcript: str,
    target_word_count: int = 250,
) -> AbstractInput:
    """
    Prepare structured input for abstract generation API call.

    Args:
        metadata: Dict with speaker, event_type, title, domain
        topics_markdown: Raw Topics section from extraction output
        themes_markdown: Raw Interpretive Themes section from extraction output
        transcript: Full formatted transcript text
        target_word_count: Target word count for the abstract

    Returns:
        AbstractInput ready for serialization
    """
    section_count = count_sections(transcript)
    qa_percentage, qa_topics = calculate_qa_percentage(transcript)

    abstract_input = AbstractInput(
        metadata=metadata,
        topics=parse_topics_from_extraction(topics_markdown),
        themes=parse_themes_from_extraction(themes_markdown),
        opening_purpose=extract_opening_purpose(transcript, section_count),
        closing_conclusion=extract_closing_conclusion(
            transcript, section_count),
        qa_percentage=qa_percentage,
        qa_topics=qa_topics,
        target_word_count=target_word_count,
    )
    # M3.B — producer self-validation: the assembled input must conform to the
    # abstract_input schema before it drives a (costly) generation call. A malformed
    # input (e.g. a topic parsed with an empty name, an out-of-range percentage) is
    # a fail-closed SchemaError, not a garbage abstract generated from bad input.
    import artifact_contracts as ac

    ac.validate("abstract_input", abstract_input.to_contract_dict())
    return abstract_input


# === API Integration ===


def load_prompt() -> str:
    """Load the abstract generation prompt template."""
    prompt_path = config.PROMPTS_DIR / config.PROMPT_STRUCTURED_ABSTRACT_FILENAME
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path}\n"
            f"Expected location: {config.PROMPTS_DIR}/{config.PROMPT_STRUCTURED_ABSTRACT_FILENAME}"
        )
    return prompt_path.read_text(encoding="utf-8")


def generate_abstract(
    abstract_input: AbstractInput,
    api_client,  # Anthropic client or compatible
    model: str = config.AUX_MODEL,  # Haiku: cost-effective for abstract generation
    system: Optional[list] = None,
    feedback_claims: Optional[list] = None,
) -> str:
    """
    Generate abstract via API call.

    Args:
        abstract_input: Prepared AbstractInput object
        api_client: Anthropic API client
        model: Model identifier
        feedback_claims: On a regeneration attempt, the specific statements a
            previous draft made that were NOT supported by the transcript — fed
            back so the model corrects them (grounds every sentence).

    Returns:
        Generated abstract text
    """
    prompt_template = load_prompt()
    prompt = prompt_template.format(
        input_json=abstract_input.to_json(),
        target_word_count=abstract_input.target_word_count,
    )
    if feedback_claims:
        prompt += (
            "\n\n---\nCORRECTION REQUIRED. A previous draft contained the following "
            "statements that are NOT supported by the transcript. Rewrite the "
            "abstract so that EVERY sentence is directly grounded in the source, "
            "and do not repeat these unsupported claims:\n"
            + "\n".join(f"- {c}" for c in feedback_claims)
        )

    kwargs = {}
    if system:
        kwargs["system"] = system

    # Use centralized call with retry and validation
    message = call_claude_with_retry(
        client=api_client,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=config.MAX_TOKENS_SUMMARY,
        temperature=config.TEMP_BALANCED,
        stream=True,
        min_length=150,  # Ensure substantial abstract
        logger=logger,  # named logger -> real script name in token-usage log
        **kwargs,
    )

    return message.content[0].text.strip()


# === Validation ===


def validate_abstract(abstract: str, target_word_count: int = 250) -> dict:
    """
    Validate generated abstract against requirements.

    Returns:
        Dict with validation results and any issues found
    """
    issues = []

    word_count = len(abstract.split())

    # Allow 20% tolerance; hard-cap the upper bound below ABSTRACT_HARD_MAX_WORDS
    # so >= 250 words is always flagged (parity with validate_structural, P5).
    min_words = int(target_word_count * 0.8)
    max_words = min(int(target_word_count * 1.2), config.ABSTRACT_HARD_MAX_WORDS - 1)

    if word_count < min_words:
        issues.append(f"Too short: {word_count} words (minimum {min_words})")
    elif word_count > max_words:
        issues.append(f"Too long: {word_count} words (maximum {max_words})")

    # Check for prohibited elements
    if re.search(r"Section \d+", abstract):
        issues.append("Contains section references")

    if '"' in abstract and abstract.count('"') >= 2:
        issues.append("May contain direct quotations")

    if re.search(r"^\s*[-•*]\s", abstract, re.MULTILINE):
        issues.append("Contains bullet points")

    # Check for evaluative language
    evaluative_terms = ["important", "valuable",
                        "insightful", "excellent", "crucial"]
    found_evaluative = [
        t for t in evaluative_terms if t.lower() in abstract.lower()]
    if found_evaluative:
        issues.append(f"Contains evaluative language: {found_evaluative}")

    return {"valid": len(issues) == 0, "word_count": word_count, "issues": issues}


# === Example Usage ===

if __name__ == "__main__":
    # Example with mock data
    sample_metadata = {
        "speaker": "Dr. Michael Kerr",
        "event_type": "webinar",
        "title": "Roots of Bowen Theory",
        "domain": "Bowen family systems theory",
    }

    sample_topics = """
### Paradigm Shifts in Astronomy: Geocentric to Heliocentric Models

Kerr traces the 2,000-year journey from Aristotle's geocentric model through Aristarchus, 
Copernicus, Kepler, Galileo, and Newton. He emphasizes that paradigm shifts can take 
extraordinarily long to achieve acceptance, drawing parallels to systems theory.

*_(~28% of transcript; Sections 6-14)_*

### Physical to Biological Carryover

The presentation examines how principles from physics—particularly forces and 
complementarity—have been preserved in biological systems. Kerr references Frank Wilczek's 
work on fundamental particles and physical laws.

*_(~22% of transcript; Sections 15-20)_*
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

## Section 30 – Conclusion  
I think we can safely say the answers extend beyond the boundaries of our species.
"""

    # Prepare input
    abstract_input = prepare_abstract_input(
        metadata=sample_metadata,
        topics_markdown=sample_topics,
        themes_markdown=sample_themes,
        transcript=sample_transcript,
    )

    print("Prepared input:")
    print(abstract_input.to_json())
    print("\n" + "=" * 50 + "\n")
    print("Ready for API call with ABSTRACT_PROMPT_TEMPLATE")
