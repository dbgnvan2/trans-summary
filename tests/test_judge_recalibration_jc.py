"""JC.0/JC.1 (docs/plan_judge_recalibration_sonnet55_2026-10-10.md): offline checks of
the calibration tooling. No API calls."""
import json
from pathlib import Path

import config
import judge_recalibration as jr

FIX = Path(__file__).parent / "fixtures"


def test_jc0_calibration_model_from_env():
    src = (Path(__file__).parent / "test_faithfulness_calibration.py").read_text(encoding="utf-8")
    assert 'os.getenv("CALIBRATION_JUDGE_MODEL")' in src
    assert 'os.getenv("CALIBRATION_JUDGE_EFFORT")' in src
    assert "model=_MODEL" in src and "model=_THEME_MODEL" in src


def _run(f_recall=1.0, f_prec=1.0, t_recall=1.0, t_prec=1.0, real_ok=True, caught=True, pred="entailed"):
    return {"faithfulness": {"metrics": {"recall": f_recall, "precision": f_prec},
                             "rows": [{"id": "k1", "pred": pred}]},
            "themes": {"metrics": {"recall": t_recall, "precision": t_prec},
                       "rows": [{"name": "T", "pred": "grounded"}]},
            "real_abstracts": [{"artifact": "roots_bowen", "status": "PASS", "ok": real_ok}],
            "injected": {"caught": caught}}


def test_jc0_bars_and_flips():
    assert jr.passes_bars(_run())
    assert not jr.passes_bars(_run(f_recall=0.8))
    assert not jr.passes_bars(_run(real_ok=False))
    assert not jr.passes_bars(_run(caught=False))
    assert jr.flips([_run(), _run()]) == []
    assert jr.flips([_run(), _run(pred="unsupported")]) == [
        {"set": "faithfulness", "case": "k1", "labels": ["entailed", "unfaithful"]}]
    # contradicted <-> unsupported both block: not a flip
    assert jr.flips([_run(pred="contradicted"), _run(pred="unsupported")]) == []


def test_jc1_gold_has_kerr_cases():
    gold = json.loads((FIX / "faithfulness_gold" / "gold.json").read_text(encoding="utf-8"))
    assert (FIX / gold["sources"]["kerr_families"]).exists()
    kerr = {c["id"]: c["label"] for c in gold["cases"] if c["source"] == "kerr_families"}
    assert kerr == {"k1": "entailed", "k2": "contradicted", "k3": "contradicted",
                    "k4": "unsupported", "k5": "unsupported", "k6": "unsupported",
                    "k7": "entailed", "k8": "contradicted", "k9": "unsupported",
                    "k10": "entailed"}
    assert len(gold["cases"]) == 43


def test_jc3_parse_retry(monkeypatch):
    import logging

    import pytest

    import faithfulness_judge as fj
    replies = iter(["I think the theme is grounded.", '[{"index": 1, "label": "grounded", "rationale": "r"}]'])
    out = fj.call_and_parse(lambda: next(replies),
                            lambda t: fj._parse_judge_response(t, ["T"], valid_labels=fj._THEME_LABELS),
                            logging.getLogger("t"), "Theme judge")
    assert out[0].label == "grounded"
    monkeypatch.setattr(config, "JUDGE_PARSE_ATTEMPTS", 2)
    with pytest.raises(ValueError, match="reply began: 'still no json'"):
        fj.call_and_parse(lambda: "still no json", lambda t: fj._extract_json_array(t),
                          logging.getLogger("t"), "Theme judge")


def test_jc3_single_verdict_object_accepted():
    import pytest

    import faithfulness_judge as fj
    one = '{"index":1,"label":"ungrounded","rationale":"fabricated survey"}'
    v = fj._parse_judge_response(one, ["T"], valid_labels=fj._THEME_LABELS)
    assert v[0].label == "ungrounded"
    with pytest.raises(ValueError):  # an object that is not a verdict is still rejected
        fj._extract_json_array('{"note": "no verdict"}')


def test_jc6_cache_version_bumped():
    # Cached Sonnet 4.6 verdicts must not be served after the switch.
    assert config.JUDGE_LOGIC_VERSION >= "2026-10-10"
    assert config.FAITHFULNESS_JUDGE_MODEL == config.THEME_JUDGE_MODEL == "claude-sonnet-5-5"
