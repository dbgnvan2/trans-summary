"""
Tests for Summary Word Count Fix (2026-01-11)

Validates that the inflation removal and validation improvements work correctly.
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from summary_pipeline import (
    calculate_word_allocations,
    prepare_summary_input,
    generate_summary,
)
from summary_validation import validate_structural


class TestConfigChanges:
    """Test configuration changes for word count fix."""

    def test_default_summary_word_count_is_650(self):
        """DEFAULT_SUMMARY_WORD_COUNT should be 650."""
        assert config.DEFAULT_SUMMARY_WORD_COUNT == 650

    def test_default_is_reasonable_ratio(self):
        """650 words is reasonable for 6-10k transcripts (6.5-10.8%)."""
        # For 6k transcript: 650/6000 = 10.8%
        # For 10k transcript: 650/10000 = 6.5%
        assert 600 <= config.DEFAULT_SUMMARY_WORD_COUNT <= 1000


class TestInflationRemoval:
    """Test that 25% inflation logic was removed."""

    def test_no_inflation_in_prepare_summary_input(self):
        """prepare_summary_input should use target_word_count directly."""
        metadata = {"speaker": "Dr. Test"}
        topics_markdown = """
### Test Topic
Description here.
*_(~100% of transcript; Sections 1-5)_*
"""
        themes_markdown = ""
        transcript = "## Section 1\nContent here."
        target = 600

        result = prepare_summary_input(
            metadata=metadata,
            topics_markdown=topics_markdown,
            themes_markdown=themes_markdown,
            transcript=transcript,
            target_word_count=target,
        )

        # Target should match input (no inflation)
        assert result.target_word_count == target

        # Total allocations should approximately match target (not target * 1.25)
        total_allocated = (
            result.opening.word_allocation
            + result.body.word_allocation
            + result.qa.word_allocation
            + result.closing.word_allocation
        )

        # Should be close to target (allow small rounding differences)
        assert abs(total_allocated - target) < 10


class TestWordAllocations:
    """Test word allocation calculations."""

    def test_allocations_match_target(self):
        """Allocations should sum to target_word_count."""
        target = 750
        topic_percentages = [40, 30, 20, 10]  # Sum = 100%
        qa_percentage = 15

        allocations = calculate_word_allocations(target, topic_percentages, qa_percentage)

        total = (
            allocations["opening"]
            + allocations["body_total"]
            + allocations["qa"]
            + allocations["closing"]
        )

        # Allow small rounding error
        assert abs(total - target) < 5

    def test_opening_allocation_is_14_percent(self):
        """Opening should get 14% of target."""
        target = 1000
        allocations = calculate_word_allocations(target, [100], 0)

        expected_opening = int(target * config.SUMMARY_OPENING_PCT)
        assert allocations["opening"] == expected_opening

    def test_closing_allocation_is_6_percent(self):
        """Closing should get 6% of target."""
        target = 1000
        allocations = calculate_word_allocations(target, [100], 0)

        expected_closing = int(target * config.SUMMARY_CLOSING_PCT)
        assert allocations["closing"] == expected_closing


class TestAPICallParameters:
    """Test that generate_summary uses correct API parameters."""

    @patch('summary_pipeline.call_claude_with_retry')
    def test_min_words_is_600(self, mock_call):
        """generate_summary should enforce min_words=600."""
        # Setup mock
        mock_message = Mock()
        mock_message.content = [Mock(text="Test summary content" * 50)]
        mock_call.return_value = mock_message

        # Create mock SummaryInput
        from summary_pipeline import SummaryInput, OpeningSection, BodySection, QASection, ClosingSection

        summary_input = SummaryInput(
            metadata={"speaker": "Test"},
            target_word_count=750,
            opening=OpeningSection(
                word_allocation=105,
                stated_purpose="Test purpose",
                content_preview=["topic1"]
            ),
            body=BodySection(word_allocation=525, topics=[]),
            qa=QASection(
                include=True,
                word_allocation=75,
                percentage=10,
                question_types=[],
                notable_exchanges=[]
            ),
            closing=ClosingSection(
                word_allocation=45,
                conclusion="Test",
                open_questions="",
                future_direction=""
            ),
            themes=[]
        )

        mock_client = Mock()

        # Call function
        generate_summary(summary_input, mock_client)

        # Verify call_claude_with_retry was called with min_words=600
        mock_call.assert_called_once()
        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs['min_words'] == 600

    @patch('summary_pipeline.call_claude_with_retry')
    def test_max_tokens_is_4000(self, mock_call):
        """generate_summary should use max_tokens=4000."""
        # Setup mock
        mock_message = Mock()
        mock_message.content = [Mock(text="Test summary content" * 50)]
        mock_call.return_value = mock_message

        # Create mock SummaryInput
        from summary_pipeline import SummaryInput, OpeningSection, BodySection, QASection, ClosingSection

        summary_input = SummaryInput(
            metadata={"speaker": "Test"},
            target_word_count=750,
            opening=OpeningSection(
                word_allocation=105,
                stated_purpose="Test purpose",
                content_preview=["topic1"]
            ),
            body=BodySection(word_allocation=525, topics=[]),
            qa=QASection(
                include=True,
                word_allocation=75,
                percentage=10,
                question_types=[],
                notable_exchanges=[]
            ),
            closing=ClosingSection(
                word_allocation=45,
                conclusion="Test",
                open_questions="",
                future_direction=""
            ),
            themes=[]
        )

        mock_client = Mock()

        # Call function
        generate_summary(summary_input, mock_client)

        # Verify call_claude_with_retry was called with max_tokens=4000
        mock_call.assert_called_once()
        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs['max_tokens'] == 4000

    @patch('summary_pipeline.call_claude_with_retry')
    def test_min_length_is_2400(self, mock_call):
        """generate_summary should use min_length=2400."""
        # Setup mock
        mock_message = Mock()
        mock_message.content = [Mock(text="Test summary content" * 50)]
        mock_call.return_value = mock_message

        # Create mock SummaryInput
        from summary_pipeline import SummaryInput, OpeningSection, BodySection, QASection, ClosingSection

        summary_input = SummaryInput(
            metadata={"speaker": "Test"},
            target_word_count=750,
            opening=OpeningSection(
                word_allocation=105,
                stated_purpose="Test purpose",
                content_preview=["topic1"]
            ),
            body=BodySection(word_allocation=525, topics=[]),
            qa=QASection(
                include=True,
                word_allocation=75,
                percentage=10,
                question_types=[],
                notable_exchanges=[]
            ),
            closing=ClosingSection(
                word_allocation=45,
                conclusion="Test",
                open_questions="",
                future_direction=""
            ),
            themes=[]
        )

        mock_client = Mock()

        # Call function
        generate_summary(summary_input, mock_client)

        # Verify call_claude_with_retry was called with min_length=2400
        mock_call.assert_called_once()
        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs['min_length'] == 2400


class TestValidationThresholds:
    """Test validation threshold changes."""

    def test_validation_fails_below_600_words(self):
        """Structural validation should warn for summaries < 600 words."""
        short_summary = " ".join(["word"] * 550)  # 550 words
        result = validate_structural(short_summary, target_word_count=750)

        # Should have a warning about being too short
        assert len(result['warnings']) > 0
        assert any("Too short" in w for w in result['warnings'])

    def test_validation_passes_at_600_words(self):
        """Structural validation should accept summaries >= 600 words."""
        good_summary = "\n\n".join([
            " ".join(["word"] * 200),  # Paragraph 1: 200 words
            " ".join(["word"] * 200),  # Paragraph 2: 200 words
            " ".join(["word"] * 200),  # Paragraph 3: 200 words
        ])  # Total: 600 words

        result = validate_structural(good_summary, target_word_count=750)

        # Should not have length warnings
        length_warnings = [w for w in result['warnings'] if "Length check" in w and "Too short" in w]
        # At exactly 600, should not warn about minimum
        assert not any("minimum 600" in w for w in length_warnings)

    def test_validation_warns_below_85_percent_of_target(self):
        """Structural validation should warn if < 85% of target."""
        target = 750
        threshold = int(target * 0.85)  # 637.5 → 637

        # Summary just below threshold
        short_summary = " ".join(["word"] * (threshold - 10))  # 627 words

        # Need at least 3 paragraphs
        words_per_para = (threshold - 10) // 3
        short_summary = "\n\n".join([
            " ".join(["word"] * words_per_para),
            " ".join(["word"] * words_per_para),
            " ".join(["word"] * words_per_para),
        ])

        result = validate_structural(short_summary, target_word_count=target)

        # Should warn about being below target
        assert any("Below target" in w for w in result['warnings'])

    def test_validation_no_upper_limit(self):
        """Structural validation should not warn about long summaries."""
        long_summary = "\n\n".join([
            " ".join(["word"] * 300),
            " ".join(["word"] * 300),
            " ".join(["word"] * 300),
        ])  # 900 words (20% over target)

        result = validate_structural(long_summary, target_word_count=750)

        # Should not warn about being too long
        assert not any("Too long" in w or "maximum" in w.lower() for w in result['warnings'])


class TestEndToEndBehavior:
    """Test end-to-end behavior of the word count fix."""

    def test_750_word_target_produces_correct_allocations(self):
        """750-word target should produce reasonable section allocations."""
        metadata = {"speaker": "Dr. Test"}
        topics_markdown = """
### Major Topic
This is the main topic.
*_(~60% of transcript; Sections 1-10)_*

### Minor Topic
This is a smaller topic.
*_(~40% of transcript; Sections 11-15)_*
"""
        themes_markdown = ""
        transcript = "\n".join([f"## Section {i}\nContent." for i in range(1, 16)])
        target = 750

        result = prepare_summary_input(
            metadata=metadata,
            topics_markdown=topics_markdown,
            themes_markdown=themes_markdown,
            transcript=transcript,
            target_word_count=target,
        )

        # Check opening allocation (14% of 750 = 105)
        assert 100 <= result.opening.word_allocation <= 110

        # Check body allocation
        # Body gets remaining after opening (14%), closing (6%), and QA (10% if included)
        # In this test, no Q&A section (0% of transcript), so:
        # Body = 750 - 105 - 45 - 0 = 600 (80% of target)
        assert 595 <= result.body.word_allocation <= 605

        # Check closing allocation (6% of 750 = 45)
        assert 40 <= result.closing.word_allocation <= 50

        # Topics should be proportional to their percentages
        topic_allocations = [t.word_allocation for t in result.body.topics]
        assert len(topic_allocations) == 2

        # Body is 600 words total (80% of target when no Q&A)
        # 60% topic should get ~60% of body = 360 words
        assert 350 <= topic_allocations[0] <= 370

        # 40% topic should get ~40% of body (240 words)
        assert 230 <= topic_allocations[1] <= 250


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
