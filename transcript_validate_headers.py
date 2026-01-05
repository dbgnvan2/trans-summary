import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, List

import anthropic

import config

# Add project root to path to allow imports
sys.path.append(str(Path(__file__).parent))

try:
    from transcript_utils import (
        call_claude_with_retry,
        create_system_message_with_cache,
        setup_logging,
        validate_api_key,
        validate_input_file,
    )
except ImportError:
    print(
        "Error: transcript_utils.py not found. Please ensure you are in the project directory."
    )
    sys.exit(1)

# Configuration
BATCH_SIZE = 5


class HeaderValidator:
    def __init__(self, api_key: str, logger):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.logger = logger

        # Resolve paths dynamically from config to respect GUI selection
        self.terms_file = (
            config.PROMPTS_DIR / config.PROMPT_PROBLEMATIC_HEADER_TERMS_FILENAME
        )
        self.prompt_file = (
            config.PROMPTS_DIR / config.PROMPT_FORMATTING_HEADER_VALIDATION_FILENAME
        )

        self.problematic_terms = self._load_problematic_terms()
        self.validation_prompt = self._load_prompt()

        # Prepare cached system message from template
        static_instructions = self.validation_prompt.replace(
            "{batch_content}", ""
        ).strip()
        self.cached_system_message = create_system_message_with_cache(
            static_instructions
        )

    def _load_problematic_terms(self) -> List[str]:
        """Load problematic terms from markdown file."""
        if not self.terms_file.exists():
            self.logger.warning(
                f"Problematic terms file not found at {self.terms_file}. Creating default."
            )
            self._create_default_terms_file()

        try:
            content = self.terms_file.read_text(encoding="utf-8")
            # Extract lines that aren't comments or empty
            terms = [
                line.strip().lower()
                for line in content.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            self.logger.info(f"Loaded {len(terms)} problematic terms.")
            return terms
        except Exception as e:
            self.logger.error(f"Failed to load problematic terms: {e}")
            return []

    def _create_default_terms_file(self):
        """Create default terms file if missing."""
        config.PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
        default_content = (
            "# Problematic Header Terms\n"
            "# These terms often indicate analytical overlays rather than the speaker's voice.\n"
            "# One term per line. Case-insensitive matching.\n\n"
            "groupiness\n"
            "dynamics\n"
            "process\n"
            "system\n"
        )
        self.terms_file.write_text(default_content, encoding="utf-8")

    def _load_prompt(self) -> str:
        """Load validation prompt template."""
        if not self.prompt_file.exists():
            raise FileNotFoundError(
                f"Validation prompt not found at {self.prompt_file}"
            )
        content = self.prompt_file.read_text(encoding="utf-8")
        if "{batch_content}" not in content:
            self.logger.warning(
                f"⚠️ Prompt template '{self.prompt_file.name}' is missing '{{batch_content}}' placeholder. Validation will likely fail."
            )
        return content

    def parse_transcript(self, file_path: Path) -> List[Dict]:
        """Parse transcript into sections based on H2 headers (##)."""
        content = file_path.read_text(encoding="utf-8")

        # Split by H2 headers
        # Regex looks for ## followed by text, capturing the header and the following content
        # It handles the start of the file and subsequent sections
        sections = []

        # Find all H2 headers and their positions
        matches = list(re.finditer(r"^##\s+(.+)$", content, re.MULTILINE))

        for i, match in enumerate(matches):
            heading = match.group(1).strip()
            start = match.end()

            # End is either start of next match or end of file
            if i + 1 < len(matches):
                end = matches[i + 1].start()
            else:
                end = len(content)

            section_content = content[start:end].strip()

            # Clean up markdown bolding in heading if present
            heading_clean = heading.replace("**", "").replace("__", "").strip()

            sections.append(
                {
                    "number": i + 1,
                    "heading": heading_clean,
                    "content": section_content,
                    "original_heading": heading,
                }
            )

        self.logger.info(f"Parsed {len(sections)} sections from transcript.")
        return sections

    def check_problematic_terms(self, heading: str) -> List[str]:
        """Check if heading contains any problematic terms."""
        found = []
        heading_lower = heading.lower()
        for term in self.problematic_terms:
            # Simple substring match, could be improved with regex for word boundaries
            if term in heading_lower:
                found.append(term)
        return found

    def validate_batch(self, batch: List[Dict], model: str = config.AUX_MODEL) -> str:
        """Send a batch of sections to Claude for validation."""

        # Construct batch content string
        batch_content = ""
        for section in batch:
            display_content = section["content"]

            batch_content += f"\nSECTION {section['number']}:\n"
            batch_content += f"Heading: {section['heading']}\n"
            batch_content += f"Content: {display_content}\n"
            batch_content += "-" * 40 + "\n"

        # Log size info
        template_len = len(self.cached_system_message[0]["text"])
        self.logger.info(
            f"Prompt size: Template (Cached)={template_len} chars, Content={len(batch_content)} chars"
        )

        self.logger.info(
            f"Sending request to Claude (max_tokens={config.MAX_TOKENS_HEADER_VALIDATION})..."
        )

        # Call API
        response = call_claude_with_retry(
            self.client,
            model=model,
            messages=[{"role": "user", "content": batch_content}],
            max_tokens=config.MAX_TOKENS_HEADER_VALIDATION,
            logger=self.logger,
            stream=True,
            system=self.cached_system_message,
        )

        return response.content[0].text

    def run(self, input_path: Path, model: str = config.AUX_MODEL):
        """Main execution flow."""
        sections = self.parse_transcript(input_path)
        if not sections:
            self.logger.error(
                "No sections found in transcript (expected '## Heading' format)."
            )
            return

        results = []

        # Process in batches
        total_batches = (len(sections) + BATCH_SIZE - 1) // BATCH_SIZE

        self.logger.info(
            f"Starting validation of {len(sections)} sections in {total_batches} batches..."
        )

        for i in range(0, len(sections), BATCH_SIZE):
            batch = sections[i: i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1

            self.logger.info(
                f"Processing Batch {batch_num}/{total_batches} (Sections {batch[0]['number']}-{batch[-1]['number']})"
            )

            # 1. Local Check for Problematic Terms
            for section in batch:
                bad_terms = self.check_problematic_terms(section["heading"])
                if bad_terms:
                    self.logger.warning(
                        f"Section {section['number']} heading contains problematic terms: {bad_terms}"
                    )
                    section["local_flag"] = bad_terms

            # 2. AI Validation
            try:
                ai_response = self.validate_batch(batch, model=model)
                results.append(
                    {"batch": batch_num, "sections": batch, "response": ai_response}
                )
            except Exception as e:
                self.logger.error(f"Failed to validate batch {batch_num}: {e}")

        self._save_report(input_path, results)
        return True

    def _save_report(self, input_path: Path, results: List[Dict]):
        """Save validation report to file."""
        base_name = input_path.stem.replace(
            " - formatted", "").replace(" - yaml", "")
        project_dir = config.PROJECTS_DIR / base_name
        project_dir.mkdir(parents=True, exist_ok=True)
        report_path = project_dir / \
            f"{base_name}{config.SUFFIX_HEADER_VAL_REPORT}"

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# Header Validation Report\n")
            f.write(f"Source: {input_path.name}\n")
            f.write(f"Date: {os.path.getmtime(input_path)}\n\n")

            f.write("## Problematic Term Flags (Local Check)\n")
            has_flags = False
            for batch_result in results:
                for section in batch_result["sections"]:
                    if section.get("local_flag"):
                        has_flags = True
                        f.write(
                            f"- **Section {section['number']}**: '{section['heading']}' contains {section['local_flag']}\n"
                        )

            if not has_flags:
                f.write("None found.\n")

            f.write("\n## AI Validation Details\n")
            for batch_result in results:
                f.write(f"\n### Batch {batch_result['batch']}\n")
                f.write(batch_result["response"])
                f.write("\n" + "=" * 50 + "\n")

        self.logger.info(
            f"Validation complete. Report saved to: {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Validate transcript headers in batches."
    )
    parser.add_argument(
        "input_file", help="Path to formatted transcript file (.md)")
    args = parser.parse_args()

    # Setup
    logger = setup_logging("header_validation")

    try:
        api_key = validate_api_key()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    input_path = Path(args.input_file)
    try:
        validate_input_file(input_path)
    except Exception as e:
        logger.error(str(e))
        sys.exit(1)

    # Run Validator
    validator = HeaderValidator(api_key, logger)
    validator.run(input_path)


if __name__ == "__main__":
    main()
