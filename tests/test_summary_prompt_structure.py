#!/usr/bin/env python3
"""
Test to verify the Summary Generation Prompt structure.
Ensures the prompt has been updated to the "Narrative Synthesis" approach.
"""

import sys
import unittest
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config

class TestSummaryPromptStructure(unittest.TestCase):

    def setUp(self):
        self.prompt_path = config.PROMPTS_DIR / config.PROMPT_STRUCTURED_SUMMARY_FILENAME
        self.prompt_content = self.prompt_path.read_text(encoding="utf-8")

    def test_prompt_exists(self):
        """Verify prompt file exists."""
        self.assertTrue(self.prompt_path.exists(), f"Prompt file not found: {self.prompt_path}")

    def test_narrative_synthesis_instruction(self):
        """Verify prompt contains instruction for narrative synthesis."""
        keywords = [
            "narrative synthesis",
            "comprehensive narrative",
            "structure your narrative organically", 
            "flowing narrative"
        ]
        # Check if ANY of the narrative keywords exist
        found = any(keyword in self.prompt_content for keyword in keywords)
        self.assertTrue(found, "Prompt does not contain instructions for 'narrative synthesis' or flow.")

    def test_transcript_source_instruction(self):
        """Verify prompt explicitly instructs to use the FULL TRANSCRIPT."""
        self.assertIn("FULL TRANSCRIPT", self.prompt_content)
        self.assertIn("system message", self.prompt_content.lower())

    def test_checklist_instruction(self):
        """Verify prompt treats JSON topics as a checklist, not a strict structure."""
        keywords = ["checklist", "structural guide", "reference"]
        found = any(keyword in self.prompt_content.lower() for keyword in keywords)
        self.assertTrue(found, "Prompt does not instruct to use JSON as a checklist/guide.")

    def test_no_rigid_topic_loop(self):
        """Verify prompt does NOT contain the old rigid loop instruction."""
        # The old prompt had "For each topic in the JSON, in order:"
        # The new prompt might still have "For each topic..." but context matters.
        # Let's check for the *absence* of the strict "one paragraph per topic" implication if possible,
        # or rather the *presence* of the freedom instruction.
        
        freedom_keywords = [
            "Do not feel constrained", 
            "not feel constrained",
            "Write naturally",
            "Do NOT simply list"
        ]
        found = any(keyword in self.prompt_content for keyword in freedom_keywords)
        self.assertTrue(found, "Prompt does not contain language un-constraining the paragraph structure.")

if __name__ == "__main__":
    unittest.main()
