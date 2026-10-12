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


def test_q4_blank_topic_name_skipped(caplog):
    """Q4: a header with no name (blank, or only emphasis marks) is skipped and
    logged, so it cannot fail the abstract-input schema (name minLength 1)."""
    md = ("###   \nFamily systems explain a lot here.\n*~20% of discussion; Sections 1-3*\n\n"
          "###  **  **\nAnxiety spreads.\n*~15% of discussion; Sections 4-5*\n\n"
          "### Topic A\nDescription text.\n*_(~25% of transcript; Sections 6-7)_*\n")
    with caplog.at_level("WARNING"):
        topics = parse_topics_from_extraction(md)
    assert [t.name for t in topics] == ["Topic A"]
    assert "2 topic(s) with no name skipped" in caplog.text


def test_q4_blank_header_does_not_take_the_next_line_as_name(caplog):
    """Adversarial (sweep): a blank header followed by a multi-line description must
    not turn the description's first sentence into a topic name."""
    md = ("###   \nFamily systems explain a lot here.\nMore on that.\n"
          "*~20% of discussion; Sections 1-3*\n\n"
          "### Topic A\nDescription text.\n*_(~25% of transcript; Sections 6-7)_*\n")
    with caplog.at_level("WARNING"):
        topics = parse_topics_from_extraction(md)
    assert [t.name for t in topics] == ["Topic A"]


def test_q4_header_fallback_blank_name_skipped():
    """Strategy 2 (no metadata lines): a blank header is skipped, not named by its body."""
    md = "### Topic A\nDescription only.\n\n###   \nBody of an unnamed topic.\n"
    assert [t.name for t in parse_topics_from_extraction(md)] == ["Topic A"]
