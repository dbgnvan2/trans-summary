# Model-Agnostic API Response Validation

This document explains how to adapt the validation patterns in `transcript_utils.py` for different AI providers.

## Overview

The `validate_api_response()` function in `transcript_utils.py` is designed with **model-agnostic patterns** that can be adapted to work with:

- Anthropic Claude
- OpenAI GPT models
- Google Gemini
- Other AI providers

The validation checks 7 universal patterns that all AI APIs should provide:

1. **Message Type**: Is this a valid response object?
2. **Role Verification**: Did the assistant respond?
3. **Completion Status**: Did the request finish successfully or get truncated?
4. **Content Exists**: Is there actual content in the response?
5. **Content Format**: Is the content in the expected format?
6. **Text Validity**: Is the text field populated and non-empty?
7. **Token Usage**: Are token counts available for billing/monitoring?

## Anthropic Claude (Current Implementation)

```python
def validate_api_response(message, expected_model=None, min_length=10, logger=None):
    # 1. Message Type
    if not hasattr(message, 'type') or message.type != 'message':
        raise ValueError("Invalid response: not a message object")

    # 2. Role
    if not hasattr(message, 'role') or message.role != 'assistant':
        raise ValueError(f"Unexpected role: {getattr(message, 'role', 'unknown')}")

    # 3. Completion Status
    if not hasattr(message, 'stop_reason'):
        raise ValueError("Response missing stop_reason")

    if message.stop_reason == 'max_tokens':
        raise RuntimeError("Output truncated at max_tokens limit")
    elif message.stop_reason not in ['end_turn', 'stop_sequence', 'tool_use']:
        raise ValueError(f"Unexpected stop_reason: {message.stop_reason}")

    # 4. Content Array
    if not hasattr(message, 'content') or not message.content:
        raise ValueError("Response has no content")

    # 5. Content Format
    if not hasattr(message.content[0], 'type') or message.content[0].type != 'text':
        raise ValueError(f"Unexpected content type: {getattr(message.content[0], 'type', 'unknown')}")

    # 6. Text Validity
    text = getattr(message.content[0], 'text', None)
    if not text or not isinstance(text, str) or not text.strip():
        raise ValueError("Response text is empty or invalid")
    if len(text) < min_length:
        raise ValueError(f"Response too short: {len(text)} chars (minimum {min_length})")

    # 7. Token Usage
    if not hasattr(message, 'usage'):
        raise ValueError("Response missing usage information")
    if not hasattr(message.usage, 'input_tokens') or not hasattr(message.usage, 'output_tokens'):
        raise ValueError("Response missing token counts")

    return text
```

## OpenAI GPT (Adaptation Guide)

OpenAI uses a different response structure. Here's how to adapt:

```python
def validate_openai_response(response, expected_model=None, min_length=10, logger=None):
    """
    Validate OpenAI API response.

    OpenAI response structure:
    {
        "id": "chatcmpl-...",
        "object": "chat.completion",
        "model": "gpt-4",
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "..."
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 200,
            "total_tokens": 300
        }
    }
    """
    # 1. Message Type (object field)
    if not hasattr(response, 'object') or response.object != 'chat.completion':
        raise ValueError(f"Invalid response type: {getattr(response, 'object', 'unknown')}")

    # 2. Role (in choices[0].message.role)
    if not response.choices or not response.choices[0].message:
        raise ValueError("Response missing choices/message")
    if response.choices[0].message.role != 'assistant':
        raise ValueError(f"Unexpected role: {response.choices[0].message.role}")

    # 3. Completion Status (finish_reason)
    finish_reason = response.choices[0].finish_reason
    if finish_reason == 'length':  # OpenAI's equivalent to max_tokens
        raise RuntimeError("Output truncated at token limit")
    elif finish_reason not in ['stop', 'function_call', 'tool_calls']:
        raise ValueError(f"Unexpected finish_reason: {finish_reason}")

    # 4-5. Content Format (OpenAI has single content field)
    if not hasattr(response.choices[0].message, 'content'):
        raise ValueError("Response message has no content field")

    # 6. Text Validity
    text = response.choices[0].message.content
    if not text or not isinstance(text, str) or not text.strip():
        raise ValueError("Response text is empty or invalid")
    if len(text) < min_length:
        raise ValueError(f"Response too short: {len(text)} chars")

    # 7. Token Usage
    if not hasattr(response, 'usage'):
        raise ValueError("Response missing usage information")
    if not hasattr(response.usage, 'prompt_tokens') or not hasattr(response.usage, 'completion_tokens'):
        raise ValueError("Response missing token counts")

    # Model verification
    if expected_model and response.model != expected_model:
        if logger:
            logger.warning(f"Model mismatch: requested {expected_model}, got {response.model}")

    return text
```

## Google Gemini (Adaptation Guide)

Google's structure is different again:

```python
def validate_gemini_response(response, expected_model=None, min_length=10, logger=None):
    """
    Validate Google Gemini API response.

    Gemini response structure:
    {
        "candidates": [{
            "content": {
                "parts": [{"text": "..."}],
                "role": "model"
            },
            "finishReason": "STOP"
        }],
        "usageMetadata": {
            "promptTokenCount": 100,
            "candidatesTokenCount": 200,
            "totalTokenCount": 300
        }
    }
    """
    # 1-2. Message Type and Role
    if not response.candidates or not response.candidates[0].content:
        raise ValueError("Response missing candidates/content")
    if response.candidates[0].content.role != 'model':
        raise ValueError(f"Unexpected role: {response.candidates[0].content.role}")

    # 3. Completion Status (finishReason)
    finish_reason = response.candidates[0].finishReason
    if finish_reason == 'MAX_TOKENS':
        raise RuntimeError("Output truncated at token limit")
    elif finish_reason not in ['STOP', 'OTHER']:
        raise ValueError(f"Unexpected finishReason: {finish_reason}")

    # 4-5. Content Format (parts array)
    parts = response.candidates[0].content.parts
    if not parts or not parts[0].text:
        raise ValueError("Response has no text parts")

    # 6. Text Validity
    text = parts[0].text
    if not text or not isinstance(text, str) or not text.strip():
        raise ValueError("Response text is empty or invalid")
    if len(text) < min_length:
        raise ValueError(f"Response too short: {len(text)} chars")

    # 7. Token Usage
    if not hasattr(response, 'usageMetadata'):
        raise ValueError("Response missing usage metadata")
    if not hasattr(response.usageMetadata, 'promptTokenCount'):
        raise ValueError("Response missing token counts")

    return text
```

## Universal Abstraction Layer

For true model-agnostic code, create an abstraction layer:

```python
class AIResponse:
    """Universal response wrapper for different AI providers."""

    def __init__(self, provider: str, raw_response):
        self.provider = provider
        self.raw = raw_response
        self._parse_response()

    def _parse_response(self):
        """Extract common fields from provider-specific response."""
        if self.provider == 'anthropic':
            self.text = self.raw.content[0].text
            self.stop_reason = self.raw.stop_reason
            self.input_tokens = self.raw.usage.input_tokens
            self.output_tokens = self.raw.usage.output_tokens
            self.truncated = (self.stop_reason == 'max_tokens')

        elif self.provider == 'openai':
            self.text = self.raw.choices[0].message.content
            self.stop_reason = self.raw.choices[0].finish_reason
            self.input_tokens = self.raw.usage.prompt_tokens
            self.output_tokens = self.raw.usage.completion_tokens
            self.truncated = (self.stop_reason == 'length')

        elif self.provider == 'gemini':
            self.text = self.raw.candidates[0].content.parts[0].text
            self.stop_reason = self.raw.candidates[0].finishReason
            self.input_tokens = self.raw.usageMetadata.promptTokenCount
            self.output_tokens = self.raw.usageMetadata.candidatesTokenCount
            self.truncated = (self.stop_reason == 'MAX_TOKENS')

        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

def validate_universal_response(
    response: AIResponse,
    min_length: int = 10,
    logger = None
) -> str:
    """Provider-agnostic validation."""

    # Check for truncation
    if response.truncated:
        raise RuntimeError(
            f"Output truncated at token limit "
            f"({response.output_tokens} tokens)"
        )

    # Validate text
    if not response.text or not response.text.strip():
        raise ValueError("Response text is empty")

    if len(response.text) < min_length:
        raise ValueError(
            f"Response too short: {len(response.text)} chars "
            f"(minimum {min_length})"
        )

    # Log usage
    if logger:
        logger.info(
            f"{response.provider} API call - "
            f"Input: {response.input_tokens} tokens, "
            f"Output: {response.output_tokens} tokens, "
            f"Stop: {response.stop_reason}"
        )

    return response.text
```

## Usage Example

```python
# Anthropic
from anthropic import Anthropic
client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
raw_response = client.messages.create(...)
response = AIResponse('anthropic', raw_response)
text = validate_universal_response(response, logger=logger)

# OpenAI
from openai import OpenAI
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
raw_response = client.chat.completions.create(...)
response = AIResponse('openai', raw_response)
text = validate_universal_response(response, logger=logger)

# Gemini
import google.generativeai as genai
genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
model = genai.GenerativeModel('gemini-pro')
raw_response = model.generate_content(...)
response = AIResponse('gemini', raw_response)
text = validate_universal_response(response, logger=logger)
```

## Key Takeaways

1. **Universal Patterns**: All AI APIs provide:

   - Response type/object identification
   - Role verification
   - Completion status (stop reason)
   - Content/text field
   - Token usage metrics

2. **Provider Differences**:

   - **Field Names**: `stop_reason` vs `finish_reason` vs `finishReason`
   - **Text Location**: `content[0].text` vs `message.content` vs `parts[0].text`
   - **Token Fields**: `input_tokens` vs `prompt_tokens` vs `promptTokenCount`
   - **Truncation Values**: `max_tokens` vs `length` vs `MAX_TOKENS`

3. **Abstraction Benefits**:

   - Single validation function for all providers
   - Easy to switch providers
   - Reusable across projects
   - Consistent error handling

4. **Exception Handling**: Each provider has unique exception types:
   - **Anthropic**: `RateLimitError`, `APIError`, `AuthenticationError`
   - **OpenAI**: `RateLimitError`, `APIError`, `AuthenticationError`
   - **Google**: `ResourceExhausted`, `InvalidArgument`, `Unauthenticated`

## Reusing This Pattern

To use this validation pattern in other projects:

1. Copy the **7-step validation checklist** from this document
2. Adapt field names for your AI provider
3. Map completion statuses (stop_reason equivalents)
4. Update token field names
5. Add provider-specific exception handling
6. Test with truncated responses to verify detection works

The `validate_api_response()` function in `transcript_utils.py` serves as a **reference template** showing how to implement comprehensive validation for any AI provider.
