"""Domain-semantic key-terms judge (gap #4) — offline tests (mocked judge, zero
API spend).

Covers: artifact parsing, the fail-closed parse contract, judge aggregation
(correct->PASS, incorrect->FAIL, judge-error->ERROR), and the calibration metrics
for the labeled head-to-head. The LIVE head-to-head run is a separate script.
"""
import json
import types

import pytest

import key_terms_semantic_judge as kj
from key_terms_semantic_judge import ClaimVerdict


def _fake_message(text):
    return types.SimpleNamespace(content=[types.SimpleNamespace(text=text)])


def _canned_client(monkeypatch, response_text=None, raises=None):
    def fake_call(**kwargs):
        if raises is not None:
            raise raises
        return _fake_message(response_text)
    monkeypatch.setattr("transcript_utils.call_claude_with_retry", fake_call)
    return object()  # placeholder client; the wrapper is mocked


SOURCE = "Bowen described differentiation of self as the capacity to be guided by "
"one's own thinking rather than the togetherness pressure. He linked anxiety to "
"emotional reactivity in the family system."

KEY_TERMS_MD = (
    "## Key Terms\n\n"
    "### Differentiation of Self\n"
    "The capacity to be guided by one's own thinking rather than emotional "
    "togetherness pressure.\n\n"
    "### Emotional Cutoff\n"
    "The process of managing unresolved emotional attachment by distancing.\n"
)


def _canned_correct():
    return json.dumps([
        {"index": 1, "label": "correct", "rationale": "matches Bowen"},
        {"index": 2, "label": "correct", "rationale": "matches Bowen"},
    ])


def test_parse_key_terms_artifact_extracts_pairs():
    pairs = kj.parse_key_terms_artifact(KEY_TERMS_MD)
    assert pairs[0][0] == "Differentiation of Self"
    assert "guided by one's own thinking" in pairs[0][1]
    assert pairs[1][0] == "Emotional Cutoff"
    assert len(pairs) == 2


def test_parse_key_terms_artifact_skips_header():
    pairs = kj.parse_key_terms_artifact("## Key Terms\n\n### Key Terms\nno\n")
    assert pairs == []


def test_judge_key_terms_maps_verdicts_in_order(monkeypatch):
    client = _canned_client(monkeypatch, _canned_correct())
    terms = kj.parse_key_terms_artifact(KEY_TERMS_MD)
    verdicts = kj.judge_key_terms(terms, SOURCE, client)
    assert [v.claim for v in verdicts] == ["Differentiation of Self", "Emotional Cutoff"]
    assert all(v.label == "correct" for v in verdicts)


def test_judge_artifact_passes_when_all_correct(monkeypatch):
    client = _canned_client(monkeypatch, _canned_correct())
    r = kj.judge_key_terms_artifact(KEY_TERMS_MD, SOURCE, client)
    assert r.status == kj.PASS


def test_judge_artifact_fails_on_incorrect(monkeypatch):
    resp = json.dumps([
        {"index": 1, "label": "correct", "rationale": "ok"},
        {"index": 2, "label": "incorrect", "rationale": "wrong concept"},
    ])
    client = _canned_client(monkeypatch, resp)
    r = kj.judge_key_terms_artifact(KEY_TERMS_MD, SOURCE, client)
    assert r.status == kj.FAIL
    assert "1 of 2" in r.detail
    assert r.claims[1].label == "incorrect"


def test_judge_artifact_errors_on_judge_exception(monkeypatch):
    client = _canned_client(monkeypatch, raises=RuntimeError("api down"))
    r = kj.judge_key_terms_artifact(KEY_TERMS_MD, SOURCE, client)
    assert r.status == kj.ERROR


def test_judge_artifact_errors_on_unparseable_response(monkeypatch):
    client = _canned_client(monkeypatch, "no json here at all")
    r = kj.judge_key_terms_artifact(KEY_TERMS_MD, SOURCE, client)
    assert r.status == kj.ERROR


def test_judge_artifact_errors_on_missing_verdict(monkeypatch):
    # fail-closed: a short response that omits term 2 must ERROR, not default to pass
    resp = json.dumps([{"index": 1, "label": "correct", "rationale": "ok"}])
    client = _canned_client(monkeypatch, resp)
    r = kj.judge_key_terms_artifact(KEY_TERMS_MD, SOURCE, client)
    assert r.status == kj.ERROR


def test_judge_artifact_errors_on_missing_source(monkeypatch):
    client = _canned_client(monkeypatch, _canned_correct())
    r = kj.judge_key_terms_artifact(KEY_TERMS_MD, "", client)
    assert r.status == kj.ERROR


def test_judge_artifact_passes_when_no_terms(monkeypatch):
    client = _canned_client(monkeypatch, _canned_correct())
    r = kj.judge_key_terms_artifact("## Key Terms\n", SOURCE, client)
    assert r.status == kj.PASS


def test_binary_key_terms_metrics():
    # 3 wrong caught, 1 wrong missed, 1 correct falsely flagged, 5 correct clean
    pairs = [
        ("incorrect", "incorrect"), ("incorrect", "incorrect"),
        ("incorrect", "incorrect"), ("incorrect", "correct"),   # FN
        ("correct", "incorrect"),                               # FP
        ("correct", "correct"), ("correct", "correct"),
        ("correct", "correct"), ("correct", "correct"),
        ("correct", "correct"),
    ]
    m = kj.binary_key_terms_metrics(pairs)
    assert m == {"tp": 3, "fp": 1, "fn": 1, "tn": 5,
                 "recall": 0.75, "precision": 0.75, "accuracy": 0.8}


def test_binary_key_terms_metrics_empty_is_neutral():
    m = kj.binary_key_terms_metrics([])
    assert m["recall"] == 1.0 and m["precision"] == 1.0 and m["accuracy"] == 1.0


def test_build_labeled_set():
    import key_terms_head_to_head as h2h
    terms = [("Differentiation", "def A"), ("Fusion", "def B"), ("Triangles", "def C")]
    labeled = h2h.build_labeled_set(terms)
    assert len(labeled) == 6
    assert all(l == kj.CORRECT for (_t, _d, l) in labeled[:3])
    # term 0 (Differentiation) swapped with term 1's (Fusion's) definition
    assert labeled[3] == ("Differentiation", "def B", kj.INCORRECT)
    assert labeled[4] == ("Fusion", "def C", kj.INCORRECT)
    assert labeled[5] == ("Triangles", "def A", kj.INCORRECT)


def test_run_head_to_head_perfect_judge(monkeypatch):
    """The calibration pipeline (build set -> judge -> metrics) reports 1.0 across
    the board for a judge that labels every example correctly."""
    import key_terms_head_to_head as h2h
    terms = [("A", "def A"), ("B", "def B"), ("C", "def C")]
    resp = json.dumps([
        {"index": 1, "label": "correct", "rationale": "ok"},
        {"index": 2, "label": "correct", "rationale": "ok"},
        {"index": 3, "label": "correct", "rationale": "ok"},
        {"index": 4, "label": "incorrect", "rationale": "swapped"},
        {"index": 5, "label": "incorrect", "rationale": "swapped"},
        {"index": 6, "label": "incorrect", "rationale": "swapped"},
    ])
    client = _canned_client(monkeypatch, resp)
    m = h2h.run_head_to_head("source text", terms, client, "model")
    assert m["n"] == 6
    assert m["recall"] == 1.0 and m["precision"] == 1.0 and m["accuracy"] == 1.0
