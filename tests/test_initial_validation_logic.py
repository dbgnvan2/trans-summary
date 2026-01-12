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
# Import V2 explicitly
from transcript_initial_validation_v2 import TranscriptValidatorV2

class TestTranscriptValidatorLogicV2(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.api_key = "dummy_key"
        self.logger = MagicMock()
        self.validator = TranscriptValidatorV2(self.api_key, self.logger)
        self.validator.client = MagicMock()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_deduplicate_findings_exact(self):
        """Test that exact duplicates (same original & correction) are removed."""
        findings = [
            {'original_text': 'typo', 'suggested_correction': 'fixed', 'chunk_id': 0},
            {'original_text': 'typo', 'suggested_correction': 'fixed', 'chunk_id': 1}, # Duplicate from overlap
            {'original_text': 'other', 'suggested_correction': 'fixed', 'chunk_id': 1}
        ]
        
        unique = self.validator._deduplicate_findings(findings)
        self.assertEqual(len(unique), 2)
        texts = [f['original_text'] for f in unique]
        self.assertIn('typo', texts)
        self.assertIn('other', texts)

    def test_deduplicate_findings_different_correction(self):
        """Test that same original text but DIFFERENT correction is NOT deduplicated (ambiguous)."""
        findings = [
            {'original_text': 'typo', 'suggested_correction': 'fix1', 'chunk_id': 0},
            {'original_text': 'typo', 'suggested_correction': 'fix2', 'chunk_id': 1}
        ]
        
        unique = self.validator._deduplicate_findings(findings)
        # Should keep both because they are conflicting instructions
        self.assertEqual(len(unique), 2)

    def test_validate_correction_valid(self):
        """Test a perfectly valid correction."""
        valid = {
            'error_type': 'spelling',
            'original_text': 'this is a long enough context',
            'suggested_correction': 'this is a long enough fixed',
            'confidence': 'high'
        }
        is_valid, msg = self.validator.validate_correction(valid)
        self.assertTrue(is_valid, f"Should be valid: {msg}")

    def test_validate_correction_invalid_context(self):
        """Test rejection of short context."""
        invalid = {
            'error_type': 'spelling',
            'original_text': 'too short', # 2 words
            'suggested_correction': 'too fixed',
            'confidence': 'high'
        }
        is_valid, msg = self.validator.validate_correction(invalid)
        self.assertFalse(is_valid)
        self.assertIn("Context length", msg)

    def test_validate_correction_identical(self):
        """Test rejection of identical original/correction."""
        invalid = {
            'error_type': 'spelling',
            'original_text': 'same same same same same',
            'suggested_correction': 'same same same same same',
            'confidence': 'high'
        }
        is_valid, msg = self.validator.validate_correction(invalid)
        self.assertFalse(is_valid)
        self.assertIn("identical", msg)

    def test_apply_corrections_safe_basic(self):
        """Test basic replacement."""
        content = "Start. The wrong word here. End."
        path = Path(self.test_dir) / "test_basic.txt"
        path.write_text(content)

        corrections = [{
            'original_text': 'The wrong word here',
            'suggested_correction': 'The right word here',
            'confidence': 'high'
        }]

        out_path, count, skipped = self.validator.apply_corrections_safe(path, corrections)
        result = out_path.read_text()

        self.assertEqual(count, 1)
        self.assertEqual(result, "Start. The right word here. End.")
        self.assertEqual(len(skipped), 0)

    def test_apply_corrections_safe_overlap_handling(self):
        """Test that overlapping matches are handled (one wins, one skipped)."""
        content = "A B C D E"
        path = Path(self.test_dir) / "test_overlap.txt"
        path.write_text(content)

        corrections = [
            # "B C" -> "X" (indices 2-5)
            {'original_text': 'A B C', 'suggested_correction': 'X', 'confidence': 'high'},
            # "C D" -> "Y" (indices 4-7) - Overlaps "C"
            {'original_text': 'C D E', 'suggested_correction': 'Y', 'confidence': 'high'}
        ]
        
        # In V2, we sort by position descending (reverse).
        # "C D E" is at end, processed first.
        # "A B C" is at start.
        # IF they overlap, the second one processed (lower index) usually gets applied 
        # BUT we must check overlap with *already applied* segments.
        # 
        # Implementation Detail: 
        # replacements.sort(key=lambda x: x[0], reverse=True)
        # 1. (4, 9, 'Y') -> Applied. Last start = 4.
        # 2. (0, 5, 'X') -> End is 5. 5 > 4? YES. Overlap detected.
        
        out_path, count, skipped = self.validator.apply_corrections_safe(path, corrections)
        result = out_path.read_text()
        
        self.assertEqual(count, 1)
        self.assertEqual(len(skipped), 1)
        # Expected: "A B Y" (since C D E was applied first/last depending on sort)
        # Actually, let's see which one wins.
        # Reverse sort: higher index (C D E) is first in list.
        # Loop applies first in list, updates last_start.
        # Next item (A B C) overlaps last_start. Skipped.
        self.assertEqual(result, "A B Y") 

    def test_hallucination_detection(self):
        """Test that text not found in content is flagged."""
        content = "Real text exists."
        findings = [
            {'original_text': 'Real text exists', 'suggested_correction': 'Fixed'},
            {'original_text': 'Fake text exists', 'suggested_correction': 'Fixed'}
        ]
        
        valid, hall = self.validator.detect_hallucinations(findings, content)
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0]['original_text'], 'Real text exists')
        self.assertEqual(len(hall), 1)
        self.assertEqual(hall[0]['original_text'], 'Fake text exists')

    def test_fuzzy_auto_apply(self):
        """Test that slight mismatches (fuzzy) are found and applied."""
        content = "The quick brown fox jumps over the lazy dog."
        path = Path(self.test_dir) / "test_fuzzy.txt"
        path.write_text(content)

        corrections = [{
            'original_text': 'The quick brown fox jumps over the lazy dog', # Missing period
            'suggested_correction': 'The quick brown fox jumps over the lazy cat.',
            'confidence': 'high'
        }]
        
        # Ratio should be high enough (>0.95)
        
        out_path, count, skipped = self.validator.apply_corrections_safe(path, corrections)
        result = out_path.read_text()
        
        self.assertEqual(count, 1)
        self.assertEqual(result, "The quick brown fox jumps over the lazy cat..")

if __name__ == '__main__':
    unittest.main()
