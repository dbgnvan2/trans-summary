"""
Unit tests for validation logic, including fuzzy matching and procedural ignores.
"""

import re
import unittest

from formatting_pipeline import _compare_transcripts


class TestValidationLogic(unittest.TestCase):

    def test_fuzzy_matching_typos(self):
        """Test that minor typos are accepted as matches."""
        
        # 'livel' vs 'life' (First char matches, similarity > 0.65)
        # SequenceMatcher ratio for "livel" vs "life" is 0.66. Matches 'l', 'i', 'e'.
        
        raw = "livel"
        formatted = "life"
        skip_words = set()
        
        result = _compare_transcripts(
            raw, formatted, skip_words, max_lookahead=1, max_mismatch_ratio=1.0, max_mismatches=None
        )
        
        # Should be 0 mismatches if fuzzy logic works
        self.assertEqual(result['mismatch_count'], 0, "Fuzzy match failed for livel vs life")

    def test_fuzzy_matching_rejection(self):
        """Test that distinct words are NOT matched."""
        
        # 'cat' vs 'bat' (First char mismatch)
        raw = "cat"
        formatted = "bat"
        skip_words = set()
        
        result = _compare_transcripts(
            raw, formatted, skip_words, max_lookahead=1, max_mismatch_ratio=1.0, max_mismatches=None
        )
        
        self.assertEqual(result['mismatch_count'], 1, "Should have rejected cat vs bat")

    def test_procedural_ignore_regex(self):
        """Test the regex used to strip procedural speech."""
        
        # Replicating the logic from validate_format since it's inline there.
        # We test the regexes themselves here.
        
        raw_text = "Content. Next slide, please. More content. Thanks. Next, go to slide, please."
        
        procedural_patterns = [
            r"\bnext slide(?:,? please)?\.?",
            r"\bnext one(?:,? please)?\.?",
            r"\bslide please\.?",
            r"\bintro\b",  
            r"(?:^|[\.\!\?]\s+)so(?:,)?\s+",
            r"(?:^|[\.\!\?]\s+)okay(?:,)?\s+",
            r"(?:^|[\.\!\?]\s+)right(?:,)?\s+",
            r"\bjust to emphasize(?: this)?",
            r"\bone please",
            r"\bthere you see",
            r"\bthanks\.?",
            r"\bnext(?:,)?\s+",
            r"\bone(?:,)?\s+",
            r"\bslide(?:,)?\s+",
            r"\bplease\.?"
        ]
        
        cleaned = raw_text
        for p in procedural_patterns:
            cleaned = re.sub(p, " ", cleaned, flags=re.IGNORECASE | re.MULTILINE)
            
        self.assertNotIn("Next slide", cleaned)
        self.assertNotIn("Thanks", cleaned)
        self.assertNotIn("slide,", cleaned)
        self.assertIn("Content", cleaned)
        self.assertIn("More content", cleaned)

    def test_compare_transcripts_skip_logic(self):
        """Test that missing words are counted as mismatches."""
        
        raw = "one two three four"
        formatted = "one three four" # Deleted 'two'
        
        result = _compare_transcripts(
            raw, formatted, set(), max_lookahead=5, max_mismatch_ratio=1.0, max_mismatches=None
        )
        
        # Should find 1 mismatch (the deletion of 'two')
        self.assertEqual(result['mismatch_count'], 1)
        self.assertEqual(result['mismatches'][0]['a_word'], 'two')

if __name__ == '__main__':
    unittest.main()
