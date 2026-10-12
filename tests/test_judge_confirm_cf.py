"""CF — a first-pass faithfulness flag counts only when a fresh judgement agrees
(majority of 3 with early stop), so a random false flag does not fail a run.

Spec: docs/plan_judge_confirm_flags_2026-10-11.md
"""
import ast
from pathlib import Path
from unittest.mock import patch

import pytest

import config
import faithfulness_judge as fj
import release_gate

ROOT = Path(__file__).resolve().parent.parent
SRC = "The source says the cat sat on the mat. " * 5
A, B = "The cat sat on the mat today.", "The dog flew to the moon yesterday."


def _scripted(labels_by_claim):
    """A fake judge_claims: each claim's verdicts are taken in order, one per call
    that includes it. Records the claims sent in each call."""
    calls = []
    state = {k: list(v) for k, v in labels_by_claim.items()}

    def fake(claims, source, client, *, model=None, logger=None):
        calls.append(list(claims))
        return [fj.ClaimVerdict(c, state[c].pop(0), f"r{len(calls)}") for c in claims]
    return fake, calls


def _run(labels, mode="majority3"):
    fake, calls = _scripted(labels)
    with patch.object(fj, "judge_claims", fake), \
            patch.object(config, "FAITHFULNESS_CONFIRM_MODE", mode):
        verdicts, overturned = fj.judge_claims_confirmed(list(labels), SRC, client=None)
    return verdicts, overturned, calls


def test_cf1_reject_reject_is_unfaithful():
    v, over, calls = _run({A: ["entailed", "entailed"], B: ["unsupported", "unsupported"]})
    assert [x.label for x in v] == ["entailed", "unsupported"]
    # pass 2 carries the flag plus the claim before it (context, sweep finding 5)
    assert over == [] and calls == [[A, B], [A, B]]
    assert "2 of 2 judgements reject" in v[1].rationale


def test_cf1_context_claim_verdict_is_ignored():
    """The predecessor is sent for context only: its pass-2 verdict changes nothing."""
    v, over, calls = _run({A: ["entailed", "unsupported"], B: ["unsupported", "unsupported"]})
    assert [x.label for x in v] == ["entailed", "unsupported"]
    assert calls[1] == [A, B]


def test_cf1_only_flagged_and_predecessors_resent():
    C = "The bird sang a song at dawn."
    _, _, calls = _run({A: ["entailed"], B: ["entailed", "entailed"],
                        C: ["unsupported", "unsupported"]})
    assert calls[1] == [B, C]  # A is neither flagged nor C's predecessor


def test_cf1_reject_accept_reject_is_unfaithful():
    v, over, calls = _run({B: ["contradicted", "entailed", "unsupported"]})
    assert v[0].label == "contradicted"  # pass 1's label and rationale are kept
    assert over == [] and len(calls) == 3


def test_cf1_reject_accept_accept_is_overturned():
    v, over, calls = _run({A: ["entailed"] * 3, B: ["unsupported", "entailed", "entailed"]})
    assert [x.label for x in v] == ["entailed", "entailed"]
    assert len(over) == 1 and over[0]["claim"] == B and over[0]["first_label"] == "unsupported"
    assert over[0]["votes"] == "1 of 3 reject"
    assert [p["label"] for p in over[0]["passes"]] == ["unsupported", "entailed", "entailed"]
    assert "not confirmed" in v[1].rationale
    assert len(calls) == 3


def test_cf1_no_flag_no_extra_call():
    _, over, calls = _run({A: ["entailed"], B: ["entailed"]})
    assert over == [] and len(calls) == 1


def test_cf1_mode_off_skips_confirmation():
    v, over, calls = _run({B: ["unsupported"]}, mode="off")
    assert v[0].label == "unsupported" and len(calls) == 1


def test_cf1_error_in_confirmation_fails_closed():
    calls = []

    def fake(claims, source, client, *, model=None, logger=None):
        calls.append(claims)
        if len(calls) == 2:
            raise RuntimeError("API timeout")
        return [fj.ClaimVerdict(c, "unsupported") for c in claims]
    with patch.object(fj, "judge_claims", fake), \
            patch.object(config, "FAITHFULNESS_CONFIRM_MODE", "majority3"):
        r = fj.judge_artifact(B, SRC, client=None)
    assert r.status == fj.ERROR and "API timeout" in r.detail


def test_cf1_unknown_mode_is_an_error():
    with pytest.raises(ValueError):
        _run({B: ["unsupported"]}, mode="majority5")


def test_cf2_overturned_flags_recorded():
    fake, _ = _scripted({B: ["unsupported", "entailed", "entailed"]})
    with patch.object(fj, "judge_claims", fake), \
            patch.object(config, "FAITHFULNESS_CONFIRM_MODE", "majority3"):
        r = fj.judge_artifact(B, SRC, client=None)
    assert r.status == fj.PASS
    assert "1 first-pass flag(s) not confirmed" in r.detail
    d = r.to_dict()
    assert d["overturned"][0]["claim"] == B
    # the disk cache round-trips the overturned list
    key = "cf2-test"
    with patch.object(release_gate, "_load_judge_disk_cache", return_value={key: d}):
        back = release_gate._disk_cached_verdict(key, fj)
    assert back.overturned == d["overturned"]


def test_cf2_gate_items_show_overturned(tmp_path, monkeypatch):
    base = "T - P - 2026-01-01"
    proj = tmp_path / base
    proj.mkdir()
    (proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}").write_text(B, encoding="utf-8")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(release_gate, "_FAITHFULNESS_CACHE", {})
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ENABLED", True)
    result = fj.FaithfulnessResult(fj.PASS, "all 1 claim(s) entailed; 1 first-pass flag(s) not confirmed",
                                   claims=[fj.ClaimVerdict(B, "entailed")],
                                   overturned=[{"claim": B, "first_label": "unsupported",
                                                "votes": "1 of 3"}])
    with patch.object(release_gate, "_source_with_metadata", return_value=SRC), \
            patch("transcript_utils.resolve_anthropic_key", return_value="k"), \
            patch("transcript_utils.get_anthropic_client", return_value=object()), \
            patch.object(release_gate, "_judge_cached", return_value=result):
        v = release_gate.check_faithfulness(base, None, suffixes=[config.SUFFIX_ABSTRACT_GEN])
    assert v.status is release_gate.Status.PASS
    assert v.items and v.items[0]["overturned"][0]["claim"] == B


def _gate_setup(tmp_path, monkeypatch, base, files):
    proj = tmp_path / base
    proj.mkdir()
    for suffix, text in files.items():
        (proj / f"{base}{suffix}").write_text(text, encoding="utf-8")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ENABLED", True)
    monkeypatch.setattr(release_gate, "_FAITHFULNESS_CACHE", {})


_OVER = [{"claim": B, "first_label": "unsupported", "votes": "1 of 3 reject"}]


def test_cf2_fail_keeps_overturned_of_other_artifacts(tmp_path, monkeypatch):
    base = "T - P - 2026-01-01"
    _gate_setup(tmp_path, monkeypatch, base, {config.SUFFIX_ABSTRACT_GEN: "x",
                                               config.SUFFIX_SUMMARY_GEN: "y"})
    passed = fj.FaithfulnessResult(fj.PASS, "ok", overturned=_OVER)
    failed = fj.FaithfulnessResult(fj.FAIL, "bad", claims=[fj.ClaimVerdict(A, "unsupported")])
    with patch.object(release_gate, "_source_with_metadata", return_value=SRC), \
            patch("transcript_utils.resolve_anthropic_key", return_value="k"), \
            patch("transcript_utils.get_anthropic_client", return_value=object()), \
            patch.object(release_gate, "_judge_cached", side_effect=[passed, failed]):
        v = release_gate.check_faithfulness(
            base, None, suffixes=[config.SUFFIX_ABSTRACT_GEN, config.SUFFIX_SUMMARY_GEN])
    assert v.status is release_gate.Status.FAIL
    assert any(it.get("overturned") == _OVER for it in v.items)


def test_cf2_topic_term_check_records_overturned(tmp_path, monkeypatch):
    base = "T - P - 2026-01-01"
    _gate_setup(tmp_path, monkeypatch, base,
                {config.SUFFIX_TOPICS: "### A Topic\nThe cat sat on the mat today.\n"})
    result = fj.FaithfulnessResult(fj.PASS, "ok", overturned=_OVER)
    with patch.object(release_gate, "_source_with_metadata", return_value=SRC), \
            patch("transcript_utils.resolve_anthropic_key", return_value="k"), \
            patch("transcript_utils.get_anthropic_client", return_value=object()), \
            patch.object(release_gate, "_judge_cached", return_value=result):
        v = release_gate.check_topic_term_faithfulness(base, None)
    assert v.status is release_gate.Status.PASS
    assert "1 first-pass flag(s) not confirmed" in v.detail
    assert v.items[0]["overturned"] == _OVER


def _calls_in(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.func.attr for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}


def test_cf3_all_callers_use_confirmed_judgement():
    # the gate goes through judge_artifact (via _judge_cached), which confirms
    assert "judge_artifact" in _calls_in(ROOT / "release_gate.py")
    # calibration and drift monitoring measure the behaviour that ships (P5)
    for f in ("judge_recalibration.py", "judge_drift_monitor.py",
              "tests/test_faithfulness_calibration.py"):
        calls = _calls_in(ROOT / f)
        assert "judge_claims_confirmed" in calls, f
    # judge_artifact and classify_claim call the confirmed function
    src = (ROOT / "faithfulness_judge.py").read_text(encoding="utf-8")
    for fn in ("judge_artifact", "classify_claim"):
        body = src.split(f"def {fn}(", 1)[1].split("\ndef ", 1)[0]
        assert "judge_claims_confirmed(" in body, fn


def test_cf4_mode_changes_logic_version(monkeypatch):
    a = release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS)
    monkeypatch.setattr(config, "FAITHFULNESS_CONFIRM_MODE", "off")
    assert release_gate._judge_logic_version(fj._JUDGE_INSTRUCTIONS) != a


def test_cf4_confirm_function_in_logic_version_inputs():
    assert fj.judge_claims_confirmed in release_gate._judge_input_functions()


def test_cf4_default_mode_is_majority3():
    assert config.FAITHFULNESS_CONFIRM_MODE == "majority3"
