"""
Unit tests for extraction robustness and text normalization.
Verifies that the system can handle variable LLM outputs and clean text correctly.
"""

import unittest

from extraction_pipeline import _normalize_headers
from transcript_utils import extract_section, strip_yaml_frontmatter


class TestExtractionRobustness(unittest.TestCase):

    def test_extract_section_variations(self):
        """Test that extract_section handles various header formats."""
        
        # Test Case 1: Standard
        content_standard = """
## Topics
This is the content.
## Next Section
"""
        self.assertEqual(extract_section(content_standard, "Topics"), "This is the content.")

        # Test Case 2: Bold
        content_bold = """
## **Topics**
Bold content.
## Next
"""
        self.assertEqual(extract_section(content_bold, "Topics"), "Bold content.")

        # Test Case 3: Numbered
        content_numbered = """
## 1. Topics
Numbered content.
## 2. Next
"""
        self.assertEqual(extract_section(content_numbered, "Topics"), "Numbered content.")

        # Test Case 4: Colon
        content_colon = """
## Topics:
Colon content.
## Next
"""
        self.assertEqual(extract_section(content_colon, "Topics"), "Colon content.")

        # Test Case 5: Single Hash (Downgraded header)
        content_h1 = """
# Topics
H1 content.
# Next
"""
        self.assertEqual(extract_section(content_h1, "Topics"), "H1 content.")

        # Test Case 6: Mixed (Bold + Number + Colon)
        content_mixed = """
## **1. Topics:**
Mixed content.
## Next
"""
        self.assertEqual(extract_section(content_mixed, "Topics"), "Mixed content.")

    def test_normalize_headers(self):
        """Test that _normalize_headers enforces standard format."""
        
        # Input with messy headers
        messy_text = """
**Topics**
Content A

# Key Themes:
Content B

## 3. Key Terms
Content C
"""
        # Note: The function replaces the HEADER line.
        # We need to verify the replacement works as expected on the lines.
        
        normalized = _normalize_headers(messy_text)
        
        self.assertIn("## Topics", normalized)
        self.assertNotIn("**Topics**", normalized)
        
        self.assertIn("## Key Themes", normalized)
        self.assertNotIn("# Key Themes:", normalized)
        
        self.assertIn("## Key Terms", normalized)
        self.assertNotIn("## 3. Key Terms", normalized)

    def test_extract_section_nested(self):
        """Test extraction of a section containing nested sub-headers."""
        text = """
## Topics
### Subtopic 1
Content 1
### Subtopic 2
Content 2

## Next Section
Other content
"""
        extracted = extract_section(text, "Topics")
        self.assertIn("### Subtopic 1", extracted)
        self.assertIn("Content 1", extracted)
        self.assertIn("### Subtopic 2", extracted)
        self.assertIn("Content 2", extracted)
        self.assertNotIn("## Next Section", extracted)
        self.assertNotIn("Other content", extracted)

    def test_strip_yaml(self):
        """Test YAML frontmatter removal."""
        text = """---
key: value
---
Real content."""
        self.assertEqual(strip_yaml_frontmatter(text).strip(), "Real content.")

        text_no_yaml = "Just content."
        self.assertEqual(strip_yaml_frontmatter(text_no_yaml), "Just content.")

if __name__ == '__main__':
    unittest.main()
