from unittest.mock import MagicMock

import abstract_validation


def test_verify_with_llm_uses_reasonable_token_budget(monkeypatch):
    captured = {}

    def fake_call_claude_with_retry(**kwargs):
        captured["max_tokens"] = kwargs["max_tokens"]
        # Minimal valid response object
        msg = MagicMock()
        msg.content = [MagicMock(text="YES\nNO\n")]
        return msg

    monkeypatch.setattr(
        abstract_validation, "call_claude_with_retry", fake_call_claude_with_retry
    )

    items = [
        abstract_validation.CoverageItem(
            category="topic",
            label="Item 1",
            required=True,
            keywords=["topic"],
            source_text="topic text",
        ),
        abstract_validation.CoverageItem(
            category="theme",
            label="Item 2",
            required=True,
            keywords=["theme"],
            source_text="theme text",
        ),
    ]
    out = abstract_validation.verify_with_llm(
        "abstract text", items, api_client=MagicMock(), model="claude-3-5-haiku-20241022"
    )

    assert out == [True, False]
    assert captured["max_tokens"] >= 512


def test_verify_with_llm_fallback_on_exception(monkeypatch):
    def fake_call_claude_with_retry(**_kwargs):
        raise RuntimeError("Response truncated at token limit")

    monkeypatch.setattr(
        abstract_validation, "call_claude_with_retry", fake_call_claude_with_retry
    )

    items = [
        abstract_validation.CoverageItem(
            category="topic",
            label="Item 1",
            required=True,
            keywords=["topic"],
            source_text="topic text",
        )
    ]
    out = abstract_validation.verify_with_llm(
        "abstract text", items, api_client=MagicMock(), model="claude-3-5-haiku-20241022", logger=MagicMock()
    )

    assert out == [False]
