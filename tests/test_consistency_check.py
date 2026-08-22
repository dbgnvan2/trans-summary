"""Tests for transcript_validate_consistency.py — the cross-artifact consistency check.

The key behaviour under test: an empty content-derived artifact (Bowen references)
on a transcript that is dense in that artifact's domain must FAIL — the exact bug
the check was written to catch.
"""

from transcript_validate_consistency import (
    count_bowen_occurrences,
    count_items,
    normalize,
    parse_key_terms,
    run,
)


def test_normalize_collapses_and_strips():
    assert normalize("Differentiation of Self!") == "differentiation of self"
    assert normalize("Bowen's  theory—") == "bowen s theory"


def test_count_bowen_occurrences_finds_terms():
    text = "differentiation of self, triangles, fusion, and anxiety."
    assert count_bowen_occurrences(text) >= 4


def test_count_items_parses_bowen_format():
    md = (
        "## Bowen References\n\n"
        "### Concept A [00:00:00]\n> \"quote\"\n\n"
        "### Concept B\n> \"quote2\"\n"
    )
    assert count_items(md, "bowen") == 2


def test_count_items_empty_bowen_file_is_zero():
    assert count_items("## Bowen References\n", "bowen") == 0


def test_parse_key_terms_extracts_headers():
    md = "### Differentiation of Self\nDef\n\n### Emotional Cutoff\nDef2\n"
    assert parse_key_terms(md) == ["Differentiation of Self", "Emotional Cutoff"]


def test_run_flags_empty_bowen_on_dense_transcript(tmp_path):
    """The core regression: 0 Bowen references on a Bowen-dense transcript FAILs."""
    base = "Sample - Author - 2024-01-01"
    proj = tmp_path / base
    proj.mkdir()
    transcript = (
        "differentiation of self " * 10
        + "triangles anxiety fusion "
        + "emotional system " * 5
    )
    (proj / f"{base} - formatted.md").write_text(transcript, encoding="utf-8")
    (proj / f"{base} - bowen-references.md").write_text(
        "## Bowen References\n", encoding="utf-8"
    )
    fails, _warns, _info = run(proj)
    assert any("Bowen references are EMPTY" in f for f in fails)


def test_run_passes_when_bowen_populated(tmp_path):
    base = "Sample - Author - 2024-01-01"
    proj = tmp_path / base
    proj.mkdir()
    transcript = "differentiation of self " * 10 + "triangles anxiety fusion"
    (proj / f"{base} - formatted.md").write_text(transcript, encoding="utf-8")
    (proj / f"{base} - bowen-references.md").write_text(
        "## Bowen References\n\n### Concept A\n> \"differentiation\"\n", encoding="utf-8"
    )
    fails, _warns, _info = run(proj)
    assert not any("Bowen references are EMPTY" in f for f in fails)
