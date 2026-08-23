import unittest
from unittest.mock import patch

from transcript_utils import (
    extract_section,
    load_bowen_references,
    markdown_to_html,
    normalize_text,
    parse_filename_metadata,
    parse_scored_emphasis_output,
    strip_yaml_frontmatter,
    validate_emphasis_item,
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

    def test_parse_filename_metadata_strips_internal_timestamp(self):
        """A trailing `_YYYYMMDD_HHMMSS` is an internal processing timestamp, not
        part of the lecture date — the ``date`` field must be the clean YYYY-MM-DD
        while ``stem`` keeps the full unique segment."""
        metadata = parse_filename_metadata(
            "Systems Biology Meets Bowen Theory - Michael Kerr - "
            "2021-06-25_20260718_155038.txt"
        )
        self.assertEqual(metadata["date"], "2021-06-25")
        self.assertEqual(metadata["year"], "2021")
        self.assertEqual(
            metadata["stem"],
            "Systems Biology Meets Bowen Theory - Michael Kerr - "
            "2021-06-25_20260718_155038",
        )
    
    def test_parse_scored_emphasis_output_with_timestamp(self):
        emphasis_text = """
[Implicit - A3 - Rank: 88% | 00:12:34] Concept: The concept description
"The quote text."
"""
        items = parse_scored_emphasis_output(emphasis_text)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['timestamp'], '00:12:34')
        self.assertEqual(items[0]['concept'], 'The concept description')

    def test_parse_scored_emphasis_output_no_timestamp(self):
        emphasis_text = """
[Explicit - B1 - Rank: 95%] Concept: Another concept
"Another quote."
"""
        items = parse_scored_emphasis_output(emphasis_text)
        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0]['timestamp'])

    def test_parse_scored_emphasis_output_decimal_score(self):
        """A decimal rank ("92.9%") must parse to the nearest integer, not be
        digit-averaged into a wrong value (92.9 -> 50, which mis-displayed and
        mis-validated against the category range)."""
        emphasis_text = """
[Explicit - A2 - Rank: 92.9%] Concept: Decimal rank concept
"A quote that is long enough to be a valid emphasis item."
"""
        items = parse_scored_emphasis_output(emphasis_text)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['score'], 93)

    def test_validate_emphasis_item_rejects_unrecognized_type(self):
        """An emphasis type outside the prompt's Explicit/Implicit/Clinical set
        (e.g. 'UNRECOGNIZED') must be rejected, not written through to the artifact."""
        item = {
            "type": "UNRECOGNIZED",
            "category": "A2",
            "score": 92,
            "concept": "Some concept",
            "quote": "This is a sufficiently long quote for emphasis validation.",
            "timestamp": None,
        }
        is_valid, issues = validate_emphasis_item(item)
        self.assertFalse(is_valid)
        self.assertTrue(any("Unrecognized emphasis type" in i for i in issues))

    def test_validate_emphasis_item_accepts_known_types(self):
        """Explicit/Implicit/Clinical (case-insensitive) are the only valid types."""
        for t in ("Explicit", "implicit", "CLINICAL"):
            item = {
                "type": t,
                "category": "A8",
                "score": 92,
                "concept": "Some concept",
                "quote": "Emphasis detection requires a sufficiently long quote to pass validation cleanly.",
                "timestamp": None,
            }
            is_valid, issues = validate_emphasis_item(item)
            self.assertTrue(is_valid, f"type {t!r} should be valid: {issues}")

    @patch('pathlib.Path.read_text')
    @patch('pathlib.Path.exists')
    def test_load_bowen_references_with_timestamp(self, mock_exists, mock_read_text):
        mock_exists.return_value = True
        bowen_text = """
### Concept Name [00:12:34]
> "The quote text."

### Another Concept
> "Another quote."
"""
        mock_read_text.return_value = bowen_text
        
        refs = load_bowen_references("any-base-name")
        self.assertEqual(len(refs), 2)
        self.assertEqual(refs[0], ('Concept Name', 'The quote text.', '00:12:34'))
        self.assertEqual(refs[1], ('Another Concept', 'Another quote.', None))

    @patch('transcript_utils.config')
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.read_text')
    def test_load_bowen_references_path_construction(self, mock_read_text, mock_exists, mock_config):
        """Test that the function constructs the file path correctly before trying to access it."""
        # This test is designed to catch a NameError if the `bowen_file` variable is not defined.
        # By mocking the config and the Path methods, we can assert that the
        # path construction logic is called correctly.
        
        # Setup mock behavior. `config` is fully mocked, so `PROJECTS_DIR / a / b`
        # produces a MagicMock (not a real Path) — the Path.exists patch does not
        # apply to it. Drive the chained mock's own .exists() to False so the
        # function short-circuits to [] instead of feeding a mock to re.findall.
        mock_exists.return_value = False
        bowen_file_mock = (
            mock_config.PROJECTS_DIR.__truediv__.return_value.__truediv__.return_value
        )
        bowen_file_mock.exists.return_value = False

        # Call the function
        result = load_bowen_references("test-base-name")

        # The core assertion: was the config variable used to build the path?
        # This confirms the line that was previously missing is now present and executed.
        self.assertTrue(mock_config.PROJECTS_DIR.__truediv__.called)
        self.assertEqual(result, [])

if __name__ == '__main__':
    unittest.main()
