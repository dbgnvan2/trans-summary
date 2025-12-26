#!/usr/bin/env python3
"""
Comprehensive test script to find available Anthropic models.
Attempts to list models dynamically and tests specific known models.
"""
import os
import sys
from dotenv import load_dotenv
import anthropic

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

    print("="*60)
    print("ANTHROPIC MODEL AVAILABILITY CHECK")
    print("="*60)

    # 1. Try dynamic listing
    print("\n--- Attempting to list models via API ---")
    discovered_models = []
    try:
        # Check if models attribute exists (newer SDK versions)
        if hasattr(client, 'models'):
            models_page = client.models.list()
            count = 0
            for model in models_page:
                # Handle different response structures if necessary
                model_id = getattr(model, 'id', str(model))
                display_name = getattr(model, 'display_name', 'N/A')
                print(f"Found: {model_id:<30} ({display_name})")
                discovered_models.append(model_id)
                count += 1

            if count == 0:
                print("No models returned by list endpoint.")
        else:
            print("Client does not support models.list() (SDK might be old).")
    except Exception as e:
        print(f"Dynamic listing failed: {e}")

    # 2. Test models (discovered + known fallbacks)
    print("\n--- Testing models ---")
    known_models = [
        "claude-3-5-sonnet-20241022",
        "claude-3-5-sonnet-latest",
        "claude-3-5-sonnet-20240620",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307",
        "claude-2.1",
        "claude-2.0",
        "claude-instant-1.2"
    ]

    # Combine discovered models with known models (avoiding duplicates)
    models_to_test = list(discovered_models)
    for model in known_models:
        if model not in models_to_test:
            models_to_test.append(model)

    print(f"{'Model ID':<35} | {'Status':<10}")
    print("-" * 50)

    for model_id in models_to_test:
        print(f"{model_id:<35} | ", end="", flush=True)
        try:
            client.messages.create(
                model=model_id,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}]
            )
            print("✅ OK")
        except anthropic.NotFoundError:
            print("❌ 404 (Not Found)")
        except anthropic.AuthenticationError:
            print("❌ 401 (Auth Error)")
        except Exception as e:
            print(f"❌ Error: {type(e).__name__}")


if __name__ == "__main__":
    main()
