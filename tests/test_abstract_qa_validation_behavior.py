from types import SimpleNamespace

import abstract_pipeline
import abstract_validation


def _make_input(qa_percentage, qa_topics):
    topic = SimpleNamespace(name="Family systems", percentage=35, sections="1-3")
    theme = SimpleNamespace(
        name="Chronic anxiety",
        description="Anxiety influences symptom formation across relationships.",
    )
    return SimpleNamespace(
        metadata={"speaker": "Dr. Michael Kerr"},
        topics=[topic],
        themes=[theme],
        opening_purpose="My intent is to describe family systems processes.",
        closing_conclusion="I conclude these patterns are clinically relevant.",
        qa_percentage=qa_percentage,
        qa_topics=qa_topics,
        target_word_count=250,
    )


def test_qa_coverage_not_required_at_low_signal_borderline_percentage():
    abstract_input = _make_input(
        21, ["this", "You as", "this seems", "my bulletin", "the disparity"]
    )

    abstract = (
        "Dr. Michael Kerr presents family systems concepts and chronic anxiety, "
        "states his intent to describe relationship process, and concludes the "
        "patterns are clinically relevant."
    )

    items = abstract_validation.generate_coverage_items(abstract_input)
    qa_items = [item for item in items if item.category == "qa"]
    assert qa_items, "Expected optional QA item when QA share is non-trivial."
    assert qa_items[0].required is False

    result = abstract_validation.validate_abstract_coverage(
        abstract, abstract_input, use_llm_verification=False
    )
    assert result["passed"] is True


def test_qa_coverage_required_for_large_qa_share():
    abstract_input = _make_input(
        35, ["chronic anxiety", "cancer process", "relationship distance"]
    )
    items = abstract_validation.generate_coverage_items(abstract_input)
    qa_items = [item for item in items if item.category == "qa"]
    assert qa_items and qa_items[0].required is True


def test_clean_qa_topics_filters_filler_phrases():
    cleaned = abstract_pipeline._clean_qa_topics(
        ["about this", "on the", "regarding chronic anxiety in families", "my bulletin"]
    )
    assert "chronic anxiety families" in cleaned
    assert all(topic not in cleaned for topic in ("about this", "on the"))
