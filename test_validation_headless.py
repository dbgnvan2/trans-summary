import logging
import os
import sys
import traceback
from pathlib import Path

from transcript_initial_validation import TranscriptValidator

# Ensure project root is in path
sys.path.append(os.getcwd())


# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("HeadlessTest")


def test_validation():
    # 1. Setup
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ SKIPPING TEST: ANTHROPIC_API_KEY not found in environment.")
        return

    test_file = Path("source/dummy_test_transcript.txt")
    if not test_file.exists():
        print(f"❌ SKIPPING TEST: Test file not found: {test_file}")
        return

    print(f"--- Starting Validation Test on {test_file} ---")

    try:
        # 2. Initialize Validator
        validator = TranscriptValidator(api_key, logger)

        # 3. Run Validation (Actual API Call)
        print("Sending request to Claude...")
        findings = validator.validate(test_file)

        print(f"\n✅ Validation Complete. Found {len(findings)} issues.")
        for finding in findings:
            print(
                f"   - [{finding.get('error_type')}] {finding.get('original_text')} -> {finding.get('suggested_correction')}")
            print(f"     Reason: {finding.get('reasoning')}")

        # 4. Test Applying Corrections
        if findings:
            print("\n--- Testing Correction Application ---")
            # Apply the first finding as a test
            first_finding = findings[0]
            corrections = [first_finding]

            # Create a temporary output file
            output_file = test_file.parent / \
                f"test_validated_{test_file.stem}.txt"

            new_path = validator.apply_corrections(
                test_file, corrections, output_path=output_file)

            print(f"✅ Applied correction to: {new_path}")
            print("Verifying content...")
            with open(new_path, 'r', encoding='utf-8') as file_obj:
                content = file_obj.read()

            if first_finding['suggested_correction'] in content:
                print(
                    f"✅ CONFIRMED: Found '{first_finding['suggested_correction']}' in output file.")
            else:
                print("❌ FAILED: Did not find correction in output file.")

            # Cleanup
            if output_file.exists():
                output_file.unlink()
                print("Test output file cleaned up.")

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"❌ TEST FAILED with error: {e}")
        traceback.print_exc()


def test_json_format_compliance():
    """
    Specifically tests that the LLM output is correctly parsed as JSON
    and adheres to the expected schema.
    """
    print("\n--- Starting JSON Format Compliance Test ---")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ SKIPPING TEST: ANTHROPIC_API_KEY not found.")
        return

    # Create a temporary file with obvious errors to ensure non-empty JSON
    temp_file = Path("temp_json_test_transcript.txt")
    with open(temp_file, "w", encoding='utf-8') as f:
        # "tezt" -> test, "erors" -> errors
        f.write(
            "This is a tezt transcript with some obvious erors to trigger JSON output.")

    try:
        validator = TranscriptValidator(api_key, logger)
        print(f"Validating temporary file: {temp_file}")

        # This calls the API
        findings = validator.validate(temp_file)

        # Check 1: Is it a list?
        if not isinstance(findings, list):
            print(f"❌ FAILED: Expected list, got {type(findings)}")
            return

        print("✅ Output is a valid Python list (JSON parsed successfully).")

        # Check 2: If we have items, do they match schema?
        if len(findings) > 0:
            print(f"✅ Found {len(findings)} items (Expected > 0).")
            item = findings[0]
            required_keys = {'error_type', 'original_text',
                             'suggested_correction', 'reasoning'}
            missing_keys = required_keys - item.keys()

            if not missing_keys:
                print("✅ Schema Check: All required keys present in first item.")
            else:
                print(f"❌ Schema Check Failed: Missing keys {missing_keys}")
        else:
            print(
                "⚠️ Warning: No errors found. JSON parsed, but cannot verify schema of elements.")

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"❌ Test Exception: {e}")
    finally:
        if temp_file.exists():
            temp_file.unlink()
            print("Cleanup: Temporary file removed.")


if __name__ == "__main__":
    # test_validation()
    test_json_format_compliance()
