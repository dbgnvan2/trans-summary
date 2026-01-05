from extraction_pipeline import _clean_bowen_output
import unittest
import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())


class TestBowenCleaning(unittest.TestCase):
    def test_clean_standard(self):
        input_text = '**Concept**: "Quote"'
        expected = '> **Concept**: "Quote"'
        self.assertEqual(_clean_bowen_output(input_text), expected)

    def test_clean_numbered_list(self):
        input_text = '1. **Concept**: "Quote"'
        expected = '> **Concept**: "Quote"'
        self.assertEqual(_clean_bowen_output(input_text), expected)

    def test_clean_bullet_list(self):
        input_text = '- **Concept**: "Quote"'
        expected = '> **Concept**: "Quote"'
        self.assertEqual(_clean_bowen_output(input_text), expected)

    def test_clean_mixed_garbage(self):
        input_text = """
## Bowen References

1. **Concept 1**: "Quote 1"
- **Concept 2**: "Quote 2"
> **Concept 3**: "Quote 3"
"""
        expected = '> **Concept 1**: "Quote 1"\n> **Concept 2**: "Quote 2"\n> **Concept 3**: "Quote 3"'
        self.assertEqual(_clean_bowen_output(input_text).strip(), expected)


if __name__ == '__main__':
    unittest.main()
