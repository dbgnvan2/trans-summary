"""Abstracts must stay < 250 words: config target cap + validation hard ceiling."""

import config
import abstract_validation


def test_abstract_target_floors_at_min():
    assert config.abstract_target_word_count(100) == config.ABSTRACT_MIN_WORDS


def test_abstract_target_caps_below_hard_max():
    capped = config.abstract_target_word_count(1_000_000)
    assert capped == config.ABSTRACT_MAX_WORDS
    assert capped < config.ABSTRACT_HARD_MAX_WORDS  # < 250


def test_abstract_target_scales_in_range():
    # 8000 * 3% = 240 -> capped to ABSTRACT_MAX_WORDS (230)
    assert config.abstract_target_word_count(8000) == config.ABSTRACT_MAX_WORDS
    # 6000 * 3% = 180 (between min and max)
    assert config.abstract_target_word_count(6000) == 180


def test_validate_structural_flags_250_plus_as_too_long():
    """A >=250-word abstract is flagged too long regardless of a lenient target
    (the max is hard-capped below ABSTRACT_HARD_MAX_WORDS)."""
    abstract = " ".join(["word"] * 260)
    result = abstract_validation.validate_structural(abstract, target_word_count=230)
    assert result["word_count"] == 260
    assert any("too long" in w.lower() for w in result["warnings"])


def test_validate_structural_under_limit_not_flagged():
    abstract = " ".join(["word"] * 220)
    result = abstract_validation.validate_structural(abstract, target_word_count=230)
    assert not any("too long" in w.lower() for w in result["warnings"])
