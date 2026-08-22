"""Offline tests for the judge drift monitor (no API spend).

Verifies the three gold sets are structurally sound (both classes present, every
source resolves to a real fixture), and that the drift-detection logic — the
part that must be trustworthy — flags a judge that has fallen below its bar.

The LIVE run (judge_drift_monitor.py) is deliberately NOT invoked here; the
judge functions are monkeypatched so these tests are deterministic and free.
"""
import json
from pathlib import Path

import pytest

import config
import faithfulness_judge as fj
import key_terms_semantic_judge as kj
import judge_drift_monitor as jdm

FIX = Path(__file__).parent / "fixtures"

GOLDS = [
    ("faithfulness_gold", "cases", "entailed", "contradicted"),
    ("theme_gold", None, None, None),          # special shape (grounded_artifacts + ungrounded_themes)
    ("key_terms_gold", "cases", "correct", "incorrect"),
]


def _load(name):
    return json.loads((FIX / name / "gold.json").read_text(encoding="utf-8"))


def test_all_gold_sources_resolve_to_real_fixtures():
    """A gold case whose source path is missing would silently skip at runtime
    (P2/P6): every source must map to an on-disk fixture file."""
    for name in ("faithfulness_gold", "theme_gold", "key_terms_gold"):
        gold = _load(name)
        for src_id, rel in gold["sources"].items():
            assert (FIX / rel).is_file(), f"{name}: missing source {rel}"


def test_faithfulness_gold_has_both_classes():
    gold = _load("faithfulness_gold")
    labels = {c["label"] for c in gold["cases"]}
    assert "entailed" in labels and "unsupported" in labels and "contradicted" in labels


def test_key_terms_gold_has_correct_and_incorrect_and_parses_terms():
    gold = _load("key_terms_gold")
    labels = {c["label"] for c in gold["cases"]}
    assert "correct" in labels and "incorrect" in labels
    n_incorrect = sum(1 for c in gold["cases"] if c["label"] == "incorrect")
    assert n_incorrect >= 3, "recall on the incorrect class needs a real negative set"
    for c in gold["cases"]:
        assert c["term"].strip() and c["definition"].strip(), c["id"]


def test_theme_gold_has_grounded_and_ungrounded():
    gold = _load("theme_gold")
    assert gold["grounded_artifacts"], "theme gold needs grounded (real) themes"
    assert len(gold["ungrounded_themes"]) >= 3, "theme gold needs a real ungrounded set"


def test_theme_metrics_counts_a_miss():
    m = jdm._theme_metrics([("ungrounded", "grounded")])  # a fabricated theme waved through
    assert m["fn"] == 1 and m["recall"] == 0.0
    assert jdm._theme_metrics([("ungrounded", "ungrounded"), ("grounded", "grounded")]) \
        == {"tp": 1, "fp": 0, "fn": 0, "tn": 1, "recall": 1.0, "precision": 1.0}


def test_drifted_flags_below_bar():
    r = {"metrics": {"recall": 0.5, "precision": 1.0},
         "recall_bar": 0.90, "precision_bar": 0.70}
    assert jdm._drifted(r) is True
    r2 = {"metrics": {"recall": 0.95, "precision": 0.80},
          "recall_bar": 0.90, "precision_bar": 0.70}
    assert jdm._drifted(r2) is False


def _result(name, pairs, recall_bar=0.90, precision_bar=0.70, danger="x", is_danger=None):
    # metrics mirror jdm._theme_metrics shape for arbitrary binary labels.
    pos = danger
    tp = sum(1 for t, p in pairs if t == pos and p == pos)
    fp = sum(1 for t, p in pairs if t != pos and p == pos)
    fn = sum(1 for t, p in pairs if t == pos and p != pos)
    tn = sum(1 for t, p in pairs if t != pos and p != pos)
    rec = tp / (tp + fn) if (tp + fn) else 1.0
    prec = tp / (tp + fp) if (tp + fp) else 1.0
    return {"name": name, "pairs": pairs, "rows": [],
            "metrics": {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                        "recall": rec, "precision": prec},
            "recall_bar": recall_bar, "precision_bar": precision_bar,
            "danger_label": danger, "is_danger": (lambda l: l == danger) if is_danger is None else is_danger}


def test_render_reports_drift_and_clear():
    drifted = [_result("faithfulness", [("bad", "ok"), ("ok", "ok")], danger="bad")]
    assert "DRIFT DETECTED" in jdm._render(drifted, "m")
    clean = [_result("faithfulness", [("bad", "bad"), ("ok", "ok")], danger="bad")]
    assert "clear their bars" in jdm._render(clean, "m")


def test_evaluate_assembles_three_judges_with_mocked_runners(monkeypatch):
    """evaluate() must run all three judges and compute metrics without spending
    API — the judge runners are monkeypatched to return canned, perfectly-correct
    pairs, so every judge clears (recall=precision=1.0) and nothing drifts."""
    good_f = [("entailed", "entailed"), ("contradicted", "contradicted"),
              ("unsupported", "unsupported")]
    good_t = [("grounded", "grounded"), ("ungrounded", "ungrounded")]
    good_k = [("correct", "correct"), ("incorrect", "incorrect")]

    monkeypatch.setattr(jdm, "_run_faithfulness", lambda c, m: (good_f, []))
    monkeypatch.setattr(jdm, "_run_themes", lambda c, m: (good_t, []))
    monkeypatch.setattr(jdm, "_run_key_terms", lambda c, m: (good_k, []))

    results = jdm.evaluate(None, model_override="test-model")
    assert [r["name"] for r in results] == ["faithfulness", "theme", "key_terms"]
    for r in results:
        assert r["metrics"]["recall"] == 1.0, r["name"]
        assert r["metrics"]["precision"] == 1.0, r["name"]
        assert not jdm._drifted(r)


def test_evaluate_detects_drift_with_mocked_runners(monkeypatch):
    """The whole point: when a judge misses the danger class, evaluate() must
    surface it as drift (recall < bar), not a clean pass."""
    # faithfulness judge misses BOTH unfaithful claims (calls them entailed).
    bad_f = [("entailed", "entailed"), ("contradicted", "entailed"),
             ("unsupported", "entailed")]
    good_t = [("grounded", "grounded"), ("ungrounded", "ungrounded")]
    good_k = [("correct", "correct"), ("incorrect", "incorrect")]
    monkeypatch.setattr(jdm, "_run_faithfulness", lambda c, m: (bad_f, []))
    monkeypatch.setattr(jdm, "_run_themes", lambda c, m: (good_t, []))
    monkeypatch.setattr(jdm, "_run_key_terms", lambda c, m: (good_k, []))

    results = jdm.evaluate(None, model_override="test-model")
    f = next(r for r in results if r["name"] == "faithfulness")
    assert f["metrics"]["fn"] == 2
    assert f["metrics"]["recall"] < config.FAITHFULNESS_MIN_RECALL_UNFAITHFUL
    assert jdm._drifted(f)
