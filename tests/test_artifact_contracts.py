"""M3 — artifact contract codec tests (spec §M3).

Spec:  docs/spec_unattended_robustness_2026-07-15.md#M3
Covers M3.A (schemas valid+versioned), M3.C.1 (round-trip on REAL samples),
M3.C.2 (drift is a loud error, not a silent zero), M3.D.1 (legacy markdown
migrates). Producer-side ERROR (M3.B.1) is exercised where the producer is wired
(see test_release_gate / per-artifact staging tests).
"""
from pathlib import Path

import pytest

import artifact_contracts as ac
from artifact_contracts import SchemaError, codec

FIXTURES = Path(__file__).parent / "fixtures"
WHERE_ROOTS = (
    FIXTURES / "where_roots"
    / "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid"
)
WR_BASE = "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid"
SOCIETAL = FIXTURES / "societal_emotional"
MONIKA = FIXTURES / "monika_h3_themes"  # legacy `### N.` (H3-numbered) theme format


def _wr(suffix: str) -> str:
    return (WHERE_ROOTS / f"{WR_BASE} - {suffix}.md").read_text(encoding="utf-8")


# Real-artifact sources per boundary. (text, parse-args) — themes needs a `kind`.
REAL_SAMPLES = {
    "bowen": (lambda: _wr("bowen-references"), ()),
    "emphasis": (lambda: _wr("emphasis-scored"), ()),
    "key_terms": (lambda: _wr("key-terms"), ()),
    "topics": (lambda: (SOCIETAL / "topics.md").read_text(encoding="utf-8"), ()),
    "themes_structural": (
        lambda: (SOCIETAL / "structural-themes.md").read_text(encoding="utf-8"),
        ("structural",),
    ),
    "themes_interpretive": (
        lambda: (SOCIETAL / "interpretive-themes.md").read_text(encoding="utf-8"),
        ("interpretive",),
    ),
    # legacy H3-numbered (`### N.`) real format — must migrate too (AC M3.D.1)
    "themes_h3_structural": (
        lambda: (MONIKA / "structural-themes.md").read_text(encoding="utf-8"),
        ("structural",),
    ),
}


def _codec_and_args(sample_key: str):
    key = "themes" if sample_key.startswith("themes") else sample_key
    _, args = REAL_SAMPLES[sample_key]
    return codec(key), args


# --------------------------------------------------------------------------- M3.A
def test_m3a_schemas_valid_and_versioned():
    from jsonschema import Draft202012Validator

    for key in ("bowen", "emphasis", "key_terms", "topics", "themes", "abstract_input"):
        schema = ac.load_schema(key)
        Draft202012Validator.check_schema(schema)  # the schema itself is well-formed
        assert schema.get("version") == ac.SCHEMA_VERSION
        # the envelope pins the artifact identity so a mis-routed object is caught
        assert schema["properties"]["artifact"]["const"] in (key, "themes")


# --------------------------------------------------------------------------- M3.D.1
@pytest.mark.parametrize("sample_key", list(REAL_SAMPLES))
def test_m3d1_legacy_markdown_migrates(sample_key):
    """Every real on-disk legacy artifact loads into its schema with >0 items."""
    cdc, args = _codec_and_args(sample_key)
    text_fn, _ = REAL_SAMPLES[sample_key]
    obj = cdc.parse_markdown(text_fn(), *args)  # validates internally
    assert obj["items"], f"{sample_key}: real artifact migrated to zero items"


# --------------------------------------------------------------------------- M3.C.1
@pytest.mark.parametrize("sample_key", list(REAL_SAMPLES))
def test_m3c1_roundtrip_real_samples(sample_key):
    """parse(save(obj)) == obj on the canonical object of a REAL sample, and no
    item is dropped across a markdown round-trip (the P19 guarantee)."""
    cdc, args = _codec_and_args(sample_key)
    text_fn, _ = REAL_SAMPLES[sample_key]
    legacy = cdc.parse_markdown(text_fn(), *args)
    # canonical object = one render+parse so incidental whitespace is normalized
    canonical = cdc.parse_markdown(cdc.render_markdown(legacy), *args)
    # AC M3.C.1: parse(save(obj)) == obj
    assert cdc.parse_markdown(cdc.render_markdown(canonical), *args) == canonical
    # FIELD-LEVEL fidelity: render must not drop/alter any field (timestamp,
    # category, description, ...). On the real fixtures the render is exact, so a
    # lossy render is caught here, not hidden behind a count-only check.
    assert canonical == legacy
    # no silent item loss across the round-trip
    assert len(canonical["items"]) == len(legacy["items"])
    # JSON serialization is an exact round-trip
    assert cdc.from_json(cdc.to_json(canonical)) == canonical


# --------------------------------------------------------------------------- M3.C.2
@pytest.mark.parametrize(
    "sample_key,garbage",
    [
        ("bowen", "Just some prose about Bowen with no heading and no quote block."),
        ("emphasis", "A paragraph of narrative text with no bracketed score header."),
        ("key_terms", "Plain prose, no term headings, no bold labels whatsoever here."),
        ("topics", "Prose with no ### topic headings and no percentage metadata line."),
        ("themes_structural", "Prose with no bold-numbered **N. Title** theme blocks."),
    ],
)
def test_m3c2_drift_is_error_not_silent_zero(sample_key, garbage):
    """Non-empty input that parses to zero items is a loud SchemaError, never a
    clean empty pass (the exact P19 failure mode)."""
    cdc, args = _codec_and_args(sample_key)
    with pytest.raises(SchemaError):
        cdc.parse_markdown(garbage, *args)


def test_m3c2_truly_empty_is_not_an_error():
    """Distinguish contract drift from a genuinely absent/empty source: an empty
    string is a valid empty object, not an error (LEARNINGS #7)."""
    obj = codec("bowen").parse_markdown("   \n  ")
    assert obj["items"] == []


def test_m3c2_frontmatter_only_is_not_drift():
    """A frontmatter-only stub has no body to parse -> benign empty object, NOT a
    mislabeled P19 drift error (the guard measures meaningful content, not bytes)."""
    obj = codec("bowen").parse_markdown("---\ntitle: x\ndate: 2022\n---\n")
    assert obj["items"] == []


def test_topics_contract_is_faithful_no_business_filter():
    """The topics codec must represent the artifact FAITHFULLY: a sub-5% topic is
    kept in the JSON contract (the 5% cut is a downstream editorial choice), and an
    all-sub-5% artifact is a valid non-empty object, not a false drift error."""
    import summary_pipeline as sp

    md = (
        "## Topics\n\n"
        "### Tiny Aside\nA minor tangent.\n*_(~2% of transcript; Sections 9)_*\n"
    )
    obj = codec("topics").parse_markdown(md)
    assert [t["name"] for t in obj["items"]] == ["Tiny Aside"]
    # ...but the enriched consumer view still drops it (behavior preserved)
    assert sp.parse_topics_with_details(md, "transcript text") == []


def test_emphasis_type_case_variant_normalized_not_blocked():
    """A lowercase/upper type from the model is normalized, not blocked (finding 1)."""
    md = '[explicit - A1 - Rank: 90%] Concept: Something\n\n"a quote here"'
    obj = codec("emphasis").parse_markdown(md)
    assert obj["items"][0]["type"] == "Explicit"


def test_header_only_artifact_is_benign_empty():
    """A bare section header (H1/H2) with no body is a legitimately-empty
    artifact, not drift (the empty-vs-drift discriminant the gate relies on)."""
    for md in ("## Bowen References", "## Bowen References\n", "## Bowen References\n\n",
               "# Title\n\n## Bowen References\n"):
        assert codec("bowen").parse_markdown(md)["items"] == []


def test_themes_migrates_both_bold_and_h3_numbered_formats():
    """AC M3.D.1: BOTH real theme formats migrate — `**N.**` (current) and the
    legacy `### N.` (H3-numbered, 2010-interview run). A file uses one format; the
    codec must read whichever it is, or an old run false-BLOCKs once themes gate."""
    h3 = codec("themes").parse_markdown(
        (MONIKA / "structural-themes.md").read_text(encoding="utf-8"), "structural")
    bold = codec("themes").parse_markdown(
        (SOCIETAL / "structural-themes.md").read_text(encoding="utf-8"), "structural")
    assert h3["items"] and bold["items"]
    # H3 file's numbers/names came from `### N. Title`, not positional guessing
    assert h3["items"][0]["number"] == 1
    assert "Emotional Process" in h3["items"][0]["name"]


def test_all_headers_no_body_is_drift_not_empty():
    """An all-headers-no-body artifact (### item headers whose quote bodies were
    dropped entirely) is DRIFT, not a benign empty — H3+ item headers imply
    content that must parse. Without this, the drift would slip the gate silently."""
    md = "## Bowen References\n\n### Concept A\n\n### Concept B\n"
    with pytest.raises(SchemaError):
        codec("bowen").parse_markdown(md)


# --------------------------------------------------------------------------- M3.B.1 (producer save)
def test_m3b1_verify_saved_artifact_errors_on_drift_no_sidecar(tmp_path):
    """Producer self-check: a saved artifact that drifts to zero items despite
    extracted content raises SchemaError (-> producer records retryable ERROR) and
    NO JSON sidecar is written."""
    md = tmp_path / "x - bowen-references.md"
    md.write_text("## Bowen References\n\n### Concept\nlost its quote marker\n")
    with pytest.raises(SchemaError):
        ac.verify_saved_artifact(md, "bowen", expect_items=True)
    assert not ac.json_sidecar_path(md).exists()


def test_m3b1_verify_saved_artifact_writes_sidecar_on_valid(tmp_path):
    """A conforming saved artifact validates and its JSON sidecar round-trips."""
    md = tmp_path / "x - bowen-references.md"
    md.write_text('## Bowen References\n\n### Differentiation [00:03:09]\n> "a real quote"\n')
    obj = ac.verify_saved_artifact(md, "bowen", expect_items=True)
    sidecar = ac.write_json_sidecar(md, "bowen", obj)
    assert sidecar.exists() and sidecar.name.endswith(".json")
    assert codec("bowen").from_json(sidecar.read_text()) == obj


def test_m3b1_empty_by_design_run_skips_item_check(tmp_path):
    """A zero-reference run (expect_items=False) is a clean empty, not an error."""
    md = tmp_path / "x - bowen-references.md"
    md.write_text("## Bowen References\n")
    obj = ac.verify_saved_artifact(md, "bowen", expect_items=False)
    assert obj["items"] == []
    # the DEFAULT is the safe permissive one (don't require items unless asked):
    # calling without expect_items must also not raise on an empty artifact.
    assert ac.verify_saved_artifact(md, "bowen")["items"] == []


# ---------------------------------------------------------- M3.B (_save_summary self-check)
def test_m3b_save_summary_writes_sidecar_for_codec_types(tmp_path, monkeypatch):
    """A codec-backed summary type (key-terms) gets a JSON sidecar on valid save."""
    import config
    import extraction_pipeline as ep

    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    content = "## Key Terms\n\n### Differentiation\nA real definition of the term.\n"
    out = ep._save_summary(content, "MyProj - formatted.md", "key-terms")
    assert ac.json_sidecar_path(out).exists()
    obj = codec("key_terms").from_json(ac.json_sidecar_path(out).read_text())
    assert obj["items"][0]["term"] == "Differentiation"


def test_m3b_save_summary_drift_leaves_file_no_sidecar(tmp_path, monkeypatch):
    """On drift the summary file is LEFT on disk (for the gate to BLOCK), and no
    sidecar is written — the producer must not delete the evidence."""
    import config
    import extraction_pipeline as ep

    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    drift = "## Key Terms\n\n### Orphan Term\n"  # H3 item, no definition body -> drift
    out = ep._save_summary(drift, "MyProj - formatted.md", "key-terms")
    assert out.exists()  # left on disk for the gate
    assert not ac.json_sidecar_path(out).exists()


def test_m3b_save_summary_non_codec_type_is_noop(tmp_path, monkeypatch):
    """A non-codec type (overview) saves normally with no sidecar and no error."""
    import config
    import extraction_pipeline as ep

    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    out = ep._save_summary("Some overview prose.", "MyProj - formatted.md", "overview")
    assert out.exists() and not ac.json_sidecar_path(out).exists()


# --------------------------------------------------------------------------- schema enforcement
# --------------------------------------------------------------------------- abstract_input
def test_abstract_input_valid_object_validates():
    from abstract_pipeline import AbstractInput, Theme, Topic

    ai = AbstractInput(
        metadata={"speaker": "Kerr"}, topics=[Topic("Differentiation", 40, "1-3")],
        themes=[Theme("A theme", "its description")], opening_purpose="p",
        closing_conclusion="c", qa_percentage=10, qa_topics=["q"], target_word_count=250)
    out = ac.validate("abstract_input", ai.to_contract_dict())
    assert out["artifact"] == "abstract_input"


def test_abstract_input_empty_topic_name_fails_closed():
    """A malformed assembled input (empty topic name) is a fail-closed SchemaError
    at the producer — it never drives a generation call (M3.B)."""
    from abstract_pipeline import AbstractInput, Topic

    ai = AbstractInput(
        metadata={}, topics=[Topic("", 40, "1-3")], themes=[], opening_purpose="",
        closing_conclusion="", qa_percentage=0, qa_topics=[], target_word_count=250)
    with pytest.raises(SchemaError):
        ac.validate("abstract_input", ai.to_contract_dict())


def test_abstract_input_percentage_out_of_range_fails_closed():
    from abstract_pipeline import AbstractInput, Topic

    ai = AbstractInput(
        metadata={}, topics=[Topic("T", 250, "1")], themes=[], opening_purpose="",
        closing_conclusion="", qa_percentage=0, qa_topics=[], target_word_count=250)
    with pytest.raises(SchemaError):
        ac.validate("abstract_input", ai.to_contract_dict())


def test_validate_rejects_out_of_enum_type():
    bad = {"version": "1", "artifact": "emphasis",
           "items": [{"type": "Bogus", "category": "A1", "score": 90,
                      "concept": "x", "quote": "y"}]}
    with pytest.raises(SchemaError):
        ac.validate("emphasis", bad)


def test_validate_rejects_score_out_of_range():
    bad = {"version": "1", "artifact": "emphasis",
           "items": [{"type": "Explicit", "category": "A1", "score": 150,
                      "concept": "x", "quote": "y"}]}
    with pytest.raises(SchemaError):
        ac.validate("emphasis", bad)


def test_validate_error_message_is_actionable():
    """A drift error must NAME the offending location, not raise an empty message
    — the whole point of M3 is a loud, actionable failure an operator can act on.
    Pins validate()'s detail construction (which mutation-testing found unpinned)."""
    bad = {"version": "1", "artifact": "emphasis",
           "items": [{"type": "Bogus", "category": "A1", "score": 90,
                      "concept": "x", "quote": "y"}]}
    with pytest.raises(SchemaError) as exc:
        ac.validate("emphasis", bad)
    msg = str(exc.value)
    assert msg.strip(), "SchemaError message must not be empty"
    # the offending path (items/0/type) must be surfaced
    assert "items/0/type" in msg
