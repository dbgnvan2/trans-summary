"""Q2 — an emphasis quote that contains a quotation is read whole, both from the
model's response and from the saved file (it used to stop at the inner quote mark).

Spec: docs/plan_todo_triage_2026-10-11.md#Q2
"""
from transcript_utils import parse_scored_emphasis_output

QUOTE = 'Bowen used to say "be a self" and he meant it in every relationship he had.'


def test_q2_nested_straight_quotes_read_whole():
    text = f'[Explicit - A1 - Rank: 96%] Concept: Self\n"{QUOTE}"\n(Section 3)\n'
    assert parse_scored_emphasis_output(text)[0]["quote"] == QUOTE


def test_q2_nested_curly_quotes_read_whole():
    q = "Bowen used to say “be a self” and he meant it in every relationship he had."
    text = f"[Explicit - A1 - Rank: 96%] Concept: Self\n“{q}”\n"
    assert parse_scored_emphasis_output(text)[0]["quote"] == q


def test_q2_quote_ending_in_a_quotation_read_whole():
    q = 'He told every family the same thing: "be a self"'
    text = f'[Explicit - A1 - Rank: 96%] Concept: Self\n"{q}"\n'
    assert parse_scored_emphasis_output(text)[0]["quote"] == q


def test_q2_saved_format_round_trips():
    """The saver's own layout (extraction_pipeline.extract_scored_emphasis)."""
    saved = (f'[Explicit - A1 - Rank: 96% | 00:05:29] Concept: Self\n"{QUOTE}"\n\n'
             '[Implicit - B2 - Rank: 90%] Concept: Anxiety\n"Anxiety moves through the family system."')
    items = parse_scored_emphasis_output(saved)
    assert [i["quote"] for i in items] == [QUOTE, "Anxiety moves through the family system."]
    assert items[0]["timestamp"] == "00:05:29"


def test_q2_quoted_concept_name_is_not_the_quote():
    """Adversarial: a quote mark in the header must not be taken as the quote."""
    text = '[Explicit - A1 - Rank: 96%] Concept: The "togetherness" force\n"Togetherness pulls people toward one another in a family."\n'
    item = parse_scored_emphasis_output(text)[0]
    assert item["quote"] == "Togetherness pulls people toward one another in a family."
    assert item["concept"] == 'The "togetherness" force'


def test_q2_quote_followed_by_text_on_the_same_line():
    """A closing mark followed by more text on the line still ends the quote."""
    text = '[Explicit - A1 - Rank: 96%] Concept: Self\n"Differentiation is a lifelong effort." (00:12:34)\n'
    assert parse_scored_emphasis_output(text)[0]["quote"] == "Differentiation is a lifelong effort."


def test_q2_quote_does_not_run_into_a_later_line():
    """Adversarial (sweep): a later line ending in a quote mark is not joined on."""
    text = ('[Explicit - A1 - Rank: 96%] Concept: Self\n'
            '"Differentiation is a lifelong effort." (00:12:34)\n'
            'Why: Bowen calls this "solid self"\n')
    assert parse_scored_emphasis_output(text)[0]["quote"] == "Differentiation is a lifelong effort."
