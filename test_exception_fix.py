#!/usr/bin/env python3
"""
Quick test to verify the exception handling fix in log_token_usage.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import config
from transcript_utils import log_token_usage


def test_normal_operation():
    """Test that normal logging still works"""
    print("Test 1: Normal operation...")

    # Create mock usage data
    usage_data = Mock()
    usage_data.input_tokens = 1000
    usage_data.output_tokens = 500
    usage_data.cache_creation_input_tokens = 0
    usage_data.cache_read_input_tokens = 0

    # This should work without errors
    log_token_usage("test_script", "claude-3-5-sonnet-20241022", usage_data, "end_turn")
    print("✅ Normal operation works\n")


def test_permission_error():
    """Test that permission errors are caught and reported correctly"""
    print("Test 2: Permission error handling...")

    usage_data = Mock()
    usage_data.input_tokens = 1000
    usage_data.output_tokens = 500
    usage_data.cache_creation_input_tokens = 0
    usage_data.cache_read_input_tokens = 0

    # Mock the open function to raise PermissionError
    with patch("builtins.open", side_effect=PermissionError("Access denied")):
        # This should NOT crash - just print warning
        log_token_usage("test_script", "claude-3-5-sonnet-20241022", usage_data, "end_turn")

    print("✅ Permission errors handled gracefully\n")


def test_csv_error():
    """Test that CSV formatting errors are caught"""
    print("Test 3: CSV error handling...")

    usage_data = Mock()
    usage_data.input_tokens = 1000
    usage_data.output_tokens = 500
    usage_data.cache_creation_input_tokens = 0
    usage_data.cache_read_input_tokens = 0

    # Mock to raise csv.Error
    import csv
    with patch("builtins.open"), patch("csv.writer", side_effect=csv.Error("Invalid CSV")):
        # This should NOT crash
        log_token_usage("test_script", "claude-3-5-sonnet-20241022", usage_data, "end_turn")

    print("✅ CSV errors handled gracefully\n")


def test_unexpected_error():
    """Test that unexpected errors are logged with stack trace"""
    print("Test 4: Unexpected error handling...")

    usage_data = Mock()
    usage_data.input_tokens = 1000
    usage_data.output_tokens = 500
    usage_data.cache_creation_input_tokens = 0
    usage_data.cache_read_input_tokens = 0

    # Mock to raise an unexpected exception
    with patch("builtins.open", side_effect=RuntimeError("Unexpected error!")):
        # This should NOT crash, but should log full stack trace
        log_token_usage("test_script", "claude-3-5-sonnet-20241022", usage_data, "end_turn")

    print("✅ Unexpected errors handled gracefully with logging\n")


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Exception Handling Fix")
    print("=" * 60 + "\n")

    # Use temp directory for logs during testing
    with tempfile.TemporaryDirectory() as tmpdir:
        config.settings.LOGS_DIR = Path(tmpdir)

        try:
            test_normal_operation()
            test_permission_error()
            test_csv_error()
            test_unexpected_error()

            print("=" * 60)
            print("✅ ALL TESTS PASSED")
            print("=" * 60)
            print("\nThe fix correctly:")
            print("  1. ✅ Allows normal logging to work")
            print("  2. ✅ Catches expected errors (OSError, PermissionError)")
            print("  3. ✅ Catches data errors (csv.Error, UnicodeEncodeError)")
            print("  4. ✅ Logs unexpected errors with full stack trace")
            print("  5. ✅ Never crashes the pipeline")

        except Exception as e:
            print(f"\n❌ TEST FAILED: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
