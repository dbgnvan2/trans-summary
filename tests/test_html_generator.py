import unittest

from html_generator import _generate_simple_html_page, _highlight_html_content


class TestHtmlGenerator(unittest.TestCase):

    def test_highlight_html_content_basic(self):
        formatted_html = "<p>This is a test of the highlighting system.</p>"

        # Mock data
        bowen_refs = [("Concept A", "test of the")]
        emphasis_items = [("Item 1", "highlighting system")]

        # Updated signature: 3 args
        highlighted = _highlight_html_content(formatted_html, bowen_refs, emphasis_items)

        # Check for Bowen mark
        self.assertIn('<mark class="bowen-ref" title="Bowen Reference: Concept A">', highlighted)
        self.assertIn(">test of the</mark>", highlighted)

        # Check for Emphasis mark
        self.assertIn('<mark class="emphasis" title="Emphasized: Item 1">', highlighted)
        self.assertIn(">highlighting system</mark>", highlighted)

    def test_highlight_html_content_exact_word_match(self):
        formatted_html = "<p>Word match test.</p>"
        emphasis_items = [("Target", "match")]

        # Updated signature: 3 args
        highlighted = _highlight_html_content(formatted_html, [], emphasis_items)

        self.assertIn(
            '<mark class="emphasis" title="Emphasized: Target">match</mark>', highlighted
        )

    def test_generate_simple_html_page_structure(self):
        base_name = "Test Title - Test Author - 2025-01-01"
        formatted_content = "<p>Content</p>"

        # Mock metadata dict
        metadata = {
            "abstract": "Abstract text",
            "topics": "Topics text",
            "themes": "Themes text",
            "key_terms": [
                {"name": "Term1", "definition": "Def1"},
                {"name": "Term2", "definition": "Def2"},
            ],
        }
        summary = "Summary text"
        bowen_refs = [("Ref1", "Quote1")]
        emphasis_items = [("Emp1", "Quote2")]

        html = _generate_simple_html_page(
            base_name,
            formatted_content,
            metadata,
            summary,
            bowen_refs,
            emphasis_items,
        )

        self.assertIn("<title>Test Title</title>", html)
        self.assertIn("<h1>Test Title</h1>", html)
        self.assertIn("Test Author", html)
        self.assertIn("2025-01-01", html)
        self.assertIn("<p>Content</p>", html)
        self.assertIn("<strong>Term1</strong>", html)
        self.assertIn("Abstract text", html)

if __name__ == '__main__':
    unittest.main()