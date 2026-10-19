#!/usr/bin/env python3
"""Re-score the JS6 severity votes under the stricter evidence rule (learning-qa F4).

The JS6 runs started before the rule changed: a NOT QUITE RIGHT vote then counted when
each "..."-part of 4+ words was in the source. Now every part of 2+ words must be in the
source, and the quote must share a significant word with the claim. No API calls: each
recorded vote is checked again with ``faithfulness_judge._evidence_in_source`` and the
vote sequence is replayed (first vote must count; then two counting votes downgrade;
a split needs the third). A claim whose second vote stops counting needed a third vote
that was never asked: it is reported as "needs a third vote", not guessed.

Usage:
  .venv/bin/python docs/calibration/2026-10-19_judge_severity/rescore_evidence.py \\
      --scratch <the measure_severity.py scratch folder>

Spec: docs/plan_judge_severity_2026-10-19.md (learning-qa fixes, F4)
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import config  # noqa: E402
import faithfulness_judge as fj  # noqa: E402
import judge_recalibration as jr  # noqa: E402
import measure_severity as ms  # noqa: E402
import release_gate as rg  # noqa: E402


def replay(votes: list, claim: str, source: str) -> str:
    """The outcome of the recorded votes under the current rule."""
    if not votes:
        return fj.WRONG
    ok = [v["severity"] == fj.NOT_QUITE_RIGHT and fj._evidence_in_source(v["evidence"], source, claim)
          for v in votes]
    if not ok[0] or len(votes) == 1:
        return fj.WRONG  # first vote does not count, or vote 2 failed (kept WRONG)
    if ok[1]:
        return fj.NOT_QUITE_RIGHT
    if len(votes) >= 3:
        return fj.NOT_QUITE_RIGHT if ok[2] else fj.WRONG
    return "needs a third vote"


def rows(results: dict, gold: dict, scratch: Path):
    """(set, id, claim, recorded severity, votes, source) for every judged flag."""
    gsrc = jr.gold_sources(json.loads(jr.FAITH_GOLD.read_text(encoding="utf-8")))
    gcases = {c["id"]: c for c in json.loads(jr.FAITH_GOLD.read_text(encoding="utf-8"))["cases"]}
    for n, run in enumerate(gold.get("runs", []), 1):
        for r in run["faithfulness"]["rows"]:
            if "severity_pred" in r:
                yield (f"gold run {n}", r["id"], r["claim"], r["severity_pred"],
                       r["severity_votes"], gsrc[gcases[r["id"]]["source"]])
    why = rg.with_recording_metadata(ms.WHY, (ms.PROSE / ms.WHY / f"{ms.WHY} - formatted.md")
                                     .read_text(encoding="utf-8"))
    for n, run in enumerate(results.get("c", {}).get("runs", []), 1):
        for c in run["claims"]:
            if c["severity"]:
                yield f"c run {n}", "", c["claim"], c["severity"], c["votes"], why
    config.PROJECTS_DIR = scratch
    for d in results.get("d", []):
        src = rg._source_with_metadata(d["talk"])
        for c in d.get("claims", []):
            if c["severity"]:
                yield f"d {d['talk'][:30]} #{d['k']}", "", c["claim"], c["severity"], c["votes"], src
    if results.get("e"):
        src = rg._source_with_metadata(ms.WHY)
        for n, run in enumerate(results["e"]["runs"], 1):
            for a in run["artifacts"]:
                for c in a["claims"]:
                    if c["severity"]:
                        yield f"e check {n}", "", c["claim"], c["severity"], c["votes"], src
    if results.get("f"):
        fsrc = {s: rg.with_recording_metadata(b, p.read_text(encoding="utf-8"))
                for s, (b, p) in ms.DEV_SOURCES.items()}
        for c in results["f"]["claims"]:
            for n, r in enumerate(c["runs"], 1):
                yield (f"f run {n}", c["id"], c["claim"], r["severity"], r["votes"],
                       fsrc[c["section"]])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", type=Path, required=True)
    args = ap.parse_args()
    results = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    gold = json.loads((HERE / "gold_severity.json").read_text(encoding="utf-8"))
    out, changed = {}, []
    for where, cid, claim, old, votes, source in rows(results, gold, args.scratch):
        new = replay(votes, claim, source)
        part = where.split()[0]
        tally = out.setdefault(part, {"judged": 0, "nqr_before": 0, "nqr_after": 0,
                                      "needs_third_vote": 0})
        tally["judged"] += 1
        tally["nqr_before"] += old == fj.NOT_QUITE_RIGHT
        tally["nqr_after"] += new == fj.NOT_QUITE_RIGHT
        tally["needs_third_vote"] += new == "needs a third vote"
        if new != old:
            changed.append({"where": where, "id": cid, "claim": claim, "before": old, "after": new})
    (HERE / "rescore_evidence.json").write_text(
        json.dumps({"by_part": out, "changed": changed}, indent=1, ensure_ascii=False),
        encoding="utf-8")
    for part, t in out.items():
        print(part, t)
    print(f"{len(changed)} outcome(s) changed; saved rescore_evidence.json")


if __name__ == "__main__":
    main()
