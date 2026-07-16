"""M2.B.1 — LIVE gold-set calibration of the faithfulness judge.

Runs the real Sonnet judge over the curated gold set and asserts it clears the
precision/recall bars on the dangerous (contradicted+unsupported) class. This is
the ONLY test that spends Anthropic API, so it is gated behind an explicit opt-in
env var — it never runs on a normal `pytest` invocation.

    RUN_FAITHFULNESS_CALIBRATION=1 ANTHROPIC_API_KEY=... pytest \
        tests/test_faithfulness_calibration.py -q -s

Spec: docs/spec_unattended_robustness_2026-07-15.md#M2.B.1
"""
import json
import os
from collections import defaultdict
from pathlib import Path

import pytest

import config
import faithfulness_judge as fj

FIX = Path(__file__).parent / "fixtures"
GOLD = FIX / "faithfulness_gold" / "gold.json"

_OPT_IN = os.getenv("RUN_FAITHFULNESS_CALIBRATION")
_HAS_KEY = bool(os.getenv("ANTHROPIC_API_KEY"))

pytestmark = pytest.mark.skipif(
    not (_OPT_IN and _HAS_KEY),
    reason="live calibration: set RUN_FAITHFULNESS_CALIBRATION=1 and ANTHROPIC_API_KEY",
)


def _load_gold():
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    sources = {k: (FIX / v).read_text(encoding="utf-8") for k, v in gold["sources"].items()}
    return gold["cases"], sources


def evaluate_gold(client, model=None):
    """Judge every gold claim (batched per source) and return (pairs, rows) where
    pairs = [(true_label, pred_label)] and rows carry per-case detail for the report."""
    cases, sources = _load_gold()
    by_source = defaultdict(list)
    for c in cases:
        by_source[c["source"]].append(c)
    pairs, rows = [], []
    for source_id, group in by_source.items():
        claims = [c["claim"] for c in group]
        verdicts = fj.judge_claims(claims, sources[source_id], client, model=model)
        for case, v in zip(group, verdicts):
            pairs.append((case["label"], v.label))
            rows.append((case["id"], case["label"], v.label, v.rationale))
    return pairs, rows


def test_m2b1_judge_meets_gold_thresholds():
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    pairs, rows = evaluate_gold(client, model=config.FAITHFULNESS_JUDGE_MODEL)
    m = fj.binary_faithfulness_metrics(pairs)

    print("\n=== M2.B.1 faithfulness gold calibration "
          f"(model={config.FAITHFULNESS_JUDGE_MODEL}) ===")
    for cid, truth, pred, why in rows:
        flag = "" if (fj.is_unfaithful(truth) == fj.is_unfaithful(pred)) else "  <-- MISS"
        print(f"  {cid:5} truth={truth:12} pred={pred:12} {why[:50]}{flag}")
    print(f"  metrics: {m}")
    print(f"  bars: recall>={config.FAITHFULNESS_MIN_RECALL_UNFAITHFUL} "
          f"precision>={config.FAITHFULNESS_MIN_PRECISION_UNFAITHFUL}")

    assert m["recall"] >= config.FAITHFULNESS_MIN_RECALL_UNFAITHFUL, (
        f"judge recall {m['recall']:.2f} below bar — it missed "
        f"{m['fn']} unfaithful claim(s) (hallucinations waved through)")
    assert m["precision"] >= config.FAITHFULNESS_MIN_PRECISION_UNFAITHFUL, (
        f"judge precision {m['precision']:.2f} below bar — {m['fp']} false alarm(s)")


# Real full PROSE artifacts judged end-to-end through the production extraction path
# (the P10 fix — the isolated-claim gold set didn't exercise this). Expected verdict
# verified by hand against the source (P6).
_DG = FIX / "dave_g_test2"
_RB = FIX / "roots_bowen_test"
_WR = (FIX / "where_roots"
       / "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid")
_WR_BASE = _WR.name
REAL_ARTIFACTS = [
    # (label, source_path, abstract_path, expect_status, must_flag_substr)
    ("roots_bowen", _RB / "formatted.md", _RB / "abstract-generated.md", "PASS", None),
    ("where_roots", _WR / f"{_WR_BASE} - formatted.md",
     _WR / f"{_WR_BASE} - abstract-generated.md", "FAIL", "Malorni"),
    ("dave_g", _DG / "formatted.md", _DG / "abstract-generated.md", "FAIL", "nubbin"),
]


def test_m2b1_real_abstract_artifacts_judged_correctly():
    """The gate's REAL behaviour: judge full real abstracts through the production
    path. A clean abstract PASSES; the real Luciano-Malorni fabrication and a genuine
    over-reach are FAILed and named. This is the calibration the isolated gold set
    missed (P10)."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    print("\n=== M2.B.1 real-artifact calibration ===")
    for label, src, ab, expect, must_flag in REAL_ARTIFACTS:
        r = fj.judge_artifact(ab.read_text(encoding="utf-8"),
                              src.read_text(encoding="utf-8"), client)
        flagged = " | ".join(c.claim[:50] for c in r.unfaithful)
        print(f"  {label:12} status={r.status} (expect {expect})  {flagged[:80]}")
        assert r.status == expect, f"{label}: got {r.status}, expected {expect}"
        if must_flag:
            assert any(must_flag.lower() in c.claim.lower() for c in r.unfaithful), (
                f"{label}: expected an unfaithful claim mentioning {must_flag!r}")


def test_m2b1_injected_fabrication_in_real_abstract_is_caught():
    """Inject a fabricated concrete specific into a CLEAN real abstract; the judge
    must FAIL and name it (controlled detection on real prose)."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    src = (_RB / "formatted.md").read_text(encoding="utf-8")
    clean = (_RB / "abstract-generated.md").read_text(encoding="utf-8").rstrip()
    injected = clean + (" The webinar was funded by a 2021 grant from the "
                        "Vienna Institute for Family Systems.")
    r = fj.judge_artifact(injected, src, client)
    assert r.status == "FAIL"
    assert any("Vienna" in c.claim or "grant" in c.claim for c in r.unfaithful)
