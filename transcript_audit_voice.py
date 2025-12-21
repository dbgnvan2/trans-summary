#!/usr/bin/env python3
"""
Audit blog post for Dr. Kerr's textual voice characteristics.

This script evaluates whether a blog post matches Dr. Kerr's distinctive
communication patterns and style, providing feedback on authenticity.

Usage:
    python transcript_audit_voice.py "Title - Presenter - Date"
    
Example:
    python transcript_audit_voice.py "Developing the Unidisease Concept - Monika Baege and Michael Kerr - 2010-09-23"
"""

import argparse
import json
import os
from pathlib import Path
import anthropic


# Directories
TRANSCRIPTS_BASE = Path(
    os.getenv("TRANSCRIPTS_DIR", Path.home() / "transcripts"))
SUMMARIES_DIR = TRANSCRIPTS_BASE / "summaries"


# System prompt defining Kerr's voice characteristics
VOICE_CHARACTERISTICS = """
Dr. Michael Kerr's Textual Voice Print - Key Characteristics:

1. **Intellectual Humility & Self-Awareness**
   - Frequent acknowledgment of uncertainty ("I think...", "It seems to me...")
   - Self-deprecating humor and candid admissions of confusion or mistakes
   - Willingness to say "I don't know" or "I could be wrong"

2. **Long-Form, Exploratory Sentence Structure**
   - Extended sentences with multiple clauses and qualifications
   - Tangential asides introduced mid-thought ("but anyway...", "make a long story short...")
   - Stream-of-consciousness quality that circles back to main points

3. **Concrete Examples & Personal Anecdotes**
   - Regular use of specific clinical cases or personal experiences
   - Stories about patients, family members, or professional encounters
   - Grounding of abstract concepts in lived experience

4. **Systems Thinking Language**
   - Emphasis on "relationship process" and "context"
   - Avoidance of simple cause-and-effect explanations
   - Frequent use of terms like "complexity," "interaction," "disturbance"

5. **Reverence for Bowen Theory with Critical Engagement**
   - Respectful citations of Murray Bowen's ideas
   - Willingness to refine or extend theory based on experience
   - Balance between theoretical fidelity and clinical innovation

6. **Biological & Scientific Grounding**
   - Integration of medical/biological research findings
   - References to specific studies, researchers, or biological mechanisms
   - Bridging between cellular/molecular and family systems levels

7. **Measured Optimism About Theory's Future**
   - Long-term perspective on paradigm shifts ("not in my lifetime, but...")
   - Confidence in theory's accuracy despite inability to "prove" it
   - Focus on usefulness over validation

8. **Conversational Informality**
   - Occasional mild profanity or colloquialisms ("damn thing")
   - Direct address to audience or interviewer
   - Natural speech patterns even in formal writing

9. **Emphasis on Learning Over Teaching**
   - Frequent references to "lessons learned" from patients
   - Research attitude over therapeutic intervention
   - Curiosity-driven rather than outcome-driven stance

10. **Careful Qualification & Nuance**
    - Multiple perspectives presented on complex issues
    - Recognition of exceptions and variations
    - Avoidance of oversimplification or dogmatic statements
"""


EVALUATOR_PROMPT = """You are an expert evaluator assessing whether text authentically represents Dr. Michael Kerr's distinctive communication style.

VOICE CHARACTERISTICS TO EVALUATE:
{voice_characteristics}

TEXT TO EVALUATE:
{generated_text}

EVALUATION CRITERIA:
Assess the text on these dimensions (score each 0-10):

1. **Intellectual Humility** (0-10): Does the text show appropriate uncertainty, self-awareness, and willingness to admit limitations?

2. **Sentence Structure** (0-10): Are sentences exploratory, multi-clausal, with natural tangents and qualifications?

3. **Concrete Examples** (0-10): Are abstract concepts grounded in specific cases, stories, or personal experiences?

4. **Systems Thinking** (0-10): Is there emphasis on relationships, context, complexity vs. simple causation?

5. **Bowen Theory Integration** (0-10): Are references to Bowen theory respectful yet critically engaged?

6. **Scientific Grounding** (0-10): Is there integration of biological/medical research appropriately?

7. **Tone & Voice** (0-10): Does the conversational, informal, exploratory tone feel authentic?

8. **Learning Stance** (0-10): Is there emphasis on learning from patients/experience vs. prescriptive teaching?

9. **Nuance & Qualification** (0-10): Are complex issues presented with appropriate qualifications and multiple perspectives?

10. **Overall Authenticity** (0-10): Does this sound like Dr. Kerr could have written/said it?

RESPONSE FORMAT (JSON):
{{
  "scores": {{
    "intellectual_humility": <0-10>,
    "sentence_structure": <0-10>,
    "concrete_examples": <0-10>,
    "systems_thinking": <0-10>,
    "bowen_integration": <0-10>,
    "scientific_grounding": <0-10>,
    "tone_and_voice": <0-10>,
    "learning_stance": <0-10>,
    "nuance_qualification": <0-10>,
    "overall_authenticity": <0-10>
  }},
  "total_score": <sum of all scores>,
  "percentage": <total/100>,
  "pass": <true if percentage >= 75, false otherwise>,
  "failed_criteria": [<list of criteria scoring below 7>],
  "strengths": "<1-2 sentences on what works well>",
  "improvements": "<1-2 sentences on what could be more authentic>",
  "specific_examples": "<1-2 quotes from text showing authentic or inauthentic voice>"
}}

Provide only the JSON response, no additional commentary.
"""


def load_blog_post(base_name: str) -> str:
    """Load blog post content."""
    blog_file = SUMMARIES_DIR / f"{base_name} - blog.md"

    if not blog_file.exists():
        raise FileNotFoundError(f"Blog post not found: {blog_file}")

    with open(blog_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Strip YAML front matter if present
    if content.startswith('---'):
        parts = content.split('---\n', 2)
        if len(parts) >= 3:
            content = parts[2]

    return content


def audit_voice(blog_content: str, api_key: str) -> dict:
    """Audit blog content for Kerr voice characteristics."""

    client = anthropic.Anthropic(api_key=api_key)

    print("\n🔍 Evaluating text for Dr. Kerr's voice characteristics...")
    print(f"   Content length: {len(blog_content)} characters\n")

    # Create evaluation prompt
    evaluation_prompt = EVALUATOR_PROMPT.format(
        voice_characteristics=VOICE_CHARACTERISTICS,
        generated_text=blog_content
    )

    # Call Claude for evaluation
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        temperature=0.3,
        messages=[
            {
                "role": "user",
                "content": evaluation_prompt
            }
        ]
    )

    # Parse JSON response
    response_text = response.content[0].text

    # Handle potential markdown code blocks
    if response_text.strip().startswith('```'):
        # Extract JSON from code block
        lines = response_text.strip().split('\n')
        json_text = '\n'.join(
            lines[1:-1] if lines[-1].strip() == '```' else lines[1:])
    else:
        json_text = response_text

    audit_result = json.loads(json_text)

    return audit_result


def print_audit_results(audit_result: dict):
    """Print formatted audit results."""

    print("\n" + "="*80)
    print("VOICE AUDIT RESULTS")
    print("="*80)

    scores = audit_result['scores']

    print("\nINDIVIDUAL SCORES:")
    print("-" * 80)

    criteria_labels = {
        'intellectual_humility': 'Intellectual Humility',
        'sentence_structure': 'Sentence Structure',
        'concrete_examples': 'Concrete Examples',
        'systems_thinking': 'Systems Thinking',
        'bowen_integration': 'Bowen Theory Integration',
        'scientific_grounding': 'Scientific Grounding',
        'tone_and_voice': 'Tone & Voice',
        'learning_stance': 'Learning Stance',
        'nuance_qualification': 'Nuance & Qualification',
        'overall_authenticity': 'Overall Authenticity'
    }

    for key, label in criteria_labels.items():
        score = scores[key]
        bar = "█" * score + "░" * (10 - score)
        status = "✓" if score >= 7 else "✗"
        print(f"{status} {label:.<35} {score:>2}/10  {bar}")

    print("\nSUMMARY:")
    print("-" * 80)
    print(f"Total Score:      {audit_result['total_score']}/100")
    print(f"Percentage:       {audit_result['percentage']:.1%}")
    print(
        f"Overall Result:   {'✅ PASS' if audit_result['pass'] else '❌ FAIL'}")

    if audit_result['failed_criteria']:
        print(
            f"\nFailed Criteria:  {', '.join(audit_result['failed_criteria'])}")

    print("\nSTRENGTHS:")
    print(audit_result['strengths'])

    print("\nIMPROVEMENTS:")
    print(audit_result['improvements'])

    print("\nEXAMPLES:")
    print(audit_result['specific_examples'])

    print("\n" + "="*80)


def save_audit_report(base_name: str, audit_result: dict):
    """Save audit report to file."""

    report_file = SUMMARIES_DIR / f"{base_name} - voice-audit.json"

    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(audit_result, f, indent=2)

    print(f"\n📄 Audit report saved to: {report_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Audit blog post for Dr. Kerr's textual voice characteristics"
    )
    parser.add_argument(
        "base_name",
        help='Base name without suffix (e.g., "Title - Presenter - Date")'
    )
    parser.add_argument(
        "--save-report",
        action="store_true",
        help="Save audit report to JSON file"
    )

    args = parser.parse_args()

    # Get API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ Error: ANTHROPIC_API_KEY environment variable not set")
        return 1

    try:
        # Load blog post
        print(f"📄 Loading blog post: {args.base_name}")
        blog_content = load_blog_post(args.base_name)

        # Audit voice
        audit_result = audit_voice(blog_content, api_key)

        # Print results
        print_audit_results(audit_result)

        # Save report if requested
        if args.save_report:
            save_audit_report(args.base_name, audit_result)

        # Return appropriate exit code
        return 0 if audit_result['pass'] else 1

    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        return 1
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing audit response: {e}")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
