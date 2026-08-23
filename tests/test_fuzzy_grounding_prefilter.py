"""H10 (review 2026-07-18): the fuzzy grounding scan must short-circuit an ungrounded
needle before the O(haystack x needle) sliding window.

find_text_in_content's sliding window has no early stop when nothing matches, so an
ungrounded (hallucinated / heavily paraphrased) quote scans every window position —
minutes of CPU on a long transcript, called 2-4x per Bowen reference. The cheap
distinct-word coverage pre-filter must reject it in O(haystack), while a genuinely
grounded quote must still match.
"""
import config
import transcript_utils as tu
from transcript_utils import find_text_in_content

_LONG_HAYSTACK = "the quick brown fox jumps over the lazy dog. " * 2000


def test_ungrounded_needle_returns_no_match():
    needle = "zulu yankee xray whiskey victor tango"  # shares no words with haystack
    assert find_text_in_content(needle, _LONG_HAYSTACK, aggressive_normalization=True) == (None, None, 0)


def test_ungrounded_needle_skips_sliding_window(monkeypatch):
    """Pin the optimization itself: the pre-filter returns before any SequenceMatcher
    comparison runs. Without the fix this loops len(haystack)-needle_len+1 times."""
    needle = "zulu yankee xray whiskey victor tango"
    calls = {"n": 0}
    real = tu.SequenceMatcher

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(tu, "SequenceMatcher", counting)
    find_text_in_content(needle, _LONG_HAYSTACK, aggressive_normalization=True)
    assert calls["n"] == 0, "prefilter should short-circuit before the sliding window"


def test_grounded_fuzzy_needle_still_matches():
    # One word dropped -> not an exact substring, so this exercises the fuzzy path
    # (the prefilter must let it through and the window must still find it).
    needle = "the quick brown fox jumps over lazy dog"
    start, end, ratio = find_text_in_content(needle, _LONG_HAYSTACK, aggressive_normalization=True)
    assert start is not None
    assert ratio >= config.FUZZY_MATCH_THRESHOLD


def test_grounded_exact_needle_still_matches():
    needle = "quick brown fox jumps over"
    start, end, ratio = find_text_in_content(needle, _LONG_HAYSTACK, aggressive_normalization=True)
    assert start is not None
    assert ratio >= config.FUZZY_MATCH_THRESHOLD


def test_find_text_in_content_returns_raw_offsets_for_whitespace_diff():
    """Offsets must bound the needle in the RAW haystack, not the normalized one. A
    double space used to shift the offset and produce a misaligned slice, which the
    span guard then (correctly but wastefully) skipped — a recall loss, not corruption."""
    start, end, ratio = find_text_in_content("beta gamma", "X beta   gamma Y")
    assert (start, end, ratio) == (2, 14, 1.0)
    assert "X beta   gamma Y"[start:end] == "beta   gamma"


def test_find_text_in_content_returns_raw_offsets_case_insensitive():
    start, end, ratio = find_text_in_content("Beta Gamma", "prefix beta gamma suffix")
    assert (start, end, ratio) == (7, 17, 1.0)
    assert "prefix beta gamma suffix"[start:end] == "beta gamma"


def test_find_text_in_content_locates_timestamp_split_occurrence():
    """A timestamp between words is stripped by normalize_text, so the raw search must
    tolerate it to find the SAME (first) occurrence the normalized match did — not
    silently re-locate to a later verbatim copy (P11: locate-back != what matched)."""
    hay = "beta [00:01:02] gamma ... later beta gamma"
    start, end, ratio = find_text_in_content("beta gamma", hay)
    assert (start, end, ratio) == (0, 21, 1.0)
    assert hay[start:end] == "beta [00:01:02] gamma"


def test_find_text_in_content_no_partial_word_match():
    """The raw re-location must not match a needle inside a longer word."""
    assert find_text_in_content("beta gamma", "betablocker gamma") == (None, None, 0)
