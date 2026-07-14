"""Regression tests for the post-Core emphasis/key-terms validators that were
silently finding nothing despite the artifacts existing (see the run-log review).

Root causes fixed:
  - parse_scored_emphasis_output required the header and quote in one block, but
    the saved file separates them with a blank line -> 0 items parsed.
  - the emphasis save wrote header/quote as separate "\\n\\n"-joined entries,
    creating that blank line (write->read round-trip mismatch).
  - _parse_key_terms_section required a "## Key Terms" heading, but the dedicated
    key-terms artifact often has bare "### Term" blocks with no heading.
"""
from transcript_utils import parse_scored_emphasis_output
from validation_pipeline import _parse_key_terms_section


# --- Emphasis parser: both layouts must parse -------------------------------

SAME_BLOCK = '[Clinical - C5 - Rank: 92%] Concept: Losing self\n"He came into therapy about his daughter."'
SPLIT_BLOCK = '[Clinical - C5 - Rank: 92%] Concept: Losing self\n\n"He came into therapy about his daughter."'


def test_emphasis_parses_header_and_quote_in_same_block():
    items = parse_scored_emphasis_output(SAME_BLOCK)
    assert len(items) == 1
    assert items[0]["concept"] == "Losing self"
    assert "daughter" in items[0]["quote"]


def test_emphasis_parses_header_and_quote_split_by_blank_line():
    """The saved-file layout (blank line between header and quote) must parse."""
    items = parse_scored_emphasis_output(SPLIT_BLOCK)
    assert len(items) == 1
    assert items[0]["concept"] == "Losing self"
    assert "daughter" in items[0]["quote"]


def test_emphasis_parses_multiple_split_items_without_crosstalk():
    text = (
        '[Clinical - C5 - Rank: 92%] Concept: First\n\n"quote one here"\n\n'
        '[Explicit - A1 - Rank: 88%] Concept: Second\n\n"quote two here"'
    )
    items = parse_scored_emphasis_output(text)
    assert [i["concept"] for i in items] == ["First", "Second"]
    assert items[0]["quote"] == "quote one here"
    assert items[1]["quote"] == "quote two here"


def test_emphasis_save_format_round_trips():
    """The exact string extract_scored_emphasis now writes must re-parse."""
    items = [
        {"type": "Clinical", "category": "C5", "score": 92, "concept": "Alpha", "quote": "first quote", "timestamp": None},
        {"type": "Explicit", "category": "A1", "score": 88, "concept": "Beta", "quote": "second quote", "timestamp": "00:01:02"},
    ]
    lines = []
    for i in items:
        ts = f" | {i['timestamp']}" if i.get("timestamp") else ""
        lines.append(
            f"[{i['type']} - {i['category']} - Rank: {i['score']}%{ts}] "
            f"Concept: {i['concept']}\n\"{i['quote']}\""
        )
    saved = "\n\n".join(lines)
    parsed = parse_scored_emphasis_output(saved)
    assert len(parsed) == 2
    assert {p["concept"] for p in parsed} == {"Alpha", "Beta"}


# --- Key-terms parser: no "Key Terms" heading -------------------------------

BARE_TERMS = (
    "### Family Diagram\n"
    "A visual tool used to map family members across generations.\n\n"
    "### Catatonia\n"
    "A state of high awareness but inability to relate to others.\n"
)


def test_key_terms_parse_without_key_terms_heading():
    terms = _parse_key_terms_section(BARE_TERMS)
    names = [t for t, _ in terms]
    assert "Family Diagram" in names
    assert "Catatonia" in names


def test_key_terms_parse_with_heading_still_works():
    with_heading = "## Key Terms\n\n" + BARE_TERMS
    terms = _parse_key_terms_section(with_heading)
    assert len(terms) >= 2
