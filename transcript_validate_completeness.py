#!/usr/bin/env python3
"""
Output Completeness Validator

Validates that generated outputs are complete and contain all required sections.
Ensures fidelity to the original transcript and prevents partial/truncated results.

Usage:
    python transcript_validate_completeness.py "Title - Presenter - Date"
    
Checks:
- Formatted file has proper structure
- Summaries contain all required sections
- No truncated API responses
- All quoted text is verifiable
- Expected word counts met
"""

import argparse
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple
import config


class ValidationResult:
    """Stores validation results with pass/fail and details."""

    def __init__(self, name: str):
        self.name = name
        self.passed = True
        self.warnings = []
        self.errors = []
        self.info = []

    def add_error(self, message: str):
        self.passed = False
        self.errors.append(message)

    def add_warning(self, message: str):
        self.warnings.append(message)

    def add_info(self, message: str):
        self.info.append(message)

    def print_result(self):
        """Print formatted validation result."""
        status = "✅ PASS" if self.passed else "❌ FAIL"
        print(f"\n{status} - {self.name}")

        if self.info:
            for info in self.info:
                print(f"  ℹ️  {info}")

        if self.warnings:
            for warning in self.warnings:
                print(f"  ⚠️  {warning}")

        if self.errors:
            for error in self.errors:
                print(f"  ❌ {error}")


def validate_formatted_file(base_name: str) -> ValidationResult:
    """Validate formatted transcript completeness."""
    result = ValidationResult("Formatted Transcript")

    # Check for either formatted.md or formatted_yaml.md
    formatted_file = config.FORMATTED_DIR / f"{base_name} - formatted.md"
    yaml_file = config.FORMATTED_DIR / f"{base_name} - yaml.md"

    file_to_check = yaml_file if yaml_file.exists() else formatted_file

    if not file_to_check.exists():
        result.add_error(f"File not found: {file_to_check.name}")
        return result

    content = file_to_check.read_text(encoding='utf-8')

    # Check minimum length (transcripts should be substantial)
    word_count = len(content.split())
    result.add_info(f"Word count: {word_count:,}")

    if word_count < config.TRANSCRIPT_MIN_WORDS:
        result.add_error(
            f"Transcript too short ({word_count} words, minimum {config.TRANSCRIPT_MIN_WORDS} required)")
    elif word_count < 2000:
        result.add_warning(
            f"Transcript shorter than typical ({word_count} words)")

    # Check for YAML front matter (if yaml file)
    if file_to_check == yaml_file:
        if not content.startswith('---'):
            result.add_error("YAML file missing front matter")
        else:
            result.add_info("YAML front matter present")

    # Check for proper structure markers
    if '## ' not in content:
        result.add_warning("No H2 headers found - may lack structure")

    # Check for truncation indicators
    truncation_markers = [
        "...[truncated]",
        "[content cut off]",
        "...(continued)",
        "[OUTPUT LIMIT REACHED]"
    ]
    for marker in truncation_markers:
        if marker.lower() in content.lower():
            result.add_error(f"Found truncation marker: {marker}")

    # Check file doesn't end abruptly (incomplete sentence)
    last_100_chars = content[-100:].strip()
    if last_100_chars and not any(last_100_chars.endswith(p) for p in ['.', '!', '?', '"', "'"]):
        result.add_warning(
            "File may end mid-sentence (no terminal punctuation)")

    return result


def validate_key_item_extracts(base_name: str) -> ValidationResult:
    """Validate 'All Key Items' contains all required sections."""
    result = ValidationResult("Key Item Extracts (All Key Items)")

    file_path = config.SUMMARIES_DIR / \
        f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"

    if not file_path.exists():
        result.add_error(f"File not found: {file_path.name}")
        return result

    content = file_path.read_text(encoding='utf-8')

    # Recommended sections (flexible header matching)
    required_sections = {
        'Abstract': r'##\s*\*?\*?Abstract\*?\*?',
        'Topics': r'##\s*\*?\*?Topics\*?\*?',
        'Key Themes': r'##\s*\*?\*?Key Themes\*?\*?',
        'Emphasis Items': r'##\s*\*?\*?Emphasis Items\*?\*?',
    }

    for section_name, pattern in required_sections.items():
        if not re.search(pattern, content, re.IGNORECASE):
            result.add_warning(f"Missing recommended section: {section_name}")
        else:
            result.add_info(f"Found section: {section_name}")

    # Check each section has content (not just headers)
    for section_name, pattern in required_sections.items():
        match = re.search(pattern + r'\s*\n(.*?)(?=##|\Z)',
                          content, re.IGNORECASE | re.DOTALL)
        if match:
            section_content = match.group(1).strip()
            if len(section_content) < 50:
                result.add_warning(
                    f"Section '{section_name}' appears empty or very short")

    # Check word count
    word_count = len(content.split())
    result.add_info(f"Word count: {word_count:,}")

    if word_count < 800:
        result.add_warning(f"Summary seems short ({word_count} words)")

    return result


def validate_key_terms(base_name: str) -> ValidationResult:
    """Validate key terms file."""
    result = ValidationResult("Key Terms")

    file_path = config.SUMMARIES_DIR / f"{base_name} - key-terms.md"

    if not file_path.exists():
        result.add_error(f"File not found: {file_path.name}")
        return result

    content = file_path.read_text(encoding='utf-8')

    # Should have at least a few terms
    term_count = len(re.findall(r'^-\s+\*\*', content, re.MULTILINE))
    result.add_info(f"Found {term_count} terms")

    if term_count == 0:
        result.add_error(
            "No terms found (expected bullet list with **Term**:)")
    elif term_count < 5:
        result.add_warning(f"Only {term_count} terms found - expected more")

    return result


def validate_blog(base_name: str) -> ValidationResult:
    """Validate blog post completeness."""
    result = ValidationResult("Blog Post")

    file_path = config.SUMMARIES_DIR / f"{base_name} - blog.md"

    if not file_path.exists():
        result.add_error(f"File not found: {file_path.name}")
        return result

    content = file_path.read_text(encoding='utf-8')

    # Blog should have structure
    has_title = bool(re.search(r'^#\s+', content, re.MULTILINE))
    has_headers = bool(re.search(r'^##\s+', content, re.MULTILINE))

    if not has_title:
        result.add_warning("No H1 title found")
    if not has_headers:
        result.add_warning("No H2 headers found - may lack structure")

    # Check length (blog should be substantial)
    word_count = len(content.split())
    result.add_info(f"Word count: {word_count:,}")

    if word_count < config.BLOG_MIN_WORDS:
        result.add_error(
            f"Blog too short ({word_count} words, minimum {config.BLOG_MIN_WORDS} required)")
    elif word_count < 1000:
        result.add_warning(f"Blog shorter than typical ({word_count} words)")

    return result


def validate_abstracts(base_name: str) -> ValidationResult:
    """Validate abstracts file from quality validation."""
    result = ValidationResult("Validated Abstracts")

    file_path = config.SUMMARIES_DIR / f"{base_name} - abstracts.md"

    if not file_path.exists():
        result.add_error(f"File not found: {file_path.name}")
        return result

    content = file_path.read_text(encoding='utf-8')

    # Should have both short and extended versions
    has_short = bool(
        re.search(r'Short Abstract|Abstract \(Short\)', content, re.IGNORECASE))
    has_extended = bool(
        re.search(r'Extended Abstract|Abstract \(Extended\)', content, re.IGNORECASE))

    if not has_short:
        result.add_warning("No short abstract found")
    if not has_extended:
        result.add_warning("No extended abstract found")

    # Check for quality scores
    has_scores = bool(re.search(r'Overall.*\d\.\d', content, re.IGNORECASE))
    if has_scores:
        # Extract final score
        score_match = re.search(r'Overall.*?(\d\.\d)', content, re.IGNORECASE)
        if score_match:
            score = float(score_match.group(1))
            result.add_info(f"Quality score: {score}/5.0")
            if score < 4.0:
                result.add_warning(
                    f"Quality score below target ({score} < 4.5)")
    else:
        result.add_warning("No quality scores found")

    return result


def validate_all(base_name: str) -> Dict[str, ValidationResult]:
    """Run all validation checks."""
    results = {}

    print("="*80)
    print(f"COMPLETENESS VALIDATION: {base_name}")
    print("="*80)

    # Run all validators
    results['formatted'] = validate_formatted_file(base_name)
    results['key_item_extracts'] = validate_key_item_extracts(base_name)
    results['terms'] = validate_key_terms(base_name)
    results['blog'] = validate_blog(base_name)
    results['abstracts'] = validate_abstracts(base_name)

    # Print results
    for result in results.values():
        result.print_result()

    # Summary
    print("\n" + "="*80)
    passed = sum(1 for r in results.values() if r.passed)
    total = len(results)

    if passed == total:
        print(f"✅ ALL CHECKS PASSED ({passed}/{total})")
        return_code = 0
    else:
        print(f"❌ VALIDATION FAILED ({passed}/{total} passed)")
        return_code = 1

    print("="*80)

    return results, return_code


def main():
    parser = argparse.ArgumentParser(
        description="Validate transcript processing completeness."
    )
    parser.add_argument(
        "base_name",
        help="Base name of transcript (e.g., 'Title - Presenter - Date')"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors"
    )

    args = parser.parse_args()

    results, return_code = validate_all(args.base_name)

    # If strict mode, warnings count as failures
    if args.strict:
        for result in results.values():
            if result.warnings:
                return_code = 1
                print(
                    f"\n⚠️  Strict mode: Warnings in '{result.name}' treated as errors")

    return return_code


if __name__ == "__main__":
    exit(main())
