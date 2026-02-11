import unittest

from transcript_utils import (
    extract_section,
    markdown_to_html,
    normalize_text,
    parse_filename_metadata,
    strip_yaml_frontmatter,
)


class TestTranscriptUtils(unittest.TestCase):

    def test_markdown_to_html_headings(self):
        self.assertEqual(markdown_to_html("# Title"), "<h1>Title</h1>")
        self.assertEqual(markdown_to_html("## Subtitle"), "<h2>Subtitle</h2>")
        self.assertEqual(markdown_to_html("### Sub-subtitle"), "<h3>Sub-subtitle</h3>")

    def test_markdown_to_html_bold(self):
        self.assertEqual(
            markdown_to_html("This is **bold** text."),
            "<p>This is <strong>bold</strong> text.</p>"
        )

    def test_markdown_to_html_italic(self):
        self.assertEqual(
            markdown_to_html("This is *italic* text."),
            "<p>This is <em>italic</em> text.</p>"
        )

    def test_markdown_to_html_paragraphs(self):
        self.assertEqual(
            markdown_to_html("Paragraph 1\n\nParagraph 2"),
            "<p>Paragraph 1</p>\n<p>Paragraph 2</p>"
        )

    def test_normalize_text_simple(self):
        self.assertEqual(normalize_text("  This is a Test  "), "this is a test")
        self.assertEqual(normalize_text("This has <p>HTML</p> tags."), "this has html tags.")

    def test_normalize_text_aggressive(self):
        self.assertEqual(
            normalize_text("This is a **Speaker:** test.", aggressive=True),
            "this is a test"
        )
        self.assertEqual(
            normalize_text("This has punctuation,!-.", aggressive=True),
            "this has punctuation"
        )

    def test_strip_yaml_frontmatter(self):
        content = """---
title: My Title
---
This is the real content.
"""
        self.assertEqual(strip_yaml_frontmatter(content), "This is the real content.\n")

    def test_strip_yaml_frontmatter_no_yaml(self):
        content = "This is the real content."
        self.assertEqual(strip_yaml_frontmatter(content), "This is the real content.")

    def test_extract_section(self):
        sample_markdown_content = """
# First Section

Content of first section.

## **Topics**

- Topic 1
- Topic 2

## Some Other Section

Some other content.

## Interpretive Themes

- Theme A
- Theme B
"""
        topics_section = extract_section(sample_markdown_content, "Topics")
        self.assertIn("- Topic 1", topics_section)
        self.assertIn("- Topic 2", topics_section)
        self.assertNotIn("Some Other Section", topics_section)

        themes_section = extract_section(sample_markdown_content, "Interpretive Themes")
        self.assertIn("- Theme A", themes_section)
        self.assertIn("- Theme B", themes_section)

        non_existent_section = extract_section(sample_markdown_content, "Non Existent")
        self.assertEqual(non_existent_section, "")

    def test_parse_filename_metadata(self):
        metadata = parse_filename_metadata("My Awesome Title - John Doe - 2025-12-21.txt")
        self.assertEqual(metadata["title"], "My Awesome Title")
        self.assertEqual(metadata["presenter"], "John Doe")
        self.assertEqual(metadata["author"], "John Doe")
        self.assertEqual(metadata["date"], "2025-12-21")
        self.assertEqual(metadata["year"], "2025")
        self.assertEqual(metadata["stem"], "My Awesome Title - John Doe - 2025-12-21")

    def test_parse_filename_metadata_with_hyphens(self):
        metadata = parse_filename_metadata(
            "A Title - With - Hyphens - Jane Doe - 2025-01-01.md"
        )
        self.assertEqual(metadata["title"], "A Title - With - Hyphens")
        self.assertEqual(metadata["presenter"], "Jane Doe")
        self.assertEqual(metadata["date"], "2025-01-01")
        self.assertEqual(metadata["year"], "2025")

    def test_parse_filename_metadata_formatted(self):
        metadata = parse_filename_metadata(
            "Some Title - Some Presenter - 2023-03-03 - formatted.md"
        )
        self.assertEqual(metadata["title"], "Some Title")
        self.assertEqual(metadata["presenter"], "Some Presenter")
        self.assertEqual(metadata["date"], "2023-03-03")
        self.assertEqual(metadata["stem"], "Some Title - Some Presenter - 2023-03-03")

    def test_parse_filename_metadata_invalid(self):
        with self.assertRaises(ValueError):
            parse_filename_metadata("invalid-filename.txt")

if __name__ == '__main__':
    unittest.main()
