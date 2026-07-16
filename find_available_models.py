#!/usr/bin/env python3
"""
Comprehensive test script to find available Anthropic models.
Attempts to list models dynamically and tests specific known models.
"""

import os

import anthropic
from dotenv import load_dotenv
import model_specs  # ADDED
import config

# Load environment variables
load_dotenv()


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not found in environment.")
        return

    try:
        client = anthropic.Anthropic(api_key=api_key)
    except Exception as e:
        print(f"❌ Failed to initialize Anthropic client: {e}")
        return

    print("=" * 60)
    print("ANTHROPIC MODEL AVAILABILITY CHECK")
    print("=" * 60)

    # 1. Try dynamic listing
    print("\n--- Attempting to list models via API ---")
    discovered_models = []
    try:
        # Check if models attribute exists (newer SDK versions)
        if hasattr(client, "models"):
            # Pagination handling if necessary, though usually list returns a page
            models_page = client.models.list()

            # Handle pagination if the SDK returns a page object that is iterable
            for model in models_page:
                model_id = getattr(model, "id", str(model))
                display_name = getattr(model, "display_name", "N/A")
                print(f"Found: {model_id:<30} (Name: {display_name})")
                discovered_models.append(model_id)

            if not discovered_models:
                print("No models returned by list endpoint.")
        else:
            print("Client does not support models.list() (SDK might be old).")
    except Exception as e:
        print(f"Dynamic listing failed: {e}")
        print("Falling back to known model list.")

    # 2. Prepare list to test
    if discovered_models:
        print(f"\nTesting {len(discovered_models)} discovered models...")
        models_to_test = discovered_models
    else:
        print("\n--- Testing known fallback models ---")
        known_models = [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-sonnet-latest",
            "claude-3-5-sonnet-20240620",
            "claude-3-5-haiku-20241022",
            "claude-3-haiku-20240307",
            "claude-2.1",
            "claude-2.0",
            "claude-instant-1.2",
        ]
        models_to_test = known_models

    print(f"{ 'Model ID':<35} | {'Status & Pricing':<30}")  # MODIFIED header
    print("-" * 66)  # MODIFIED separator length

    working_models_with_pricing = []  # MODIFIED to store tuples

    for model_id in models_to_test:
        print(f"{model_id:<35} | ", end="", flush=True)
        try:
            client.messages.create(
                model=model_id,
                max_tokens=config.MAX_TOKENS_MODEL_PROBE,
                messages=[{"role": "user", "content": "Hi"}],
            )
            pricing = model_specs.get_pricing(model_id)  # ADDED
            # MODIFIED print
            print(
                f"✅ OK (In: ${pricing['input']}/M, Out: ${pricing['output']}/M)")
            working_models_with_pricing.append(
                (model_id, pricing))  # MODIFIED to store pricing
        except anthropic.NotFoundError:
            print("❌ 404 (Not Found)")
        except anthropic.AuthenticationError:
            print("❌ 401 (Auth Error)")
        except anthropic.BadRequestError as e:
            print(f"❌ 400 (Bad Request: {str(e).split(' - ')[0]})")
        except Exception as e:
            print(f"❌ Error: {type(e).__name__}")

    print("\n" + "=" * 60)
    print("SUMMARY OF WORKING MODELS")
    print("=" * 60)
    if working_models_with_pricing:  # MODIFIED
        # MODIFIED to unpack model_id and pricing
        for model_id, pricing in working_models_with_pricing:
            print(
                f"- {model_id:<30} (Input: ${pricing['input']}/M, Output: ${pricing['output']}/M)")

        print("\nRecommended Config Update:")
        # MODIFIED to unpack model_id from the first working model
        # Unpack model_id from tuple
        print(f'DEFAULT_MODEL = "{working_models_with_pricing[0][0]}"')
        if len(working_models_with_pricing) > 1:
            # MODIFIED to unpack model_id and pricing
            aux = next((m_id for m_id, _ in working_models_with_pricing if "haiku" in m_id),
                       working_models_with_pricing[-1][0])  # Unpack
            print(f'AUX_MODEL = "{aux}"')
        else:
            # Unpack
            print(f'AUX_MODEL = "{working_models_with_pricing[0][0]}"')
    else:
        print("No working models found. Please check your API key and billing status.")


if __name__ == "__main__":
    main()
