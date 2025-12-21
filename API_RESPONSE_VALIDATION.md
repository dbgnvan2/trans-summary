# Anthropic API Response Validation Reference

## Message Response Object Structure

When you call `client.messages.create()`, you get a Message object with these fields:

```python
message = client.messages.create(...)

# Message object structure:
message.id                    # Unique message identifier
message.type                  # Should be "message"
message.role                  # Should be "assistant"
message.content               # Array of content blocks
message.model                 # Model used (e.g., "claude-sonnet-4-5-20250929")
message.stop_reason           # Why generation stopped
message.stop_sequence         # Stop sequence that triggered (if applicable)
message.usage                 # Token usage information
  message.usage.input_tokens  # Number of input tokens consumed
  message.usage.output_tokens # Number of output tokens generated
```

---

## Fields Currently Checked ✅

1. **`stop_reason`** - Partially checked

   - ✅ Checking for `"max_tokens"` (in updated scripts)
   - ❌ NOT checking for other stop reasons

2. **`usage.output_tokens`** - Checked in `transcript_utils.py`

   - ✅ Warns if > 90% of max_tokens
   - ✅ Logs input/output token counts

3. **`content[0].text`** - Implicitly used
   - ✅ All scripts access this field
   - ❌ NOT validating it exists or checking for errors

---

## stop_reason Values - What They Mean

| Value                 | Meaning                               | Should We Handle?                             |
| --------------------- | ------------------------------------- | --------------------------------------------- |
| **`"end_turn"`**      | ✅ Normal completion                  | ✅ **Expected** - This is good!               |
| **`"max_tokens"`**    | ❌ Hit token limit - output truncated | ✅ **Currently checking** - Raise error       |
| **`"stop_sequence"`** | ⏹️ Hit a custom stop sequence         | ⚠️ **Should check** - May indicate early stop |
| **`"tool_use"`**      | 🔧 Model wants to use a tool          | ❌ Not relevant (we don't use tools)          |

### Recommended Validation

```python
# Check stop reason is acceptable
if message.stop_reason == "max_tokens":
    # Already handling this - output was truncated
    raise RuntimeError("Output truncated at max_tokens limit")
elif message.stop_reason == "stop_sequence":
    # This might be unexpected - depends if you set stop sequences
    logger.warning(f"Generation stopped early due to stop_sequence: {message.stop_sequence}")
    # Decide: fail, warn, or continue
elif message.stop_reason != "end_turn":
    # Unexpected stop reason
    logger.error(f"Unexpected stop_reason: {message.stop_reason}")
    raise RuntimeError(f"Unexpected stop reason: {message.stop_reason}")
```

---

## Fields NOT Currently Validated ❌

### 1. Content Array Validation

**Risk**: `message.content[0]` could fail if content is empty or malformed

**Current Code** (vulnerable):

```python
return message.content[0].text  # What if content is empty?
```

**Should Check**:

```python
# Validate content exists and has expected structure
if not message.content:
    raise ValueError("API returned empty content array")

if len(message.content) == 0:
    raise ValueError("API returned no content blocks")

content_block = message.content[0]

# Check content block type
if not hasattr(content_block, 'type'):
    raise ValueError("Content block missing type field")

if content_block.type != "text":
    raise ValueError(f"Expected text content, got: {content_block.type}")

if not hasattr(content_block, 'text'):
    raise ValueError("Content block missing text field")

if not content_block.text or len(content_block.text.strip()) == 0:
    raise ValueError("API returned empty text content")

return content_block.text
```

---

### 2. Message Type Validation

**Risk**: Response might not be a proper message object

**Should Check**:

```python
if message.type != "message":
    raise ValueError(f"Expected message type, got: {message.type}")

if message.role != "assistant":
    raise ValueError(f"Expected assistant role, got: {message.role}")
```

---

### 3. Model Verification

**Risk**: API might use different model than requested (rare but possible)

**Should Check**:

```python
if message.model != expected_model:
    logger.warning(f"Requested {expected_model} but got {message.model}")
```

---

### 4. Token Usage Validation

**Currently**: Checking if near limit  
**Should Also Check**: Total tokens don't exceed known limits

```python
# Claude 4 has 200k context window
MAX_CONTEXT_TOKENS = 200000

total_tokens = message.usage.input_tokens + message.usage.output_tokens

if total_tokens > MAX_CONTEXT_TOKENS:
    logger.error(f"Total tokens ({total_tokens}) exceeds context window!")
```

---

### 5. Response Completeness

**Risk**: Text might be empty or just whitespace

**Should Check**:

```python
text = message.content[0].text

if not text or not text.strip():
    raise ValueError("API returned empty or whitespace-only text")

if len(text) < 50:  # Arbitrary minimum
    logger.warning(f"Response suspiciously short: {len(text)} characters")
```

---

## API Error Responses

The Anthropic SDK can raise these exceptions (already handled in `transcript_utils.py`):

| Exception                 | Meaning                  | Current Handling                  |
| ------------------------- | ------------------------ | --------------------------------- |
| **`RateLimitError`**      | Hit API rate limit       | ✅ Retry with exponential backoff |
| **`APIError`**            | General API error        | ✅ Log and raise                  |
| **`APIConnectionError`**  | Network/connection issue | ❌ Not explicitly handled         |
| **`APITimeoutError`**     | Request timed out        | ❌ Not explicitly handled         |
| **`AuthenticationError`** | Invalid API key          | ❌ Not explicitly handled         |
| **`BadRequestError`**     | Invalid request          | ❌ Not explicitly handled         |

### Recommended Exception Handling

```python
from anthropic import (
    APIError,
    RateLimitError,
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError
)

try:
    message = client.messages.create(...)
except AuthenticationError as e:
    logger.error("Invalid API key")
    raise ValueError("ANTHROPIC_API_KEY is invalid or expired") from e
except BadRequestError as e:
    logger.error(f"Invalid request: {e}")
    raise ValueError(f"API request was malformed: {e}") from e
except APIConnectionError as e:
    logger.error(f"Connection error: {e}")
    raise RuntimeError("Could not connect to Anthropic API - check network") from e
except APITimeoutError as e:
    logger.error(f"Request timed out: {e}")
    raise RuntimeError("API request timed out - transcript may be too long") from e
except RateLimitError as e:
    # Already handling with retry logic
    raise
except APIError as e:
    logger.error(f"API error: {e}")
    raise
```

---

## Streaming Responses (Not Currently Used)

If you ever use streaming mode (`stream=True`), different validation is needed:

```python
with client.messages.stream(...) as stream:
    for event in stream:
        # Check event types: message_start, content_block_start,
        # content_block_delta, content_block_stop, message_stop
        pass
```

**Current Status**: Not using streaming, so not relevant

---

## Complete Validation Function

Here's a comprehensive validation function that checks everything:

```python
def validate_api_response(message, expected_model: str, logger: Optional[logging.Logger] = None):
    """
    Comprehensive validation of API response.

    Args:
        message: API response message
        expected_model: Model name that was requested
        logger: Optional logger

    Raises:
        ValueError: If response is invalid
        RuntimeError: If response indicates failure
    """
    # 1. Check message type
    if not hasattr(message, 'type') or message.type != "message":
        raise ValueError(f"Invalid message type: {getattr(message, 'type', 'missing')}")

    if not hasattr(message, 'role') or message.role != "assistant":
        raise ValueError(f"Invalid role: {getattr(message, 'role', 'missing')}")

    # 2. Validate stop reason
    if not hasattr(message, 'stop_reason'):
        raise ValueError("Message missing stop_reason field")

    if message.stop_reason == "max_tokens":
        raise RuntimeError("Output truncated at max_tokens limit")

    if message.stop_reason == "stop_sequence":
        if logger:
            logger.warning(f"Stopped at sequence: {message.stop_sequence}")
        # Decide based on your use case: fail or continue

    if message.stop_reason not in ["end_turn", "stop_sequence", "max_tokens", "tool_use"]:
        raise ValueError(f"Unexpected stop_reason: {message.stop_reason}")

    # 3. Validate content
    if not hasattr(message, 'content'):
        raise ValueError("Message missing content field")

    if not message.content or len(message.content) == 0:
        raise ValueError("Message has empty content array")

    content_block = message.content[0]

    if not hasattr(content_block, 'type') or content_block.type != "text":
        raise ValueError(f"Expected text content, got: {getattr(content_block, 'type', 'missing')}")

    if not hasattr(content_block, 'text'):
        raise ValueError("Content block missing text field")

    text = content_block.text
    if not text or not text.strip():
        raise ValueError("API returned empty text")

    if len(text) < 50:
        if logger:
            logger.warning(f"Response very short: {len(text)} characters")

    # 4. Validate token usage
    if not hasattr(message, 'usage'):
        raise ValueError("Message missing usage field")

    if not hasattr(message.usage, 'input_tokens') or not hasattr(message.usage, 'output_tokens'):
        raise ValueError("Usage missing token counts")

    # 5. Check model (warning only)
    if hasattr(message, 'model') and message.model != expected_model:
        if logger:
            logger.warning(f"Requested {expected_model} but got {message.model}")

    return text
```

---

## Summary: What Should Be Added

### High Priority ✅

1. **Validate content array exists** - Prevent IndexError
2. **Check text is not empty** - Catch null responses
3. **Validate stop_reason is acceptable** - Currently only checking max_tokens

### Medium Priority ⚠️

4. **Handle stop_sequence** - Log unexpected early stops
5. **Add more exception types** - Handle network, auth, timeout errors
6. **Validate message structure** - Check type and role fields

### Low Priority 📝

7. **Model verification** - Warn if different model used
8. **Total token limits** - Check against context window

---

## Recommended Next Steps

1. **Update `transcript_utils.py`** - Add `validate_api_response()` function
2. **Update `call_claude_with_retry()`** - Call validation before returning
3. **Test with edge cases**:
   - Very long inputs (near token limit)
   - Empty/malformed responses
   - Network interruptions

---

## Quick Reference: Fields to Check

```python
# Required checks:
✅ message.stop_reason == "end_turn" or handle appropriately
✅ len(message.content) > 0
✅ message.content[0].type == "text"
✅ message.content[0].text is not empty
✅ message.usage.output_tokens < max_tokens

# Recommended checks:
⚠️ message.type == "message"
⚠️ message.role == "assistant"
⚠️ message.model == expected_model (warning only)
⚠️ message.stop_reason not in unexpected values

# Nice to have:
📝 total tokens within context limit
📝 response length exceeds minimum threshold
```

---

## Example Integration

**Before** (current code):

```python
message = client.messages.create(...)
if message.stop_reason == "max_tokens":
    raise RuntimeError("Truncated")
return message.content[0].text  # Could fail!
```

**After** (robust):

```python
from transcript_utils import call_claude_with_retry, validate_api_response

message = call_claude_with_retry(
    client=client,
    model=model,
    messages=[{"role": "user", "content": prompt}],
    max_tokens=16000,
    logger=logger
)

# Validate response structure and content
text = validate_api_response(message, expected_model=model, logger=logger)

return text
```

This ensures every API response is thoroughly validated before use.
