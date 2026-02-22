#!/usr/bin/env python3
"""
Configuration Check Script
Validates environment variables, directory structure, and prompt files.

Usage:
    python transcript_config_check.py
"""

import os
import sys

import anthropic

import config


def check_environment_variables():
    """Check for required environment variables."""
    print("\n--- Environment Variables ---")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        masked_key = f"{api_key[:8]}...{api_key[-4:]}"
        print(f"✅ ANTHROPIC_API_KEY found: {masked_key}")
        return True
    else:
        print("❌ ANTHROPIC_API_KEY not set.")
        print("   Please set it in your environment or .env file.")
        return False


def check_directories():
    """Check if configured directories exist."""
    print("\n--- Directory Structure ---")
    all_exist = True

    dirs_to_check = [
        ("Base", config.TRANSCRIPTS_BASE),
        ("Source", config.SOURCE_DIR),
        ("Projects", config.PROJECTS_DIR),
        ("Processed", config.PROCESSED_DIR),
        ("Prompts", config.PROMPTS_DIR),
        ("Logs", config.LOGS_DIR),
    ]

    for name, path in dirs_to_check:
        if path.exists():
            print(f"✅ {name:<10}: {path}")
        else:
            print(f"❌ {name:<10}: {path} (Missing)")
            # Don't fail for output directories, just warn/create
            if name in ["Source", "Prompts"]:
                all_exist = False
            else:
                print("   (Will be created automatically)")

    return all_exist


def check_prompt_files():
    """Check if all referenced prompt files exist."""
    print("\n--- Prompt Files ---")
    all_exist = True

    # Get all attributes from config that start with PROMPT_ and end with _FILENAME
    prompt_vars = [
        attr
        for attr in dir(config)
        if attr.startswith("PROMPT_") and attr.endswith("_FILENAME")
    ]

    for var_name in prompt_vars:
        filename = getattr(config, var_name)
        file_path = config.PROMPTS_DIR / filename

        if file_path.exists():
            print(f"✅ {var_name:<40}: {filename}")
        else:
            print(f"❌ {var_name:<40}: {filename} (Missing)")
            all_exist = False

    return all_exist


def check_model_availability():
    """Check if the configured models are available via the API."""
    print("\n--- Model Availability ---")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ Cannot check model: ANTHROPIC_API_KEY not set.")
        return False

    models_to_check = []
    for model in [
        config.DEFAULT_MODEL,
        config.AUX_MODEL,
        config.FORMATTING_MODEL,
        config.VALIDATION_MODEL,
    ]:
        if model not in models_to_check:
            models_to_check.append(model)

    all_available = True
    client = anthropic.Anthropic(api_key=api_key)

    for model in models_to_check:
        print(f"Checking model: {model:<30} ... ", end="", flush=True)
        try:
            client.messages.create(
                model=model,
                max_tokens=config.MAX_TOKENS_MODEL_PROBE,
                messages=[{"role": "user", "content": "Hi"}],
            )
            print("✅ Available")
        except anthropic.NotFoundError:
            print("❌ Not Found (404)")
            print(f"   The model '{model}' does not exist or you don't have access.")
            all_available = False
        except Exception as e:
            print(f"❌ Error: {e}")
            all_available = False

    return all_available


def check_internal_config_validation():
    """Run config.py's built-in validation to catch logical drift."""
    print("\n--- Internal Config Validation ---")
    result = config.validate_configuration(verbose=False, auto_fix=False)
    if result.is_valid():
        if result.warnings:
            print(f"⚠️  Internal validation warnings: {len(result.warnings)}")
        else:
            print("✅ Internal config validation passed")
        return True

    print(f"❌ Internal config validation errors: {len(result.errors)}")
    for error in result.errors:
        first_line = error.splitlines()[0]
        print(f"   - {first_line}")
    return False


def main():
    print("=" * 60)
    print("TRANSCRIPT PIPELINE CONFIGURATION CHECK")
    print("=" * 60)

    env_ok = check_environment_variables()
    dirs_ok = check_directories()
    prompts_ok = check_prompt_files()

    model_ok = True
    internal_ok = check_internal_config_validation()
    if env_ok:
        model_ok = check_model_availability()

    print("\n" + "=" * 60)
    if env_ok and dirs_ok and prompts_ok and model_ok and internal_ok:
        print("✅ CONFIGURATION VALID. Ready to run pipeline.")
        return 0
    else:
        print("❌ CONFIGURATION ISSUES FOUND. Please fix errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
