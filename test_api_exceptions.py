#!/usr/bin/env python3
"""
Test specifically for API exception handling in call_claude_with_retry.
Ensures robustness against RateLimitError, APITimeoutError, and generic APIError.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import transcript_utils
from anthropic import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    RateLimitError,
)

class TestAPIExceptions(unittest.TestCase):

    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_logger = MagicMock()

    def test_rate_limit_retry(self):
        """Test that RateLimitError triggers retries and exponential backoff."""
        # Setup mock to raise RateLimitError twice then succeed
        success_response = MagicMock()
        success_response.type = "message"
        success_response.role = "assistant"
        success_response.stop_reason = "end_turn"
        success_response.content = [MagicMock(type="text", text="Success response content that is definitely longer than fifty characters to pass validation.")]
        success_response.usage = MagicMock(
            input_tokens=10, 
            output_tokens=10,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0
        )

        # Mock the request header since the library checks it for rate limits
        error_response = MagicMock()
        error_response.headers = {}
        
        self.mock_client.messages.create.side_effect = [
            RateLimitError(message="Rate limited", response=error_response, body={}),
            RateLimitError(message="Rate limited again", response=error_response, body={}),
            success_response
        ]

        with patch("time.sleep") as mock_sleep:
            response = transcript_utils.call_claude_with_retry(
                self.mock_client, "model", [], 100, logger=self.mock_logger
            )

        self.assertEqual(response, success_response)
        self.assertEqual(self.mock_client.messages.create.call_count, 3)
        
        # Rate-limit backoff (no retry-after header): RATE_LIMIT_BACKOFF_SECONDS *
        # (attempt + 1) — 10s, 20s since SDK retries are off (sweep finding).
        mock_sleep.assert_any_call(transcript_utils.config.RATE_LIMIT_BACKOFF_SECONDS)
        mock_sleep.assert_any_call(2 * transcript_utils.config.RATE_LIMIT_BACKOFF_SECONDS)

    def test_timeout_retry(self):
        """Test that APITimeoutError triggers retries and increases timeout."""
        success_response = MagicMock()
        success_response.type = "message"
        success_response.role = "assistant"
        success_response.stop_reason = "end_turn"
        success_response.content = [MagicMock(type="text", text="Success response content that is definitely longer than fifty characters to pass validation.")]
        success_response.usage = MagicMock(
            input_tokens=10, 
            output_tokens=10,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0
        )

        request = MagicMock()

        self.mock_client.messages.create.side_effect = [
            APITimeoutError(request=request),
            success_response
        ]

        # Initial call with explicit timeout
        response = transcript_utils.call_claude_with_retry(
            self.mock_client, "model", [], 100, logger=self.mock_logger, timeout=10.0
        )

        self.assertEqual(response, success_response)
        self.assertEqual(self.mock_client.messages.create.call_count, 2)
        
        # Verify second call had increased timeout (10.0 * 1.5 = 15.0)
        args, kwargs = self.mock_client.messages.create.call_args
        self.assertEqual(kwargs['timeout'], 15.0)

    def test_generic_api_error_no_retry(self):
        """Test that generic APIError does NOT trigger retry and is raised."""
        request = MagicMock()
        body = {}
        self.mock_client.messages.create.side_effect = APIError(message="Generic error", request=request, body=body)

        with self.assertRaises(APIError):
            transcript_utils.call_claude_with_retry(
                self.mock_client, "model", [], 100, logger=self.mock_logger
            )
        
        # Should fail immediately on first attempt
        self.assertEqual(self.mock_client.messages.create.call_count, 1)

    def test_connection_error_retry(self):
        """Test that APIConnectionError triggers retries."""
        success_response = MagicMock()
        success_response.type = "message"
        success_response.role = "assistant"
        success_response.stop_reason = "end_turn"
        success_response.content = [MagicMock(type="text", text="Success response content that is definitely longer than fifty characters to pass validation.")]
        success_response.usage = MagicMock(
            input_tokens=10, 
            output_tokens=10,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0
        )

        request = MagicMock()

        self.mock_client.messages.create.side_effect = [
            APIConnectionError(message="Connection failed", request=request),
            success_response
        ]

        with patch("time.sleep") as mock_sleep:
            response = transcript_utils.call_claude_with_retry(
                self.mock_client, "model", [], 100, logger=self.mock_logger
            )

        self.assertEqual(response, success_response)
        self.assertEqual(self.mock_client.messages.create.call_count, 2)
        mock_sleep.assert_called_with(1)

    def test_overloaded_api_error_retries_then_succeeds(self):
        """Test that overloaded APIError triggers retry/backoff and then succeeds."""
        success_response = MagicMock()
        success_response.type = "message"
        success_response.role = "assistant"
        success_response.stop_reason = "end_turn"
        success_response.content = [
            MagicMock(
                type="text",
                text="Success response content that is definitely longer than fifty characters to pass validation.",
            )
        ]
        success_response.usage = MagicMock(
            input_tokens=10,
            output_tokens=10,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )

        request = MagicMock()
        overload_body = {"error": {"type": "overloaded_error", "message": "Overloaded"}}
        overloaded = APIError(message="Overloaded", request=request, body=overload_body)

        self.mock_client.messages.create.side_effect = [overloaded, success_response]

        with patch("time.sleep") as mock_sleep:
            response = transcript_utils.call_claude_with_retry(
                self.mock_client, "model", [], 100, logger=self.mock_logger
            )

        self.assertEqual(response, success_response)
        self.assertEqual(self.mock_client.messages.create.call_count, 2)
        mock_sleep.assert_called_with(transcript_utils.config.RATE_LIMIT_BACKOFF_SECONDS)

    def test_rate_limit_honours_retry_after_header(self):
        """The API's retry-after header sets the wait (capped)."""
        error_response = MagicMock()
        error_response.headers = {"retry-after": "37"}
        self.assertEqual(transcript_utils._retry_wait_seconds(
            RateLimitError(message="x", response=error_response, body={}), 0), 37.0)
        error_response.headers = {"retry-after": "9999"}
        self.assertEqual(transcript_utils._retry_wait_seconds(
            RateLimitError(message="x", response=error_response, body={}), 0),
            transcript_utils.config.MAX_RETRY_AFTER_SECONDS)

if __name__ == "__main__":
    unittest.main()
