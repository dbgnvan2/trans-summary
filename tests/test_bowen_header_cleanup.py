import unittest
import re

class TestBowenHeaderCleanup(unittest.TestCase):

    def test_cleanup_regex(self):
        """Test that the regex removes various header forms."""
        regex = r'^#+\s*.*(?:Bowen|Reference).*$'
        
        examples = [
            "# Bowen References Extracted from Transcript",
            "## Bowen References",
            "# BOWEN REFERENCE EXTRACTION",
            "### References to Bowen",
            "# Extracted Bowen Quotes"
        ]
        
        for ex in examples:
            result = re.sub(regex, '', ex, flags=re.MULTILINE | re.IGNORECASE).strip()
            self.assertEqual(result, "", f"Failed to strip: {ex}")

    def test_cleanup_preserves_content(self):
        """Test that content is preserved."""
        text = """# Bowen References Extracted from Transcript

> **Concept**: "Quote"
"""
        regex = r'^#+\s*.*(?:Bowen|Reference).*$'
        result = re.sub(regex, '', text, flags=re.MULTILINE | re.IGNORECASE).strip()
        self.assertIn('> **Concept**: "Quote"', result)
        self.assertNotIn("# Bowen", result)

if __name__ == '__main__':
    unittest.main()
