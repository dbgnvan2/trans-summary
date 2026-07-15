"""Contract tests for the remaining P19-audit findings A4/A6/A7/A8/A12.

Spec:  TODO.md#p19-contract-audit-findings
Tests: this file

  A4  — extract_closing_conclusion used a single-group re.findall, capturing only
        section NUMBERS and discarding the closing body, so the conclusion search
        always failed and the required conclusion-coverage check was skipped.
  A6  — parse_section_range truncated a multi-segment citation to its first range
        ('7-8, 15, 33-35' -> [7,8]), deflating section grounding.
  A7  — verify_highlights_bs4.load_source_quotes read an abandoned bowen/emphasis
        format, returning [] on the real artifacts and "verifying nothing".
  A8  — the top_lens was accepted on a truthy-dict gate, never reconciled to the
        ranked lenses the producer actually wrote (a hallucinated lens rode through).
  A12 — the abstract word count included the forbidden '# Abstract' header.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import abstract_pipeline  # noqa: E402
import abstract_validation  # noqa: E402
import summary_pipeline  # noqa: E402


# ---------------------------------------------------------------------------
# A6 — parse_section_range must expand every comma-separated segment
# ---------------------------------------------------------------------------

def test_a6_multisegment_range_is_fully_expanded():
    assert summary_pipeline.parse_section_range("7-8, 15, 33-35") == [7, 8, 15, 33, 34, 35]


def test_a6_single_range_and_list_still_work():
    assert summary_pipeline.parse_section_range("6-14") == list(range(6, 15))
    assert summary_pipeline.parse_section_range("6, 8, 10") == [6, 8, 10]


def test_a6_leading_range_no_longer_swallows_the_rest():
    # The old anchored re.match returned only [3, 4]; the trailing singles were lost.
    assert summary_pipeline.parse_section_range("3-4, 25-26, 49") == [3, 4, 25, 26, 49]


def test_a6_word_prefixed_segments_are_not_dropped():
    # Regression (learning-qa F2): anchored re.match dropped numbers behind a
    # leading word like the model's own "Section(s) N" header wording.
    assert summary_pipeline.parse_section_range("Sections 7-8, 15") == [7, 8, 15]
    assert summary_pipeline.parse_section_range("Section 7") == [7]
    assert summary_pipeline.parse_section_range("Sections 3, 4") == [3, 4]


# ---------------------------------------------------------------------------
# A4 — extract_closing_conclusion must search the closing BODY, not the numbers
# ---------------------------------------------------------------------------

def _multi_section_transcript(n=50, closing_sentence="In conclusion, the pattern holds."):
    parts = []
    for i in range(1, n + 1):
        body = f"Body text for section {i} discussing the material at length."
        if i == n:
            body = f"{body} {closing_sentence}"
        parts.append(f"## Section {i} - Heading ([00:{i:02d}:00]).\n{body}\n")
    return "\n".join(parts)


def test_a4_recovers_closing_sentence_from_body():
    transcript = _multi_section_transcript()
    result = abstract_pipeline.extract_closing_conclusion(transcript, section_count=50)
    assert result != "No explicit conclusion stated", (
        "closing body was discarded (only section numbers were searched) — A4"
    )
    assert "in conclusion" in result.lower()


def test_a4_absent_conclusion_still_reports_default():
    # A closing with none of the conclusion indicators returns the honest default.
    transcript = _multi_section_transcript(closing_sentence="Thanks everyone, good night.")
    result = abstract_pipeline.extract_closing_conclusion(transcript, section_count=50)
    assert result == "No explicit conclusion stated"


# ---------------------------------------------------------------------------
# A7 — load_source_quotes must read the REAL bowen + emphasis-scored formats
# ---------------------------------------------------------------------------

def test_a7_reads_real_bowen_format(tmp_path):
    from verify_highlights_bs4 import load_source_quotes

    f = tmp_path / "bowen.md"
    f.write_text(
        "## Bowen References\n\n"
        "### Pseudo-Self / No Self [01:20:09]\n"
        '> "Bowen\'s basic ideas that were really pioneering the concept of self."\n',
        encoding="utf-8",
    )
    quotes = load_source_quotes(f)
    assert len(quotes) == 1, "real '### Concept\\n> \"quote\"' bowen format must parse (A7)"
    label, quote = quotes[0]
    assert "Pseudo-Self" in label
    assert quote.startswith("Bowen's basic ideas")


def test_a7_reads_real_emphasis_scored_format(tmp_path):
    from verify_highlights_bs4 import load_source_quotes

    f = tmp_path / "emphasis-scored.md"
    f.write_text(
        "[Clinical - C1 - Rank: 95% | 00:00:07] Concept: Early hypothesis\n"
        '"One of her hypotheses in that first initial session was she is avoiding growing up."\n\n'
        "[Explicit - A3 - Rank: 90% | 00:20:11] Concept: Cannot function independently\n"
        '"She can\'t do it without me."\n',
        encoding="utf-8",
    )
    quotes = load_source_quotes(f)
    assert len(quotes) == 2, "real emphasis-scored format must parse (A7)"
    assert quotes[0][1].startswith("One of her hypotheses")


def test_a7_legacy_format_still_parses(tmp_path):
    from verify_highlights_bs4 import load_source_quotes

    f = tmp_path / "legacy.md"
    f.write_text('> **Differentiation:** "A defined self holds its position."\n', encoding="utf-8")
    quotes = load_source_quotes(f)
    assert len(quotes) == 1
    assert quotes[0][0] == "Differentiation"


# ---------------------------------------------------------------------------
# A8 — top_lens must be grounded in the lenses actually generated
# ---------------------------------------------------------------------------

_LENSES = (
    "## Lenses (Ranked)\n\n"
    '1. **"She Can\'t Do It Without Me" — The Belief That Keeps Adult Children Stuck**\n'
    "   - Description: ...\n\n"
    "2. **The Turning Point No One Talks About: Facing the Worst-Case Scenario**\n"
    "   - Description: ...\n"
)


def test_a8_grounded_top_lens_accepted():
    from extraction_pipeline import _top_lens_is_grounded

    top = {"title": '"She Can\'t Do It Without Me" — The Belief That Keeps Adult Children Stuck'}
    assert _top_lens_is_grounded(top, _LENSES) is True


def test_a8_hallucinated_top_lens_rejected():
    from extraction_pipeline import _top_lens_is_grounded

    top = {"title": "A Completely Invented Lens About Something Never Generated"}
    assert _top_lens_is_grounded(top, _LENSES) is False


def test_a8_empty_or_missing_title_rejected():
    from extraction_pipeline import _top_lens_is_grounded

    assert _top_lens_is_grounded({}, _LENSES) is False
    assert _top_lens_is_grounded({"title": ""}, _LENSES) is False
    assert _top_lens_is_grounded({"title": "anything"}, "") is False


def test_a8_stopword_only_title_not_grounded():
    # Regression (learning-qa F5): a title reusing only common filler words must not
    # false-match via token overlap; grounding is on CONTENT tokens only.
    from extraction_pipeline import _top_lens_is_grounded

    assert _top_lens_is_grounded({"title": "The That It Of And To Me"}, _LENSES) is False


def test_a8_paraphrase_with_shared_content_words_is_grounded():
    from extraction_pipeline import _top_lens_is_grounded

    # Smart-quotes + em-dash variant of lens #1 — same content words, must ground.
    top = {"title": "“She Can’t Do It Without Me” — The Belief That Keeps Adult Children Stuck"}
    assert _top_lens_is_grounded(top, _LENSES) is True


# ---------------------------------------------------------------------------
# A12 — abstract word count must exclude a leading '# Abstract' header
# ---------------------------------------------------------------------------

def test_a12_word_count_excludes_leading_header():
    body = " ".join(f"word{i}" for i in range(200))  # 200-word body
    with_header = f"# Abstract\n\n{body}"
    result = abstract_validation.validate_structural(with_header, target_word_count=200)
    assert result["word_count"] == 200, (
        "leading '# Abstract' header must not inflate the word count (A12)"
    )


def test_a12_plain_abstract_unaffected():
    body = " ".join(f"word{i}" for i in range(200))
    result = abstract_validation.validate_structural(body, target_word_count=200)
    assert result["word_count"] == 200
