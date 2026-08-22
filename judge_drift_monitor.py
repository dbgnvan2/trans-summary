#!/usr/bin/env python3
"""Drift monitor for the three semantic judges (faithfulness, theme, key-terms).

Runs each judge over its curated gold set and asserts it still clears its
precision/recall bars. Exits non-zero if ANY judge has drifted below its bar —
the signal that a model bump, prompt edit, or threshold change silently
un-calibrated an armed judge (P20). This is the insurance policy that keeps
every future change honest: it re-verifies the semantic layer the way it was
verified when it was armed, not once and then trusted forever.

It is the ONLY script that spends Anthropic API across all three judges, and it
is deliberately NOT run by a normal ``pytest`` invocation (the offline wrapper is
``tests/test_judge_drift_monitor.py``). Run it directly, in CI, or from a cron
job:

    python judge_drift_monitor.py
    # or pin a model / use an explicit key:
    ANTHROPIC_API_KEY=... python judge_drift_monitor.py [--model <name>]

Exit codes: 0 = all judges clear their bars; 1 = drift detected (>=1 judge below
a bar); 2 = setup/key error (could not run — not a clean pass).

Spec: docs/spec_unattended_robustness_2026-07-15.md (M2.B calibration, extended).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import config
import faithfulness_judge as fj
import key_terms_semantic_judge as kj

FIX = Path(__file__).parent / "tests" / "fixtures"


def _load(gold_dir: str, filename: str = "gold.json"):
    """Return (gold dict, {source_id: source_text})."""
    gold = json.loads((FIX / gold_dir / filename).read_text(encoding="utf-8"))
    sources = {k: (FIX / v).read_text(encoding="utf-8")
               for k, v in gold["sources"].items()}
    return gold, sources


# ---------------------------------------------------------------------------
# Per-judge runners: each returns (pairs, rows) where pairs = [(true, pred)]
# and rows = [(id, true, pred, sample)].
# ---------------------------------------------------------------------------

def _run_faithfulness(client, model):
    gold, sources = _load("faithfulness_gold")
    by_source = defaultdict(list)
    for c in gold["cases"]:
        by_source[c["source"]].append(c)
    pairs, rows = [], []
    for sid, group in by_source.items():
        claims = [c["claim"] for c in group]
        verdicts = fj.judge_claims(claims, sources[sid], client, model=model)
        for case, v in zip(group, verdicts):
            pairs.append((case["label"], v.label))
            rows.append((case["id"], case["label"], v.label, case["claim"][:55]))
    return pairs, rows


def _run_themes(client, model):
    import artifact_contracts as ac

    gold, sources = _load("theme_gold")
    pairs, rows = [], []
    for ga in gold["grounded_artifacts"]:
        src = sources[ga["source"]]
        text = (FIX / ga["dir"] / f"{ga['suffix']}.md").read_text(encoding="utf-8")
        obj = ac.codec("themes").parse_markdown(text, ga["kind"])
        if not obj["items"]:
            # Zero-from-non-empty is format-contract drift (P19), not a clean
            # empty — a grounded artifact that parses to nothing must not silently
            # shrink the precision denominator.
            raise ValueError(
                f"theme gold {ga['source']}/{ga['suffix']} parsed to zero items — "
                f"contract drift, cannot verify")
        verdicts = fj.judge_themes(obj["items"], src, client)
        for t, v in zip(obj["items"], verdicts):
            pairs.append(("grounded", v.label))
            rows.append((ga["source"], "grounded", v.label, t["name"][:45]))
    for ut in gold["ungrounded_themes"]:
        src = sources[ut["source"]]
        v = fj.judge_themes([{"name": ut["name"], "description": ut["description"]}],
                            src, client)[0]
        pairs.append(("ungrounded", v.label))
        rows.append((ut["source"], "ungrounded", v.label, ut["name"][:45]))
    return pairs, rows


def _run_key_terms(client, model):
    gold, sources = _load("key_terms_gold")
    by_source = defaultdict(list)
    for c in gold["cases"]:
        by_source[c["source"]].append(c)
    pairs, rows = [], []
    for sid, group in by_source.items():
        terms = [(c["term"], c["definition"]) for c in group]
        verdicts = kj.judge_key_terms(terms, sources[sid], client, model=model)
        for case, v in zip(group, verdicts):
            pairs.append((case["label"], v.label))
            rows.append((case["id"], case["label"], v.label, case["term"][:45]))
    return pairs, rows


def _theme_metrics(pairs):
    is_ung = lambda lab: lab == fj.UNGROUNDED  # noqa: E731
    tp = sum(1 for t, p in pairs if is_ung(t) and is_ung(p))
    fp = sum(1 for t, p in pairs if not is_ung(t) and is_ung(p))
    fn = sum(1 for t, p in pairs if is_ung(t) and not is_ung(p))
    tn = sum(1 for t, p in pairs if not is_ung(t) and not is_ung(p))
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "recall": recall, "precision": precision}


# ---------------------------------------------------------------------------
# One judge -> result dict. `is_danger` is the predicate for the judge's
# load-bearing (must-NOT-pass) class; `metrics` keyed to it.
# ---------------------------------------------------------------------------

def _judge_result(name, pairs, rows, metrics, recall_bar, precision_bar, danger_label, is_danger):
    return {"name": name, "pairs": pairs, "rows": rows, "metrics": metrics,
            "recall_bar": recall_bar, "precision_bar": precision_bar,
            "danger_label": danger_label, "is_danger": is_danger}


def evaluate(client, model_override: str | None = None) -> list:
    """Run all three judges and return a list of result dicts (one per judge).

    Without an override, each judge runs on its OWN configured model (its pin) —
    the drift check must test the model the judge actually uses, not some other
    model (P6)."""
    f_model = model_override or config.FAITHFULNESS_JUDGE_MODEL
    t_model = model_override or config.THEME_JUDGE_MODEL
    k_model = model_override or config.KEY_TERMS_JUDGE_MODEL
    f_pairs, f_rows = _run_faithfulness(client, f_model)
    t_pairs, t_rows = _run_themes(client, t_model)
    k_pairs, k_rows = _run_key_terms(client, k_model)
    # Fail closed: a judge whose gold set has NO danger-class examples cannot be
    # verified — that must read as "could not run" (exit 2), never a clean pass
    # with recall/precision defaulting to 1.0 on an empty denominator (P24).
    for name, pairs, is_danger in [
        ("faithfulness", f_pairs, fj.is_unfaithful),
        ("theme", t_pairs, lambda lab: lab == fj.UNGROUNDED),
        ("key_terms", k_pairs, lambda lab: lab == kj.INCORRECT),
    ]:
        if not any(is_danger(t) for t, _ in pairs):
            raise ValueError(
                f"{name} gold set has no danger-class examples — cannot verify")
    return [
        _judge_result("faithfulness", f_pairs, f_rows,
                      fj.binary_faithfulness_metrics(f_pairs),
                      config.FAITHFULNESS_MIN_RECALL_UNFAITHFUL,
                      config.FAITHFULNESS_MIN_PRECISION_UNFAITHFUL,
                      "unfaithful", fj.is_unfaithful),
        _judge_result("theme", t_pairs, t_rows,
                      _theme_metrics(t_pairs),
                      config.THEME_JUDGE_MIN_RECALL_UNGROUNDED,
                      config.THEME_JUDGE_MIN_PRECISION_UNGROUNDED,
                      "ungrounded", lambda lab: lab == fj.UNGROUNDED),
        _judge_result("key_terms", k_pairs, k_rows,
                      kj.binary_key_terms_metrics(k_pairs),
                      config.KEY_TERMS_JUDGE_MIN_RECALL_INCORRECT,
                      config.KEY_TERMS_JUDGE_MIN_PRECISION_INCORRECT,
                      "incorrect", lambda lab: lab == kj.INCORRECT),
    ]


def _drifted(r: dict) -> bool:
    return (r["metrics"]["recall"] < r["recall_bar"]
            or r["metrics"]["precision"] < r["precision_bar"])


def _render(results: list, model: str) -> str:
    """Compact, cron-friendly report (stdout of a no_agent cron IS the message)."""
    drift = any(_drifted(r) for r in results)
    lines = [f"=== judge drift monitor (model={model}) ==="]
    for r in results:
        m = r["metrics"]
        d = _drifted(r)
        lines.append(
            f"{r['name']:12} recall={m['recall']:.3f} (>={r['recall_bar']:.2f})  "
            f"precision={m['precision']:.3f} (>={r['precision_bar']:.2f})  "
            f"n={len(r['pairs'])} tp={m['tp']} fp={m['fp']} fn={m['fn']} tn={m['tn']}  "
            f"{'DRIFT' if d else 'ok'}"
        )
    # Surface the missed false-negatives (a drifted judge waving through the danger class).
    for r in results:
        if not r["metrics"]["fn"]:
            continue
        lines.append(f"  [{r['name']}] missed {r['danger_label']} ({r['metrics']['fn']}):")
        for row in r["rows"]:
            _id, truth, pred, sample = row
            if r["is_danger"](truth) and not r["is_danger"](pred):
                lines.append(f"      {_id} truth={truth} pred={pred} {sample!r}")
    lines.append("RESULT: " + ("DRIFT DETECTED — >=1 judge below its bar"
                               if drift else "all judges clear their bars"))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Drift monitor for the three semantic judges.")
    ap.add_argument("--model", default=None,
                    help="Override ALL three judges' model (default: each judge's own pin).")
    args = ap.parse_args()

    from transcript_utils import resolve_anthropic_key
    api_key = resolve_anthropic_key()
    if not api_key:
        print("No Anthropic API key resolved — cannot run the drift monitor.", file=sys.stderr)
        return 2
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    try:
        results = evaluate(client, args.model)
    except Exception as e:  # noqa: BLE001 — a judge that errors is not a clean pass
        print(f"Drift monitor errored (not a clean pass): {type(e).__name__}: {e}",
              file=sys.stderr)
        return 2

    print(_render(results, args.model or "per-judge configured model"))
    return 1 if any(_drifted(r) for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
