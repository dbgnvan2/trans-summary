"""Tests for transcript_validate_consistency.py — the cross-artifact consistency check.

The key behaviour under test: an empty content-derived artifact (Bowen references)
on a transcript that recounts Murray Bowen the person must FAIL. The signal is
person-recollection density computed by ``bowen_attribution.find_bowen_person_
attributions`` — the SAME detector the extractor's filter uses — NOT theory
vocabulary ("differentiation", "fusion", "Bowen theory…"): a theory-dense talk
that never recounts Bowen the person legitimately has zero references.
"""

from transcript_validate_consistency import (
    _content_words,
    count_items,
    count_person_recollections,
    distinct_person_markers,
    keyword_overlap,
    normalize,
    parse_key_terms,
    run,
)


def test_normalize_collapses_and_strips():
    assert normalize("Differentiation of Self!") == "differentiation of self"
    assert normalize("Dr. Bowen's theory") == "dr bowen s theory"


def test_keyword_overlap_is_exact_word_match():
    """Exact-word semantics: a morphological variant (homeostatic) does NOT ground
    a term (Homeostasis), nor does a near-miss — a looser match was found to
    silently suppress warnings across every caller (P7)."""
    assert keyword_overlap("Homeostasis", "monitoring homeostatic threats") == 0.0
    assert keyword_overlap("family", "families are the unit here") == 0.0
    assert keyword_overlap("internal", "interpersonal dynamics") == 0.0
    assert keyword_overlap("family", "the family is a unit") == 1.0


def test_content_words_strips_derived_attribution_scaffold():
    """The attribution scaffold is DERIVED from the detector's own verb lists, so
    a recollection matched via ANY detector verb ('believed', 'concluded', …) has
    that verb stripped — not just the verbs a hand-copied list happened to name."""
    cw = _content_words("bowen believed differentiation of self is key")
    assert "bowen" not in cw and "believed" not in cw
    assert "differentiation" in cw and "self" in cw
    # 'concluded' was absent from an earlier hand-maintained scaffold
    assert "concluded" not in _content_words("bowen concluded the family is a unit")


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


# ---------------------------------------------------------------------------
# Cross-artifact reconciliation (gap #3) — artifact ↔ artifact
# ---------------------------------------------------------------------------
def test_run_flags_abstract_recollection_dropped_from_empty_bowen(tmp_path):
    """The abstract recounts Bowen the person (>= 2 recollections) but
    bowen-references.md is EMPTY -> recollections the pipeline surfaced were
    dropped (FAIL)."""
    base = "Sample - Author - 2024-01-01"
    proj = tmp_path / base
    proj.mkdir()
    (proj / f"{base} - formatted.md").write_text(
        "some transcript words here that are long enough", encoding="utf-8")
    (proj / f"{base} - abstract-generated.md").write_text(
        "Bowen said the family is an emotional unit. To quote Bowen, fusion is the default.",
        encoding="utf-8")
    (proj / f"{base} - bowen-references.md").write_text(
        "## Bowen References\n", encoding="utf-8")
    fails, _warns, _info = run(proj)
    assert any("Abstract recounts Bowen the person" in f and "EMPTY" in f
               for f in fails)


def test_run_does_not_fail_single_abstract_recollection(tmp_path):
    """A single incidental abstract recollection (e.g. 'Bowen's framework') + empty
    bowen-references is a WARN, not a FAIL — mirrors the >=2 transcript threshold."""
    base = "Sample - Author - 2024-01-01"
    proj = tmp_path / base
    proj.mkdir()
    (proj / f"{base} - formatted.md").write_text(
        "some transcript words here that are long enough", encoding="utf-8")
    (proj / f"{base} - abstract-generated.md").write_text(
        "Drawing on Bowen's framework, this talk explores differentiation.",
        encoding="utf-8")
    (proj / f"{base} - bowen-references.md").write_text(
        "## Bowen References\n", encoding="utf-8")
    fails, warns, _info = run(proj)
    assert not fails
    assert any("possibly an incidental mention" in w for w in warns)


def test_run_warns_abstract_recollection_without_bowen_artifact(tmp_path):
    """A missing bowen-references.md (stage skipped) is a WARN, not a FAIL, even
    when the abstract recounts Bowen the person."""
    base = "Sample - Author - 2024-01-01"
    proj = tmp_path / base
    proj.mkdir()
    (proj / f"{base} - formatted.md").write_text(
        "some transcript words here that are long enough", encoding="utf-8")
    (proj / f"{base} - abstract-generated.md").write_text(
        "Bowen said the family is an emotional unit.", encoding="utf-8")
    fails, warns, _info = run(proj)
    assert not fails
    assert any("no bowen-references.md artifact is present" in w for w in warns)


def test_run_passes_abstract_recollection_reflected_in_bowen(tmp_path):
    """An abstract recollection that IS captured in bowen-references.md is not
    flagged (no false drop)."""
    base = "Sample - Author - 2024-01-01"
    proj = tmp_path / base
    proj.mkdir()
    (proj / f"{base} - formatted.md").write_text("transcript text", encoding="utf-8")
    (proj / f"{base} - abstract-generated.md").write_text(
        "Bowen said the family is an emotional unit.", encoding="utf-8")
    (proj / f"{base} - bowen-references.md").write_text(
        "## Bowen References\n\n### Concept\n> \"Bowen said the family is an emotional unit\"\n",
        encoding="utf-8")
    fails, warns, _info = run(proj)
    assert not any("Abstract recounts Bowen the person" in f for f in fails)
    assert not any("not reflected in bowen-references" in w for w in warns)


def test_run_warns_abstract_recollection_content_not_in_bowen(tmp_path):
    """A POPULATED bowen-references.md whose content words are disjoint from an
    abstract recollection -> the recollection's substance is missing -> WARN (the
    drop path, the mirror of the reflected-pass test)."""
    base = "Sample - Author - 2024-01-01"
    proj = tmp_path / base
    proj.mkdir()
    (proj / f"{base} - formatted.md").write_text("transcript text", encoding="utf-8")
    (proj / f"{base} - abstract-generated.md").write_text(
        "Bowen believed differentiation of self is crucial to families.",
        encoding="utf-8")
    (proj / f"{base} - bowen-references.md").write_text(
        "## Bowen References\n\n### Unrelated\n> \"Bowen discussed triangles in detail\"\n",
        encoding="utf-8")
    _fails, warns, _info = run(proj)
    assert any("not reflected in bowen-references" in w for w in warns)


def test_run_warns_orphan_key_term(tmp_path):
    """A key term reflected in neither the abstract nor any topic is a candidate
    orphan -> WARN."""
    base = "Sample - Author - 2024-01-01"
    proj = tmp_path / base
    proj.mkdir()
    (proj / f"{base} - formatted.md").write_text("transcript text", encoding="utf-8")
    (proj / f"{base} - abstract-generated.md").write_text(
        "This talk is about family systems.", encoding="utf-8")
    (proj / f"{base} - key-terms.md").write_text(
        "### Zygotic Differentiation\nA concept.\n", encoding="utf-8")
    (proj / f"{base} - topics.md").write_text(
        "### Family Systems\nTopic body.\n", encoding="utf-8")
    _fails, warns, _info = run(proj)
    assert any("not reflected in the abstract or any topic" in w for w in warns)


def test_run_does_not_flag_reflected_key_term(tmp_path):
    """A key term present in the abstract is not an orphan."""
    base = "Sample - Author - 2024-01-01"
    proj = tmp_path / base
    proj.mkdir()
    (proj / f"{base} - formatted.md").write_text("transcript text", encoding="utf-8")
    (proj / f"{base} - abstract-generated.md").write_text(
        "This talk discusses differentiation of self in families.", encoding="utf-8")
    (proj / f"{base} - key-terms.md").write_text(
        "### Differentiation of Self\nA concept.\n", encoding="utf-8")
    _fails, warns, _info = run(proj)
    assert not any("not reflected in the abstract" in w for w in warns)


def test_run_skips_orphan_check_without_topics_artifact(tmp_path):
    """With no topics artifact, the orphan check must not fire — a key term absent
    from the abstract alone is not an orphan (the 'not in any topic' half is
    vacuous)."""
    base = "Sample - Author - 2024-01-01"
    proj = tmp_path / base
    proj.mkdir()
    (proj / f"{base} - formatted.md").write_text("transcript text", encoding="utf-8")
    (proj / f"{base} - abstract-generated.md").write_text(
        "This talk is about family systems.", encoding="utf-8")
    (proj / f"{base} - key-terms.md").write_text(
        "### Zygotic Differentiation\nA concept.\n", encoding="utf-8")
    # no topics.md
    _fails, warns, _info = run(proj)
    assert not any("not reflected in the abstract or any topic" in w for w in warns)


def test_run_warns_topic_barely_reflected_in_abstract(tmp_path):
    """A topic the abstract silently omits (while reflecting others) is flagged
    individually, not just via the max-overlap signal."""
    base = "Sample - Author - 2024-01-01"
    proj = tmp_path / base
    proj.mkdir()
    (proj / f"{base} - formatted.md").write_text("transcript text here", encoding="utf-8")
    (proj / f"{base} - abstract-generated.md").write_text(
        "This talk is about family anxiety and triangles.", encoding="utf-8")
    (proj / f"{base} - topics.md").write_text(
        "### Family Anxiety\nBody.\n\n### Zygotic Mutation\nBody.\n", encoding="utf-8")
    _fails, warns, _info = run(proj)
    assert any("barely reflected in the abstract" in w for w in warns)
