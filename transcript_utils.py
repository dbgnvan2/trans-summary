"""
Shared utilities for transcript processing scripts.
Reduces code duplication and provides common validation/error handling.
"""

import re
import os
import time
import logging
from pathlib import Path
from typing import Optional
from anthropic import (
    APIError,
    RateLimitError,
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError
)


# Configure logging
def setup_logging(script_name: str) -> logging.Logger:
    """Set up logging for a script."""
    logs_dir = Path(__file__).parent / "logs"
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
            logger.warning(
                f"Generation stopped early at stop_sequence: "
                f"{getattr(message, 'stop_sequence', 'unknown')}"
            )
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
            logger.warning(
                f"Response suspiciously short: {len(text)} characters "
                f"(expected at least {min_length})"
            )

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
            if logger:
                logger.warning(
                    f"Model mismatch: requested '{expected_model}' "
                    f"but got '{message.model}'"
                )

    return text


def call_claude_with_retry(
    client,
    model: str,
    messages: list,
    max_tokens: int,
    temperature: float = 0.3,
    max_retries: int = 3,
    logger: Optional[logging.Logger] = None
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

    Returns:
        API response message

    Raises:
        ValueError: If API key is invalid or request is malformed
        RuntimeError: If output is truncated or connection fails
        APIError: If API call fails after retries
    """
    for attempt in range(max_retries):
        try:
            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=messages
            )

            # Comprehensive response validation
            try:
                validate_api_response(
                    message,
                    expected_model=model,
                    logger=logger
                )
            except (ValueError, RuntimeError) as e:
                # Validation failed - don't retry, this is a logic error
                if logger:
                    logger.error(f"Response validation failed: {e}")
                raise

            # Warn if close to limit
            if message.usage.output_tokens > max_tokens * 0.9:
                warning = (
                    f"⚠️  Nearly hit token limit: "
                    f"{message.usage.output_tokens}/{max_tokens} tokens used"
                )
                if logger:
                    logger.warning(warning)
                print(f"\n{warning}")

            # Log successful usage
            if logger:
                logger.info(
                    f"API call successful - "
                    f"Input: {message.usage.input_tokens} tokens, "
                    f"Output: {message.usage.output_tokens} tokens, "
                    f"Stop reason: {message.stop_reason}"
                )

            return message

        except AuthenticationError as e:
            # Don't retry - API key is invalid
            if logger:
                logger.error("Authentication failed - invalid API key")
            raise ValueError(
                "ANTHROPIC_API_KEY is invalid or expired. "
                "Get a new key from https://console.anthropic.com/"
            ) from e

        except BadRequestError as e:
            # Don't retry - request is malformed
            if logger:
                logger.error(f"Bad request: {e}")
            raise ValueError(
                f"API request was malformed: {e}\n"
                "Check that model name, max_tokens, and message format are valid."
            ) from e

        except APITimeoutError as e:
            if logger:
                logger.error(f"Request timed out: {e}")
            raise RuntimeError(
                "API request timed out. "
                "The transcript may be too long. Try processing in smaller chunks."
            ) from e

        except APIConnectionError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                msg = f"Connection error, retrying in {wait_time}s... ({attempt + 2}/{max_retries})"
                if logger:
                    logger.warning(msg)
                print(f"\n⚠️  {msg}")
                time.sleep(wait_time)
            else:
                if logger:
                    logger.error("Connection failed after retries")
                raise RuntimeError(
                    "Could not connect to Anthropic API. "
                    "Check your internet connection."
                ) from e

        except RateLimitError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                msg = f"Rate limit hit, waiting {wait_time}s before retry {attempt + 2}/{max_retries}..."
                if logger:
                    logger.warning(msg)
                print(f"\n⚠️  {msg}")
                time.sleep(wait_time)
            else:
                if logger:
                    logger.error(
                        f"Rate limit exceeded after {max_retries} retries")
                raise

        except APIError as e:
            if logger:
                logger.error(f"API error: {e}")
            raise


def extract_metadata_from_filename(filename: str) -> tuple[str, str, str]:
    """
    Extract title, author, date from filename.

    Args:
        filename: Filename in format "Title - Author - Date.ext"

    Returns:
        Tuple of(title, author, date)

    Raises:
        ValueError: If filename doesn't match expected pattern
    """
    stem = Path(filename).stem
    parts = [p.strip() for p in stem.split(' - ')]

    if len(parts) < 3:
        raise ValueError(
            f"Filename must follow pattern 'Title - Author - Date.ext'\n"
            f"Got: {filename}"
        )

    # Handle case where title or author contains ' - '
    if len(parts) > 3:
        # Date is last, author is second-to-last, rest is title
        date = parts[-1]
        author = parts[-2]
        title = ' - '.join(parts[:-2])
    else:
        title, author, date = parts

    return title, author, date


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
    return len(text) // 4


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
    safe_limit = max_tokens * 0.8

    if estimated > safe_limit:
        warning = (
            f"⚠️  Input may exceed token limit:\n"
            f"   Estimated tokens: {estimated:,}\n"
            f"   Safe limit: {int(safe_limit):,} (80% of {max_tokens:,})\n"
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
    Extract a markdown section by name, handling variations in formatting.

    Args:
        content: The markdown content to search
        section_name: The section name (e.g., "Topics", "Abstract", "Key Themes")
        allow_bold: If True, matches both "## Section" and "## **Section**"

    Returns:
        The section content (stripped), or empty string if not found

    Examples:
        >>> extract_section(content, "Topics")  # Matches both:
        # ## Topics
        # ## **Topics**
    """
    # Build pattern that optionally matches bold markers
    if allow_bold:
        # Pattern matches: ## Topics  OR  ## **Topics**
        pattern = rf'## \*{{0,2}}{re.escape(section_name)}\*{{0,2}}(.*?)(?=^## |\Z)'
    else:
        # Exact match only
        pattern = rf'## {re.escape(section_name)}(.*?)(?=^## |\Z)'

    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ''


def extract_bowen_references(content: str) -> list:
    """
    Extract Bowen reference quotes from extracts-summary content.
    Handles variations in section header formatting.

    Returns:
        List of tuples: [(concept, quote), ...]
    """
    section_content = extract_section(content, "Bowen References")
    if not section_content:
        return []

    # Extract quotes in blockquote format: > **Concept:** "Quote"
    quote_pattern = r'>\s*\*\*([^*]+):\*\*\s*"([^"]+)"'
    quotes = re.findall(quote_pattern, section_content)

    return [(concept.strip(), quote.strip()) for concept, quote in quotes]


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

    # Extract quotes in blockquote format: > **Item:** "Quote"
    quote_pattern = r'>\s*\*\*([^*]+):\*\*\s*"([^"]+)"'
    quotes = re.findall(quote_pattern, section_content)

    return [(item.strip(), quote.strip()) for item, quote in quotes]


def strip_yaml_frontmatter(content: str) -> str:
    """
    Remove YAML frontmatter from markdown content.

    Args:
        content: Markdown content that may start with YAML frontmatter

    Returns:
        Content with YAML frontmatter removed
    """
    if content.startswith('---'):
        parts = content.split('---\n', 2)
        if len(parts) >= 3:
            return parts[2]
    return content
