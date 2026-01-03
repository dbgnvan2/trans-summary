import pytest

from transcript_utils import (
    extract_section,
    markdown_to_html,
    normalize_text,
    parse_filename_metadata,
    strip_yaml_frontmatter,
)


def test_markdown_to_html_headings():
    assert markdown_to_html("# Title") == "<h1>Title</h1>"
    assert markdown_to_html("## Subtitle") == "<h2>Subtitle</h2>"
    assert markdown_to_html("### Sub-subtitle") == "<h3>Sub-subtitle</h3>"


def test_markdown_to_html_bold():
    assert (
        markdown_to_html("This is **bold** text.")
        == "<p>This is <strong>bold</strong> text.</p>"
    )


def test_markdown_to_html_italic():
    assert (
        markdown_to_html("This is *italic* text.")
        == "<p>This is <em>italic</em> text.</p>"
    )


def test_markdown_to_html_paragraphs():
    assert (
        markdown_to_html("Paragraph 1\n\nParagraph 2")
        == "<p>Paragraph 1</p>\n<p>Paragraph 2</p>"
    )


def test_normalize_text_simple():
    assert normalize_text("  This is a Test  ") == "this is a test"
    assert normalize_text("This has <p>HTML</p> tags.") == "this has html tags."


def test_normalize_text_aggressive():
    assert (
        normalize_text("This is a **Speaker:** test.", aggressive=True)
        == "this is a test"
    )
    assert (
        normalize_text("This has punctuation,!-.", aggressive=True)
        == "this has punctuation"
    )


def test_strip_yaml_frontmatter():
    content = """---
title: My Title
---
This is the real content.
"""
    assert strip_yaml_frontmatter(content) == "This is the real content.\n"


def test_strip_yaml_frontmatter_no_yaml():
    content = "This is the real content."
    assert strip_yaml_frontmatter(content) == "This is the real content."


@pytest.fixture
def sample_markdown_content():
    return """
# First Section

Content of first section.

## **Topics**

- Topic 1
- Topic 2

## Some Other Section

Some other content.

## Key Themes

- Theme A
- Theme B
"""


def test_extract_section(sample_markdown_content):
    topics_section = extract_section(sample_markdown_content, "Topics")
    assert "- Topic 1" in topics_section
    assert "- Topic 2" in topics_section
    assert "Some Other Section" not in topics_section

    themes_section = extract_section(sample_markdown_content, "Key Themes")
    assert "- Theme A" in themes_section
    assert "- Theme B" in themes_section

    non_existent_section = extract_section(sample_markdown_content, "Non Existent")
    assert non_existent_section == ""


def test_parse_filename_metadata():
    metadata = parse_filename_metadata("My Awesome Title - John Doe - 2025-12-21.txt")
    assert metadata["title"] == "My Awesome Title"
    assert metadata["presenter"] == "John Doe"
    assert metadata["author"] == "John Doe"
    assert metadata["date"] == "2025-12-21"
    assert metadata["year"] == "2025"
    assert metadata["stem"] == "My Awesome Title - John Doe - 2025-12-21"


def test_parse_filename_metadata_with_hyphens():
    metadata = parse_filename_metadata(
        "A Title - With - Hyphens - Jane Doe - 2025-01-01.md"
    )
    assert metadata["title"] == "A Title - With - Hyphens"
    assert metadata["presenter"] == "Jane Doe"
    assert metadata["date"] == "2025-01-01"
    assert metadata["year"] == "2025"


def test_parse_filename_metadata_formatted():
    metadata = parse_filename_metadata(
        "Some Title - Some Presenter - 2023-03-03 - formatted.md"
    )
    assert metadata["title"] == "Some Title"
    assert metadata["presenter"] == "Some Presenter"
    assert metadata["date"] == "2023-03-03"
    assert metadata["stem"] == "Some Title - Some Presenter - 2023-03-03"


def test_parse_filename_metadata_invalid():
    with pytest.raises(ValueError):
        parse_filename_metadata("invalid-filename.txt")
