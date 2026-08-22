"""Tests for transcript_validate_consistency.py — the cross-artifact consistency check.

The key behaviour under test: an empty content-derived artifact (Bowen references)
on a transcript that recounts Murray Bowen the person must FAIL. The signal is
person-recollection density computed by ``bowen_attribution.find_bowen_person_
attributions`` — the SAME detector the extractor's filter uses — NOT theory
vocabulary ("differentiation", "fusion", "Bowen theory…"): a theory-dense talk
that never recounts Bowen the person legitimately has zero references.
"""

from transcript_validate_consistency import (
    count_items,
    count_person_recollections,
    distinct_person_markers,
    normalize,
    parse_key_terms,
    run,
)


def test_normalize_collapses_and_strips():
    assert normalize("Differentiation of Self!") == "differentiation of self"
    assert normalize("Dr. Bowen's theory") == "dr bowen s theory"


def test_count_person_recollections_finds_markers():
    text = "Bowen said the family is a unit. To quote Bowen, people push for oneness."
    assert count_person_recollections(text) >= 2


def test_count_person_recollections_ignores_theory_vocabulary():
    # Theory terms must NOT count as person recollections (the false-FAIL class).
    text = "Differentiation of self, triangles, fusion, and anxiety in Bowen theory."
    assert count_person_recollections(text) == 0


def test_count_person_recollections_handles_newline_only_sentences():
    """F2 — rough dictation that separates sentences with newlines and no terminal
    punctuation must still count each recollection, not collapse to one unit."""
    text = (
        "Bowen said the family is a unit\n"
        "Bowen wrote about anxiety\n"
        "Bowen said to focus on self"
    )
    assert count_person_recollections(text) == 3


def test_count_person_recollections_bridges_name_verb_newline_split():
    """F1 — a recollection whose person name and verb straddle a newline must
    still count (the extractor collapses newlines to spaces)."""
    text = "Murray Bowen\nsaid the family is an emotional unit."
    assert count_person_recollections(text) == 1


def test_count_person_recollections_bridges_multi_line_straddle():
    """A recollection whose name and verb are separated by an intervening line
    (>= 3 lines) must still count — the extractor collapses ALL whitespace, so
    the bridge must grow past a single pair of lines."""
    text = "Bowen\nalways\nsaid the family is an emotional unit."
    assert count_person_recollections(text) == 1


def test_bridge_guard_stops_before_self_matching_line():
    """The grow-bridge must stop before a line that itself matches, so a
    mid-bridge self-matching recollection is reported cleanly, not folded into a
    polluted join."""
    text = "Bowen\nalways\nBowen said the family is a unit"
    assert distinct_person_markers(text) == ["bowen said the family is a unit"]


def test_density_signal_shares_the_extractors_detector():
    """The density signal must derive from the extractor's OWN detector, not a
    parallel hand-maintained list — an identity check, not a comment (P19 fix)."""
    import bowen_attribution
    import extraction_pipeline as ep

    assert ep._has_bowen_source_attribution is bowen_attribution.has_bowen_source_attribution


def test_possessive_attribution_is_counted():
    """Under-coverage fix: 'Bowen's key insight' is an attribution the extractor
    accepts, so the density signal must count it (was silently dropped before)."""
    text = "Bowen's key insight was about anxiety. Bowen's concept of differentiation follows."
    assert count_person_recollections(text) >= 2


def test_unrecognized_attribution_verb_is_not_counted():
    """Over-coverage fix: verbs the extractor does not recognise (e.g. 'explained',
    'emphasized') must NOT inflate the density — empty may be correct, not a miss."""
    text = "Bowen explained the theory in detail. Bowen emphasized differentiation."
    assert count_person_recollections(text) == 0


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


def test_run_flags_empty_bowen_when_transcript_recounts_bowen(tmp_path):
    """Core regression: 0 Bowen references while the transcript recounts Bowen
    the person -> FAIL."""
    base = "Sample - Author - 2024-01-01"
    proj = tmp_path / base
    proj.mkdir()
    transcript = "Bowen said the family is an emotional unit. To quote Bowen, fusion is the default."
    (proj / f"{base} - formatted.md").write_text(transcript, encoding="utf-8")
    (proj / f"{base} - bowen-references.md").write_text("## Bowen References\n", encoding="utf-8")
    fails, _warns, _info = run(proj)
    assert any("Bowen references are EMPTY" in f for f in fails)


def test_run_does_not_false_fail_on_theory_dense_talk(tmp_path):
    """A theory-dense talk with NO person recollection legitimately has zero
    Bowen references — must NOT be flagged (the P7/P19 false-FAIL fix)."""
    base = "Sample - Author - 2024-01-01"
    proj = tmp_path / base
    proj.mkdir()
    transcript = "Differentiation of self and triangles and fusion are central to the theory."
    (proj / f"{base} - formatted.md").write_text(transcript, encoding="utf-8")
    (proj / f"{base} - bowen-references.md").write_text("## Bowen References\n", encoding="utf-8")
    fails, _warns, _info = run(proj)
    assert not any("Bowen references are EMPTY" in f for f in fails)


def test_run_passes_when_bowen_populated(tmp_path):
    base = "Sample - Author - 2024-01-01"
    proj = tmp_path / base
    proj.mkdir()
    transcript = "Bowen said the family is a unit. To quote Bowen, oneness."
    (proj / f"{base} - formatted.md").write_text(transcript, encoding="utf-8")
    (proj / f"{base} - bowen-references.md").write_text(
        "## Bowen References\n\n### Concept A\n> \"Bowen said\"\n", encoding="utf-8"
    )
    fails, _warns, _info = run(proj)
    assert not any("Bowen references are EMPTY" in f for f in fails)


def test_consistency_check_is_wired_into_release_gate():
    """P21 — the check must be registered in the gate, not CLI-only."""
    import release_gate

    names = [name for name, _fn in release_gate.DEFAULT_CHECKS]
    assert "consistency" in names
    assert any(name == "consistency" and fn is release_gate.check_consistency
               for name, fn in release_gate.DEFAULT_CHECKS)
