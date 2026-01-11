import os
import logging
import pytest
from anthropic import Anthropic
import transcript_utils
import config

# Use pytest-style test
class TestCachingIntegration:
    @pytest.fixture
    def client(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            pytest.skip("ANTHROPIC_API_KEY not set")
        return Anthropic(api_key=api_key)

    @pytest.fixture
    def logger(self):
        return logging.getLogger("TestCaching")

    @pytest.mark.integration
    def test_caching_flow(self, client, logger):
        """
        Verify that prompt caching works end-to-end with the configured model.
        Requires:
        1. Call 1: cache_creation_input_tokens > 0
        2. Call 2: cache_read_input_tokens > 0
        """
        model = config.DEFAULT_MODEL
        logger.info(f"Testing caching with model: {model}")

        # Create a large static system message (>1024 tokens)
        large_text = "This is a test of the prompt caching system. " * 300
        system_message = transcript_utils.create_system_message_with_cache(large_text)

        # --- Call 1: Expect Creation ---
        msg1 = transcript_utils.call_claude_with_retry(
            client,
            model=model,
            messages=[{"role": "user", "content": "Hello 1"}],
            system=system_message,
            max_tokens=100,
            logger=logger,
            min_length=1
        )
        
        create_tokens = getattr(msg1.usage, 'cache_creation_input_tokens', 0) or 0
        logger.info(f"Call 1 Cache Creation: {create_tokens}")
        
        # Assert creation happened (unless it was already cached by a previous run recently, 
        # but usually with a unique prompt it creates. If we use fixed text, it might read.
        # So we accept EITHER Create > 0 OR Read > 0 for the first call to be safe,
        # but crucially, the system MUST support it).
        assert create_tokens > 0 or getattr(msg1.usage, 'cache_read_input_tokens', 0) > 0, \
            f"Model {model} did not create or read cache on first call. Caching might be unsupported."

        # --- Call 2: Expect Read ---
        msg2 = transcript_utils.call_claude_with_retry(
            client,
            model=model,
            messages=[{"role": "user", "content": "Hello 2"}],
            system=system_message,
            max_tokens=100,
            logger=logger,
            min_length=1
        )
        
        read_tokens = getattr(msg2.usage, 'cache_read_input_tokens', 0) or 0
        logger.info(f"Call 2 Cache Read: {read_tokens}")
        
        assert read_tokens > 0, f"Model {model} failed to read cache on second call."
