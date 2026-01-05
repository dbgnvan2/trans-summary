#!/usr/bin/env python3
"""
Test Runner Script
Executes all unit and integration tests in the project using pytest.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Run all tests.")
    parser.add_argument("--skip-integration", action="store_true",
                        help="Skip tests requiring API keys")
    args = parser.parse_args()

    # Define test files
    # Unit tests: Fast, no API calls
    unit_tests = [
        "test_formatting_helpers.py",
        "test_emphasis_detector.py",
        "test_regex.py",
        "test_timestamp_regex.py",
        "test_validation_model_passing.py",
        "test_summary_pipeline_parsing.py",
        "test_extraction_model_passing.py",
        "test_pipeline_integration.py",
        "test_bowen_cleaning.py"
    ]

    # Integration tests: Slower, require API calls
    integration_tests = [
        "test_anthropic_models.py",
        "test_validation_headless.py"
    ]

    current_dir = Path.cwd()

    # Filter for files that actually exist
    unit_tests = [t for t in unit_tests if (current_dir / t).exists()]
    integration_tests = [
        t for t in integration_tests if (current_dir / t).exists()]

    print(f"Found {len(unit_tests)} unit test files.")
    print(f"Found {len(integration_tests)} integration test files.")

    exit_code = 0

    # 1. Run Unit Tests
    if unit_tests:
        print("\n" + "="*40)
        print("RUNNING UNIT TESTS")
        print("="*40)
        cmd = [sys.executable, "-m", "pytest", "-v"] + unit_tests
        result = subprocess.run(cmd)
        if result.returncode != 0:
            exit_code = result.returncode

    # 2. Run Integration Tests
    if not args.skip_integration and integration_tests:
        print("\n" + "="*40)
        print("RUNNING INTEGRATION TESTS")
        print("="*40)

        if not os.getenv("ANTHROPIC_API_KEY"):
            print(
                "⚠️  ANTHROPIC_API_KEY not found. Integration tests may fail or be skipped.")

        cmd = [sys.executable, "-m", "pytest", "-v"] + integration_tests
        result = subprocess.run(cmd)
        if result.returncode != 0:
            if exit_code == 0:
                exit_code = result.returncode

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
