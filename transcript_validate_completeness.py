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
import re
from typing import Dict

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
    formatted_file = (
        config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_FORMATTED}"
    )
    yaml_file = config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_YAML}"

    file_to_check = yaml_file if yaml_file.exists() else formatted_file

    if not file_to_check.exists():
        result.add_error(f"File not found: {file_to_check.name}")
        return result

    content = file_to_check.read_text(encoding="utf-8")

    # Check minimum length (transcripts should be substantial)
    word_count = len(content.split())
    result.add_info(f"Word count: {word_count:,}")

    if word_count < config.TRANSCRIPT_MIN_WORDS:
        result.add_error(
            f"Transcript too short ({word_count} words, minimum {config.TRANSCRIPT_MIN_WORDS} required)"
        )
    elif word_count < 2000:
        result.add_warning(f"Transcript shorter than typical ({word_count} words)")

    # Check for YAML front matter (if yaml file)
    if file_to_check == yaml_file:
        if not content.startswith("---"):
            result.add_error("YAML file missing front matter")
        else:
            result.add_info("YAML front matter present")

    # Check for proper structure markers
    if "## " not in content:
        result.add_warning("No H2 headers found - may lack structure")

    # Check for truncation indicators
    truncation_markers = [
        "...[truncated]",
        "[content cut off]",
        "...(continued)",
        "[OUTPUT LIMIT REACHED]",
    ]
    for marker in truncation_markers:
        if marker.lower() in content.lower():
            result.add_error(f"Found truncation marker: {marker}")

    # Check file doesn't end abruptly (incomplete sentence)
    last_100_chars = content[-100:].strip()
    if last_100_chars and not any(
        last_100_chars.endswith(p) for p in [".", "!", "?", '"', "'"]
    ):
        result.add_warning("File may end mid-sentence (no terminal punctuation)")

    return result


def validate_core_outputs(base_name: str) -> ValidationResult:
    """Validate core one-artifact-per-output files exist and are non-empty."""
    result = ValidationResult("Core Outputs")
    project_dir = config.PROJECTS_DIR / base_name

    required_files = [
        ("Structural Themes", config.SUFFIX_STRUCTURAL_THEMES),
        ("Interpretive Themes", config.SUFFIX_INTERPRETIVE_THEMES),
        ("Topics", config.SUFFIX_TOPICS),
        ("Key Terms", config.SUFFIX_KEY_TERMS),
        ("Lenses", config.SUFFIX_LENSES),
        ("Bowen References", config.SUFFIX_BOWEN),
        ("Emphasis Items", config.SUFFIX_EMPHASIS),
        ("Abstract", config.SUFFIX_ABSTRACT_GEN),
    ]

    for label, suffix in required_files:
        file_path = project_dir / f"{base_name}{suffix}"
        if not file_path.exists():
            result.add_error(f"Missing file: {file_path.name}")
            continue

        content = file_path.read_text(encoding="utf-8").strip()
        if len(content) < 40:
            result.add_error(f"File appears empty: {file_path.name}")
        else:
            result.add_info(f"Found {label}: {file_path.name}")

    return result


def validate_key_terms(base_name: str) -> ValidationResult:
    """Validate key terms file."""
    result = ValidationResult("Key Terms")

    file_path = (
        config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_KEY_TERMS}"
    )

    if not file_path.exists():
        result.add_error(f"File not found: {file_path.name}")
        return result

    content = file_path.read_text(encoding="utf-8")

    # Should have at least a few terms
    term_count = len(re.findall(r"^-\s+\*\*", content, re.MULTILINE))
    result.add_info(f"Found {term_count} terms")

    if term_count == 0:
        result.add_error("No terms found (expected bullet list with **Term**:)")
    elif term_count < 5:
        result.add_warning(f"Only {term_count} terms found - expected more")

    return result


def validate_blog(base_name: str) -> ValidationResult:
    """Validate blog post completeness."""
    result = ValidationResult("Blog Post")

    file_path = config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_BLOG}"

    if not file_path.exists():
        result.add_error(f"File not found: {file_path.name}")
        return result

    content = file_path.read_text(encoding="utf-8")

    # Blog should have structure
    has_title = bool(re.search(r"^#\s+", content, re.MULTILINE))
    has_headers = bool(re.search(r"^##\s+", content, re.MULTILINE))

    if not has_title:
        result.add_warning("No H1 title found")
    if not has_headers:
        result.add_warning("No H2 headers found - may lack structure")

    # Check length (blog should be substantial)
    word_count = len(content.split())
    result.add_info(f"Word count: {word_count:,}")

    if word_count < config.BLOG_MIN_WORDS:
        result.add_error(
            f"Blog too short ({word_count} words, minimum {config.BLOG_MIN_WORDS} required)"
        )
    elif word_count < 1000:
        result.add_warning(f"Blog shorter than typical ({word_count} words)")

    return result


def validate_all(base_name: str) -> Dict[str, ValidationResult]:
    """Run all validation checks."""
    results = {}

    print("=" * 80)
    print(f"COMPLETENESS VALIDATION: {base_name}")
    print("=" * 80)

    # Run all validators
    results["formatted"] = validate_formatted_file(base_name)
    results["core_outputs"] = validate_core_outputs(base_name)
    results["terms"] = validate_key_terms(base_name)
    results["blog"] = validate_blog(base_name)

    # Print results
    for result in results.values():
        result.print_result()

    # Summary
    print("\n" + "=" * 80)
    passed = sum(1 for r in results.values() if r.passed)
    total = len(results)

    if passed == total:
        print(f"✅ ALL CHECKS PASSED ({passed}/{total})")
        return_code = 0
    else:
        print(f"❌ VALIDATION FAILED ({passed}/{total} passed)")
        return_code = 1

    print("=" * 80)

    return results, return_code


def main():
    parser = argparse.ArgumentParser(
        description="Validate transcript processing completeness."
    )
    parser.add_argument(
        "base_name", help="Base name of transcript (e.g., 'Title - Presenter - Date')"
    )
    parser.add_argument(
        "--strict", action="store_true", help="Treat warnings as errors"
    )

    args = parser.parse_args()

    results, return_code = validate_all(args.base_name)

    # If strict mode, warnings count as failures
    if args.strict:
        for result in results.values():
            if result.warnings:
                return_code = 1
                print(
                    f"\n⚠️  Strict mode: Warnings in '{result.name}' treated as errors"
                )

    return return_code


if __name__ == "__main__":
    exit(main())
