"""
Shared utilities for transcript processing scripts.
Reduces code duplication and provides common validation/error handling.
"""

import csv
import logging
import os
import re
import time
from copy import deepcopy
from datetime import datetime
from difflib import SequenceMatcher
from html import unescape
from pathlib import Path
from typing import Any, Optional

from anthropic import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    RateLimitError,
)

import config
import model_specs

LARGE_INPUT_CACHE_THRESHOLD_CHARS = 10000


# Configure logging
def setup_logging(script_name: str) -> logging.Logger:
    """Set up logging for a script."""
    logs_dir = config.LOGS_DIR
    logs_dir.mkdir(exist_ok=True)

    log_file = logs_dir / f"{script_name}_{datetime.now():%Y%m%d_%H%M%S}.log"
    logger = logging.getLogger(script_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    logger.info("Logging initialized: %s", log_file)
    return logger


def validate_api_key() -> str:
    """
    Validate that ANTHROPIC_API_KEY is set.

    Returns:
        The API key

    Raises:
        ValueError: If API key is not set
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable not set.\n"
            "Please set it in your .env file or environment:\n"
            "  export ANTHROPIC_API_KEY='your-api-key-here'\n"
            "Get your key from: https://console.anthropic.com/"
        )
    return api_key


def validate_input_file(file_path: Path) -> None:
    """
    Validate that input file exists and is readable.

    Args:
        file_path: Path to validate

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file is empty or not a file
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    if not file_path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")

    if file_path.stat().st_size == 0:
        raise ValueError(f"Input file is empty: {file_path}")


def load_project_transcript(base_name: str, logger: Optional[logging.Logger] = None) -> str:
    """Load a project transcript, preferring formatted markdown and falling back to YAML."""
    candidate_paths = [
        config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_FORMATTED}",
        config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_YAML}",
    ]

    last_error: Optional[Exception] = None
    for path in candidate_paths:
        try:
            validate_input_file(path)
            if logger and path.name.endswith(config.SUFFIX_YAML):
                logger.info(
                    "Formatted transcript missing; falling back to YAML transcript: %s",
                    path,
                )
            return strip_yaml_frontmatter(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError) as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise FileNotFoundError(f"No structured transcript found for project: {base_name}")


def validate_api_response(
    message,
    expected_model: str,
    min_length: int = 50,
    min_words: int = 0,
    logger: Optional[logging.Logger] = None
) -> str:
    """
    Comprehensive validation of Anthropic API response.
    Ensures response is complete, well-formed, and contains valid content.

    This function provides model-agnostic validation patterns that can be
    adapted for other AI providers (OpenAI, Google, etc.) by checking:
    - Response structure integrity
    - Completion status (not truncated)
    - Content existence and validity
    - Token usage within limits

    Args:
        message: API response message object
        expected_model: Model name that was requested
        min_length: Minimum expected text length in characters
        min_words: Minimum expected text length in words
        logger: Optional logger for warnings

    Returns:
        Validated text content

    Raises:
        ValueError: If response structure is invalid
        RuntimeError: If response indicates failure or truncation

    Example:
        ```python
        message = client.messages.create(...)
        text = validate_api_response(
            message, "claude-sonnet-4-5", logger=logger)
        ```
    """
    # 1. Validate message type and role
    if not hasattr(message, 'type'):
        raise ValueError("Response missing 'type' field")

    if message.type != "message":
        raise ValueError(f"Invalid message type: {message.type}")

    if not hasattr(message, 'role'):
        raise ValueError("Response missing 'role' field")

    if message.role != "assistant":
        raise ValueError(
            f"Invalid role: {message.role} (expected 'assistant')")

    # 2. Validate stop_reason (completion status)
    if not hasattr(message, 'stop_reason'):
        raise ValueError("Response missing 'stop_reason' field")

    stop_reason = message.stop_reason

    if stop_reason == "max_tokens":
        raise RuntimeError(
            "Response truncated at token limit - output is incomplete. "
            "Increase max_tokens or process in smaller chunks."
        )

    if stop_reason == "stop_sequence":
        # This might indicate early termination
        if logger:
            logger.warning("Generation stopped early at stop_sequence: %s",
                           getattr(message, 'stop_sequence', 'unknown'))
        # Continue but log the warning

    if stop_reason not in ["end_turn", "stop_sequence", "max_tokens", "tool_use"]:
        raise ValueError(f"Unexpected stop_reason: {stop_reason}")

    # 3. Validate content array exists and has items
    if not hasattr(message, 'content'):
        raise ValueError("Response missing 'content' field")

    if not message.content:
        raise ValueError("Response has empty content array")

    if len(message.content) == 0:
        raise ValueError("Response content array has no items")

    # 4. Validate first content block
    content_block = message.content[0]

    if not hasattr(content_block, 'type'):
        raise ValueError("Content block missing 'type' field")

    if content_block.type != "text":
        raise ValueError(
            f"Expected text content block, got type: {content_block.type}"
        )

    if not hasattr(content_block, 'text'):
        raise ValueError("Content block missing 'text' field")

    # 5. Validate text content
    text = content_block.text

    if text is None:
        raise ValueError("Content text is None")

    if not isinstance(text, str):
        raise ValueError(f"Content text is not a string: {type(text)}")

    if not text.strip():
        raise ValueError("Response contains only whitespace or empty text")

    if len(text) < min_length:
        if logger:
            logger.warning("Response suspiciously short: %d characters (expected at least %d)",
                           len(text), min_length)

    if min_words > 0:
        word_count = len(text.split())
        if word_count < min_words:
            if logger:
                logger.warning("Response suspiciously short: %d words (expected at least %d)",
                               word_count, min_words)

    # 6. Validate token usage exists
    if not hasattr(message, 'usage'):
        raise ValueError("Response missing 'usage' field")

    if not hasattr(message.usage, 'input_tokens'):
        raise ValueError("Usage missing 'input_tokens' field")

    if not hasattr(message.usage, 'output_tokens'):
        raise ValueError("Usage missing 'output_tokens' field")

    # 7. Verify model (warning only - API might use different version)
    if hasattr(message, 'model'):
        if message.model != expected_model:
            # Check for alias resolution (e.g. latest -> specific date)
            # If expected is "claude-3-5-sonnet-latest" and actual is "claude-3-5-sonnet-20241022", that's fine.
            is_alias_resolution = (
                "latest" in expected_model and
                expected_model.replace("-latest", "") in message.model
            )
            if not is_alias_resolution:
                if logger:
                    logger.warning("Model mismatch: requested '%s' but got '%s'",
                                   expected_model, message.model)

    return text


def warn_if_empty_parse(
    logger,
    label: str,
    parsed_count: int,
    *,
    source_path=None,
    source_text: str = None,
    min_chars: int = 20,
) -> bool:
    """Surface a likely format/parser mismatch (P2: never silently drop).

    A parser/validator that yields ZERO items from a NON-EMPTY source is almost
    always a format drift between producer (prompt + save) and consumer, not a
    genuinely empty result — and it otherwise masquerades as a clean "nothing to
    validate" pass. This makes that case loud while staying quiet when the
    source is truly absent/empty.

    Returns True if it emitted the mismatch warning (source had real content but
    parsed to nothing); False otherwise (genuinely empty/absent — caller may log
    a benign info instead).
    """
    if parsed_count:
        return False
    content_len = 0
    if source_text is not None:
        content_len = len(source_text.strip())
    elif source_path is not None:
        try:
            path = Path(source_path)
            if path.exists():
                content_len = len(path.read_text(encoding="utf-8").strip())
        except OSError:
            content_len = 0
    if content_len >= min_chars:
        where = f": {source_path}" if source_path is not None else ""
        logger.warning(
            "⚠️ Parsed 0 %s from a non-empty source (%d chars%s) — likely a "
            "format/parser mismatch, not an empty result.",
            label,
            content_len,
            where,
        )
        return True
    return False


def log_token_usage(script_name: str, model: str, usage_data: object, stop_reason: str):
    """
    Log token usage and estimated cost to a CSV file.

    This function is designed to never crash the pipeline - token logging
    is informational only and should not disrupt API operations.
    """
    try:
        log_file = config.LOGS_DIR / "token_usage.csv"
        # Ensure logs directory exists
        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)

        file_exists = log_file.exists()

        input_tokens = getattr(usage_data, 'input_tokens', 0)
        output_tokens = getattr(usage_data, 'output_tokens', 0)

        # Handle cache usage if present (Anthropic specific)
        cache_creation = getattr(
            usage_data, 'cache_creation_input_tokens', 0) or 0
        cache_read = getattr(usage_data, 'cache_read_input_tokens', 0) or 0

        # Calculate Cost
        pricing = model_specs.get_pricing(model)
        input_cost = (input_tokens / 1_000_000) * pricing.get("input", 0)
        output_cost = (output_tokens / 1_000_000) * pricing.get("output", 0)
        cache_write_cost = (cache_creation / 1_000_000) * \
            pricing.get("cache_write", 0)
        cache_read_cost = (cache_read / 1_000_000) * \
            pricing.get("cache_read", 0)

        total_cost = input_cost + output_cost + cache_write_cost + cache_read_cost

        cache_str = "No"
        if cache_read > 0:
            cache_str = f"Yes (Read {cache_read})"
        elif cache_creation > 0:
            cache_str = f"Yes (Created {cache_creation})"

        with open(log_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Timestamp', 'Script Name', 'Items',
                                'Status', 'Cache', 'Tokens Sent', 'Tokens Response',
                                 'Cache Creation Tokens', 'Cache Read Tokens', 'Estimated Cost ($)'])

            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                script_name,
                model,
                stop_reason,
                cache_str,
                input_tokens,
                output_tokens,
                cache_creation,
                cache_read,
                f"{total_cost:.4f}"
            ])
    except (OSError, IOError, PermissionError) as e:
        # Expected file system errors (disk full, permissions, etc.)
        # These are informational - token logging should not crash the pipeline
        print(f"⚠️  Failed to log token usage (file system error): {e}")
    except (csv.Error, UnicodeEncodeError) as e:
        # CSV formatting or encoding errors
        print(f"⚠️  Failed to log token usage (data formatting error): {e}")
    except Exception as e:
        # Unexpected errors - log with full context for debugging
        # Use logging module to capture stack trace
        logger = logging.getLogger('token_usage')
        logger.error(
            "Unexpected error logging token usage for %s: %s",
            script_name, e, exc_info=True
        )
        # Also print to console as this function may be called before logging setup
        print(f"⚠️  Failed to log token usage (unexpected error): {e}")


def _check_caching_for_large_input(messages: list, system: Any, logger: Optional[logging.Logger] = None):
    """
    Check if large inputs (system or messages) are using prompt caching.
    Warns if content exceeding ~2500 tokens (10k chars) is sent without cache_control.
    """
    # Threshold: 10,000 characters (approx 2500 tokens)
    THRESHOLD_CHARS = LARGE_INPUT_CACHE_THRESHOLD_CHARS

    def check_content(content, source_name):
        if isinstance(content, str):
            if len(content) > THRESHOLD_CHARS:
                # Used in print
                msg = f"Large {source_name} ({len(content):,} chars) sent without caching! Consider using create_system_message_with_cache."
                if logger:
                    logger.warning("⚠️ %s", msg)
                else:
                    print(f"\n⚠️ {msg}")
        elif isinstance(content, list):
            for i, block in enumerate(content):
                if isinstance(block, dict) and block.get('type') == 'text':
                    text = block.get('text', '')
                    if len(text) > THRESHOLD_CHARS and 'cache_control' not in block:
                        # Used in print
                        msg = f"Large {source_name} block {i} ({len(text):,} chars) sent without caching!"
                        if logger:
                            logger.warning("⚠️ %s", msg)
                        else:
                            print(f"\n⚠️ {msg}")

    # Check system
    if system:
        check_content(system, "system message")

    # Check messages
    for i, msg in enumerate(messages):
        check_content(msg.get('content'), f"message {i}")


def _content_text_block_with_optional_cache(text: str) -> dict[str, Any]:
    """Create Anthropic text block, adding ephemeral cache control for large text."""
    block: dict[str, Any] = {"type": "text", "text": text}
    if len(text) > LARGE_INPUT_CACHE_THRESHOLD_CHARS:
        block["cache_control"] = {"type": "ephemeral"}
    return block


def _normalize_content_for_caching(content: Any) -> Any:
    """
    Normalize content into Anthropic block format and auto-cache large text blocks.
    Leaves non-text/tool content untouched.
    """
    if isinstance(content, str):
        return [_content_text_block_with_optional_cache(content)]

    if isinstance(content, list):
        normalized = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                updated = dict(block)
                if len(text) > LARGE_INPUT_CACHE_THRESHOLD_CHARS and "cache_control" not in updated:
                    updated["cache_control"] = {"type": "ephemeral"}
                normalized.append(updated)
            else:
                normalized.append(deepcopy(block))
        return normalized

    return content


def _normalize_messages_and_system_for_caching(
    messages: list, system: Any
) -> tuple[list, Any]:
    """Apply caching-aware normalization to messages and system payloads."""
    normalized_messages = []
    for message in messages:
        message_copy = dict(message)
        message_copy["content"] = _normalize_content_for_caching(
            message.get("content", "")
        )
        normalized_messages.append(message_copy)

    normalized_system = _normalize_content_for_caching(system) if system else system
    return normalized_messages, normalized_system


def cap_max_tokens_for_model(
    model: str,
    requested_max_tokens: int,
    logger: Optional[logging.Logger] = None,
) -> int:
    """
    Cap max output tokens to model-safe limits.

    Currently enforces Anthropic Haiku output cap (8192). Other models pass through.
    """
    model_lower = model.lower()

    # Use explicit model output limits where known; otherwise default to configured limit.
    # Then honor the lower of requested max and allowed max.
    known_model_output_limits = config.MODEL_OUTPUT_TOKEN_LIMITS
    model_limit = known_model_output_limits.get(model_lower)
    allowed_max_tokens = (
        config.MAX_TOKENS_SUMMARY
        if model_limit is None
        else min(model_limit, config.MAX_TOKENS_SUMMARY)
    )
    capped_max_tokens = min(requested_max_tokens, allowed_max_tokens)

    if capped_max_tokens != requested_max_tokens and logger:
        logger.warning(
            "Capping max_tokens from %d to %d for model %s",
            requested_max_tokens,
            capped_max_tokens,
            model,
        )

    return capped_max_tokens


def call_claude_with_retry(
    client,
    model: str,
    messages: list,
    max_tokens: int,
    temperature: float = config.TEMP_BALANCED,
    max_retries: int = 3,
    logger: Optional[logging.Logger] = None,
    min_length: int = 50,
    min_words: int = 0,
    stream: bool = False,
    **kwargs
):
    """
    Call Claude API with retry logic and comprehensive validation.

    Args:
        client: Anthropic client
        model: Model name
        messages: Message list
        max_tokens: Maximum tokens
        temperature: Temperature setting
        max_retries: Maximum retry attempts
        logger: Optional logger
        min_length: Minimum expected length of response text
        min_words: Minimum expected length of response in words
        stream: Whether to stream the response (recommended for long outputs)

    Returns:
        API response message

    Raises:
        ValueError: If API key is invalid or request is malformed
        RuntimeError: If output is truncated or connection fails
        APIError: If API call fails after retries
    """
    # Track timeout across retries
    current_timeout = kwargs.get('timeout')

    # Handle suppression of caching warnings
    suppress_caching_warnings = kwargs.pop('suppress_caching_warnings', False)

    normalized_messages, normalized_system = _normalize_messages_and_system_for_caching(
        messages, kwargs.get('system')
    )
    if normalized_system is not None:
        kwargs['system'] = normalized_system

    # Check for missing cache on large inputs
    if not suppress_caching_warnings:
        _check_caching_for_large_input(normalized_messages, kwargs.get('system'), logger)

    for attempt in range(max_retries):
        try:
            call_kwargs = kwargs.copy()

            # Apply dynamic timeout if set
            if current_timeout is not None:
                call_kwargs['timeout'] = current_timeout

            # Handle streaming argument
            # Check if 'stream' was also in kwargs (legacy support)
            is_streaming = stream or call_kwargs.pop('stream', False)

            if is_streaming:
                with client.messages.stream(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=normalized_messages,
                    extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
                    **call_kwargs
                ) as stream_manager:
                    message = stream_manager.get_final_message()
            else:
                message = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=normalized_messages,
                    extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
                    **call_kwargs
                )

            # Comprehensive response validation
            try:
                validate_api_response(
                    message,
                    expected_model=model,
                    min_length=min_length,
                    min_words=min_words,
                    logger=logger
                )
                # Enforce minimum length with retry
                text_content = message.content[0].text
                if len(text_content) < min_length:
                    raise ValueError(
                        f"Response text too short: {len(text_content)} chars (expected >= {min_length})")

                if min_words > 0:
                    if len(text_content.split()) < min_words:
                        raise ValueError(
                            f"Response text too short: {len(text_content.split())} words (expected >= {min_words})")
            except (ValueError, RuntimeError) as e:
                # Validation failed
                if logger:
                    logger.error("Response validation failed: %s", e)
                # If we have retries left, continue to next attempt
                if attempt < max_retries - 1:
                    if logger:
                        logger.warning("Retrying due to validation failure (%d/%d)...",
                                       attempt + 1, max_retries)
                    continue
                raise

            # Warn if close to limit
            if message.usage.output_tokens > max_tokens * config.TOKEN_USAGE_WARNING_THRESHOLD:
                warning = f"⚠️  Nearly hit token limit: {message.usage.output_tokens}/{max_tokens} tokens used"
                if logger:
                    logger.warning(warning)
                print(f"\n{warning}")

            # Log successful usage
            if logger:
                # Estimate breakdown
                system_content = kwargs.get('system', [])
                if isinstance(system_content, list):
                    sys_text = "".join(
                        [b.get('text', '') for b in system_content if b.get('type') == 'text'])
                else:
                    sys_text = str(system_content) if system_content else ""

                msg_text = "".join([m.get('content', '') if isinstance(m.get('content'), str) else
                                   "".join([b.get('text', '') for b in m.get(
                                       'content', []) if b.get('type') == 'text'])
                                    for m in normalized_messages])

                est_sys_tokens = len(sys_text) // config.CHARS_PER_TOKEN
                est_msg_tokens = len(msg_text) // config.CHARS_PER_TOKEN

                # Get cache stats
                cache_read = getattr(
                    message.usage, 'cache_read_input_tokens', 0) or 0
                cache_create = getattr(
                    message.usage, 'cache_creation_input_tokens', 0) or 0

                cache_msg = ""
                if cache_read > 0:
                    cache_msg = f" (+{cache_read} cached)"
                elif cache_create > 0:
                    cache_msg = f" (created {cache_create} cache)"

                logger.info("API call successful - Input: %d%s (~%d context, ~%d prompt), Output: %d, Stop: %s",
                            message.usage.input_tokens, cache_msg, est_sys_tokens, est_msg_tokens,
                            message.usage.output_tokens, message.stop_reason)

            # Log to CSV
            script_name = getattr(
                logger, 'name', 'unknown_script') if logger else "unknown_script"
            log_token_usage(script_name, model, message.usage,
                            message.stop_reason)

            return message

        except AuthenticationError as e:
            # Don't retry - API key is invalid
            if logger:
                logger.error("Authentication failed - invalid API key")
            raise ValueError(
                "ANTHROPIC_API_KEY is invalid or expired. "
                "Get a new key from https://console.anthropic.com/"
            ) from e

        except NotFoundError as e:
            # Don't retry - model not found
            if logger:
                logger.error("Model not found: %s", e)
            raise ValueError(
                f"The model '{model}' is not available (404). "
                "Please check config.py or your API key permissions."
            ) from e

        except BadRequestError as e:
            # Don't retry - request is malformed
            if logger:
                logger.error("Bad request: %s", e)
            if "credit balance is too low" in str(e):
                raise ValueError(
                    "Anthropic API credit balance is too low. "
                    "Please go to Plans & Billing to upgrade or purchase credits."
                ) from e
            raise ValueError(
                f"API request was malformed: {e}\n"
                "Check that model name, max_tokens, and message format are valid."
            ) from e

        except APITimeoutError as e:
            if attempt < max_retries - 1:
                # Increase timeout by 50%
                if current_timeout is not None:
                    current_timeout = float(current_timeout) * 1.5
                else:
                    # Default fallback if no timeout specified but timed out
                    current_timeout = 900.0

                # Used in print
                msg = f"Request timed out. Increasing timeout to {current_timeout:.0f}s and retrying ({attempt + 2}/{max_retries})..."
                if logger:
                    logger.warning("Request timed out. Increasing timeout to %.0fs and retrying (%d/%d)...",
                                   current_timeout, attempt + 2, max_retries)
                print(f"\n⚠️  {msg}")
                continue

            if logger:
                logger.error("Request timed out: %s", e)
            raise RuntimeError(
                "API request timed out. "
                "The transcript may be too long. Try processing in smaller chunks."
            ) from e

        except APIConnectionError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                # Used in print
                msg = f"Connection error, retrying in {wait_time}s... ({attempt + 2}/{max_retries})"
                if logger:
                    logger.warning("Connection error, retrying in %ds... (%d/%d)",
                                   wait_time, attempt + 2, max_retries)
                print(f"\n⚠️  {msg}")
                time.sleep(wait_time)
            else:
                if logger:
                    logger.error("Connection failed after retries")
                raise RuntimeError(
                    "Could not connect to Anthropic API. "
                    "Check your internet connection."
                ) from e

        except RateLimitError:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                # Used in print
                msg = f"Rate limit hit, waiting {wait_time}s before retry {attempt + 2}/{max_retries}..."
                if logger:
                    logger.warning("Rate limit hit, waiting %ds before retry %d/%d...",
                                   wait_time, attempt + 2, max_retries)
                print(f"\n⚠️  {msg}")
                time.sleep(wait_time)
            else:
                if logger:
                    logger.error(
                        "Rate limit exceeded after %d retries", max_retries)
                raise

        except APIError as e:
            error_text = str(e).lower()
            body = getattr(e, "body", None)
            body_error_type = ""
            if isinstance(body, dict):
                body_error = body.get("error", {})
                if isinstance(body_error, dict):
                    body_error_type = str(body_error.get("type", "")).lower()

            is_overloaded = (
                "overloaded" in error_text
                or body_error_type == "overloaded_error"
            )

            if is_overloaded and attempt < max_retries - 1:
                wait_time = 2 ** attempt
                if logger:
                    logger.warning(
                        "API overloaded, retrying in %ds... (%d/%d)",
                        wait_time,
                        attempt + 2,
                        max_retries,
                    )
                print(
                    f"\n⚠️  API overloaded, retrying in {wait_time}s... ({attempt + 2}/{max_retries})"
                )
                time.sleep(wait_time)
                continue

            if logger:
                logger.error("API error: %s", e)

            if is_overloaded:
                raise RuntimeError(
                    "Anthropic API is currently overloaded after retries. "
                    "Please retry in a few minutes."
                ) from e

            raise


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent path traversal attacks and ensure safety.

    Removes:
    - Path separators (/, \\)
    - Parent directory references (..)
    - Null bytes
    - Control characters
    - Leading/trailing whitespace and dots

    Args:
        filename: The filename to sanitize

    Returns:
        Sanitized filename safe for use in file operations

    Raises:
        ValueError: If filename is empty or becomes empty after sanitization
    """
    if not filename or not isinstance(filename, str):
        raise ValueError(f"Filename must be a non-empty string, got: {type(filename).__name__}")

    # Get just the filename component (remove any path)
    filename = Path(filename).name

    # Remove null bytes (can cause security issues)
    filename = filename.replace('\0', '')

    # Remove or replace dangerous characters
    # Keep: letters, numbers, spaces, hyphens, underscores, periods
    # Remove: path separators, control characters, etc.
    safe_chars = []
    for char in filename:
        if char in ('/', '\\'):
            # Path separators - skip completely
            continue
        elif char == '\0':
            # Null byte - skip
            continue
        elif ord(char) < 32:
            # Control characters - skip
            continue
        else:
            safe_chars.append(char)

    filename = ''.join(safe_chars)

    # Remove any parent directory references
    filename = filename.replace('..', '')

    # Strip leading/trailing whitespace and dots
    filename = filename.strip().strip('.')

    # Validate result
    if not filename:
        raise ValueError("Filename is empty after sanitization")

    if len(filename) > 255:
        raise ValueError(f"Filename too long: {len(filename)} characters (max 255)")

    # Additional security check: ensure no path separators remain
    if '/' in filename or '\\' in filename:
        raise ValueError(f"Filename contains path separators after sanitization: {filename}")

    return filename


def clean_project_name(filename_or_stem: str) -> str:
    """
    Get the clean project/base name from a filename or stem.
    Strips extensions and version suffixes like '_validated' or '_v1'.

    Args:
        filename_or_stem: The input filename or stem (e.g., "MyVideo_validated.txt", "MyVideo_v2")

    Returns:
        The clean base name (e.g., "MyVideo")
    """
    # Remove extension if present
    stem = Path(filename_or_stem).stem

    # Strip suffixes using regex
    # Matches _validated or _v<numbers> at the end of the string
    # We loop to handle cases like "Name_v1_validated" (though rare)
    while True:
        match = re.search(r'(_validated|_v\d+)$', stem)
        if match:
            stem = stem[:match.start()]
        else:
            break

    return stem


def parse_filename_metadata(filename: str) -> dict:
    """
    Extract metadata from filename pattern: 'Title - Presenter - Date.ext'

    This function sanitizes the filename to prevent path traversal attacks
    before processing.

    Args:
        filename: The filename to parse (e.g., "Talk - Speaker - 2024-01-01.md")

    Returns:
        Dictionary with title, presenter, author, date, year, and stem.

    Raises:
        ValueError: If filename doesn't match expected pattern or is unsafe

    Security:
        - Sanitizes filename to prevent directory traversal
        - Validates all components are non-empty
        - Ensures date contains a valid year
    """
    # SECURITY: Sanitize filename first to prevent path traversal
    safe_filename = sanitize_filename(filename)

    # Use sanitized filename for all operations
    stem = Path(safe_filename).stem

    # Strip known suffixes to get the base stem
    # We iterate through known suffix constants that start with " - "
    # Note: iterating explicitly might be safer than relying on arbitrary order if suffixes overlap
    suffixes_to_strip = [
        config.SUFFIX_FORMATTED.replace('.md', ''),
        '_yaml',  # special case intermediate
        config.SUFFIX_YAML.replace('.md', ''),
        config.SUFFIX_WEBPAGE_SIMPLE.replace('.html', '')
    ]

    for suffix in suffixes_to_strip:
        if stem.endswith(suffix):
            stem = stem[:-len(suffix)]
            break  # Assume only one suffix type applies

    # Allow common copy suffixes (e.g., " - copy", " - copy 2")
    stem = re.sub(r'\s+-\s+copy(?:\s+\d+)?$', '', stem, flags=re.IGNORECASE)

    parts = [p.strip() for p in stem.split(' - ')]

    if len(parts) < 3:
        raise ValueError(
            f"Filename must follow pattern 'Title - Presenter - Date.ext', got: {safe_filename}")

    # Handle case where title or presenter contains ' - '
    if len(parts) > 3:
        date = parts[-1]
        presenter = parts[-2]
        title = ' - '.join(parts[:-2])
    else:
        title, presenter, date = parts

    # Validate that components are non-empty
    if not title or not title.strip():
        raise ValueError(f"Title cannot be empty in filename: {safe_filename}")
    if not presenter or not presenter.strip():
        raise ValueError(f"Presenter cannot be empty in filename: {safe_filename}")
    if not date or not date.strip():
        raise ValueError(f"Date cannot be empty in filename: {safe_filename}")

    # Validate date contains a year
    year_match = re.search(r'(\d{4})', date)
    if not year_match:
        raise ValueError(f"Date must contain a 4-digit year, got: {date}")
    year = year_match.group(1)

    return {
        "title": title,
        "presenter": presenter,
        "author": presenter,  # for backward compatibility
        "date": date,
        "year": year,
        "filename": safe_filename,  # Return sanitized filename
        "stem": stem
    }


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def estimate_token_count(text: str) -> int:
    """
    Rough estimate of token count.
    Claude uses ~4 characters per token on average.

    Args:
        text: Text to estimate

    Returns:
        Estimated token count
    """
    return len(text) // config.CHARS_PER_TOKEN


def check_token_budget(text: str, max_tokens: int, logger: Optional[logging.Logger] = None) -> bool:
    """
    Check if text will likely fit within token budget.

    Args:
        text: Input text
        max_tokens: Maximum allowed tokens
        logger: Optional logger

    Returns:
        True if likely to fit, False otherwise
    """
    estimated = estimate_token_count(text)

    # Leave 20% margin for safety
    safe_limit = max_tokens * config.TOKEN_BUDGET_SAFETY_MARGIN

    if estimated > safe_limit:
        warning = (
            f"⚠️  Input may exceed context budget:\n"
            f"   Estimated tokens: {estimated:,}\n"
            f"   Safe input budget: {int(safe_limit):,} ({config.TOKEN_BUDGET_SAFETY_MARGIN:.0%} of {max_tokens:,})\n"
            f"   Consider processing in smaller chunks."
        )
        if logger:
            logger.warning(warning)
        print(f"\n{warning}")
        return False

    return True


# ============================================================================
# CENTRALIZED MARKDOWN EXTRACTION PATTERNS
# ============================================================================
# These patterns handle variations in markdown formatting (with/without bold)
# to avoid hardcoding patterns across multiple files.


def extract_section(content: str, section_name: str, allow_bold: bool = True) -> str:
    """
    Extract a markdown section by name, correctly handling nested subsections.
    Stops extracting only when a header of the same or higher level (fewer hashes) is found.

    Args:
        content: The markdown content to search
        section_name: The section name (e.g., "Topics", "Abstract", "Interpretive Themes")
        allow_bold: If True, matches bold/numbered variations (implicitly handled by regex)

    Returns:
        The section content (stripped), or empty string if not found
    """
    escaped_name = re.escape(section_name).replace(r'\ ', r'\s+')

    # 1. Find the start of the section
    # Matches: start of line, optional hash, optional bold/markup, optional number, name, anything, end of line
    # Capture group 1: The hashes (if any)
    start_pattern = re.compile(
        rf'^(#*)\s*(?:[\*\_]+)?(?:\d+\.?\s*)?{escaped_name}\b.*?$',
        re.MULTILINE | re.IGNORECASE
    )

    match = start_pattern.search(content)
    if not match:
        return ''

    start_hashes = match.group(1)
    # Default to level 2 if no hashes (e.g. **Topics**) so we stop at ## or #
    start_level = len(start_hashes) if start_hashes else 2
    start_pos = match.end()

    # 2. Find the end of the section
    # Iterate through all subsequent headers to find one that closes this section
    header_pattern = re.compile(r'^(#+)\s', re.MULTILINE)

    for next_header in header_pattern.finditer(content, start_pos):
        next_hashes = next_header.group(1)
        next_level = len(next_hashes)

        # If next header is same level or higher (fewer hashes), stop here
        # e.g. if we are in ## (level 2), we stop at ## (2) or # (1).
        # We do NOT stop at ### (3).
        if next_level <= start_level:
            return content[start_pos:next_header.start()].strip()

    # If no matching end header found, return everything to the end
    return content[start_pos:].strip()


def extract_bowen_references(content: str) -> list:
    """
    Extract Bowen reference quotes from extracts-summary content.
    Handles variations in section header formatting.

    Returns:
        List of tuples: [(concept, quote), ...]
    """
    # First, try to extract the main "Bowen References" section
    outer_section_content = extract_section(content, "Bowen References")

    # If the outer section is not found or is empty, try to directly extract
    # "Bowen References Extracted from Transcript" from the main content
    if not outer_section_content:
        target_content = extract_section(
            content, "Bowen References Extracted from Transcript")
    else:
        # If outer section exists, search within it for the more specific header
        target_content = extract_section(
            outer_section_content, "Bowen References Extracted from Transcript")
        # Fallback if specific header not found within outer, use outer content itself
        if not target_content:
            target_content = outer_section_content

    if not target_content:
        return []

    # Relaxed pattern using MULTILINE mode
    # Handles:
    # - **Label:** "Quote" (colon inside bold)
    # - **Label**: "Quote" (colon outside bold)
    # - Label: "Quote" (no bold)
    quote_pattern = r'^\s*(?:[-*>]+\s+)?(?:\*\*)?([^*\n]+?)(?:\*\*)?:?\s*["“](.+?)["”]'  # noqa
    quotes = re.findall(quote_pattern, target_content, flags=re.MULTILINE)

    return [(concept.strip().rstrip(':'), quote.strip()) for concept, quote in quotes]


# ---------------------------------------------------------------------------
# Theme-artifact parsing (shared by abstract_pipeline + summary_pipeline)
#
# The extraction stage writes structural/interpretive themes as bold-numbered
# blocks — the real on-disk format:
#
#     ### Structural Themes (3 total)          <- scaffolding header, not a theme
#     **1. Theme Title**
#     **Description:** ...
#     **Key evidence:** ...
#     ### Summary Paragraph                    <- scaffolding header, not a theme
#
# Both theme consumers must read THIS format first; the `###`/`##` headers are
# scaffolding, never themes. Keeping the parse in one place stops the two
# consumers from drifting apart (P19). See TODO.md A1/A2/A3.
# ---------------------------------------------------------------------------

def is_scaffolding_theme_name(name: str) -> bool:
    """True when `name` is section scaffolding (a header/roll-up), not a theme.

    Three discriminators, deliberately narrow to avoid dropping a real theme
    (a false-positive here silently loses one theme without tripping the
    zero-from-non-empty guard — P2). Covers the real scaffolding seen in the
    artifacts (``### Structural Themes (3 total)``, ``### Summary Paragraph``,
    ``## Interpretive / Process Themes (7 total)``, the ``# ...`` title lines):
      1. empty,
      2. markdown-heading-prefixed (``#...``) — catches every ``#``/``##`` title,
      3. a ``config.THEME_SCAFFOLDING_LABELS`` word (summary/conclusion/...),
      4. a ``... (N total)`` roll-up header.
    """
    normalized = name.strip().lower()
    if not normalized:
        return True
    if normalized.startswith("#"):
        return True
    if normalized in config.THEME_SCAFFOLDING_LABELS:
        return True
    # Roll-up scaffolding header: "... (N total)"
    if re.search(r"\(\s*\d+\s+total\s*\)\s*$", normalized):
        return True
    return False


def _extract_theme_description(block: str) -> str:
    """Pull the ``**Description:**`` field from a theme block; if absent, strip
    ``**Field:**`` labels and horizontal rules and return the residual prose."""
    desc_match = re.search(
        r"\*\*Description:\*\*\s*(.+?)(?=(?:\n\*\*[A-Z][^:\n]+:\*\*)|\Z)",
        block,
        re.DOTALL,
    )
    if desc_match:
        return " ".join(
            ln.strip() for ln in desc_match.group(1).split("\n") if ln.strip()
        ).strip()
    stripped = re.sub(r"\*\*[^*\n]+:\*\*\s*", "", block)
    return " ".join(
        ln.strip()
        for ln in stripped.split("\n")
        if ln.strip() and ln.strip() != "---"
    ).strip()


# Body-end lookahead for a `**N. Title**` theme block: the next bold-numbered
# theme, ANY markdown heading (H1–H6 — the trailing `### Summary Paragraph`
# scaffold and any future level), or end-of-text.
_BOLD_THEME_RE = (
    r"(?:^|\n)\*\*(\d+)\.\s+(.+?)\*\*\s*\n(.*?)"
    r"(?=(?:\n\*\*\d+\.\s+.+?\*\*\s*\n)|(?:\n#{1,6}\s+)|\Z)"
)
# Legacy real format (e.g. 2025-02-prompt runs): `### N. Title` H3+ headings. A
# block ends at the next H3+ numbered theme, a SHALLOWER `#`/`##` section header
# (not a deeper one, which is in-block scaffolding), or end-of-text. The `**Field:**`
# metadata lines are NOT headings, so they stay inside the block.
_H3_THEME_RE = (
    r"(?:^|\n)#{3,6}\s+(\d+)\.\s+(.+?)\n(.*?)"
    r"(?=(?:\n#{3,6}\s+\d+\.\s+)|(?:\n#{1,2}\s+)|\Z)"
)


def parse_bold_numbered_theme_blocks(text: str) -> list:
    """Parse the real theme formats into ``(name, description)`` tuples in document
    order. Handles BOTH producer formats seen in real runs: ``**N. Title**``
    (current) and the legacy ``### N. Title`` (H3-numbered) blocks — each followed
    by a ``**Description:**`` field. The bold format is tried first; the H3 format
    is a fallback only when it finds nothing (a file uses one format consistently),
    so a bold-format file can't be mis-parsed by the fallback.

    Returns ``[]`` when the text has neither format, so callers can fall back to
    other legacy shapes; an empty result from *non-empty* input is contract drift
    the caller should surface loudly (P19). Migrating both formats is required by
    AC M3.D.1 (a real 2010-interview structural-themes file used ``### N.``)."""
    themes = _theme_blocks(text, _BOLD_THEME_RE)
    if not themes:
        themes = _theme_blocks(text, _H3_THEME_RE)
    return themes


def _theme_blocks(text: str, pattern: str) -> list:
    themes = []
    for match in re.finditer(pattern, text, re.DOTALL):
        name = match.group(2).strip()
        block = match.group(3).strip()
        if is_scaffolding_theme_name(name) or not block:
            continue
        description = _extract_theme_description(block)
        if description:
            themes.append((name, description))
    return themes


def count_header_verdicts(report_text: str) -> dict:
    """Count PASS/WARN/FAIL verdicts in a header-validation report.

    Tolerant of the model's real format drift — plain ``STATUS: FAIL``,
    markdown-bold ``**STATUS:** FAIL``, and ``##``-prefixed section headers — so a
    real FAIL can't hide behind a formatting variation (A5/P19). The prompt's own
    ``STATUS: [PASS / WARN / FAIL]`` scaffold line is NOT counted (the verdict must
    be a bare PASS/WARN/FAIL token, not a bracketed list).

    Returns ``{"PASS": n, "WARN": n, "FAIL": n, "total": n}``. A ``total`` of 0 from
    a non-empty report is contract drift the caller should surface, not treat as a
    clean pass.
    """
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
    pattern = r"(?im)^\s*#{0,6}\s*\*{0,2}\s*STATUS\s*\*{0,2}\s*:\s*\*{0,2}\s*(PASS|WARN|FAIL)\b"
    for match in re.finditer(pattern, report_text or ""):
        counts[match.group(1).upper()] += 1
    counts["total"] = counts["PASS"] + counts["WARN"] + counts["FAIL"]
    return counts


def load_bowen_references(base_name: str) -> list:
    """
    Load Bowen reference quotes from canonical dedicated file.

    Args:
        base_name: The base name of the transcript

    Returns:
        List of tuples: [(concept, quote), ...]
    """
    # Try dedicated file first
    bowen_file = config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_BOWEN}"
    if bowen_file.exists():
        content = bowen_file.read_text(encoding='utf-8')
        deduped = parse_bowen_references_text(content)
        if deduped:
            return deduped

    return []


def parse_bowen_references_text(content: str) -> list:
    """Parse the Bowen-references markdown into ``[(concept, quote, timestamp)]``.

    The single canonical text-level parser for the bowen boundary — the file
    loader (``load_bowen_references``) and the M3 schema codec both delegate here
    so there is exactly ONE implementation of the format contract (P19).
    """
    content = strip_yaml_frontmatter(content)

    # ONE pattern with an OPTIONAL timestamp, so a file that MIXES timestamped
    # and non-timestamped references parses every entry. (The previous
    # strict-then-lenient loop tried the with-timestamp pattern first and
    # broke as soon as it matched anything, silently dropping every
    # timestamp-less reference in a mixed file.)
    pattern = re.compile(
        r'###\s+([^\n\[]+?)(?:\s+\[(\d{2}:\d{2}:\d{2})\])?\s*\n>\s+"([^"]+)"'
    )
    refs = [
        (concept.strip(), quote.strip(), timestamp or None)
        for concept, timestamp, quote in pattern.findall(content)
    ]

    # Dedupe by normalized quote text: the model sometimes emits the SAME
    # quote under two different concept headers, which inflates any
    # "N references" count and double-highlights the same span. Keep the
    # first occurrence and MERGE the later concept label(s) into it (the
    # highlighter shows a "; "-joined label), so no concept association is
    # lost — then surface the merge (P2) rather than silently collapsing.
    seen: dict[str, int] = {}
    deduped: list[tuple] = []
    merged = []
    for concept, quote, timestamp in refs:
        key = normalize_text(quote, aggressive=True)
        if key in seen:
            idx = seen[key]
            c0, q0, t0 = deduped[idx]
            labels = [x.strip() for x in c0.split(";") if x.strip()]
            if concept and concept not in labels:
                deduped[idx] = ("; ".join(labels + [concept]), q0, t0)
            merged.append(concept)
            continue
        seen[key] = len(deduped)
        deduped.append((concept, quote, timestamp))
    if merged:
        logging.getLogger('bowen_references').warning(
            "Merged %d duplicate Bowen reference(s) sharing a quote already "
            "listed under another concept: %s",
            len(merged), "; ".join(merged),
        )
    return deduped


def extract_emphasis_items(content: str) -> list:
    """
    Extract emphasized item quotes from extracts-summary content.
    Handles variations in section header formatting.

    Returns:
        List of tuples: [(item_name, quote), ...]
    """
    section_content = extract_section(content, "Emphasized Items")
    if not section_content:
        return []

    # Relaxed pattern using MULTILINE mode
    quote_pattern = r'^\s*(?:[-*>]+\s+)?(?:\*\*)?([^*\n]+?)(?:\*\*)?:?\s*["“](.+?)["”]'  # noqa
    quotes = re.findall(quote_pattern, section_content, flags=re.MULTILINE)

    return [(item.strip().rstrip(':'), quote.strip()) for item, quote in quotes]


def load_emphasis_items(base_name: str) -> list:
    """
    Load emphasis item quotes from canonical dedicated files.

    Args:
        base_name: The base name of the transcript

    Returns:
        List of tuples: [(item_name, quote), ...]
    """
    # Load Bowen references first to check for duplicates
    bowen_refs = load_bowen_references(base_name)
    bowen_quotes = {normalize_text(item[1], aggressive=True) for item in bowen_refs}

    # Try new scored emphasis file first
    scored_file = config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_EMPHASIS_SCORED}"
    if scored_file.exists():
        content = scored_file.read_text(encoding='utf-8')
        items = parse_scored_emphasis_output(content)
        filtered_items = [
            (f"{item['concept']} ({item['score']}%)", item['quote'], item.get('timestamp'))
            for item in items
            if normalize_text(item['quote'], aggressive=True) not in bowen_quotes
        ]
        if filtered_items:
            return filtered_items

    # Fallback to older, unscored emphasis file with flexible parsing
    emphasis_file = config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_EMPHASIS}"
    if emphasis_file.exists():
        content = emphasis_file.read_text(encoding='utf-8')
        content = strip_yaml_frontmatter(content)
        
        patterns = [
            re.compile(r'>\s+\*\*(.+?)\*\*\s*\n>\s+"([^"]+)"', re.DOTALL),  # Original: > **Label** \n > "Quote"
            re.compile(r'>\s+\*\*(.+?)\*\*\s*\n>\s*([^\n]+)', re.DOTALL),   # > **Label** \n > Quote
            re.compile(r'\*\*(.+?)\*\*:\s*"([^"]+)"', re.DOTALL),        # **Label**: "Quote"
            re.compile(r'^\s*[-*]\s+\*\*(.+?)\*\*:\s*(.+)', re.MULTILINE), # - **Label**: Quote
        ]
        
        all_matches = []
        for pattern in patterns:
            all_matches = pattern.findall(content)
            if all_matches:
                break
        
        items = [(label.strip(), quote.strip(), None) for label, quote in all_matches] # Add None for timestamp
        
        filtered_items = [
            (label, quote, timestamp)
            for label, quote, timestamp in items
            if normalize_text(quote, aggressive=True) not in bowen_quotes
        ]
        return filtered_items

    return []


def strip_yaml_frontmatter(content: str) -> str:
    """
    Remove YAML frontmatter from markdown content.

    Args:
        content: Markdown content that may start with YAML frontmatter

    Returns:
        Content with YAML frontmatter removed
    """
    # Use regex to match YAML block at start, handling potential whitespace/newlines
    # Matches --- at start, any content (non-greedy), then --- followed by newline
    match = re.match(r'^\s*---\s*\n.*?\n---\s*\n', content, re.DOTALL)
    if match:
        return content[match.end():]
    return content


def parse_scored_emphasis_output(text: str) -> list[dict]:
    """
    Parse the output from the emphasis scoring prompt.
    Expected Format:
    [Type - Category - Rank: XX%] Concept: Descriptor
    "Quote"
    (Location)
    """
    def _parse_score(score_str: str) -> int:
        nums = [int(n) for n in re.findall(r'\d+', score_str or '')]
        return int(sum(nums) / len(nums)) if nums else 0

    def _clean_field(value: str) -> str:
        return re.sub(r'\s+', ' ', (value or '').replace('*', '').strip())

    items = []
    seen = set()

    header_patterns = [
        re.compile(
            r'^\s*(?:[-*>]+\s+)?(?:\*\*)?\[(?P<type>[^-\]]+?)\s*-\s*(?P<category>.+?)\s*-\s*'
            r'(?:(?:Rank|rank)\s*:\s*)?(?P<score>[^\]%\n]+)%?\s*(\|\s*(?P<timestamp>\d{2}:\d{2}:\d{2}))?\](?:\*\*)?\s*(?:\|\s*)?'
            r'(?:Concept|concept)\s*:\s*(?P<concept>.+?)\s*$',
            re.MULTILINE,
        ),
        re.compile(
            r'^\s*(?:[-*>]+\s+)?(?:\*\*)?(?P<type>Explicit|Implicit|Clinical)\s*-\s*(?P<category>.+?)\s*-\s*'
            r'(?:(?:Rank|rank)\s*:\s*)?(?P<score>[^|\n%]+)%?\s*(\|\s*(?P<timestamp>\d{2}:\d{2}:\d{2}))?\s*(?:\|\s*)?'
            r'(?:Concept|concept)\s*:\s*(?P<concept>.+?)\s*$',
            re.MULTILINE,
        ),
    ]

    quote_re = re.compile(r'["“](?P<quote>[\s\S]+?)["”]')

    def _find_header(block):
        if 'concept' not in block.lower():
            return None
        for pattern in header_patterns:
            m = pattern.search(block)
            if m:
                return m
        return None

    def _add_item(header_match, quote_match):
        item = {
            'type': _clean_field(header_match.group('type')),
            'category': _clean_field(header_match.group('category')),
            'score': _parse_score(header_match.group('score')),
            'concept': _clean_field(header_match.group('concept')),
            'quote': re.sub(r'\s+', ' ', quote_match.group('quote').strip()),
            'timestamp': header_match.group('timestamp') or None,
        }
        item_key = (item['concept'].lower(), item['quote'].lower())
        if item_key in seen:
            return
        seen.add(item_key)
        items.append(item)

    # An item's header and its quote may render either in one block or split
    # across a blank line into adjacent blocks (the saved file uses the latter).
    # Carry a pending header so both layouts parse — fixes the write->read
    # round-trip and tolerates model output that blank-lines between them.
    pending_header = None
    for block in re.split(r'\n\s*\n+', text):
        block = block.strip()
        if not block:
            continue
        header_match = _find_header(block)
        quote_match = quote_re.search(block)
        if header_match and quote_match:
            _add_item(header_match, quote_match)
            pending_header = None
        elif header_match:
            pending_header = header_match
        elif quote_match and pending_header is not None:
            _add_item(pending_header, quote_match)
            pending_header = None

    return items


def get_emphasis_expected_range(category: str) -> tuple[int, int]:
    """Return expected ranking range for an emphasis category."""
    # Extract the code (e.g. A1, B2) if the category string is verbose
    # e.g. "A14 Source Commentary" -> "A14"
    match = re.match(r'([A-C]\d+)', category.strip())
    category_code = match.group(1) if match else category

    # Based on emphasis_dedection_v3_production.md
    ranges = {
        'A1': (95, 100), 'A2': (90, 95), 'A3': (85, 90), 'A4': (95, 100),
        'A5': (90, 95), 'A6': (85, 90), 'A7': (85, 92), 'A8': (90, 98),
        'A9': (90, 100), 'A10': (85, 95), 'A11': (88, 95), 'A12': (87, 93),
        'A13': (85, 94), 'A14': (87, 96), 'A15': (88, 94), 'A16': (85, 92),
        'A17': (90, 96), 'A18': (92, 98), 'A19': (90, 96), 'A20': (87, 93),
        'A21': (92, 98),
        'B1': (90, 100), 'B2': (85, 100), 'B3': (85, 100), 'B4': (85, 100),
        'B5': (85, 100), 'B6': (85, 100), 'B7': (85, 100), 'B8': (85, 100),
        'B9': (88, 95), 'B10': (90, 95), 'B11': (88, 94), 'B12': (87, 93),
        'B13': (87, 93), 'B14': (85, 90), 'B15': (88, 94), 'B16': (88, 94),
        'C1': (90, 98), 'C2': (88, 95), 'C3': (90, 95), 'C4': (87, 93),
        'C5': (88, 94), 'C6': (92, 98),
    }
    # Default range if category is unknown
    return ranges.get(category_code, (85, 100))


def validate_emphasis_item(item: dict) -> tuple[bool, list[str]]:
    """
    Validate a single scored emphasis item based on quality standards.
    Inspired by the VALIDATION HELPER example.

    Returns: (is_valid, list_of_issues)
    """
    issues = []

    # 1. Check word count
    word_count = len(item.get('quote', '').split())
    if word_count > 200:
        issues.append(f"Quote too long: {word_count} words (max 200)")
    if word_count < 5:
        issues.append(f"Quote too short: {word_count} words (min 5)")

    # 2. Check for vague pronouns at the start
    vague_pronouns = ['that', 'this', 'these', 'those', 'it']
    first_word = item.get('quote', '').split()[0].lower().strip(
        ".,") if item.get('quote', '') else ''
    if first_word in vague_pronouns:
        issues.append(f"Starts with vague pronoun: '{first_word}'")

    # 3. Check if ranking is in expected range for its category
    category = item.get('category')
    score = item.get('score')
    if category and score is not None:
        min_rank, max_rank = get_emphasis_expected_range(category)
        if not (min_rank <= score <= max_rank):
            issues.append(
                f"Score {score}% outside expected range [{min_rank}-{max_rank}] for category {category}")

    return len(issues) == 0, issues


def create_system_message_with_cache(text: str) -> list:
    """
    Create a system message with Anthropic's prompt caching enabled.
    This is useful for large contexts (like transcripts) reused across multiple calls.

    Returns:
        List containing the system message dictionary.
    """
    return [
        {
            "type": "text",
            "text": text,
            "cache_control": {"type": "ephemeral"}
        }
    ]


# ============================================================================
# MARKDOWN UTILITIES
# ============================================================================

def markdown_to_html(text: str) -> str:
    """
    Convert basic markdown to HTML.

    Args:
        text: Markdown text

    Returns:
        HTML formatted text
    """
    # Handle section headings
    text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)

    # Handle bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

    # Handle italic
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)

    # Handle paragraphs
    paragraphs = text.split('\n\n')
    paragraphs = [f'<p>{p.strip()}</p>' if not p.strip().startswith('<') else p.strip()
                  for p in paragraphs if p.strip()]

    return '\n'.join(paragraphs)


# ============================================================================
# TEXT PROCESSING UTILITIES
# ============================================================================

def normalize_text(text: str, aggressive: bool = False) -> str:
    """
    Normalize text for comparison.

    Args:
        text: The text to normalize.
        aggressive: If True, performs more aggressive cleaning,
                    including removing punctuation and speaker tags.

    Returns:
        Normalized text.
    """
    # Unescape HTML entities (e.g. &apos; -> ')
    text = unescape(text)

    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)

    # Remove timestamps (e.g. [00:00:00], 10:00, 1:10:10)
    # Matches n:nn, nn:nn, n:nn:nn, nn:nn:nn with optional brackets/parens
    text = re.sub(
        r'[\[\(]?\b\d+:\d{2}(?:\d{2})?(?:[ap]m)?[\]\)]?', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'(?:^|\s)[\[\(]?:\d{2}\b[\]\)]?', ' ', text)

    if aggressive:
        # Remove speaker tags (Markdown and plain text)
        text = re.sub(r'\*\*[^*]+:\*\*\s*', '', text)
        text = re.sub(r'(Speaker \d+|Unknown Speaker):\s*',
                      '', text, flags=re.IGNORECASE)
        # Remove punctuation
        text = re.sub(r'[.,!?;:—\-\'"()]', ' ', text)

    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text.lower()


def find_text_in_content(needle: str, haystack: str, aggressive_normalization: bool = False) -> tuple[Optional[int], Optional[int], float]:
    """
    Find needle in haystack and return (start_pos, end_pos, match_ratio).
    Uses fuzzy matching to find the best fit.

    Args:
        needle: The text to search for.
        haystack: The text to search within.
        aggressive_normalization: Whether to use aggressive normalization.

    Returns:
        A tuple containing (start_pos, end_pos, match_ratio).
        Returns (None, None, 0) if no good match is found.
    """
    needle_normalized = normalize_text(
        needle, aggressive=aggressive_normalization)
    haystack_normalized = normalize_text(
        haystack, aggressive=aggressive_normalization)

    # Try exact match first
    if needle_normalized in haystack_normalized:
        # Find position in original (non-normalized) text
        # Use first 20 chars to locate in original
        search_start = needle[:min(
            config.FUZZY_MATCH_PREFIX_LEN, len(needle))].strip()
        pos = haystack.lower().find(search_start.lower())
        if pos >= 0:
            return (pos, pos + len(needle), 1.0)

    # Fuzzy match - try sliding window
    needle_words = needle_normalized.split()
    haystack_words = haystack_normalized.split()
    needle_len = len(needle_words)

    best_ratio = 0
    best_pos = None

    for i in range(len(haystack_words) - needle_len + 1):
        window = ' '.join(haystack_words[i:i + needle_len])
        ratio = SequenceMatcher(None, needle_normalized, window).ratio()

        if ratio > best_ratio and ratio >= config.FUZZY_MATCH_THRESHOLD:
            best_ratio = ratio
            best_pos = i
            # Early termination for near-perfect match
            if ratio >= config.FUZZY_MATCH_EARLY_STOP:
                break

    if best_pos is not None:
        # Approximate position in original text
        # This is rough but works for highlighting
        words_before = ' '.join(haystack_words[:best_pos])
        approx_start = len(words_before)
        approx_end = approx_start + \
            len(' '.join(haystack_words[best_pos:best_pos + needle_len]))
        return (approx_start, approx_end, best_ratio)

    return (None, None, 0)


def delete_logs(logger=None) -> bool:
    """Permanently delete log files and token usage CSV."""
    if logger is None:
        logger = setup_logging('delete_logs')

    logs_dir = config.LOGS_DIR
    if not logs_dir.exists():
        logger.info("Logs directory not found: %s", logs_dir)
        return True

    files_to_delete = list(logs_dir.glob("*.log")) + \
        list(logs_dir.glob("*.csv"))

    if not files_to_delete:
        logger.info("No log files found to delete.")
        return True

    logger.info("Found %d files to delete.", len(files_to_delete))
    for f in files_to_delete:
        f.unlink()
        logger.info("  - Deleted: %s", f.name)
    logger.info("✅ Deletion complete.")
    return True
