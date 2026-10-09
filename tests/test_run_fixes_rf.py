"""RF.A-RF.E: fixes from the 2026-10-09 Kerr run (docs/plan_run_fixes_2026-10-09.md).

That run was blocked by wrong heading timestamps (m:ss read as h:mm) and by a
verbatim quote that only changed the inner quotation marks; the blog stage stopped
without a recorded reason, and the GUI offered no Simple Web stage.
"""
from pathlib import Path

import config
import validation_pipeline as vp

FIX = Path(__file__).resolve().parent / "fixtures" / "prose_real" / \
    "Why Families Repeat the Same Patterns - Michael Kerr - 2026-09-13"
BASE = FIX.name

# The emphasis quote from the 2026-10-09 run, verbatim: the speaker's inner
# "He's smiling..." became 'He's smiling...'.
KERR_QUOTE = (
    "Then I looked up at him, and he hadn't said much of anything, and I said, "
    "'He's smiling. What's he smiling about?' But then I realized he hadn't got "
    "tangled up with it, with me. And that was a big step to help me start doing "
    "something differently. It was the first time I had seen that he could stay "
    "outside the system with my utterings and utterings and utterings."
)


def _formatted():
    return (FIX / f"{BASE} - formatted.md").read_text(encoding="utf-8")


# --- RF.B: quote-within-a-quote --------------------------------------------------

def test_rfb1_nested_single_quotes_are_verbatim():
    source = _formatted()
    assert vp._emphasis_quote_found_ratio(KERR_QUOTE, source) >= config.EMPHASIS_QUOTE_FOUND_RATIO
    assert vp._quote_word_coverage(KERR_QUOTE, source) >= config.QUOTE_MIN_WORD_COVERAGE


def test_rfb1_curly_inner_quotes_are_verbatim():
    curly = KERR_QUOTE.replace("'He's", "‘He's").replace("about?'", "about?’")
    assert vp._emphasis_quote_found_ratio(curly, _formatted()) >= config.EMPHASIS_QUOTE_FOUND_RATIO


def test_rfb1_changed_word_inside_nested_quote_still_fails():
    # P7: a quote that looks right but changes a word inside the inner quotation.
    altered = KERR_QUOTE.replace("'He's smiling.", "'He's laughing.")
    assert vp._quote_word_coverage(altered, _formatted()) < config.QUOTE_MIN_WORD_COVERAGE


def test_rfb1_contractions_kept():
    assert vp._without_disfluencies("'He's here,' I said. Don't go.") == "he's here i said don't go"
    assert vp._without_disfluencies("he's") != vp._without_disfluencies("hes")


def test_rfb1_quote_ending_inside_a_repeat_is_verbatim():
    # The quote stops at "utterings and utterings and utterings"; the source goes
    # on "... and that was very helpful". Both must collapse the same way.
    assert vp._collapse_disfluencies("my utterings and utterings and utterings".split()) == \
        ["my", "utterings", "and"]
    assert vp._collapse_disfluencies("my utterings and utterings and utterings and that".split()) == \
        ["my", "utterings", "and", "that"]


def test_rfb1_trailing_word_kept_when_no_repeat_was_collapsed():
    # P7: "the dog the" is not a repeat; the final word must not be dropped.
    assert vp._collapse_disfluencies("i saw the dog the".split()) == ["i", "saw", "the", "dog", "the"]
