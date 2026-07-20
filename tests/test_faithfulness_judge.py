"""M2 — semantic faithfulness judge, offline tests (mocked judge, zero API spend).

Spec: docs/spec_unattended_robustness_2026-07-15.md#M2
Covers claim extraction, the fail-closed parse contract, and judge_artifact
aggregation (M2.A fabricated->FAIL, clean->PASS; M2.C judge-error->ERROR). The
LIVE gold-set calibration (M2.B.1) is a separate API-gated test.
"""
import json
import types
from pathlib import Path

import pytest

import config
import faithfulness_judge as fj
from faithfulness_judge import ClaimVerdict, FaithfulnessResult

FIX = Path(__file__).parent / "fixtures"
DAVE = FIX / "dave_g_test2"


def _fake_message(text):
    return types.SimpleNamespace(content=[types.SimpleNamespace(text=text)])


def _canned_client(monkeypatch, response_text=None, raises=None):
    """Monkeypatch the hardened call wrapper to return canned JSON or raise."""
    def fake_call(**kwargs):
        if raises is not None:
            raise raises
        return _fake_message(response_text)
    monkeypatch.setattr("transcript_utils.call_claude_with_retry", fake_call)
    return object()  # a placeholder client; the wrapper is mocked


# --------------------------------------------------------------------------- claim extraction
def test_extract_claims_from_real_abstract():
    text = (DAVE / "abstract-generated.md").read_text(encoding="utf-8")
    claims = fj.extract_claims(text)
    assert len(claims) >= 4  # the real abstract has several sentences
    # the `# Abstract` heading is not a claim
    assert not any(c.startswith("#") or c.lower() == "abstract" for c in claims)
    # every claim clears the min-length bound
    assert all(len(c) >= config.FAITHFULNESS_MIN_CLAIM_CHARS for c in claims)


def test_extract_claims_strips_headings_and_short_fragments():
    text = "# Title\n\n## Section\n\nThe client was born in 1956 and hospitalized twice.\n\nOK.\n"
    claims = fj.extract_claims(text)
    assert claims == ["The client was born in 1956 and hospitalized twice."]


def test_extract_claims_empty():
    assert fj.extract_claims("") == []
    assert fj.extract_claims("# Only a heading\n") == []


def test_extract_claims_keeps_short_concrete_claims():
    """A short sentence stating a concrete specific (a number or a proper noun) is
    a judgeable claim, not a dropped fragment — else a short fabrication slips the
    judge unjudged (F1/P2). True fragments ('OK.') are still dropped."""
    text = "He married in 1975. He died in Boston. OK."
    claims = fj.extract_claims(text)
    assert "He married in 1975." in claims  # short + digit
    assert "He died in Boston." in claims    # short + proper noun
    assert "OK." not in claims               # true fragment


def test_extract_claims_does_not_strip_fabricated_attribution_prefix():
    """H11 (review 2026-07-18): a fabricated pre-colon specific (a cited study / named
    entity phrased as a 'Prefix: ...' line) must NOT be stripped before the armed judge
    sees it — else the attribution rides through the gate UNJUDGED (gate bypass, P7/P20).
    A GENERIC scaffolding label (config allowlist) IS still stripped so the claim itself
    is judged."""
    text = (
        "Stanford study: transcription accuracy rose to ninety-eight percent.\n\n"
        "Description: the client was hospitalized twice in 1975.\n"
    )
    claims = fj.extract_claims(text)
    # the fabricated attribution SURVIVES verbatim inside a judgeable claim
    assert any("Stanford study" in c for c in claims), claims
    # the generic label IS stripped; its substantive remainder is judged on its own
    assert "the client was hospitalized twice in 1975." in claims, claims
    assert not any(c.lower().startswith("description:") for c in claims), claims


# --------------------------------------------------------------------------- parse contract
def test_parse_judge_response_maps_by_index():
    claims = ["A.", "B.", "C."]
    resp = json.dumps([
        {"index": 1, "label": "entailed", "rationale": "stated"},
        {"index": 2, "label": "unsupported", "rationale": "fabricated name"},
        {"index": 3, "label": "contradicted", "rationale": "wrong date"},
    ])
    verdicts = fj._parse_judge_response(resp, claims)
    assert [v.label for v in verdicts] == ["entailed", "unsupported", "contradicted"]


def test_parse_judge_response_tolerates_code_fence_and_prose():
    claims = ["A."]
    resp = 'Here is my analysis:\n```json\n[{"index":1,"label":"entailed"}]\n```\nDone.'
    verdicts = fj._parse_judge_response(resp, claims)
    assert verdicts[0].label == "entailed"


def test_parse_judge_response_missing_verdict_raises_fail_closed():
    """A claim with no returned verdict must RAISE (-> ERROR), never default to
    entailed — a silently-dropped claim would let a hallucination through (P14)."""
    claims = ["A.", "B."]
    resp = json.dumps([{"index": 1, "label": "entailed"}])  # claim 2 missing
    with pytest.raises(ValueError):
        fj._parse_judge_response(resp, claims)


def test_parse_judge_response_invalid_label_treated_as_missing():
    claims = ["A."]
    resp = json.dumps([{"index": 1, "label": "probably fine"}])
    with pytest.raises(ValueError):
        fj._parse_judge_response(resp, claims)


def test_extract_json_array_no_array_raises():
    with pytest.raises(ValueError):
        fj._extract_json_array("The model refused and wrote prose only.")


# --------------------------------------------------------------------------- M2.A / M2.C aggregation
def test_m2a2_clean_artifact_passes(monkeypatch):
    """A faithful artifact (every claim entailed) -> PASS, no false FAIL."""
    text = "The client was born in 1956. He was hospitalized twice in the 1970s."
    claims = fj.extract_claims(text)
    resp = json.dumps([{"index": i + 1, "label": "entailed"} for i in range(len(claims))])
    client = _canned_client(monkeypatch, resp)
    result = fj.judge_artifact(text, "source text about a 1956 client, two hospitalizations", client)
    assert result.status == fj.PASS
    assert result.unfaithful == []


def test_m2a1_fabricated_claim_flagged(monkeypatch):
    """An artifact with one fabricated (unsupported) claim -> FAIL naming it."""
    text = ("The client was born in 1956. "
            "The presentation was co-authored by Dr. Luciano Malorni of Milan.")
    claims = fj.extract_claims(text)
    # "Dr. Luciano Malorni" must stay ONE claim (abbreviation-aware split)
    assert any("Luciano Malorni of Milan" in c for c in claims)
    # judge marks the fabricated-name claim unsupported, the rest entailed
    resp = json.dumps([
        {"index": i + 1, "label": "unsupported" if "Malorni" in c else "entailed",
         "rationale": "x"}
        for i, c in enumerate(claims)
    ])
    client = _canned_client(monkeypatch, resp)
    result = fj.judge_artifact(text, "source about a 1956 client", client)
    assert result.status == fj.FAIL
    assert len(result.unfaithful) == 1
    assert "Malorni" in result.unfaithful[0].claim


def test_m2c1_judge_error_is_error_not_pass(monkeypatch):
    """A judge API error/timeout -> ERROR (blocks), never a silent PASS (M2.C)."""
    text = "The client was born in 1956."
    client = _canned_client(monkeypatch, raises=RuntimeError("API timeout"))
    result = fj.judge_artifact(text, "source", client)
    assert result.status == fj.ERROR


def test_m2c_unparseable_judge_response_is_error(monkeypatch):
    """An unparseable judge response -> ERROR, never PASS (fail closed, P14)."""
    text = "The client was born in 1956."
    client = _canned_client(monkeypatch, "I could not complete this task.")
    result = fj.judge_artifact(text, "source", client)
    assert result.status == fj.ERROR


def test_missing_source_is_error_not_pass():
    result = fj.judge_artifact("Some claim about something.", "", client=None)
    assert result.status == fj.ERROR


def test_no_claims_is_pass():
    result = fj.judge_artifact("# Heading only\n", "source", client=None)
    assert result.status == fj.PASS


# --------------------------------------------------------------------------- M2.B metrics
def test_binary_metrics_recall_is_load_bearing():
    # 2 unfaithful truths; judge catches 1, misses 1 (FN) -> recall 0.5
    pairs = [("unsupported", "unsupported"), ("contradicted", "entailed"),
             ("entailed", "entailed")]
    m = fj.binary_faithfulness_metrics(pairs)
    assert m["tp"] == 1 and m["fn"] == 1 and m["tn"] == 1
    assert m["recall"] == 0.5


def test_binary_metrics_false_alarm_hits_precision():
    pairs = [("entailed", "unsupported"), ("unsupported", "unsupported")]
    m = fj.binary_faithfulness_metrics(pairs)
    assert m["fp"] == 1 and m["precision"] == 0.5 and m["recall"] == 1.0


def test_binary_metrics_all_entailed_no_false_failure():
    m = fj.binary_faithfulness_metrics([("entailed", "entailed")] * 3)
    assert m["recall"] == 1.0 and m["precision"] == 1.0


def test_is_unfaithful():
    assert fj.is_unfaithful("contradicted") and fj.is_unfaithful("unsupported")
    assert not fj.is_unfaithful("entailed")


# --------------------------------------------------------------------------- gold set well-formed
def test_gold_set_is_balanced_and_sources_exist():
    """The gold set must have enough of the DANGEROUS class to measure recall, and
    reference REAL on-disk sources (not synthetic)."""
    gold = json.loads((FIX / "faithfulness_gold" / "gold.json").read_text())
    labels = [c["label"] for c in gold["cases"]]
    assert labels.count("entailed") >= 6
    assert sum(1 for l in labels if l in ("contradicted", "unsupported")) >= 8
    assert set(labels) == {"entailed", "contradicted", "unsupported"}
    for rel in gold["sources"].values():
        assert (FIX / rel).exists(), f"gold source missing: {rel}"


# --------------------------------------------------------------------------- theme grounding judge
def test_theme_judge_grounded_artifact_passes(monkeypatch):
    md = "## Structural Themes\n\n**1. A Grounded Theme**\n**Description:** interprets content in the source.\n"
    client = _canned_client(monkeypatch, json.dumps([{"index": 1, "label": "grounded"}]))
    r = fj.judge_themes_artifact(md, "some real source text", "structural", client)
    assert r.status == fj.PASS


def test_theme_judge_ungrounded_theme_fails(monkeypatch):
    md = "## Structural Themes\n\n**1. A Fabricated Theme**\n**Description:** about content absent from the source.\n"
    client = _canned_client(monkeypatch, json.dumps(
        [{"index": 1, "label": "ungrounded", "rationale": "absent from source"}]))
    r = fj.judge_themes_artifact(md, "source", "structural", client)
    assert r.status == fj.FAIL
    assert len(r.unfaithful) == 1 and "Fabricated" in r.unfaithful[0].claim


def test_theme_judge_mixed_reports_only_the_ungrounded_theme(monkeypatch):
    """With one grounded + one ungrounded theme, the FAIL report must name ONLY the
    ungrounded theme — not both (regression: ClaimVerdict.faithful once hardcoded
    `== entailed`, so every theme showed as ungrounded)."""
    md = ("## Structural Themes\n\n"
          "**1. A Grounded Theme**\n**Description:** interprets real content.\n\n"
          "**2. A Fabricated Theme**\n**Description:** about content not in the source.\n")
    resp = json.dumps([
        {"index": 1, "label": "grounded"},
        {"index": 2, "label": "ungrounded", "rationale": "absent"},
    ])
    client = _canned_client(monkeypatch, resp)
    r = fj.judge_themes_artifact(md, "source", "structural", client)
    assert r.status == fj.FAIL
    assert [c.claim for c in r.unfaithful] == ["A Fabricated Theme"]


def test_theme_judge_error_is_error_not_pass(monkeypatch):
    md = "## Structural Themes\n\n**1. T**\n**Description:** d.\n"
    client = _canned_client(monkeypatch, raises=RuntimeError("api down"))
    assert fj.judge_themes_artifact(md, "source", "structural", client).status == fj.ERROR


def test_theme_judge_missing_source_is_error():
    md = "## Structural Themes\n\n**1. T**\n**Description:** d.\n"
    assert fj.judge_themes_artifact(md, "", "structural", client=None).status == fj.ERROR


def test_theme_judge_no_themes_is_pass():
    assert fj.judge_themes_artifact("## Structural Themes\n", "source", "structural",
                                    client=None).status == fj.PASS


def test_theme_judge_drift_is_error_not_pass():
    """A non-empty themes artifact that parses to zero themes (format drift) -> the
    codec raises -> ERROR (fail closed), never a silent PASS."""
    md = "## Structural Themes\n\n### Not a numbered theme heading\nsome prose here\n"
    assert fj.judge_themes_artifact(md, "source", "structural", client=None).status == fj.ERROR


def test_theme_parse_response_uses_theme_labels():
    v = fj._parse_judge_response(
        json.dumps([{"index": 1, "label": "grounded", "rationale": "x"}]),
        ["A theme"], valid_labels=fj._THEME_LABELS)
    assert v[0].label == "grounded"
    # a faithfulness label is INVALID for the theme judge -> raises (fail closed)
    with pytest.raises(ValueError):
        fj._parse_judge_response(
            json.dumps([{"index": 1, "label": "entailed"}]), ["A theme"],
            valid_labels=fj._THEME_LABELS)


def test_theme_gold_set_well_formed():
    gold = json.loads((FIX / "theme_gold" / "gold.json").read_text())
    assert len(gold["ungrounded_themes"]) >= 5
    assert len(gold["grounded_artifacts"]) >= 4
    for rel in gold["sources"].values():
        assert (FIX / rel).exists(), f"gold source missing: {rel}"
