import unittest
from unittest.mock import MagicMock, patch
import json
from pathlib import Path
import tempfile
import shutil
import os
import sys

# Ensure project root is in path
sys.path.append(os.getcwd())

import config
from transcript_initial_validation_v2 import TranscriptValidatorV2

class TestTranscriptValidatorV2(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.api_key = "dummy_key"
        self.logger = MagicMock()
        self.validator = TranscriptValidatorV2(self.api_key, self.logger)
        self.validator.client = MagicMock()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_deduplicate_findings(self):
        """Test that duplicate findings (same original/correction) are removed."""
        findings = [
            {'original_text': 'error one', 'suggested_correction': 'fix one', 'chunk_id': 0},
            {'original_text': 'error one', 'suggested_correction': 'fix one', 'chunk_id': 1}, # Duplicate
            {'original_text': 'error two', 'suggested_correction': 'fix two', 'chunk_id': 1}
        ]
        
        unique = self.validator._deduplicate_findings(findings)
        self.assertEqual(len(unique), 2)
        self.assertEqual(unique[0]['original_text'], 'error one')
        self.assertEqual(unique[1]['original_text'], 'error two')

    def test_validate_correction_logic(self):
        """Test semantic validation of corrections."""
        # Valid
        valid = {
            'error_type': 'spelling',
            'original_text': 'word ' * 6, # 6 words (min is 5)
            'suggested_correction': 'word ' * 6 + 'fix',
            'confidence': 'high'
        }
        is_valid, msg = self.validator.validate_correction(valid)
        self.assertTrue(is_valid, msg)

        # Invalid: Too short
        short = valid.copy()
        short['original_text'] = 'too short'
        is_valid, msg = self.validator.validate_correction(short)
        self.assertFalse(is_valid)
        self.assertIn("Context length", msg)

        # Invalid: Identical
        identical = valid.copy()
        identical['suggested_correction'] = identical['original_text']
        is_valid, msg = self.validator.validate_correction(identical)
        self.assertFalse(is_valid)
        self.assertIn("identical", msg)

    def test_apply_corrections_safe_overlap(self):
        """Test that overlapping replacements are handled safely."""
        transcript_path = Path(self.test_dir) / "test.txt"
        content = "The quick brown fox jumps over the lazy dog."
        with open(transcript_path, 'w') as f:
            f.write(content)

        corrections = [
            # Matches "quick brown"
            {'original_text': 'quick brown', 'suggested_correction': 'FAST', 'confidence': 'high'},
            # Matches "brown fox" - OVERLAPS!
            {'original_text': 'brown fox', 'suggested_correction': 'ANIMAL', 'confidence': 'high'}
        ]

        # V2 sorts by start pos descending and skips overlaps.
        # "brown fox" (index ~10) comes AFTER "quick brown" (index ~4)
        # So "brown fox" is processed FIRST (reverse sort), applied.
        # Then "quick brown" is processed. Its end overlaps "brown fox" start?
        # Let's trace:
        # "quick brown": 4-15
        # "brown fox": 10-19
        # Reverse Sort order: (10, 19) then (4, 15)
        # 1. Apply (10, 19) -> "ANIMAL". last_start = 10.
        # 2. Check (4, 15). End (15) > last_start (10). OVERLAP! Should skip.
        
        # NOTE: My implementation sorts reverse. 
        # replacements.sort(key=lambda x: x[0], reverse=True)
        # So (10, 19) is first.
        # Loop:
        # 1. (10, 19): Valid. last_start = 10.
        # 2. (4, 15): End 15 > 10. Skip.
        
        out_path, count, skipped = self.validator.apply_corrections_safe(transcript_path, corrections)
        
        with open(out_path, 'r') as f:
            result = f.read()
            
        # Should contain ANIMAL but not FAST (or vice versa depending on sort stability, but one must skip)
        self.assertEqual(count, 1)
        self.assertEqual(len(skipped), 1)
        self.assertIn("The quick ANIMAL jumps", result) # brown fox -> ANIMAL
        
    def test_hallucination_detection(self):
        full_text = "This is the actual text."
        findings = [
            {'original_text': 'actual text', 'suggested_correction': 'real text'}, # Exists
            {'original_text': 'imaginary text', 'suggested_correction': 'foo'}    # Does not exist
        ]
        
        valid, hallucinations = self.validator.detect_hallucinations(findings, full_text)
        
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0]['original_text'], 'actual text')
        self.assertEqual(len(hallucinations), 1)
        self.assertEqual(hallucinations[0]['original_text'], 'imaginary text')

if __name__ == '__main__':
    unittest.main()
