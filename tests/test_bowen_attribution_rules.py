from unittest.mock import MagicMock

from extraction_pipeline import (
    _compact_bowen_quote,
    _format_bowen_refs,
    _has_bowen_source_attribution,
    _rule_filter_bowen_references,
)


def test_has_bowen_source_attribution_accepts_direct_patterns():
    assert _has_bowen_source_attribution(
        "Murray said this is what happens with families under stress."
    )
    assert _has_bowen_source_attribution(
        "I remember talking to Murray about this, and he said the pattern repeats."
    )
    assert _has_bowen_source_attribution(
        "That was Bowen's quote about togetherness and individuality."
    )
    assert _has_bowen_source_attribution(
        "Bowen was very clear about the impact of fusion."
    )
    assert _has_bowen_source_attribution(
        "Bowen talked about anxiety as a force in family patterns."
    )


def test_has_bowen_source_attribution_rejects_theory_and_theorists():
    assert not _has_bowen_source_attribution(
        "In Bowen theory terms this is a field process."
    )
    assert not _has_bowen_source_attribution(
        "Bowen theory says anxiety drives the system."
    )
    assert not _has_bowen_source_attribution(
        "Many Bowen theorists deal with these families without being judgmental."
    )


def test_theory_rejection_uses_the_short_verb_list():
    """The 'Bowen theory' rejection check uses a SHORTER verb list than the
    primary attribution pattern. Locking this boundary prevents a future
    refactor from unifying the two lists and silently changing behaviour.

    - "suggested"/"did" are in the LONG (attribution) list only, so a
      "Bowen theory … as Bowen suggested/did …" clause is still rejected.
    - "noted" is in the SHORT (rejection) list too, so "… as Murray noted …"
      is accepted as a person recollection even with "Bowen theory" nearby.
    """
    assert not _has_bowen_source_attribution(
        "Bowen theory, as Bowen suggested, explains anxiety."
    )
    assert not _has_bowen_source_attribution(
        "Bowen theory, as Bowen did, shaped the field."
    )
    assert _has_bowen_source_attribution(
        "Bowen theory, as Murray noted, is about triangles."
    )


def test_has_bowen_source_attribution_rejects_non_attributed_content():
    assert not _has_bowen_source_attribution(
        "The emotional system is the force that motivates the relationship system."
    )
    assert not _has_bowen_source_attribution(
        "Dr. Kerr said this process unfolds over generations."
    )
    assert not _has_bowen_source_attribution(
        "He said this repeats across generations."
    )


def test_concept_has_bowen_attribution_rejects_possessive_theory():
    """A possessive theory-framing concept label is theory exposition, not a person
    recollection — the exclusion must cover "Bowen's theory" (with the apostrophe-s),
    not just a bare "bowen theory" (P3/P4)."""
    from bowen_attribution import concept_has_bowen_attribution
    assert not concept_has_bowen_attribution("Bowen's theory of differentiation")
    assert not concept_has_bowen_attribution("Murray Bowen's theory")
    assert not concept_has_bowen_attribution("Bowen's differentiation theory")
    # a genuine possessive label still counts as person attribution
    assert concept_has_bowen_attribution("Bowen's Timeline Prediction")
    assert concept_has_bowen_attribution("Murray Bowen's Prediction")


def test_concept_has_bowen_attribution_keeps_adjectival_insights():
    """'theoretical' as an adjective is NOT theory framing — 'Bowen's theoretical
    insights' is a recollection of his thinking, not 'Bowen theory' exposition. The
    theory rejection must be narrow (theory/theorist NOUNS only, not 'theoretical')."""
    from bowen_attribution import concept_has_bowen_attribution
    assert concept_has_bowen_attribution("Bowen's theoretical insights")
    assert concept_has_bowen_attribution("Bowen's theoretical contributions")


def test_rule_filter_bowen_references_keeps_only_attributed_items():
    refs = [
        ("Direct", "Murray Bowen said anxiety binds the family process."),
        ("Theory-only", "In Bowen theory terms and not parts and wholes."),
        ("Theorists", "A lot of Bowen theorists think this way."),
        ("No Attribution", "Differentiation helps with reactivity."),
        ("Coreference", "I remember talking to Murray, and he said to watch triangles."),
    ]
    logger = MagicMock()

    filtered = _rule_filter_bowen_references(refs, logger)

    assert filtered == [
        ("Direct", "Murray Bowen said anxiety binds the family process."),
        ("Coreference", "I remember talking to Murray, and he said to watch triangles."),
    ]


def test_compact_bowen_quote_preserves_attribution_when_trimming():
    quote = (
        "We reviewed several observations about family process over time. "
        "I remember talking to Murray about this and he said the pattern repeats in triangles. "
        "Then we discussed multiple downstream implications for clinical work and training."
    )

    compact = _compact_bowen_quote(quote, max_words=18)

    assert len(compact.split()) <= 18
    assert "murray" in compact.lower() or "he said" in compact.lower()


def test_compact_bowen_quote_trims_no_punctuation_runs():
    quote = (
        "Murray said this process repeats across triangles and generations "
        "and it keeps showing up in how families handle stress and conflict "
        "and this continues when anxiety increases and people pull together"
    )
    compact = _compact_bowen_quote(quote, max_words=16)
    assert len(compact.split()) <= 16
    assert "murray" in compact.lower()


def test_format_bowen_refs_keeps_full_quote_text():
    quote = (
        "I can distinctly remember riding back from Georgetown and Murray said, Mike, "
        "that's not going to solve it. Cancer is a part of nature and not a disease."
    )
    rendered = _format_bowen_refs([("Cancer as Part of Nature", quote)])

    assert "Cancer is a part of nature and not a disease." in rendered
    assert "..." not in rendered
