#!/usr/bin/env python3
"""
Test script to verify Anthropic API access and available models.
"""
import os
import sys
from dotenv import load_dotenv
import anthropic

# Load environment variables
load_dotenv()


def test_model(model_id):
    print(f"Testing model: {model_id:<30} ... ", end="", flush=True)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("\n❌ ANTHROPIC_API_KEY not found in environment.")
        return False

    client = anthropic.Anthropic(api_key=api_key)

    try:
        client.messages.create(
            model=model_id,
            max_tokens=10,
            messages=[{"role": "user", "content": "Hello"}]
        )
        print("✅ Available")
        return True
    except anthropic.NotFoundError:
        print("❌ Not Found (404)")
    except anthropic.AuthenticationError:
        print("❌ Auth Error (401)")
    except Exception as e:
        print(f"❌ Error: {e}")
    return False


if __name__ == "__main__":
    print("Checking Anthropic Models...")
    print("-" * 60)

    models = [
        "claude-3-5-sonnet-20241022",  # Newest Sonnet (Oct 2024)
        "claude-3-5-sonnet-latest",   # Latest Alias
        "claude-3-5-sonnet-20240620",  # Previous Sonnet (June 2024)
        "claude-3-opus-20240229",     # Opus
        "claude-3-haiku-20240307",    # Haiku (Fast/Cheap)
    ]

    for model in models:
        test_model(model)
