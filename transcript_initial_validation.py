"""
Transcript Initial Validation Script
Validates the initial transcript for transcription errors using LLM.
"""

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

from anthropic import Anthropic

import config
import transcript_utils


class TranscriptValidator:
    def __init__(self, api_key: str, logger: logging.Logger = None):
        self.api_key = api_key
        self.logger = logger or logging.getLogger(__name__)
        self.client = None
        self._setup_client()

    def _setup_client(self):
        self.client = Anthropic(api_key=self.api_key)

    def validate(self, transcript_path: Path, model: str = config.DEFAULT_MODEL) -> List[Dict[str, Any]]:
        """
        Run the validation prompt against the transcript.

        Args:
            transcript_path: Path to the transcript file.
            model: The LLM model to use.

        Returns:
            A list of error findings (dicts).
        """
        self.logger.info("Validating transcript: %s", transcript_path)
        self.logger.info("Using model: %s", model)

        if not transcript_path.exists():
            raise FileNotFoundError(f"Transcript not found: {transcript_path}")

        with open(transcript_path, 'r', encoding='utf-8') as file_obj:
            transcript_text = file_obj.read()

        prompt_path = Path("prompts/transcript_error_detection_prompt.md")
        if not prompt_path.exists():
            # Fallback if running from a different directory, try relative to project root
            prompt_path = config.PROMPTS_DIR / "transcript_error_detection_prompt.md"
            if not prompt_path.exists():
                raise FileNotFoundError(
                    f"Prompt file not found: {prompt_path}")

        with open(prompt_path, 'r', encoding='utf-8') as file_obj:
            prompt_content = file_obj.read()

        # Construct messages for optimal caching
        # The system message contains the large, reusable transcript text.
        # The user message contains the specific instructions for this call.
        system_message = transcript_utils.create_system_message_with_cache(
            f"You are an expert transcript editor. The user will provide instructions for validating the following transcript:\n\n<transcript>\n{transcript_text}\n</transcript>"
        )

        messages = [
            {
                "role": "user",
                "content": prompt_content
            }
        ]

        # Use a large context model or the configured one
        # The prompt asks for JSON output.
        try:
            response_msg = transcript_utils.call_claude_with_retry(
                self.client,
                model=model,
                messages=messages,
                max_tokens=4096,  # JSON can be large
                system=system_message,
                logger=self.logger
            )

            response_text = response_msg.content[0].text
            self.logger.info("Validation response received.")

            # Robust JSON Parsing
            try:
                # 1. Remove markdown fences
                json_str = re.sub(r'^```(?:json)?\s*|\s*```$',
                                  '', response_text.strip(), flags=re.MULTILINE)

                # 2. Find the start of the actual JSON data ([ or {)
                start_index = json_str.find('[')
                if start_index == -1:
                    start_index = json_str.find('{')

                # 3. Parse from that point
                if start_index != -1:
                    json_str = json_str[start_index:]
                    findings = json.loads(json_str)
                else:
                    self.logger.warning("No JSON block found in the response.")
                    findings = []
                self.logger.info("Parsed %d findings.", len(findings))
                return findings
            except json.JSONDecodeError as e:
                self.logger.error("Failed to parse JSON response: %s", e)
                self.logger.warning(
                    "Raw response content (first 500 chars): %s", response_text[:500])
                # return empty list or raise?
                # Let's try to recover valid objects if it's a malformed list?
                # For now, return empty and log error.
                return []

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("Error during validation: %s", e)
            raise

    def apply_corrections(self, transcript_path: Path, corrections: List[Dict[str, Any]], output_path: Path = None) -> Path:
        """
        Apply accepted corrections to the transcript.

        Args:
            transcript_path: Original transcript path.
            corrections: List of corrections to apply. Each must have 'original_text' and 'suggested_correction'.
                         (User approved/modified ones).
            output_path: Optional path to save the result. If None, appends '_validated'.

        Returns:
            Path to the saved file.
        """
        with open(transcript_path, 'r', encoding='utf-8') as file_obj:
            content = file_obj.read()

        # Sort corrections by length of original_text descending to avoid partial replacements issues?
        # Or just trust the `original_text` uniqueness.
        # The prompt asks for line numbers, but we are doing text replacement.
        # Using simple string replace might be dangerous if the phrase appears multiple times but only one is wrong.
        # However, the prompt outputs `original_text` context.
        # Let's try to be smart. If `original_text` is unique, replace it.
        # If not, warn or skip?
        # A safer way is to check if `context` is provided and helps, but that's complex.
        # For this implementation, we will use string replacement but check for multiplicity.

        applied_count = 0

        for item in corrections:
            original = item.get('original_text')
            replacement = item.get('suggested_correction')

            if not original or replacement is None:
                continue

            # Check occurrence count
            count = content.count(original)
            if count == 0:
                self.logger.warning(
                    "Could not find exact match for: '%s'", original)

                # Try fuzzy matching from transcript_utils
                start, end, ratio = transcript_utils.find_text_in_content(
                    original, content)
                if start is not None and ratio >= 0.85:
                    self.logger.info("Fuzzy match found (ratio %.2f). Applying correction.",
                                     ratio)
                    # Reconstruct content: before + replacement + after
                    content = content[:start] + replacement + content[end:]
                    applied_count += 1
                else:
                    self.logger.error("Skipping correction: '%s' not found in text.",
                                      original)

            elif count == 1:
                content = content.replace(original, replacement)
                applied_count += 1
            else:
                # For multiple occurrences, we need to be careful.
                # Without context/line numbers, replacing all is the default behavior but risky.
                # However, usually transcription errors like "their/there" are specific.
                # If the user provided context in the prompt, we could use it, but we don't have it here.
                self.logger.warning("Found %d occurrences of '%s'. Replacing ALL.",
                                    count, original)
                content = content.replace(original, replacement)
                applied_count += count  # Count all replacements

        if output_path is None:
            output_path = transcript_path.parent / \
                f"{transcript_path.stem}_validated{transcript_path.suffix}"

        with open(output_path, 'w', encoding='utf-8') as file_obj:
            file_obj.write(content)

        self.logger.info("Applied %d corrections. Saved to %s",
                         applied_count, output_path)
        return output_path

    def get_latest_version(self, file_path: Path) -> Path:
        """
        Finds the latest version of the transcript file (e.g., _v1, _v2).
        If no versioned files exist, returns the original file.
        """
        if not file_path.exists():
            return file_path

        stem = file_path.stem
        parent = file_path.parent
        suffix = file_path.suffix

        # Check if input is already versioned to find base stem
        match = re.search(r'^(.*)_v(\d+)$', stem)
        if match:
            base_stem = match.group(1)
        else:
            base_stem = stem

        # Find all matching files
        candidates = []
        # Add the base file if it exists (it might be the input file)
        base_file = parent / f"{base_stem}{suffix}"
        if base_file.exists():
            candidates.append((0, base_file))

        # Check for _validated (Treat as a version, but don't prioritize over explicit vN if vN is higher)
        # Actually, if we are iterating v1->v2, we usually want the highest vN.
        # We assign -1 to validated so it is only picked if no vN exists, or handle it separately?
        # Better: Don't auto-select validated if we are in a v-loop.
        # Let's just treat it as a candidate but without the 9999 priority override.
        validated = parent / f"{base_stem}_validated{suffix}"
        if validated.exists():
            # We don't know the version number of validated.
            # If the user wants to validate the 'validated' file, they should select it explicitly.
            # If we are auto-detecting, we prefer the highest numbered version draft.
            pass

        # Look for _vN files
        for candidate in parent.glob(f"{base_stem}_v*{suffix}"):
            # Extract version number
            c_stem = candidate.stem
            # Ensure it matches the pattern exactly (e.g. not "Title_v1_something_else")
            v_match = re.search(rf'^{re.escape(base_stem)}_v(\d+)$', c_stem)
            if v_match:
                v_num = int(v_match.group(1))
                candidates.append((v_num, candidate))

        if not candidates:
            return file_path

        # Sort by version number descending
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def run_iterative_validation(self, transcript_path: Path, iterations: int, model: str):
        """
        Runs the validation and correction process iteratively.
        This is intended for headless/CLI operation.
        """
        # Start with the latest version available
        current_file = self.get_latest_version(transcript_path)

        if not current_file.exists():
            self.logger.error("File not found: %s", current_file)
            return

        if current_file != transcript_path:
            self.logger.info("Using latest version: %s", current_file.name)

        self.logger.info("Starting validation loop for %d iterations...",
                         iterations)

        for i in range(1, iterations + 1):
            self.logger.info("\n🔄 Iteration %d: Validating %s...",
                             i, current_file.name)

            try:
                findings = self.validate(current_file, model=model)
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.logger.error("Validation failed: %s", e)
                return

            if not findings:
                self.logger.info("✅ No issues found. Validation complete.")
                break

            self.logger.info("⚠️  Found %d issues.", len(findings))

            # Determine output filename
            stem = current_file.stem
            match = re.search(r'_v(\d+)$', stem)
            if match:
                version = int(match.group(1)) + 1
                base_name = stem[:match.start()]
                new_filename = f"{base_name}_v{version}{current_file.suffix}"
            else:
                new_filename = f"{stem}_v1{current_file.suffix}"

            output_path = current_file.parent / new_filename

            self.logger.info("🛠️  Applying corrections -> %s", new_filename)
            self.apply_corrections(current_file, findings, output_path)

            current_file = output_path

        self.logger.info("\n✨ Done. Final file: %s", current_file)


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Iterative Transcript Validation")
    parser.add_argument("input_file", type=Path,
                        help="Path to the transcript file")
    parser.add_argument("--iterations", "-n", type=int,
                        default=1, help="Number of validation iterations")
    parser.add_argument(
        "--model", default=config.DEFAULT_MODEL, help="Claude model to use")

    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ Error: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    logging.basicConfig(level=logging.INFO, format='%(message)s')
    logger = logging.getLogger("TranscriptValidator")

    validator = TranscriptValidator(api_key, logger)
    validator.run_iterative_validation(
        args.input_file, args.iterations, args.model)


if __name__ == "__main__":
    main()
