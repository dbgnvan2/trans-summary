"""
Unit tests for validation logic, including fuzzy matching and procedural ignores.
"""

import re
import unittest

from formatting_pipeline import (
    _compare_transcripts,
    detect_transcript_source_format,
    strip_raw_speaker_prefixes,
    strip_transcript_metadata_header,
    strip_transcript_validation_footer,
)


class TestValidationLogic(unittest.TestCase):

    def test_detect_transcript_source_format_trx_wrapper(self):
        raw = """TRANSCRIPT
==========
Source file:  Example.mp4
Date:         2026-03-12
Duration:     01:28:00
Speakers:     6
Warnings:     Cloud transcription used chunked upload.
"""

        self.assertEqual(
            detect_transcript_source_format(raw),
            "trx_whisper_wrapped",
        )

    def test_detect_transcript_source_format_plain_transcript(self):
        raw = "[00:00:03] A: Okay.\n[00:00:05] A: Welcome.\n"
        self.assertEqual(detect_transcript_source_format(raw), "plain_transcript")

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

    def test_strip_transcript_metadata_header_removes_trx_preamble(self):
        raw = """TRANSCRIPT
==========
Source file:  Example.mp4
Date:         2026-03-12
Duration:     01:28:00
Speakers:     6
Warnings:     Cloud transcription used chunked upload.

--------------------------------------------------

[00:00:03] A: Okay.
[00:00:05] A: Welcome.
"""

        cleaned = strip_transcript_metadata_header(raw)

        self.assertTrue(cleaned.startswith("[00:00:03] A: Okay."))
        self.assertNotIn("Source file:", cleaned)
        self.assertNotIn("Warnings:", cleaned)

    def test_strip_raw_speaker_prefixes_removes_trx_labels(self):
        raw = """[00:00:03] A: Okay.
[00:00:55] B: Here it comes.
Speaker 3: This is another line.
Unknown Speaker: Final line.
"""

        cleaned = strip_raw_speaker_prefixes(raw)

        self.assertIn("Okay.", cleaned)
        self.assertIn("Here it comes.", cleaned)
        self.assertIn("This is another line.", cleaned)
        self.assertIn("Final line.", cleaned)
        self.assertNotIn("[00:00:03] A:", cleaned)
        self.assertNotIn("Speaker 3:", cleaned)
        self.assertNotIn("Unknown Speaker:", cleaned)

    def test_strip_transcript_validation_footer_removes_appended_report(self):
        raw = """[00:00:03] A: Okay.
[00:00:05] A: Welcome.

VALIDATION REPORT
-----------------
  - [00:00:05] foo -> bar (alias_mapping_exact)

FLAGGED ITEMS
-------------
  - None
"""

        cleaned = strip_transcript_validation_footer(raw)

        self.assertEqual(cleaned, "[00:00:03] A: Okay.\n[00:00:05] A: Welcome.\n")
        self.assertNotIn("VALIDATION REPORT", cleaned)
        self.assertNotIn("FLAGGED ITEMS", cleaned)

if __name__ == '__main__':
    unittest.main()
