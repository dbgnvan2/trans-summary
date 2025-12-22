#!/usr/bin/env python3
"""
Abstract Quality Validator using Claude API
Evaluates and revises abstracts against source transcripts.

Takes the "extracts-summary" file (which contains the initial abstract)
and validates it against the original formatted transcript, then creates
high-quality short and extended abstracts.

Usage:
    python transcript_validate_abstract.py "Title - Presenter - Date"
    
Example:
    python transcript_validate_abstract.py "Roots of Bowen Theory - Dr Michael Kerr - 2019-11-15"
"""

import argparse
import os
from pathlib import Path
import anthropic
import re


# Directories (from environment variable)
TRANSCRIPTS_BASE = Path(
    os.getenv("TRANSCRIPTS_DIR", Path.home() / "transcripts"))
FORMATTED_DIR = TRANSCRIPTS_BASE / "formatted"
SUMMARIES_DIR = TRANSCRIPTS_BASE / "summaries"
PROMPTS_DIR = TRANSCRIPTS_BASE / "prompts"

# Prompt file name
ABSTRACT_VALIDATION_PROMPT = "abstract_quality_assessment_prompt_v2.md"


def load_prompt() -> str:
    """Load the abstract validation prompt template."""
    prompt_path = PROMPTS_DIR / ABSTRACT_VALIDATION_PROMPT
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path}\n"
            f"Expected location: $TRANSCRIPTS_DIR/prompts/{ABSTRACT_VALIDATION_PROMPT}"
        )
    return prompt_path.read_text(encoding='utf-8')


def load_formatted_transcript(base_name: str) -> str:
    """Load the formatted transcript."""
    transcript_path = FORMATTED_DIR / f"{base_name} - formatted.md"
    if not transcript_path.exists():
        raise FileNotFoundError(
            f"Formatted transcript not found: {transcript_path}\n"
            f"Expected location: $TRANSCRIPTS_DIR/formatted/{base_name} - formatted.md"
        )
    return transcript_path.read_text(encoding='utf-8')


def load_extracts_summary(base_name: str) -> tuple[str, str]:
    """Load the extracts-summary file and extract the abstract section.
    Returns (full_content, abstract_only)"""
    summary_path = SUMMARIES_DIR / f"{base_name} - extracts-summary.md"
    if not summary_path.exists():
        raise FileNotFoundError(
            f"Extracts-summary file not found: {summary_path}\n"
            f"Expected location: $TRANSCRIPTS_DIR/summaries/{base_name} - extracts-summary.md\n"
            f"Run transcript_summarize.py first to generate this file."
        )

    content = summary_path.read_text(encoding='utf-8')

    # Find the ## Abstract section (with or without bold markers)
    # Pattern: ## Abstract or ## **Abstract** followed by content until next ## heading or ---
    abstract_match = re.search(
        r'## (?:\*\*)?Abstract(?:\*\*)?\s*\n\n(.*?)(?=\n---|\n## |\Z)',
        content,
        flags=re.DOTALL
    )

    if abstract_match:
        abstract = abstract_match.group(1).strip()
    else:
        raise ValueError(
            f"Could not find ## Abstract section in {summary_path}\n"
            "The extracts-summary file may have an unexpected format."
        )

    return content, abstract


def fill_prompt_template(template: str, source_document: str, abstract: str) -> str:
    """Fill in the prompt template with source document and abstract."""
    filled = template.replace("{source_document}", source_document)
    filled = filled.replace("{abstract}", abstract)
    return filled


def validate_abstract_with_claude(prompt: str, model: str = "claude-sonnet-4-5-20250929") -> str:
    """Send prompt to Claude for abstract validation and revision."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable not set.\n"
            "Set it with: export ANTHROPIC_API_KEY='your-api-key'"
        )

    client = anthropic.Anthropic(api_key=api_key)

    print("📊 Evaluating abstract quality...")
    print("   This will assess and revise the abstract in three tasks:")
    print("   1. Quality assessment with scores")
    print("   2. Short abstract generation (<150 words)")
    print("   3. Extended abstract generation (350-400 words)")

    message = client.messages.create(
        model=model,
        max_tokens=16000,
        temperature=0.3,  # Lower temperature for more consistent evaluation
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    # Display token usage
    print(f"   Tokens: {message.usage.input_tokens:,} input + {message.usage.output_tokens:,} output = {message.usage.input_tokens + message.usage.output_tokens:,} total")

    # Check for truncation
    if message.stop_reason == "max_tokens":
        print("\n⚠️  WARNING: Abstract validation output truncated!")
        raise RuntimeError("Output truncated at max_tokens limit")

    # Warn if close to limit
    if message.usage.output_tokens > 14400:  # 90% of 16000
        print(
            f"   ⚠️  Warning: Used {message.usage.output_tokens:,}/16,000 output tokens ({message.usage.output_tokens/160:.0f}%)")

    return message.content[0].text


def save_abstracts(content: str, base_name: str) -> Path:
    """Save the abstracts validation output."""
    output_filename = f"{base_name} - abstracts.md"
    output_path = SUMMARIES_DIR / output_filename

    # Create directory if it doesn't exist
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)

    output_path.write_text(content, encoding='utf-8')
    return output_path


def extract_scores_from_output(output: str) -> dict:
    """Extract assessment scores from the Claude output for display."""
    scores = {}

    # Try to find the scores table
    table_pattern = r'\| (.*?) \| (\d+)/5 \|'
    matches = re.findall(table_pattern, output)

    for dimension, score in matches:
        dimension = dimension.strip()
        if dimension and dimension != "Dimension":
            scores[dimension] = int(score)

    # Also look for Overall score with decimal
    # Format 1: | **Overall** | **3.6** |
    overall_match = re.search(
        r'\|\s*\*\*Overall\*\*\s*\|\s*\*\*(\d+(?:\.\d+)?)\*\*\s*\|', output)
    if not overall_match:
        # Format 2: **Overall** | **3.6**/5
        overall_match = re.search(
            r'\*\*Overall\*\*\s*\|\s*\*\*(\d+(?:\.\d+)?)/5\*\*', output)
    if not overall_match:
        # Format 3: **Overall** | 3.6/5
        overall_match = re.search(
            r'\*\*Overall\*\*\s*\|\s*(\d+(?:\.\d+)?)/5', output)
    if overall_match:
        scores['Overall'] = float(overall_match.group(1))

    return scores


def extract_extended_abstract(output: str) -> str:
    """Extract the extended abstract from the validation output."""
    # Pattern: ## EXTENDED ABSTRACT followed by content until end or next ##
    match = re.search(
        r'## EXTENDED ABSTRACT\s*\n\n(.*?)(?=\n##|\Z)',
        output,
        flags=re.DOTALL
    )
    if match:
        return match.group(1).strip()
    return ""


def extract_recommendations(output: str) -> str:
    """Extract the recommendations section from the validation output."""
    # Pattern: ### Recommendations followed by numbered list
    match = re.search(
        r'### Recommendations\s*\n(.*?)(?=\n---|\n##|\Z)',
        output,
        flags=re.DOTALL
    )
    if match:
        return match.group(1).strip()
    return ""


def display_summary(output: str, abstracts_path: Path, best_iteration: int = 1, final_score: float = 0, total_iterations: int = 1):
    """Display a summary of the validation results."""
    print("\n" + "="*60)
    if total_iterations > 1:
        print(f"VALIDATION COMPLETE - {total_iterations} ITERATIONS")
        print(f"BEST SCORE: {final_score}/5 (from Iteration {best_iteration})")
    else:
        print("VALIDATION COMPLETE")
    print("="*60)

    scores = extract_scores_from_output(output)

    if scores:
        print("\n📊 Quality Assessment Scores:")
        for dimension, score in scores.items():
            if dimension == 'Overall':
                print(f"\n   {'='*40}")
                # Handle float scores
                bar_length = int(score)
                partial = score - bar_length
                bar = '█' * bar_length
                if partial >= 0.5:
                    bar += '▌'
                bar += '░' * (5 - bar_length - (1 if partial >= 0.5 else 0))
                print(f"   {dimension:30} {score}/5  {bar}")
                print(f"   {'='*40}")
            else:
                print(
                    f"   {dimension:30} {score}/5  {'█' * score}{'░' * (5-score)}")

    # Check if short abstract exists
    if "## SHORT ABSTRACT" in output:
        print("\n✅ Short abstract generated (<150 words)")

    # Check if extended abstract exists
    if "## EXTENDED ABSTRACT" in output:
        print("✅ Extended abstract generated (350-400 words)")

    print(f"\n📄 Complete validation report saved to:")
    print(f"   {abstracts_path}")
    print("\n" + "="*60)


def main():
    parser = argparse.ArgumentParser(
        description="Validate and revise abstracts from extracts-summary files."
    )
    parser.add_argument(
        "base_name",
        help="Base name of transcript (e.g., 'Title - Presenter - Date')"
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-5-20250929",
        help="Claude model to use (default: claude-sonnet-4-5-20250929)"
    )
    parser.add_argument(
        "--target-score",
        type=float,
        default=4.5,
        help="Target quality score (default: 4.5)"
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum number of improvement iterations (default: 3)"
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Run without interactive prompts (auto-continue until target reached)"
    )

    args = parser.parse_args()

    try:
        print(f"📄 Loading files for: {args.base_name}")

        # Load the formatted transcript (source)
        print("   Loading formatted transcript...")
        transcript = load_formatted_transcript(args.base_name)
        print(f"   ✓ Source document: {len(transcript)} characters")

        # Load the extracts-summary file and extract abstract
        print("   Loading extracts-summary file...")
        _full_content, initial_abstract = load_extracts_summary(args.base_name)
        print(
            f"   ✓ Initial abstract: {len(initial_abstract)} characters ({len(initial_abstract.split())} words)")

        # Load the validation prompt
        print("   Loading validation prompt...")
        prompt_template = load_prompt()

        # Iterative improvement
        current_abstract = initial_abstract
        all_outputs = []
        best_score = 0
        best_iteration = 0
        best_output = None

        print(f"\n🎯 Target score: {args.target_score}/5.0")
        print(f"🔄 Max iterations: {args.max_iterations}")

        # Iteration 0: Evaluate the initial abstract (baseline)
        print(f"\n{'='*60}")
        print(f"ITERATION 0 (Initial Abstract Evaluation)")
        print(f"{'='*60}")

        prompt = fill_prompt_template(
            prompt_template, transcript, current_abstract)

        print(f"🔍 Evaluating initial abstract (model: {args.model})...")
        validation_output = validate_abstract_with_claude(
            prompt, args.model)

        all_outputs.append({
            'iteration': 0,
            'output': validation_output,
            'abstract': current_abstract
        })

        # Extract scores from initial evaluation
        scores = extract_scores_from_output(validation_output)
        overall_score = scores.get('Overall', 0)

        print(f"\n📊 Initial Score: {overall_score}/5.0")

        # Display score breakdown
        if scores:
            print(f"\n   Score Breakdown:")
            for dimension, score in scores.items():
                if dimension != 'Overall':
                    print(f"   • {dimension:30} {score}/5")

        # Set initial score as baseline
        best_score = overall_score
        best_iteration = 0
        best_output = validation_output

        # Check if initial abstract already meets target
        if overall_score >= args.target_score:
            print(
                f"\n✅ Initial abstract already meets target score! ({overall_score} >= {args.target_score})")
            print(f"   No improvements needed.")
            # Skip to saving results
        else:
            # Prompt user if they want to continue to improvements
            print(
                f"\n🤔 Initial score: {overall_score}/5.0 (target: {args.target_score})")

            if args.auto:
                # Auto mode: continue without prompting
                iteration = 1
            else:
                try:
                    response = input(
                        "\n   Continue to improvement iterations? (Y/n): ").strip().lower()
                    if response in ['n', 'no']:
                        print(
                            f"\n⏹️  Stopping at user request after initial evaluation")
                        print(
                            f"   Using initial abstract (score: {best_score}/5.0)")
                        # Skip to saving results
                        iteration = args.max_iterations + 1
                    else:
                        iteration = 1
                except (KeyboardInterrupt, EOFError):
                    print(
                        f"\n\n⏹️  Interrupted by user after initial evaluation")
                    print(
                        f"   Using initial abstract (score: {best_score}/5.0)")
                    iteration = args.max_iterations + 1

        # Improvement iterations (1 to max_iterations)
        while iteration <= args.max_iterations:
            print(f"\n{'='*60}")
            print(f"ITERATION {iteration}")
            print(f"{'='*60}")

            # Extract the extended abstract from previous iteration for revision
            next_abstract = extract_extended_abstract(validation_output)
            if not next_abstract:
                print("⚠️  Could not extract extended abstract for revision")
                break

            current_abstract = next_abstract
            print(f"🔄 Revising abstract...")

            # Fill in the template with revised abstract
            prompt = fill_prompt_template(
                prompt_template, transcript, current_abstract)

            # Send to Claude for validation
            print(f"🔍 Evaluating revised abstract (model: {args.model})...")
            validation_output = validate_abstract_with_claude(
                prompt, args.model)

            # Store this iteration's output
            all_outputs.append({
                'iteration': iteration,
                'output': validation_output,
                'abstract': current_abstract
            })

            # Extract scores
            scores = extract_scores_from_output(validation_output)
            overall_score = scores.get('Overall', 0)

            print(f"\n📊 Iteration {iteration} Score: {overall_score}/5.0")

            # Display score breakdown
            if scores:
                print(f"\n   Score Breakdown:")
                for dimension, score in scores.items():
                    if dimension != 'Overall':
                        print(f"   • {dimension:30} {score}/5")

            # Track the best score
            if overall_score > best_score:
                best_score = overall_score
                best_iteration = iteration
                best_output = validation_output
                print(f"   ⭐ New best score!")

            # Check if we've reached the target
            if overall_score >= args.target_score:
                print(
                    f"\n✅ Target score achieved! ({overall_score} >= {args.target_score})")
                break

            # Check if this is the last allowed iteration
            if iteration >= args.max_iterations:
                print(
                    f"\n⚠️  Maximum iterations reached ({args.max_iterations})")
                print(
                    f"   Best score: {best_score}/5.0 (iteration {best_iteration})")
                print(
                    f"   Final score: {overall_score}/5.0 (target: {args.target_score})")
                break

            # Prompt user if they want to continue
            print(
                f"\n🤔 Current score: {overall_score}/5.0 (target: {args.target_score})")
            print(
                f"   Best score so far: {best_score}/5.0 (iteration {best_iteration})")

            if args.auto:
                # Auto mode: continue without prompting
                iteration += 1
                continue

            try:
                response = input(
                    "\n   Continue to next iteration? (Y/n): ").strip().lower()
                if response in ['n', 'no']:
                    print(
                        f"\n⏹️  Stopping at user request after iteration {iteration}")
                    print(
                        f"   Using best result: iteration {best_iteration} (score: {best_score}/5.0)")
                    break
            except (KeyboardInterrupt, EOFError):
                print(
                    f"\n\n⏹️  Interrupted by user after iteration {iteration}")
                print(
                    f"   Using best result: iteration {best_iteration} (score: {best_score}/5.0)")
                break

            iteration += 1

        # Use the best output for final report
        if best_output:
            validation_output = best_output
            overall_score = best_score
            print(
                f"\n🏆 Using best result from iteration {best_iteration} (score: {best_score}/5.0)")

        # Compile final output with all iterations
        final_output = f"# Abstract Validation Report\n\n"
        final_output += f"**Target Score:** {args.target_score}/5.0\n"
        final_output += f"**Total Iterations:** {len(all_outputs)}\n"
        final_output += f"**Best Score:** {best_score}/5.0 (Iteration {best_iteration})\n"
        final_output += f"**Final Score:** {overall_score}/5.0\n"

        if overall_score >= args.target_score:
            final_output += f"**Status:** ✅ TARGET ACHIEVED\n\n"
        else:
            final_output += f"**Status:** ⚠️ Target not achieved after {args.max_iterations} iterations\n\n"

        final_output += "---\n\n"

        # Add each iteration
        for i, result in enumerate(all_outputs, 1):
            final_output += f"# ITERATION {i}\n\n"
            if i == 1:
                final_output += f"## Initial Abstract (from extracts-summary)\n\n"
                final_output += f"{result['abstract']}\n\n"
                final_output += "---\n\n"
            final_output += result['output']
            if i < len(all_outputs):
                final_output += "\n\n" + "="*60 + "\n\n"

        # Save the results
        abstracts_path = save_abstracts(final_output, args.base_name)

        # Display summary
        display_summary(validation_output, abstracts_path,
                        best_iteration, overall_score, len(all_outputs))

        return 0

    except FileNotFoundError as e:
        print(f"\n❌ File not found: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
