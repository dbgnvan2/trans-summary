import unittest
from summary_pipeline import parse_themes

class TestSummaryPipeline(unittest.TestCase):

    def test_parse_themes_numbered_legacy(self):
        """Test parsing of legacy numbered themes (1. **Theme**: ...)."""
        markdown = """
1. **Theme One**: Description of theme one.
*Source Sections: 1, 2*

2. **Theme Two**: Description of theme two.
"""
        themes = parse_themes(markdown)
        self.assertEqual(len(themes), 2)
        self.assertEqual(themes[0]['name'], "Theme One")
        self.assertIn("Description of theme one", themes[0]['description'])
        self.assertEqual(themes[1]['name'], "Theme Two")

    def test_parse_themes_headers_new(self):
        """Test parsing of new header-based themes (### Theme)."""
        markdown = """
### Theme One
Description of theme one.

### Theme Two
Description of theme two.
*Source Sections: 5, 6*
"""
        themes = parse_themes(markdown)
        self.assertEqual(len(themes), 2)
        self.assertEqual(themes[0]['name'], "Theme One")
        self.assertIn("Description of theme one", themes[0]['description'])
        self.assertEqual(themes[1]['name'], "Theme Two")
        self.assertEqual(themes[1]['sections'], "5, 6")

if __name__ == '__main__':
    unittest.main()
