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
import config

    return prompt_path.read_text(encoding='utf-8')


def load_blog_post(base_name: str) -> str:
    """Load blog post content."""
    blog_file = config.PROJECTS_DIR / base_name / \
        f"{base_name}{config.SUFFIX_BLOG}"

    if not blog_file.exists():
        blog_file = config.SUMMARIES_DIR / f"{base_name}{config.SUFFIX_BLOG}"
        if not blog_file.exists():
            raise FileNotFoundError(f"Blog post not found: {blog_file}")

    with open(blog_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Strip YAML front matter if present
    if content.startswith('---: -
        if len(parts) >= 3:
            content=parts[2]

    return content


def audit_voice(blog_content: str, api_key: str) -> dict:
    """Audit blog content for Kerr voice characteristics."""

    client=anthropic.Anthropic(api_key=api_key)

    print("\n🔍 Evaluating text for Dr. Kerr's voice characteristics...")
    print(f"   Content length: {len(blog_content)} characters\n")

    # Create evaluation prompt
    prompt_template=load_prompt()
    evaluation_prompt=prompt_template.replace(
        "{{blog_content}}", blog_content)

    # Call Claude for evaluation
    response=client.messages.create(
        model=config.DEFAULT_MODEL,
        max_tokens=config.MAX_TOKENS_AUDIT,
        temperature=config.TEMP_BALANCED,
        messages=[
            {
                "role": "user",
                "content": evaluation_prompt
            }
        ]
    )

    # Parse JSON response
    response_text=response.content[0].text

    # Handle potential markdown code blocks
    if response_text.strip().startswith('```'):
        # Extract JSON from code block
        lines=response_text.strip().split('\n')
        json_text='\n'.join(
            lines[1:-1] if lines[-1].strip() == '```' else lines[1:])
    else:
        json_text=response_text

    audit_result=json.loads(json_text)

    return audit_result


def print_audit_results(audit_result: dict):
    """Print formatted audit results."""

    print("\n" + "="*80)
    print("VOICE AUDIT RESULTS")
    print("="*80)

    scores=audit_result['scores']

    print("\nINDIVIDUAL SCORES:")
    print("-" * 80)

    criteria_labels={
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
        score=scores[key]
        bar="█" * score + "░" * (10 - score)
        status="✓" if score >= 7 else "✗"
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

    report_file=config.PROJECTS_DIR / base_name /
        f"{base_name}{config.SUFFIX_VOICE_AUDIT}"
    report_file.parent.mkdir(parents=True, exist_ok=True)

    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(audit_result, f, indent=2)

    print(f"\n📄 Audit report saved to: {report_file}")


def main():
    parser=argparse.ArgumentParser(

    parser.add_argument(
        "base_name",
        help='Base name without suffix (e.g., "Title - Presenter - Date")'
    )
    parser.add_argument(
        "--save-report",
        action="store_true",
        help="Save audit report to JSON file"
    )

    args=parser.parse_args()

    # Get API key
    api_key=os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ Error: ANTHROPIC_API_KEY environment variable not set")
        return 1

    try:
        # Load blog post
        print(f"📄 Loading blog post: {args.base_name}")
        blog_content=load_blog_post(args.base_name)

        # Audit voice
        audit_result=audit_voice(blog_content, api_key)

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
