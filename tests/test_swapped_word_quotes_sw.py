"""SW — a quote whose first or last words were changed still passed the verbatim gate
when the changed words also occurred a little earlier or later in the source (D6 open
item: "I think the future…" for "to me the future…", "My mother" for "her mother").

Synthetic texts only: the real cases come from client material. Each adversarial
test also checks that the quote passed before SW (with the rule switched off), so the
test fails if the rule stops working.
Spec: docs/plan_swapped_word_quotes_2026-10-12.md
"""
from unittest.mock import patch

import config
import validation_pipeline as vp

SOURCE = (
    "The council met twice and the engineers said the old wall would hold for another "
    "season. I really think the way I see it happening, to me the future of the harbour "
    "is a new wall built from the north side with stone from the quarry. The storm was "
    "the worst in thirty years, which nobody disputed at the meeting of the council."
)


def _coverage(quote, source=SOURCE, rule=True):
    if rule:
        return vp._quote_word_coverage(quote, source)
    with patch.object(vp, "_stray_edge_words", lambda *a: 0):
        return vp._quote_word_coverage(quote, source)


def _caught(quote, source=SOURCE):
    """Passed before SW (coverage 1.0 without the rule), fails with it."""
    return _coverage(quote, source, rule=False) == 1.0 and _coverage(quote, source) < 1.0


def test_sw1_changed_first_words_fail():
    """Adversarial (P7): "I think" replaces "to me"; "I think" occurs a few words earlier,
    with "really" between, so it aligns as two short blocks ("I" | "think")."""
    assert _caught("I think the future of the harbour is a new wall built from the north side")
    assert not vp.quote_is_verbatim_for_gate(
        "I think the future of the harbour is a new wall built from the north side", SOURCE)[0]


def test_sw1_changed_lead_as_one_block_fails():
    """SW review: the original D6 shape, a contiguous 2-word changed lead."""
    source = SOURCE.replace("I really think the way", "I think the way")
    assert _caught("I think the future of the harbour is a new wall built from the north side",
                   source)


def test_sw1_changed_three_word_lead_fails():
    """SW review: a changed lead of three words ("I see it" for "to me")."""
    assert _caught("I see it the future of the harbour is a new wall built from the north side")


def test_sw1_changed_last_word_fails():
    """Adversarial: the last word "council" replaces "meeting"; "council" occurs just after."""
    assert _caught("The storm was the worst in thirty years, which nobody disputed at the council")


def test_sw2_true_quote_passes():
    assert _coverage("to me the future of the harbour is a new wall built from the north side") == 1.0


def test_sw2_omitted_word_next_to_the_quote_passes():
    """The first word is beside the rest of the quote, with one omitted word between
    ("she [also] described"). An earlier "she" in the source must not make it fail."""
    source = "She said she was tired. " * 3 + "And she also described the storm as the worst in years."
    assert _coverage("She described the storm as the worst in years.", source) == 1.0


def test_sw2_marked_omission_passes():
    """SW review: an omission the quote marks with an ellipsis is not a swap."""
    source = ("They agreed that the family, as I have said many times before in these talks, "
              "is an emotional unit and that nobody escapes it entirely.")
    for quote in ("The family ... is an emotional unit and that nobody escapes it entirely.",
                  "The family … is an emotional unit and that nobody escapes it entirely.",
                  "The family, as I have said many times before ... nobody escapes it entirely."):
        assert _coverage(quote, source) == 1.0, quote


def test_sw2_inner_word_between_omissions_passes():
    """A short block inside a quote, with omitted words on both sides, is the speaker's
    word in its place, not a swap."""
    source = ("I had worked that out I know this is not terribly clear but I realized that "
              "at that moment that the way I was relating to her was the problem.")
    quote = "I had worked that out. I realized the way I was relating to her was the problem."
    assert _coverage(quote, source) == 1.0


def test_sw2_quote_starting_mid_sentence_passes():
    assert _coverage("the engineers said the old wall would hold for another season") == 1.0


def test_sw3_known_limit_unmarked_edge_omission_fails():
    """Documented limit: an omission right after a quote's first words, not marked with
    an ellipsis, looks the same as a swap and fails. None of the 782 real passing quotes
    has this shape once the near-word check applies."""
    source = ("They agreed that the family, as I have said many times before in these talks, "
              "is an emotional unit and that nobody escapes it entirely.")
    assert _caught("The family is an emotional unit and that nobody escapes it entirely.", source)


def test_sw3_thresholds_are_config():
    assert config.QUOTE_STRAY_BLOCK_MAX_WORDS == 4
    assert config.QUOTE_STRAY_BLOCK_MIN_GAP == 3
    assert config.QUOTE_STRAY_NEAR_WORDS == 3


def test_sw4_one_gap_quote_is_not_counted_twice():
    """SW review: with one large gap, the lead and the tail are each other's body.
    Only the shorter side is counted as changed, so the reported coverage is not 0."""
    source = "Then we knew the family as I said is an emotional unit for good."
    quote = "we knew the family is an emotional unit"
    assert _coverage(quote, source, rule=False) == 1.0
    assert _coverage(quote, source) == 0.5


def test_sw4_word_repeated_across_an_ellipsis_keeps_positions():
    """SW review: the normalizer collapses a word repeated across a marker; the second
    marker's position must still be found."""
    assert vp._ellipsis_word_positions("we went home ... home and then ... the family is") == {3, 5}
    assert vp._ellipsis_word_positions("no marker here") == set()
