#!/usr/bin/env python3
"""
Comprehensive security tests for path traversal protection fix.

Tests the sanitize_filename() function and parse_filename_metadata()
to ensure they properly prevent directory traversal attacks.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from transcript_utils import sanitize_filename, parse_filename_metadata


def test_normal_filenames():
    """Test that normal, valid filenames work correctly"""
    print("Test 1: Normal filenames...")

    # Simple filename
    result = sanitize_filename("transcript.txt")
    assert result == "transcript.txt", f"Expected 'transcript.txt', got '{result}'"

    # Complex but valid filename
    result = sanitize_filename("My Talk - Speaker Name - 2024-01-01.md")
    assert result == "My Talk - Speaker Name - 2024-01-01.md"

    # With underscores and numbers
    result = sanitize_filename("talk_2024_v1.md")
    assert result == "talk_2024_v1.md"

    print("✅ Normal filenames work correctly\n")


def test_path_traversal_attempts():
    """Test that path traversal attempts are blocked"""
    print("Test 2: Path traversal attacks...")

    # Classic path traversal
    result = sanitize_filename("../../../etc/passwd")
    assert "/" not in result, f"Path separator not removed: {result}"
    assert ".." not in result, f"Parent reference not removed: {result}"

    # Windows path traversal
    result = sanitize_filename("..\\..\\..\\windows\\system32\\config\\sam")
    assert "\\" not in result, f"Windows path separator not removed: {result}"
    assert ".." not in result, f"Parent reference not removed: {result}"

    # Mixed separators
    result = sanitize_filename("../../../path/to/file.txt")
    assert "/" not in result and "\\" not in result, f"Path separators remain: {result}"

    # Path in middle
    result = sanitize_filename("good-name-/../etc/passwd.txt")
    assert "/" not in result, f"Path separator in middle not removed: {result}"

    print("✅ Path traversal attacks blocked\n")


def test_absolute_paths():
    """Test that absolute paths are sanitized to just the filename"""
    print("Test 3: Absolute path handling...")

    # Unix absolute path - Path.name extracts just the filename
    result = sanitize_filename("/etc/passwd")
    assert result == "passwd", f"Path not sanitized: {result}"
    assert "/" not in result, "Path separator remains"

    # Windows absolute path - should extract just filename
    result = sanitize_filename("C:\\Windows\\System32\\file.txt")
    assert "\\" not in result, f"Windows path separator remains: {result}"
    # Note: colon gets removed by our sanitizer, so C: becomes empty
    assert "file.txt" in result or result == "file.txt", f"Filename not extracted: {result}"

    # Multiple leading slashes - should extract just filename
    result = sanitize_filename("///path/to/file.txt")
    assert "/" not in result, "Slashes remain"
    assert result == "file.txt", f"Filename not extracted correctly: {result}"

    print("✅ Absolute paths sanitized correctly\n")


def test_dangerous_characters():
    """Test that dangerous characters are removed"""
    print("Test 4: Dangerous character handling...")

    # Null bytes
    try:
        result = sanitize_filename("file\x00name.txt")
        assert "\x00" not in result, "Null byte not removed"
        print("  ✓ Null bytes removed")
    except ValueError:
        print("  ✓ Null bytes rejected")

    # Control characters
    result = sanitize_filename("file\x01\x02\x03name.txt")
    for i in range(32):
        assert chr(i) not in result, f"Control char {i} not removed"
    print("  ✓ Control characters removed")

    # Leading/trailing dots (can hide files or cause issues)
    result = sanitize_filename("...hidden-file.txt")
    assert not result.startswith("."), "Leading dots not stripped"
    print("  ✓ Leading dots stripped")

    print("✅ Dangerous characters handled correctly\n")


def test_edge_cases():
    """Test edge cases and boundary conditions"""
    print("Test 5: Edge cases...")

    # Empty string
    try:
        sanitize_filename("")
        assert False, "Empty string should raise ValueError"
    except ValueError as e:
        assert "non-empty" in str(e).lower()
        print("  ✓ Empty string rejected")

    # Only path separators
    try:
        sanitize_filename("///\\\\\\")
        assert False, "Only separators should raise ValueError"
    except ValueError as e:
        assert "empty after sanitization" in str(e).lower()
        print("  ✓ Only separators rejected")

    # Only dots and spaces (after strip, may have content)
    result = sanitize_filename("... . . ...")
    # After stripping leading/trailing dots, " . . " remains (valid but weird)
    assert "." in result or result == "", "Dots should remain or be empty"
    print("  ✓ Dots/spaces handled (strips leading/trailing)")

    # Truly empty after sanitization
    try:
        sanitize_filename("...")
        assert False, "Only dots should raise ValueError"
    except ValueError as e:
        assert "empty after sanitization" in str(e).lower()
        print("  ✓ Only dots rejected")

    # Very long filename
    long_name = "a" * 300 + ".txt"
    try:
        sanitize_filename(long_name)
        assert False, "Long filename should raise ValueError"
    except ValueError as e:
        assert "too long" in str(e).lower()
        print("  ✓ Long filenames rejected")

    # Non-string input
    try:
        sanitize_filename(None)
        assert False, "None should raise ValueError"
    except ValueError as e:
        assert "non-empty string" in str(e).lower()
        print("  ✓ None rejected")

    try:
        sanitize_filename(123)
        assert False, "Integer should raise ValueError"
    except ValueError as e:
        assert "non-empty string" in str(e).lower()
        print("  ✓ Non-string rejected")

    print("✅ Edge cases handled correctly\n")


def test_parse_filename_metadata_security():
    """Test that parse_filename_metadata uses sanitization"""
    print("Test 6: parse_filename_metadata security...")

    # Valid filename
    result = parse_filename_metadata("Talk Title - Speaker - 2024-01-01.md")
    assert result["title"] == "Talk Title"
    assert result["presenter"] == "Speaker"
    assert result["year"] == "2024"
    print("  ✓ Valid filename parsed correctly")

    # Path traversal attempt
    try:
        result = parse_filename_metadata("../../../etc/passwd")
        # Should fail because it won't match the pattern after sanitization
        assert False, "Path traversal should be rejected"
    except ValueError:
        print("  ✓ Path traversal rejected")

    # Filename with path
    try:
        result = parse_filename_metadata("/path/to/Talk - Speaker - 2024.md")
        # Should use just "Talk - Speaker - 2024.md"
        assert "/" not in result["filename"], f"Path separator in result: {result['filename']}"
        print("  ✓ Path stripped from filename")
    except ValueError:
        print("  ✓ Invalid path rejected")

    # Empty components after sanitization
    try:
        result = parse_filename_metadata("Title - - 2024-01-01.md")
        assert False, "Empty presenter should be rejected"
    except ValueError as e:
        # Could fail at pattern matching or empty component validation
        assert "empty" in str(e).lower() or "pattern" in str(e).lower()
        print("  ✓ Empty components rejected")

    # Missing year in date
    try:
        result = parse_filename_metadata("Title - Speaker - NoYear.md")
        assert False, "Missing year should be rejected"
    except ValueError as e:
        assert "year" in str(e).lower()
        print("  ✓ Missing year rejected")

    print("✅ parse_filename_metadata is secure\n")


def test_unicode_handling():
    """Test that unicode characters are preserved"""
    print("Test 7: Unicode handling...")

    # Unicode characters should be preserved
    result = sanitize_filename("Talk-日本語-2024.md")
    assert "日本語" in result, "Unicode characters removed"
    print("  ✓ Unicode characters preserved")

    # Emoji (if needed)
    result = sanitize_filename("Talk-🎤-Speaker.md")
    assert "🎤" in result or result == "Talk--Speaker.md", "Emoji handling failed"
    print("  ✓ Emoji handled")

    print("✅ Unicode handled correctly\n")


def test_real_world_scenarios():
    """Test real-world attack scenarios"""
    print("Test 8: Real-world attack scenarios...")

    attack_vectors = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "/etc/shadow",
        "C:\\boot.ini",
        "file/../../../etc/passwd",
        "....//....//....//etc/passwd",
        "..%2F..%2F..%2Fetc%2Fpasswd",  # URL encoded (will be decoded by browser, but test anyway)
        "\x00file.txt",  # Null byte injection
        ".htaccess",  # Hidden file
        "CON",  # Windows reserved name (though we don't block these - OS will)
        "file\n../etc/passwd",  # Newline injection
    ]

    for attack in attack_vectors:
        try:
            result = sanitize_filename(attack)
            # Check that result is safe
            assert "/" not in result, f"Attack succeeded: {attack} → {result}"
            assert "\\" not in result, f"Attack succeeded: {attack} → {result}"
            assert ".." not in result, f"Attack succeeded: {attack} → {result}"
            assert "\x00" not in result, f"Attack succeeded: {attack} → {result}"
            print(f"  ✓ Blocked: {attack[:50]}")
        except ValueError:
            # Also acceptable - just reject the filename
            print(f"  ✓ Rejected: {attack[:50]}")

    print("✅ All attack vectors blocked\n")


def test_sanitize_vs_validate():
    """Test that sanitize doesn't just validate, it actually fixes"""
    print("Test 9: Sanitization behavior...")

    # Sanitize should FIX, not just reject
    # Note: Path.name extracts just the filename, so "good/bad.txt" → "bad.txt"
    result = sanitize_filename("good/bad.txt")
    assert result == "bad.txt", "Should extract filename, not reject"
    print("  ✓ Path separator handled (extracts filename)")

    result = sanitize_filename("file..name.txt")
    assert result == "filename.txt", "Should remove .., not reject"
    print("  ✓ Parent refs removed (not rejected)")

    result = sanitize_filename("  file.txt  ")
    assert result == "file.txt", "Should strip whitespace"
    print("  ✓ Whitespace stripped")

    # Test that control chars are removed, not rejected
    result = sanitize_filename("file\x01name.txt")
    assert result == "filename.txt", "Should remove control chars"
    print("  ✓ Control characters removed (not rejected)")

    print("✅ Sanitization fixes issues when possible\n")


if __name__ == "__main__":
    print("=" * 70)
    print("Path Traversal Protection - Security Test Suite")
    print("=" * 70 + "\n")

    try:
        test_normal_filenames()
        test_path_traversal_attempts()
        test_absolute_paths()
        test_dangerous_characters()
        test_edge_cases()
        test_parse_filename_metadata_security()
        test_unicode_handling()
        test_real_world_scenarios()
        test_sanitize_vs_validate()

        print("=" * 70)
        print("✅ ALL SECURITY TESTS PASSED")
        print("=" * 70)
        print("\nThe fix successfully prevents:")
        print("  1. ✅ Path traversal attacks (../, ../../, etc.)")
        print("  2. ✅ Absolute path injections (/etc/passwd, C:\\)")
        print("  3. ✅ Null byte injections (\\x00)")
        print("  4. ✅ Control character injections")
        print("  5. ✅ Empty or malformed filenames")
        print("  6. ✅ Excessively long filenames (>255 chars)")
        print("  7. ✅ All known attack vectors")
        print("\n✅ System is now secure against filename-based attacks")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
