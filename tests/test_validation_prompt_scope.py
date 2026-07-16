from pathlib import Path

import config


def test_validation_error_types_are_transcription_only():
    assert config.VALIDATION_ERROR_TYPES == {
        "spelling",
        "homophone",
        "proper_noun",
        "word_boundary",
        "alias",
    }


def test_v2_prompt_explicitly_bans_grammar_and_punctuation_rewrites():
    prompt_path = Path(config.PROMPTS_DIR) / "transcript_error_detection_prompt_v2.md"
    prompt_text = prompt_path.read_text(encoding="utf-8")

    assert "Do not report punctuation, capitalization-only, repetition, or grammar issues." in prompt_text
    assert "Do not add words that were probably never spoken." in prompt_text
    assert "Bowen family systems theory" in prompt_text


def test_v1_prompt_is_also_transcription_only():
    prompt_path = Path(config.PROMPTS_DIR) / "transcript_error_detection_prompt.md"
    prompt_text = prompt_path.read_text(encoding="utf-8")

    assert "Do not correct:" in prompt_text
    assert "- grammar" in prompt_text
    assert "- punctuation" in prompt_text
    assert "`error_type`: One of `proper_noun`, `homophone`, `spelling`, `word_boundary`" in prompt_text
