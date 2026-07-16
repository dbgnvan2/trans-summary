from unittest.mock import MagicMock, patch

import abstract_pipeline


def test_generate_abstract_enables_streaming():
    abstract_input = MagicMock()
    abstract_input.target_word_count = 250
    abstract_input.to_json.return_value = "{}"

    api_client = MagicMock()

    with patch("abstract_pipeline.call_claude_with_retry") as mock_call:
        mock_call.return_value.content = [MagicMock(text="Abstract text")]

        abstract_pipeline.generate_abstract(abstract_input, api_client)

        _, kwargs = mock_call.call_args
        assert kwargs.get("stream") is True
