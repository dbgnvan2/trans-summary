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
            # Pagination handling if necessary, though usually list returns a page
            models_page = client.models.list()

            # Handle pagination if the SDK returns a page object that is iterable
            for model in models_page:
                model_id = getattr(model, 'id', str(model))
                display_name = getattr(model, 'display_name', 'N/A')
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
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-2.1",
            "claude-2.0",
            "claude-instant-1.2"
        ]
        models_to_test = known_models

    print(f"{'Model ID':<35} | {'Status':<10}")
    print("-" * 50)

    working_models = []

    for model_id in models_to_test:
        print(f"{model_id:<35} | ", end="", flush=True)
        try:
            client.messages.create(
                model=model_id,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}]
            )
            print("✅ OK")
            working_models.append(model_id)
        except anthropic.NotFoundError:
            print("❌ 404 (Not Found)")
        except anthropic.AuthenticationError:
            print("❌ 401 (Auth Error)")
        except anthropic.BadRequestError as e:
            print(f"❌ 400 (Bad Request: {str(e).split(' - ')[0]})")
        except Exception as e:
            print(f"❌ Error: {type(e).__name__}")

    print("\n" + "="*60)
    print("SUMMARY OF WORKING MODELS")
    print("="*60)
    if working_models:
        for m in working_models:
            print(f"- {m}")

        print("\nRecommended Config Update:")
        print(f"DEFAULT_MODEL = \"{working_models[0]}\"")
        if len(working_models) > 1:
            # Try to find a haiku model for AUX, otherwise use the last one or same
            aux = next((m for m in working_models if 'haiku' in m),
                       working_models[-1])
            print(f"AUX_MODEL = \"{aux}\"")
        else:
            print(f"AUX_MODEL = \"{working_models[0]}\"")
    else:
        print("No working models found. Please check your API key and billing status.")


if __name__ == "__main__":
    main()
