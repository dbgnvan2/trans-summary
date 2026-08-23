"""Init Val auto-apply (v1 AND v2) must never overwrite a span that doesn't
match the correction's original_text. A mis-located fuzzy span corrupted a real
run ('differentiation of self' -> 'selfhere's' + duplicated text)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import transcript_utils
import transcript_initial_validation as v1
import transcript_initial_validation_v2 as v2


def _v2():
    val = v2.TranscriptValidatorV2.__new__(v2.TranscriptValidatorV2)
    val.logger = MagicMock()
    return val


def _v1():
    val = v1.TranscriptValidator.__new__(v1.TranscriptValidator)
    val.logger = MagicMock()
    return val


def test_span_matches_original_normalizes_and_rejects_mismatch():
    assert transcript_utils.span_matches_original("beta gamma", "beta gamma") is True
    assert transcript_utils.span_matches_original("Beta,  gamma!", "beta gamma") is True  # case/punct/ws
    assert transcript_utils.span_matches_original("Alpha", "phrase not present here") is False
    assert transcript_utils.span_matches_original("", "beta gamma") is False


def test_v2_skips_mislocated_fuzzy_span_mocked(tmp_path):
    """Guard positive test: a fuzzy span that doesn't contain the original is
    skipped, not applied (content unchanged)."""
    content = "Alpha beta gamma delta epsilon zeta."
    f = tmp_path / "t.txt"
    f.write_text(content, encoding="utf-8")
    out = tmp_path / "out.txt"
    corr = [{"original_text": "phrase not present verbatim",
             "suggested_correction": "XXX", "error_type": "spelling"}]
    with patch("transcript_utils.find_text_in_content", return_value=(0, 5, 0.99)):
        _p, applied, skipped = _v2().apply_corrections_safe(f, corr, out)
    assert out.read_text(encoding="utf-8") == content
    assert applied == 0
    assert any("mis-located" in s.lower() for s in skipped)


def test_v2_applies_whitespace_difference_correction(tmp_path):
    """A normalization-affecting whitespace difference (double space) used to make
    the REAL find_text_in_content return a misaligned span, so the guard skipped a
    LEGITIMATE correction (recall loss, not corruption). With raw-text offset
    re-location, the correction now APPLIES to the exact span (replacing
    'beta   gamma' with 'XXX'); a true mis-location is still skipped (see the mocked
    test above)."""
    content = "Alpha beta   gamma delta epsilon."   # double space inside the phrase
    f = tmp_path / "t.txt"
    f.write_text(content, encoding="utf-8")
    out = tmp_path / "out.txt"
    corr = [{"original_text": "beta gamma",
             "suggested_correction": "XXX", "error_type": "spelling"}]
    _p, applied, _sk = _v2().apply_corrections_safe(f, corr, out)
    assert out.read_text(encoding="utf-8") == "Alpha XXX delta epsilon."
    assert applied == 1


def test_v1_applies_whitespace_difference_correction(tmp_path):
    """The v1 validator's apply_corrections applies the same whitespace-difference
    correction (F1)."""
    content = "Alpha beta   gamma delta epsilon."
    f = tmp_path / "t.txt"
    f.write_text(content, encoding="utf-8")
    out = tmp_path / "out.txt"
    corr = [{"original_text": "beta gamma",
             "suggested_correction": "XXX", "error_type": "spelling"}]
    result = _v1().apply_corrections(f, corr, out)
    assert Path(result).read_text(encoding="utf-8") == "Alpha XXX delta epsilon."


def test_v2_applies_exact_match(tmp_path):
    content = "Alpha beta gamma delta."
    f = tmp_path / "t.txt"
    f.write_text(content, encoding="utf-8")
    out = tmp_path / "out.txt"
    corr = [{"original_text": "beta gamma",
             "suggested_correction": "BETA GAMMA", "error_type": "spelling"}]
    _p, applied, _sk = _v2().apply_corrections_safe(f, corr, out)
    assert "BETA GAMMA" in out.read_text(encoding="utf-8")
    assert applied == 1


def test_v2_applies_verified_fuzzy_span(tmp_path):
    """A fuzzy span that DOES match the original (only case differs) is applied."""
    content = "Alpha beta gamma delta."
    f = tmp_path / "t.txt"
    f.write_text(content, encoding="utf-8")
    out = tmp_path / "out.txt"
    corr = [{"original_text": "Beta Gamma",  # case differs -> no exact re match
             "suggested_correction": "REPL", "error_type": "spelling"}]
    with patch("transcript_utils.find_text_in_content", return_value=(6, 16, 0.99)):
        _p, applied, _sk = _v2().apply_corrections_safe(f, corr, out)
    assert "REPL" in out.read_text(encoding="utf-8") and applied == 1
