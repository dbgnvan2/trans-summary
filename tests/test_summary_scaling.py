#!/usr/bin/env python3
"""
Test to verify summary scaling logic (Inflation Strategy and Min Words Floor).
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import summary_pipeline
import config

class TestSummaryScaling(unittest.TestCase):

    def test_no_inflation_strategy(self):
        """Verify that prepare_summary_input uses target_word_count directly (no inflation)."""

        # Mock inputs
        metadata = {"title": "Test"}
        topics_markdown = "### Topic 1\nDescription\n*_~50%..._*"
        themes_markdown = "Theme 1"
        transcript = "Full transcript text..."
        target_word_count = 600

        # We need to mock the helpers that parse topics so we get a controlled result
        with patch('summary_pipeline.parse_topics_with_details') as mock_parse_topics:
            with patch('summary_pipeline.analyze_qa_content') as mock_analyze_qa:
                with patch('summary_pipeline.calculate_word_allocations') as mock_calc_alloc:
                    # Setup mocks
                    mock_parse_topics.return_value = [{"name": "Topic 1", "percentage": 100, "sections": "1-5", "key_points": []}]
                    mock_analyze_qa.return_value = {"percentage": 0, "question_types": [], "notable_exchanges": []}
                    mock_calc_alloc.return_value = {
                        "opening": 50, "body_total": 400, "qa": 0, "closing": 50,
                        "include_qa": False, "topic_allocations": [400]
                    }

                    # Run function
                    summary_pipeline.prepare_summary_input(
                        metadata, topics_markdown, themes_markdown, transcript, target_word_count
                    )

                    # Verify calculate_word_allocations was called with target directly (NO inflation)
                    # Expected: 600 (not 750)
                    expected_target = 600

                    args, _ = mock_calc_alloc.call_args
                    passed_target = args[0]

                    self.assertEqual(passed_target, expected_target,
                                     f"Target should be {expected_target} (no inflation), got {passed_target}")

    def test_min_words_floor(self):
        """Verify that generate_summary enforces a min_words floor of 600."""

        # Mock inputs
        summary_input = MagicMock()
        summary_input.target_word_count = 750
        # Setup input structure for to_json calls
        summary_input.qa.include = False
        summary_input.opening.word_allocation = 105
        summary_input.body.word_allocation = 525
        summary_input.qa.word_allocation = 0
        summary_input.closing.word_allocation = 45
        summary_input.to_json.return_value = "{}"

        api_client = MagicMock()

        # Mock call_claude_with_retry to avoid actual API call
        with patch('summary_pipeline.call_claude_with_retry') as mock_call:
            mock_call.return_value.content = [MagicMock(text="Summary text")]

            # Run function
            summary_pipeline.generate_summary(summary_input, api_client)

            # Verify min_words parameter is now 600 (not 450)
            _, kwargs = mock_call.call_args
            min_words = kwargs.get('min_words')

            self.assertEqual(min_words, 600, f"min_words should be 600, got {min_words}")

if __name__ == "__main__":
    unittest.main()
