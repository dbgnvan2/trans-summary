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
