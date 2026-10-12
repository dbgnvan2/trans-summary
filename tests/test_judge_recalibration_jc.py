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


def test_jc0_output_records_prompt_and_versions():
    """A calibration file names the prompt and confirm mode that produced it."""
    import hashlib

    import faithfulness_judge as fj
    meta = jr.run_metadata()
    assert meta["faithfulness_prompt_sha"] == hashlib.sha256(
        fj._JUDGE_INSTRUCTIONS.encode()).hexdigest()[:12]
    assert meta["judge_logic_version"] == config.JUDGE_LOGIC_VERSION
    assert meta["confirm_mode"] == config.FAITHFULNESS_CONFIRM_MODE
    assert meta["faithfulness_cache_version"] and meta["theme_prompt_sha"]


def test_q5_prose_real_source_has_metadata(monkeypatch):
    """Q5: --prose-real judges each artifact against the same source the gate uses
    (transcript + recording metadata from the folder name), so dated claims are not
    over-reported. Spec: docs/plan_todo_triage_2026-10-11.md#Q5"""
    import faithfulness_judge as fj
    import judge_recalibration as jr
    import release_gate

    seen = []

    def fake(claims, source, client, *, model=None, logger=None):
        seen.append(source)
        return [fj.ClaimVerdict(c, "entailed") for c in claims], []
    monkeypatch.setattr(fj, "judge_claims_confirmed", fake)
    jr.prose_real(client=None, model="m")
    assert seen
    talks = sorted(p for p in jr.PROSE_REAL.iterdir() if p.is_dir())
    expected = {release_gate.with_recording_metadata(
        t.name, (t / f"{t.name} - formatted.md").read_text(encoding="utf-8")) for t in talks}
    assert set(seen) <= expected
    assert all(s.startswith("Recording metadata") and "Michael Kerr" in s.split("\n\n")[0]
               for s in seen)


def test_q5_real_abstracts_use_metadata_where_named(monkeypatch):
    """Sweep finding 5: where_roots (a real base name) gets the gate's metadata."""
    import faithfulness_judge as fj
    import judge_recalibration as jr

    seen = {}

    def fake(art, source, client, *, model=None, logger=None):
        seen[len(seen)] = source
        return fj.FaithfulnessResult(fj.PASS, "ok")
    monkeypatch.setattr(fj, "judge_artifact", fake)
    jr.real_abstracts(client=None, model="m")
    labels = [r[0] for r in jr.REAL_ABSTRACTS]
    by_label = dict(zip(labels, seen.values()))
    assert by_label["where_roots"].startswith("Recording metadata")
    assert not by_label["roots_bowen"].startswith("Recording metadata")
