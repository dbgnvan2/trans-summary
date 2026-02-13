from abstract_pipeline import parse_topics_from_extraction


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
