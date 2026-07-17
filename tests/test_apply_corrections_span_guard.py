"""Init Val auto-apply must never overwrite a span that doesn't match the
correction's original_text (a mis-located fuzzy span corrupted a real run:
'differentiation of self' -> 'selfhere's' + duplicated text)."""

from unittest.mock import MagicMock, patch

import transcript_initial_validation_v2 as v2


def _validator():
    val = v2.TranscriptValidatorV2.__new__(v2.TranscriptValidatorV2)
    val.logger = MagicMock()
    return val


def test_span_matches_original_normalizes_and_rejects_mismatch():
    assert v2._span_matches_original("beta gamma", "beta gamma") is True
    assert v2._span_matches_original("Beta,  gamma!", "beta gamma") is True   # case/punct/ws
    assert v2._span_matches_original("Alpha", "phrase not present here") is False
    assert v2._span_matches_original("", "beta gamma") is False


def test_apply_skips_mislocated_fuzzy_span(tmp_path):
    """The 0-exact-match fuzzy fallback must NOT overwrite text when the located
    span doesn't actually match the original — regression for the corruption."""
    content = "Alpha beta gamma delta epsilon zeta."
    f = tmp_path / "t.txt"
    f.write_text(content, encoding="utf-8")
    out = tmp_path / "out.txt"
    corr = [{"original_text": "phrase not present verbatim",
             "suggested_correction": "XXX", "error_type": "spelling"}]
    # fuzzy matcher returns a WRONG span (0..5 == "Alpha") with a high ratio
    with patch("transcript_utils.find_text_in_content", return_value=(0, 5, 0.99)):
        _p, applied, skipped = _validator().apply_corrections_safe(f, corr, out)
    assert out.read_text(encoding="utf-8") == content   # transcript NOT corrupted
    assert applied == 0
    assert any("mis-located" in s.lower() for s in skipped)


def test_apply_applies_exact_match(tmp_path):
    content = "Alpha beta gamma delta."
    f = tmp_path / "t.txt"
    f.write_text(content, encoding="utf-8")
    out = tmp_path / "out.txt"
    corr = [{"original_text": "beta gamma",
             "suggested_correction": "BETA GAMMA", "error_type": "spelling"}]
    _p, applied, _sk = _validator().apply_corrections_safe(f, corr, out)
    assert "BETA GAMMA" in out.read_text(encoding="utf-8")
    assert applied == 1


def test_apply_applies_verified_fuzzy_span(tmp_path):
    """A fuzzy span that DOES match the original (only case differs, so exact
    match missed) is still applied."""
    content = "Alpha beta gamma delta."
    f = tmp_path / "t.txt"
    f.write_text(content, encoding="utf-8")
    out = tmp_path / "out.txt"
    corr = [{"original_text": "Beta Gamma",  # case differs -> no exact re match
             "suggested_correction": "REPL", "error_type": "spelling"}]
    with patch("transcript_utils.find_text_in_content", return_value=(6, 16, 0.99)):
        _p, applied, _sk = _validator().apply_corrections_safe(f, corr, out)
    result = out.read_text(encoding="utf-8")
    assert "REPL" in result and applied == 1
