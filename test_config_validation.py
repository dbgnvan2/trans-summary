"""
Test suite for configuration validation (Issue #4).
Tests all validation rules to ensure configuration errors are caught early.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Import config module
import config


def test_validation_result_class():
    """Test ValidationResult class functionality."""
    print("Testing ValidationResult class...")

    result = config.ValidationResult()
    assert result.is_valid(), "New ValidationResult should be valid"
    assert len(result.errors) == 0, "Should have no errors"
    assert len(result.warnings) == 0, "Should have no warnings"

    result.add_warning("Test warning")
    assert result.is_valid(), "Warnings don't affect validity"
    assert len(result.warnings) == 1, "Should have 1 warning"

    result.add_error("Test error")
    assert not result.is_valid(), "Errors make validation invalid"
    assert len(result.errors) == 1, "Should have 1 error"

    report = result.format_report()
    assert "Test error" in report, "Report should include errors"
    assert "Test warning" in report, "Report should include warnings"

    print("  ✓ ValidationResult class works correctly")
    return True


def test_current_configuration():
    """Test that the current configuration is valid."""
    print("\nTesting current configuration...")

    result = config.validate_configuration(verbose=False, auto_fix=False)

    if result.errors:
        print(f"  ✗ Found {len(result.errors)} error(s):")
        for error in result.errors:
            print(f"    - {error.split(chr(10))[0]}")  # First line only
        return False

    if result.warnings:
        print(f"  ⚠  Found {len(result.warnings)} warning(s):")
        for warning in result.warnings:
            print(f"    - {warning.split(chr(10))[0]}")  # First line only

    print(f"  ✓ Current configuration is valid")
    return True


def test_model_name_validation():
    """Test that invalid model names are caught."""
    print("\nTesting model name validation...")

    # Save original values
    original_model = config.settings.DEFAULT_MODEL

    try:
        # Test with invalid model
        config.settings.DEFAULT_MODEL = "invalid-model-12345"
        result = config.validate_configuration(verbose=False, auto_fix=False)

        if not result.errors:
            print("  ✗ Failed to detect invalid model name")
            return False

        error_found = any("DEFAULT_MODEL" in err and "invalid-model" in err for err in result.errors)
        if not error_found:
            print("  ✗ Error message doesn't mention DEFAULT_MODEL or invalid model")
            return False

        print("  ✓ Invalid model names are detected")
        return True

    finally:
        # Restore original
        config.settings.DEFAULT_MODEL = original_model


def test_temperature_validation():
    """Test that temperature values outside [0.0, 1.0] are caught."""
    print("\nTesting temperature validation...")

    # Save original
    original_temp = config.TEMP_STRICT

    try:
        # Test with invalid temperature (> 1.0)
        with patch.object(config, 'TEMP_STRICT', 1.5):
            result = config.validate_configuration(verbose=False, auto_fix=False)

            if not result.errors:
                print("  ✗ Failed to detect temperature > 1.0")
                return False

            error_found = any("TEMP_STRICT" in err for err in result.errors)
            if not error_found:
                print("  ✗ Error message doesn't mention TEMP_STRICT")
                return False

        # Test with invalid temperature (< 0.0)
        with patch.object(config, 'TEMP_STRICT', -0.1):
            result = config.validate_configuration(verbose=False, auto_fix=False)

            if not result.errors:
                print("  ✗ Failed to detect temperature < 0.0")
                return False

        print("  ✓ Temperature validation works correctly")
        return True

    finally:
        # Original is restored by context manager
        pass


def test_token_limit_validation():
    """Test that invalid token limits are caught."""
    print("\nTesting token limit validation...")

    # Test with token limit exceeding Claude's max (200K)
    with patch.object(config, 'MAX_TOKENS_FORMATTING', 300000):
        result = config.validate_configuration(verbose=False, auto_fix=False)

        if not result.warnings:
            print("  ✗ Failed to warn about token limit > 200K")
            return False

        warning_found = any("MAX_TOKENS_FORMATTING" in warn and "200" in warn for warn in result.warnings)
        if not warning_found:
            print("  ✗ Warning doesn't mention token limit or 200K")
            return False

    # Test with negative token limit
    with patch.object(config, 'MAX_TOKENS_SUMMARY', -100):
        result = config.validate_configuration(verbose=False, auto_fix=False)

        if not result.errors:
            print("  ✗ Failed to detect negative token limit")
            return False

    print("  ✓ Token limit validation works correctly")
    return True


def test_timeout_validation():
    """Test that timeout validation works."""
    print("\nTesting timeout validation...")

    # Test with very short timeout (should warn)
    with patch.object(config, 'TIMEOUT_FORMATTING', 5):
        result = config.validate_configuration(verbose=False, auto_fix=False)

        if not result.warnings:
            print("  ✗ Failed to warn about very short timeout")
            return False

    # Test with negative timeout (should error)
    with patch.object(config, 'TIMEOUT_DEFAULT', -10):
        result = config.validate_configuration(verbose=False, auto_fix=False)

        if not result.errors:
            print("  ✗ Failed to detect negative timeout")
            return False

    print("  ✓ Timeout validation works correctly")
    return True


def test_percentage_validation():
    """Test that percentage/ratio values are validated."""
    print("\nTesting percentage validation...")

    # Test with percentage > 1.0
    with patch.object(config, 'FUZZY_MATCH_THRESHOLD', 1.5):
        result = config.validate_configuration(verbose=False, auto_fix=False)

        if not result.errors:
            print("  ✗ Failed to detect percentage > 1.0")
            return False

    # Test with negative percentage
    with patch.object(config, 'ABSTRACT_TARGET_PERCENT', -0.1):
        result = config.validate_configuration(verbose=False, auto_fix=False)

        if not result.errors:
            print("  ✗ Failed to detect negative percentage")
            return False

    print("  ✓ Percentage validation works correctly")
    return True


def test_word_count_validation():
    """Test that word count validation works."""
    print("\nTesting word count validation...")

    # Test with negative word count
    with patch.object(config, 'DEFAULT_SUMMARY_WORD_COUNT', -100):
        result = config.validate_configuration(verbose=False, auto_fix=False)

        if not result.errors:
            print("  ✗ Failed to detect negative word count")
            return False

    # Test with zero word count
    with patch.object(config, 'MIN_EXTRACTS_WORDS_FLOOR', 0):
        result = config.validate_configuration(verbose=False, auto_fix=False)

        if not result.errors:
            print("  ✗ Failed to detect zero word count")
            return False

    print("  ✓ Word count validation works correctly")
    return True


def test_logical_consistency():
    """Test that logical consistency checks work."""
    print("\nTesting logical consistency validation...")

    # Test chunk overlap >= chunk size
    with patch.object(config, 'VALIDATION_CHUNK_OVERLAP', 2000), \
         patch.object(config, 'VALIDATION_CHUNK_SIZE', 1500):
        result = config.validate_configuration(verbose=False, auto_fix=False)

        if not result.errors:
            print("  ✗ Failed to detect chunk overlap >= chunk size")
            return False

        error_found = any("CHUNK_OVERLAP" in err and "CHUNK_SIZE" in err for err in result.errors)
        if not error_found:
            print("  ✗ Error doesn't mention chunk overlap/size relationship")
            return False

    # Test min >= max context words
    with patch.object(config, 'VALIDATION_MIN_CONTEXT_WORDS', 50), \
         patch.object(config, 'VALIDATION_MAX_CONTEXT_WORDS', 30):
        result = config.validate_configuration(verbose=False, auto_fix=False)

        if not result.errors:
            print("  ✗ Failed to detect min >= max context words")
            return False

    # Test fuzzy match threshold ordering
    with patch.object(config, 'VALIDATION_FUZZY_REJECT', 0.95), \
         patch.object(config, 'VALIDATION_FUZZY_REVIEW', 0.90), \
         patch.object(config, 'VALIDATION_FUZZY_AUTO_APPLY', 0.85):
        result = config.validate_configuration(verbose=False, auto_fix=False)

        if not result.errors:
            print("  ✗ Failed to detect incorrect fuzzy match threshold ordering")
            return False

    print("  ✓ Logical consistency validation works correctly")
    return True


def test_confidence_set_validation():
    """Test that confidence sets are validated."""
    print("\nTesting confidence set validation...")

    # Test with non-set type
    with patch.object(config, 'VALIDATION_AUTO_APPLY_CONFIDENCE', ['high']):
        result = config.validate_configuration(verbose=False, auto_fix=False)

        if not result.errors:
            print("  ✗ Failed to detect non-set confidence variable")
            return False

        error_found = any("AUTO_APPLY_CONFIDENCE" in err and "set" in err for err in result.errors)
        if not error_found:
            print("  ✗ Error doesn't mention confidence set type")
            return False

    print("  ✓ Confidence set validation works correctly")
    return True


def test_error_types_validation():
    """Test that error types set is validated."""
    print("\nTesting error types validation...")

    # Test with non-set type
    with patch.object(config, 'VALIDATION_ERROR_TYPES', ['homophone', 'grammar']):
        result = config.validate_configuration(verbose=False, auto_fix=False)

        if not result.errors:
            print("  ✗ Failed to detect non-set error types")
            return False

    # Test with empty set (should warn)
    with patch.object(config, 'VALIDATION_ERROR_TYPES', set()):
        result = config.validate_configuration(verbose=False, auto_fix=False)

        if not result.warnings:
            print("  ✗ Failed to warn about empty error types set")
            return False

    print("  ✓ Error types validation works correctly")
    return True


def test_directory_validation_with_temp():
    """Test directory validation with temporary directory."""
    print("\nTesting directory validation...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Save original
        original_base = config.settings.TRANSCRIPTS_BASE

        try:
            # Set to temp directory
            config.settings.set_transcripts_base(tmppath)

            # Run validation with auto_fix to create directories
            result = config.validate_configuration(verbose=False, auto_fix=True)

            # Check that directories were created
            assert (tmppath / "source").exists(), "SOURCE_DIR should be created"
            assert (tmppath / "processed").exists(), "PROCESSED_DIR should be created"
            assert (tmppath / "projects").exists(), "PROJECTS_DIR should be created"

            if result.errors:
                print(f"  ✗ Unexpected errors with auto_fix: {result.errors[0]}")
                return False

            print("  ✓ Directory validation and auto_fix work correctly")
            return True

        finally:
            # Restore original
            config.settings.set_transcripts_base(original_base)


def test_summary_allocation_warning():
    """Test that high summary structure allocations trigger warning."""
    print("\nTesting summary structure allocation warning...")

    # Test with allocations summing to > 50%
    with patch.object(config, 'SUMMARY_OPENING_PCT', 0.3), \
         patch.object(config, 'SUMMARY_CLOSING_PCT', 0.2), \
         patch.object(config, 'SUMMARY_QA_PCT', 0.15):
        result = config.validate_configuration(verbose=False, auto_fix=False)

        if not result.warnings:
            print("  ✗ Failed to warn about high summary allocations")
            return False

        warning_found = any("structure allocations" in warn.lower() for warn in result.warnings)
        if not warning_found:
            print("  ✗ Warning doesn't mention summary structure allocations")
            return False

    print("  ✓ Summary allocation warning works correctly")
    return True


def main():
    """Run all configuration validation tests."""
    print("=" * 70)
    print("CONFIGURATION VALIDATION TEST SUITE")
    print("=" * 70)

    tests = [
        ("ValidationResult Class", test_validation_result_class),
        ("Current Configuration", test_current_configuration),
        ("Model Name Validation", test_model_name_validation),
        ("Temperature Validation", test_temperature_validation),
        ("Token Limit Validation", test_token_limit_validation),
        ("Timeout Validation", test_timeout_validation),
        ("Percentage Validation", test_percentage_validation),
        ("Word Count Validation", test_word_count_validation),
        ("Logical Consistency", test_logical_consistency),
        ("Confidence Set Validation", test_confidence_set_validation),
        ("Error Types Validation", test_error_types_validation),
        ("Directory Validation", test_directory_validation_with_temp),
        ("Summary Allocation Warning", test_summary_allocation_warning),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"  ✗ Test crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Configuration validation is working correctly.")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed. Please review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
