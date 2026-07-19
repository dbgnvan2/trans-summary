"""L10 (review 2026-07-18): the abstract prompt's hard word limit must come from
config.ABSTRACT_HARD_MAX_WORDS, not a hard-coded 249/250 literal (P4)."""
import config


def _template():
    return (config.PROMPTS_DIR / config.PROMPT_STRUCTURED_ABSTRACT_FILENAME).read_text(
        encoding="utf-8")


def test_l10_prompt_uses_config_placeholder_not_literal():
    tmpl = _template()
    assert "{hard_max_words}" in tmpl
    assert "249 words" not in tmpl
    assert "under 250 words" not in tmpl


def test_l10_prompt_renders_config_word_limit():
    tmpl = _template()
    rendered = tmpl.format(
        input_json="{}",
        target_word_count=200,
        hard_max_words=config.ABSTRACT_HARD_MAX_WORDS,
        hard_max_words_minus_one=config.ABSTRACT_HARD_MAX_WORDS - 1,
    )
    assert f"under {config.ABSTRACT_HARD_MAX_WORDS} words" in rendered
    assert f"never more than {config.ABSTRACT_HARD_MAX_WORDS - 1} words" in rendered
