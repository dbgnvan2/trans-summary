from abstract_pipeline import parse_themes_from_extraction, parse_topics_from_extraction


def test_parse_topics_strict_format():
    topics = parse_topics_from_extraction(
        """
### Topic A
Description text.
*_(~25% of transcript; Sections 1-3)_*
"""
    )
    assert len(topics) == 1
    assert topics[0].name == "Topic A"
    assert topics[0].percentage == 25
    assert topics[0].sections == "1-3"


def test_parse_topics_header_fallback_without_metadata():
    topics = parse_topics_from_extraction(
        """
### Topic A
Description only.

### Topic B
Another description.
"""
    )
    assert len(topics) == 2
    assert topics[0].name == "Topic A"
    assert topics[1].name == "Topic B"


def test_parse_topics_list_fallback():
    topics = parse_topics_from_extraction(
        """
1. **Differentiation of Self**: Topic description.
2. **Triangles**: Topic description.
"""
    )
    assert len(topics) == 2
    assert topics[0].name == "Differentiation of Self"
    assert topics[1].name == "Triangles"


def test_parse_themes_ignores_summary_paragraph_header():
    themes = parse_themes_from_extraction(
        """
### Theme A
Interpretive description.

### Summary Paragraph
This is only a synthesis paragraph and should not become a theme.
"""
    )
    assert len(themes) == 1
    assert themes[0].name == "Theme A"


def test_parse_themes_bold_numbered_blocks():
    themes = parse_themes_from_extraction(
        """
## Interpretive / Process Themes (2 total)

**1. Denial as a Structural Function**

**Description:** Denial maintains cutoff in real time.

**2. The Positive Occasion as Anxiety Accelerator**

**Description:** Positive events intensify anxiety in the system.

### Summary Paragraph
These themes work together.
"""
    )
    assert len(themes) == 2
    assert themes[0].name == "Denial as a Structural Function"
    assert "maintains cutoff" in themes[0].description
    assert themes[1].name == "The Positive Occasion as Anxiety Accelerator"
