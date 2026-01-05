#!/usr/bin/env python3
"""
Test script to verify Anthropic API access and list available models dynamically.
"""

import os
import warnings
import pytest # Added pytest import

import anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
# Suppress deprecation warnings from the library for cleaner output
warnings.filterwarnings("ignore", category=DeprecationWarning)


@pytest.fixture(scope="module")
def anthropic_client_fixture():
    """Provides an Anthropic client instance for tests."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not found in environment.")
    return anthropic.Anthropic(api_key=api_key)


@pytest.mark.parametrize("model_id", [
    "claude-opus-4-5-20251101",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
    "claude-3-opus-20240229",
    "claude-3-haiku-20240307",
])
def test_anthropic_model_generation(anthropic_client_fixture, model_id):
    """
    Tests if a specific Anthropic model can successfully generate a response.
    """
    print(f"Testing generation: {model_id:<35} ... ", end="", flush=True)
    try:
        response = anthropic_client_fixture.messages.create(
            model=model_id, max_tokens=10, messages=[{"role": "user", "content": "Hi"}]
        )
        # Basic assertion to ensure a response was received
        assert response.content is not None and len(response.content) > 0
        print("✅ Available")
    except anthropic.NotFoundError:
        pytest.fail(f"❌ Model '{model_id}' Not Found (404)")
    except anthropic.AuthenticationError:
        pytest.fail("❌ Anthropic Authentication Error (401)")
    except anthropic.BadRequestError as e:
        pytest.fail(f"❌ Bad Request for model '{model_id}': {e}")
    except Exception as e:
        pytest.fail(f"❌ Unexpected Error for model '{model_id}': {e}")