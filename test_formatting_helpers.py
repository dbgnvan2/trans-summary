import re
import unittest

# The function to test is in pipeline.py
from formatting_pipeline import strip_sic_annotations


class TestFormattingHelpers(unittest.TestCase):
    def _normalize_whitespace(self, text: str) -> str:
        """Helper to collapse whitespace for consistent comparison."""
        return re.sub(r"\s+", " ", text).strip()

    def test_strip_sic_with_correction(self):
        """Tests removal of [sic] with a parenthetical correction."""
        text = "Cobra [sic] (Tycho Brahe) moved to Prague."
        cleaned, count = strip_sic_annotations(text)
        self.assertEqual(self._normalize_whitespace(cleaned), "Cobra moved to Prague.")
        self.assertEqual(count, 1)

    def test_strip_sic_alone(self):
        """Tests removal of a standalone [sic]."""
        text = "Cobra [sic] moved."
        cleaned, count = strip_sic_annotations(text)
        self.assertEqual(self._normalize_whitespace(cleaned), "Cobra moved.")
        self.assertEqual(count, 1)

    def test_strip_sic_with_newlines_and_spaces(self):
        """Tests removal when surrounded by newlines and extra spaces."""
        text = "Cobra \n [sic] (Tycho Brahe) \n moved, to Prague."
        cleaned, count = strip_sic_annotations(text)
        self.assertEqual(self._normalize_whitespace(cleaned), "Cobra moved, to Prague.")
        self.assertEqual(count, 1)

    def test_multiple_sics(self):
        """Tests removal of multiple [sic] annotations in one string."""
        text = "One [sic] two [sic] (three) three."
        cleaned, count = strip_sic_annotations(text)
        self.assertEqual(self._normalize_whitespace(cleaned), "One two three.")
        self.assertEqual(count, 2)

    def test_no_sic_present(self):
        """Tests that text without [sic] is unchanged."""
        text = "This is a normal sentence."
        cleaned, count = strip_sic_annotations(text)
        self.assertEqual(
            self._normalize_whitespace(cleaned), "This is a normal sentence."
        )
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
