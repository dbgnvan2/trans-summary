from types import SimpleNamespace
from unittest.mock import MagicMock

import transcript_utils


def _ok_response():
    text = "Valid response text that is comfortably longer than fifty characters."
    return SimpleNamespace(
        type="message",
        role="assistant",
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=10,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
        model="claude-3-5-haiku-20241022",
    )


def test_call_claude_auto_caches_large_user_message():
    client = MagicMock()
    client.messages.create.return_value = _ok_response()

    large_prompt = "x" * (transcript_utils.LARGE_INPUT_CACHE_THRESHOLD_CHARS + 1)
    transcript_utils.call_claude_with_retry(
        client=client,
        model="claude-3-5-haiku-20241022",
        messages=[{"role": "user", "content": large_prompt}],
        max_tokens=64,
        logger=MagicMock(),
    )

    sent_messages = client.messages.create.call_args.kwargs["messages"]
    content = sent_messages[0]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[0]["text"] == large_prompt
    assert content[0]["cache_control"] == {"type": "ephemeral"}


def test_call_claude_auto_caches_large_system_string():
    client = MagicMock()
    client.messages.create.return_value = _ok_response()

    large_system = "s" * (transcript_utils.LARGE_INPUT_CACHE_THRESHOLD_CHARS + 1)
    transcript_utils.call_claude_with_retry(
        client=client,
        model="claude-3-5-haiku-20241022",
        messages=[{"role": "user", "content": "hello"}],
        system=large_system,
        max_tokens=64,
        logger=MagicMock(),
    )

    sent_system = client.messages.create.call_args.kwargs["system"]
    assert isinstance(sent_system, list)
    assert sent_system[0]["type"] == "text"
    assert sent_system[0]["text"] == large_system
    assert sent_system[0]["cache_control"] == {"type": "ephemeral"}


def test_call_claude_keeps_small_user_message_uncached():
    client = MagicMock()
    client.messages.create.return_value = _ok_response()

    transcript_utils.call_claude_with_retry(
        client=client,
        model="claude-3-5-haiku-20241022",
        messages=[{"role": "user", "content": "short"}],
        max_tokens=64,
        logger=MagicMock(),
    )

    sent_messages = client.messages.create.call_args.kwargs["messages"]
    content = sent_messages[0]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[0]["text"] == "short"
    assert "cache_control" not in content[0]
