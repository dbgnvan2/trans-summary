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
import re
from dataclasses import dataclass, asdict
from typing import Optional
import config


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
            "target_word_count": self.target_word_count
        }
        return json.dumps(data, indent=2)


def parse_topics_from_extraction(topics_markdown: str) -> list[Topic]:
    """
    Parse Topics section using a robust block-based approach.
    Splits by '###' headers and parses each block individually.
    """
    topics = []

    # Split by level 3 headers
    # Filter out empty strings from split
    blocks = [b.strip() for b in re.split(
        r'(?:^|\n)###\s+', topics_markdown) if b.strip()]

    print(f"DEBUG: Found {len(blocks)} potential topic blocks")

    for block in blocks:
        lines = block.split('\n')
        if not lines:
            continue

        # First line is title
        name = lines[0].strip()

        # Look for metadata line (usually at the end, contains %)
        percentage = 0
        sections = ""
        description_lines = []

        metadata_found = False

        # Check lines for metadata pattern
        # Flexible matching: looks for line with both percentage and "Section"

        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue

            # Check if line looks like metadata (contains % and Section)
            if re.search(r'\d+%', line) and re.search(r'Sections?', line, re.IGNORECASE):
                pct_match = re.search(r'(\d+)%', line)
                # Relaxed section match: allows optional colon/dash separators
                sect_match = re.search(
                    r'Sections?\s*[:\-]?\s*([0-9\-\,\s]+)', line, re.IGNORECASE)

                if pct_match:
                    percentage = int(pct_match.group(1))
                    # If section numbers aren't cleanly found, default to the whole tail or empty
                    sections = sect_match.group(
                        1).strip() if sect_match else "Unknown"
                    metadata_found = True
            else:
                # If not metadata, it's part of description
                # Clean up potential markdown formatting if it was just a wrapper line
                if not re.match(r'^[\*_\-()\[\]]+$', line):
                    description_lines.append(line)

        if metadata_found and percentage >= 5:
            # Join description lines
            description = " ".join(description_lines).strip()
            # Note: Topic dataclass currently only uses name, percentage, sections.
            topics.append(
                Topic(name=name, percentage=percentage, sections=sections))
        elif not metadata_found:
            print(f"DEBUG: Metadata not found for block '{name[:20]}...'")

    # Sort by percentage descending, take top 5
    topics.sort(key=lambda t: t.percentage, reverse=True)
    return topics[:5]


def parse_themes_from_extraction(themes_markdown: str) -> list[Theme]:
    """
    Parse Key Themes using a robust line-based approach.
    Looks for numbered lists and parses content until the next number.
    """
    themes = []

    # Split by numbered list items (e.g. "1. ", "2. ")
    # Using lookahead to keep the delimiter or just capturing it
    # Easier: finding all starts and slicing

    # Regex to find the start of a theme:
    # Start of line, number, dot, optional bold, text, optional bold, colon
    header_pattern = r'(?:^|\n)(\d+)\.\s+(?:\*\*)?(.+?)(?:\*\*)?:\s*'

    matches = list(re.finditer(header_pattern, themes_markdown))

    print(f"DEBUG: Found {len(matches)} theme headers")

    for i, match in enumerate(matches):
        label = match.group(2).strip()

        # content start is end of this match
        start_idx = match.end()

        # content end is start of next match or end of string
        end_idx = matches[i+1].start() if i + \
            1 < len(matches) else len(themes_markdown)

        raw_content = themes_markdown[start_idx:end_idx].strip()

        # Parse description and sections from raw_content
        # It typically looks like:
        # "Description text...\n*Source Sections: 1, 2*"

        # Split by newline
        lines = raw_content.split('\n')
        description_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check for Source Sections indicator
            if "Source Section" in line:
                # We don't store source sections in Theme object currently,
                # but we can stop parsing description here.
                continue

            description_lines.append(line)

        description = " ".join(description_lines).strip()

        if label and description:
            themes.append(Theme(name=label, description=description))

    # Take top 2 themes
    return themes[:2]


def extract_opening_purpose(transcript: str, section_count: int) -> str:
    """
    Extract speaker's stated purpose from opening sections.
    Looks for purpose indicators in first 10% of sections.
    """
    opening_sections = section_count // 10 or 1

    # Common purpose indicators
    purpose_patterns = [
        r"my intent[^.]+is[^.]+\.",
        r"I'm going to[^.]+\.",
        r"today[^.]+explore[^.]+\.",
        r"purpose[^.]+is[^.]+\.",
        r"goal[^.]+is[^.]+\.",
        r"I want to[^.]+\.",
    ]

    # Search in first N sections
    section_pattern = r'## Section [1-' + str(opening_sections) + r'][^#]+'
    opening_text = ' '.join(re.findall(section_pattern, transcript, re.DOTALL))

    for pattern in purpose_patterns:
        match = re.search(pattern, opening_text, re.IGNORECASE)
        if match:
            return match.group(0).strip()

    return "Not explicitly stated"


def extract_closing_conclusion(transcript: str, section_count: int) -> str:
    """
    Extract speaker's conclusions from final sections.
    Looks for conclusion indicators in last 10% of sections.
    """
    closing_start = section_count - (section_count // 10) or section_count - 1

    # Common conclusion indicators
    conclusion_patterns = [
        r"I think we can safely say[^.]+\.",
        r"in conclusion[^.]+\.",
        r"to conclude[^.]+\.",
        r"the answer[^.]+\.",
        r"I conclude[^.]+\.",
        r"this suggests[^.]+\.",
    ]

    # Search in last N sections
    section_pattern = r'## Section (' + '|'.join(str(i)
                                                 for i in range(closing_start, section_count + 1)) + r')[^#]+'
    closing_text = ' '.join(re.findall(section_pattern, transcript, re.DOTALL))

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
    total_sections = len(re.findall(r'## Section \d+', transcript))

    # Identify Q&A sections by speaker label patterns
    qa_indicators = [
        r'\*\*[A-Z][a-z]+\s*:\*\*',  # **Name:** pattern (questioner)
        r'\*\*Dr[.\s]+\w+:\*\*',      # **Dr. Name:** pattern (response)
        r'\*\*Audience',              # **Audience Member:**
        r'question',
        r'comment'
    ]

    qa_sections = 0
    qa_topics = []

    sections = re.split(r'## Section \d+[^\n]+\n', transcript)

    for section in sections:
        qa_indicator_count = sum(
            len(re.findall(pattern, section, re.IGNORECASE))
            for pattern in qa_indicators
        )

        if qa_indicator_count >= 2:  # Likely Q&A section
            qa_sections += 1

            # Extract potential topic words (nouns following "about" or "on")
            topic_matches = re.findall(
                r'(?:about|on|regarding)\s+(\w+(?:\s+\w+)?)', section, re.IGNORECASE)
            qa_topics.extend(topic_matches[:2])

    percentage = int((qa_sections / total_sections) *
                     100) if total_sections > 0 else 0

    # Deduplicate and limit topics
    unique_topics = list(dict.fromkeys(qa_topics))[:5]

    return percentage, unique_topics


def count_sections(transcript: str) -> int:
    """Count total sections in formatted transcript."""
    return len(re.findall(r'## Section \d+', transcript))


def prepare_abstract_input(
    metadata: dict,
    topics_markdown: str,
    themes_markdown: str,
    transcript: str,
    target_word_count: int = 250
) -> AbstractInput:
    """
    Prepare structured input for abstract generation API call.

    Args:
        metadata: Dict with speaker, event_type, title, domain
        topics_markdown: Raw Topics section from extraction output
        themes_markdown: Raw Key Themes section from extraction output  
        transcript: Full formatted transcript text
        target_word_count: Target word count for the abstract

    Returns:
        AbstractInput ready for serialization
    """
    section_count = count_sections(transcript)
    qa_percentage, qa_topics = calculate_qa_percentage(transcript)

    return AbstractInput(
        metadata=metadata,
        topics=parse_topics_from_extraction(topics_markdown),
        themes=parse_themes_from_extraction(themes_markdown),
        opening_purpose=extract_opening_purpose(transcript, section_count),
        closing_conclusion=extract_closing_conclusion(
            transcript, section_count),
        qa_percentage=qa_percentage,
        qa_topics=qa_topics,
        target_word_count=target_word_count
    )


# === API Integration ===

def load_prompt() -> str:
    """Load the abstract generation prompt template."""
    prompt_path = config.PROMPTS_DIR / config.PROMPT_STRUCTURED_ABSTRACT_FILENAME
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path}\n"
            f"Expected location: {config.PROMPTS_DIR}/{config.PROMPT_STRUCTURED_ABSTRACT_FILENAME}"
        )
    return prompt_path.read_text(encoding='utf-8')


def generate_abstract(
    abstract_input: AbstractInput,
    api_client,  # Anthropic client or compatible
    model: str = config.AUX_MODEL
) -> str:
    """
    Generate abstract via API call.

    Args:
        abstract_input: Prepared AbstractInput object
        api_client: Anthropic API client
        model: Model identifier

    Returns:
        Generated abstract text
    """
    prompt_template = load_prompt()
    prompt = prompt_template.format(
        input_json=abstract_input.to_json(),
        target_word_count=abstract_input.target_word_count)

    response = api_client.messages.create(
        model=model,
        max_tokens=400,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    return response.content[0].text.strip()


# === Validation ===

def validate_abstract(abstract: str, target_word_count: int = 250) -> dict:
    """
    Validate generated abstract against requirements.

    Returns:
        Dict with validation results and any issues found
    """
    issues = []

    word_count = len(abstract.split())

    # Allow 20% tolerance
    min_words = int(target_word_count * 0.8)
    max_words = int(target_word_count * 1.2)

    if word_count < min_words:
        issues.append(f"Too short: {word_count} words (minimum {min_words})")
    elif word_count > max_words:
        issues.append(f"Too long: {word_count} words (maximum {max_words})")

    # Check for prohibited elements
    if re.search(r'Section \d+', abstract):
        issues.append("Contains section references")

    if '"' in abstract and abstract.count('"') >= 2:
        issues.append("May contain direct quotations")

    if re.search(r'^\s*[-•*]\s', abstract, re.MULTILINE):
        issues.append("Contains bullet points")

    # Check for evaluative language
    evaluative_terms = ['important', 'valuable',
                        'insightful', 'excellent', 'crucial']
    found_evaluative = [
        t for t in evaluative_terms if t.lower() in abstract.lower()]
    if found_evaluative:
        issues.append(f"Contains evaluative language: {found_evaluative}")

    return {
        "valid": len(issues) == 0,
        "word_count": word_count,
        "issues": issues
    }


# === Example Usage ===

if __name__ == "__main__":
    # Example with mock data
    sample_metadata = {
        "speaker": "Dr. Michael Kerr",
        "event_type": "webinar",
        "title": "Roots of Bowen Theory",
        "domain": "Bowen family systems theory"
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
        transcript=sample_transcript
    )

    print("Prepared input:")
    print(abstract_input.to_json())
    print("\n" + "="*50 + "\n")
    print("Ready for API call with ABSTRACT_PROMPT_TEMPLATE")
