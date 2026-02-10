"""
Shared utilities for transcript processing scripts.
Reduces code duplication and provides common validation/error handling.
"""

import csv
import logging
import os
import re
import time
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


# Configure logging
def setup_logging(script_name: str) -> logging.Logger:
    """Set up logging for a script."""
    logs_dir = config.LOGS_DIR
    logs_dir.mkdir(exist_ok=True)

    from datetime import datetime
    log_file = logs_dir / f"{script_name}_{datetime.now():%Y%m%d_%H%M%S}.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

    logger = logging.getLogger(script_name)
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
    THRESHOLD_CHARS = 10000

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

    # Check for missing cache on large inputs
    if not suppress_caching_warnings:
        _check_caching_for_large_input(messages, kwargs.get('system'), logger)

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
                    messages=messages,
                    extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
                    **call_kwargs
                ) as stream_manager:
                    message = stream_manager.get_final_message()
            else:
                message = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=messages,
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
                                    for m in messages])

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
            if logger:
                logger.error("API error: %s", e)
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
            f"⚠️  Input may exceed token limit:\n"
            f"   Estimated tokens: {estimated:,}\n"
            f"   Safe limit: {int(safe_limit):,} ({config.TOKEN_BUDGET_SAFETY_MARGIN:.0%} of {max_tokens:,})\n"
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
        section_name: The section name (e.g., "Topics", "Abstract", "Key Themes")
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


def load_bowen_references(base_name: str) -> list:
    """
    Load Bowen reference quotes from dedicated file, with fallback to extracts-summary.

    Args:
        base_name: The base name of the transcript

    Returns:
        List of tuples: [(concept, quote), ...]
    """
    # Try dedicated file first
    bowen_file = config.PROJECTS_DIR / base_name / \
        f"{base_name}{config.SUFFIX_BOWEN}"
    if bowen_file.exists():
        with open(bowen_file, 'r', encoding='utf-8') as f:
            content = f.read()
        content = strip_yaml_frontmatter(content)

        refs = extract_bowen_references(content)
        if refs:
            return refs

        # Fallback: If file exists but extraction failed (likely missing header),
        # try to parse the whole content directly as a list of quotes.
        quote_pattern = r'^\s*(?:[-*>]+\s+)?(?:\*\*)?([^*\n]+?)(?:\*\*)?:?\s*["“](.+?)["”]'
        quotes = re.findall(quote_pattern, content, flags=re.MULTILINE)
        return [(concept.strip().rstrip(':'), quote.strip()) for concept, quote in quotes]

    # Fall back to All Key Items
    extracts_file = config.PROJECTS_DIR / base_name / \
        f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"
    if extracts_file.exists():
        with open(extracts_file, 'r', encoding='utf-8') as f:
            content = f.read()
        content = strip_yaml_frontmatter(content)
        return extract_bowen_references(content)

    # Fall back to topics-themes for backward compatibility
    extracts_file = config.PROJECTS_DIR / base_name / \
        f"{base_name}{config.SUFFIX_KEY_ITEMS_RAW_LEGACY}"
    if extracts_file.exists():
        with open(extracts_file, 'r', encoding='utf-8') as f:
            content = f.read()
        content = strip_yaml_frontmatter(content)
        return extract_bowen_references(content)

    return []


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
    Load emphasis item quotes from dedicated file, with fallback to extracts-summary.

    Args:
        base_name: The base name of the transcript

    Returns:
        List of tuples: [(item_name, quote), ...]
    """
    # Load Bowen references first to check for duplicates
    bowen_refs = load_bowen_references(base_name)
    bowen_quotes = {normalize_text(q, aggressive=True) for _, q in bowen_refs}

    # Try new scored emphasis file first
    scored_file = config.PROJECTS_DIR / base_name / \
        f"{base_name}{config.SUFFIX_EMPHASIS_SCORED}"
    if scored_file.exists():
        content = scored_file.read_text(encoding='utf-8')
        items = parse_scored_emphasis_output(content)
        filtered_items = []
        for item in items:
            if normalize_text(item['quote'], aggressive=True) not in bowen_quotes:
                filtered_items.append(
                    (f"{item['concept']} ({item['score']}%)", item['quote']))
        return filtered_items

    # Try dedicated file first
    emphasis_file = config.PROJECTS_DIR / base_name / \
        f"{base_name}{config.SUFFIX_EMPHASIS}"
    if emphasis_file.exists():
        with open(emphasis_file, 'r', encoding='utf-8') as f:
            content = f.read()
        content = strip_yaml_frontmatter(content)
        items = extract_emphasis_items(content)
        filtered_items = []
        for label, quote in items:
            if normalize_text(quote, aggressive=True) not in bowen_quotes:
                filtered_items.append((label, quote))
        return filtered_items

    # Fall back to All Key Items
    extracts_file = config.PROJECTS_DIR / base_name / \
        f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"
    if extracts_file.exists():
        with open(extracts_file, 'r', encoding='utf-8') as f:
            content = f.read()
        content = strip_yaml_frontmatter(content)
        items = extract_emphasis_items(content)
        filtered_items = []
        for label, quote in items:
            if normalize_text(quote, aggressive=True) not in bowen_quotes:
                filtered_items.append((label, quote))
        return filtered_items

    # Fall back to topics-themes for backward compatibility
    extracts_file = config.PROJECTS_DIR / base_name / \
        f"{base_name}{config.SUFFIX_KEY_ITEMS_RAW_LEGACY}"
    if extracts_file.exists():
        with open(extracts_file, 'r', encoding='utf-8') as f:
            content = f.read()
        content = strip_yaml_frontmatter(content)
        items = extract_emphasis_items(content)
        filtered_items = []
        for label, quote in items:
            if normalize_text(quote, aggressive=True) not in bowen_quotes:
                filtered_items.append((label, quote))
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
    items = []
    # Regex to capture the structured block
    # Matches: [Type - Category - Rank: 99%] Concept: ... \n "Quote"
    # Updated to handle optional bolding **...** and score ranges
    # Updated to be case-insensitive for labels and flexible with separators
    pattern = re.compile(
        r'(?:\*\*)?\[(?P<type>[^-\]]+?)\s*-\s*(?P<category>.+?)\s*-\s*(?:(?:Rank|rank)\s*:\s*)?(?P<score>[^\]%]+)%?\](?:\*\*)?\s*(?:Concept|concept)\s*:\s*(?P<concept>[\s\S]+?)\s+["“](?P<quote>[\s\S]+?)["”]',  # noqa
        re.MULTILINE
    )

    for match in pattern.finditer(text):
        score_str = match.group('score').strip()
        # Handle ranges like "87-96" or single numbers "95"
        nums = [int(n) for n in re.findall(r'\d+', score_str)]
        score = int(sum(nums) / len(nums)) if nums else 0

        items.append({
            'type': match.group('type').strip().replace('*', ''),
            'category': match.group('category').strip().replace('*', ''),
            'score': score,
            'concept': match.group('concept').strip().replace('*', ''),
            'quote': match.group('quote').strip()
        })

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
