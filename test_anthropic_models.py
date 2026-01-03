#!/usr/bin/env python3
"""
Test script to verify Anthropic API access and list available models dynamically.
"""

import os
import warnings

import anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
# Suppress deprecation warnings from the library for cleaner output
warnings.filterwarnings("ignore", category=DeprecationWarning)


def test_generation(client, model_id):
    print(f"Testing generation: {model_id:<35} ... ", end="", flush=True)
    try:
        client.messages.create(
            model=model_id, max_tokens=10, messages=[{"role": "user", "content": "Hi"}]
        )
        print("✅ Available")
        return True
    except anthropic.NotFoundError:
        print("❌ Not Found (404)")
    except anthropic.AuthenticationError:
        print("❌ Auth Error (401)")
    except anthropic.BadRequestError as e:
        print(f"❌ Bad Request ({str(e)})")
    except Exception as e:
        print(f"❌ Error: {e}")
    return False


def main():
    print("Checking Anthropic Models...")
    print("-" * 60)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not found in environment.")
        return

    try:
        client = anthropic.Anthropic(api_key=api_key)

        print("Fetching available models from API (dynamic list)...")
        try:
            # List models dynamically
            models_page = client.models.list()

            # Collect models
            available_models = []
            if hasattr(models_page, "data"):
                available_models = list(models_page.data)
            else:
                for model in models_page:
                    available_models.append(model)

            # Sort by created_at (newest first)
            available_models.sort(
                key=lambda x: str(getattr(x, "created_at", "")) or x.id, reverse=True
            )

            print(
                f"\nFound {len(available_models)} models available to your API key:\n"
            )

            for model in available_models:
                print(f"ID: {model.id}")
                print(f"Display Name: {getattr(model, 'display_name', 'N/A')}")
                print(f"Created: {getattr(model, 'created_at', 'N/A')}")
                print("-" * 50)

            print("\nVerifying generation capability on discovered models...")

            # Test them
            for m in available_models:
                # Focus testing on Claude 3 family to avoid spamming legacy checks
                # Also check for new Claude 4/4.5 models
                if (
                    "claude-3" in m.id
                    or "claude-4" in m.id
                    or "claude-opus" in m.id
                    or "claude-sonnet" in m.id
                    or "claude-haiku" in m.id
                ):
                    test_generation(client, m.id)

        except Exception as e:
            print(f"❌ Failed to list models dynamically: {e}")
            print("\nFalling back to hardcoded check of recent models...")
            fallback_models = [
                "claude-3-5-sonnet-20241022",
                "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229",
                "claude-3-haiku-20240307",
            ]
            for m in fallback_models:
                test_generation(client, m)

    except Exception as e:
        print(f"❌ Error initializing client: {e}")


if __name__ == "__main__":
    main()
