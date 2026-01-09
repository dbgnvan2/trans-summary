import unittest
from unittest.mock import MagicMock, patch
import logging
from pathlib import Path
import json
import os
import sys
import tempfile

# Ensure project root is in path
sys.path.append(os.getcwd())

from transcript_initial_validation import TranscriptValidator

class TestInitialValidationLogic(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger("TestLogger")
        # Mock API key so we don't need a real one for initialization
        self.validator = TranscriptValidator(api_key="dummy_key", logger=self.logger)

    @patch("transcript_utils.call_claude_with_retry")
    @patch("builtins.open")
    @patch("pathlib.Path.exists")
    def test_validate_parsing_with_extra_data(self, mock_exists, mock_open, mock_call_claude):
        """Test that the validator correctly extracts JSON when extra text follows it."""
        mock_exists.return_value = True
        
        # Mock file reading for transcript and prompt
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file
        mock_file.read.return_value = "Transcript content"

        # Mock API Response with extra data (simulating the error we fixed)
        dirty_json = """
        Here is the analysis:
        [
            {
                "error_type": "spelling",
                "original_text": "foo",
                "suggested_correction": "bar"
            }
        ]
        And here is some extra commentary that used to break the parser.
        """
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=dirty_json)]
        mock_call_claude.return_value = mock_message

        findings = self.validator.validate(Path("dummy.txt"))
        
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]['original_text'], "foo")
        self.assertEqual(findings[0]['suggested_correction'], "bar")

    def test_apply_corrections_safety_short_phrase(self):
        """Test that short repeated phrases are NOT replaced (Safety Check)."""
        content = "The cat sat on the mat. The dog ran."
        # "The" appears twice. It is short (< 20 chars).
        corrections = [{
            "original_text": "The",
            "suggested_correction": "A"
        }]

        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, encoding='utf-8') as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
            
        try:
            # We expect NO change because "The" is short and appears multiple times
            output_path = self.validator.apply_corrections(tmp_path, corrections)
            
            with open(output_path, 'r', encoding='utf-8') as f:
                new_content = f.read()
            
            # Should match original exactly (Skipped)
            self.assertEqual(new_content, content)
            
        finally:
            if tmp_path.exists():
                os.unlink(tmp_path)
            if output_path.exists():
                os.unlink(output_path)

    def test_apply_corrections_long_phrase_repeated(self):
        """Test that LONG repeated phrases ARE replaced even if multiple occurrences exist."""
        long_phrase = "This is a very long unique phrase that appears twice in the text."
        content = f"{long_phrase} Start. {long_phrase} End."
        correction_text = "Corrected Phrase"
        
        corrections = [{
            "original_text": long_phrase,
            "suggested_correction": correction_text
        }]
        
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, encoding='utf-8') as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
            
        try:
            output_path = self.validator.apply_corrections(tmp_path, corrections)
            
            with open(output_path, 'r', encoding='utf-8') as f:
                new_content = f.read()
            
            # Both instances should be replaced because it's long/specific enough
            expected = f"{correction_text} Start. {correction_text} End."
            self.assertEqual(new_content, expected)
            
        finally:
            if tmp_path.exists():
                os.unlink(tmp_path)
            if output_path.exists():
                os.unlink(output_path)
                
    def test_apply_corrections_unique_short_phrase(self):
        """Test that SHORT phrases ARE replaced if they are UNIQUE (count == 1)."""
        content = "The cat sat on the mat."
        # "cat" appears once.
        corrections = [{
            "original_text": "cat",
            "suggested_correction": "dog"
        }]

        with tempfile.NamedTemporaryFile(mode='w+', delete=False, encoding='utf-8') as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
            
        try:
            output_path = self.validator.apply_corrections(tmp_path, corrections)
            
            with open(output_path, 'r', encoding='utf-8') as f:
                new_content = f.read()
            
            # Should be replaced
            expected = "The dog sat on the mat."
            self.assertEqual(new_content, expected)
            
        finally:
            if tmp_path.exists():
                os.unlink(tmp_path)
            if output_path.exists():
                os.unlink(output_path)

if __name__ == '__main__':
    unittest.main()
