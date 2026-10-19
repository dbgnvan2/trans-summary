#!/usr/bin/env python3
"""WO6: the 12 JS6 summary drafts (old prompt) against the 12 made again with the
no-outside-facts rule (new prompt). Same talks, same summary stage, same judge.

For each draft: claims judged, confirmed flags, % of claims supported. Then each new
flag in full, and a text search of both sets of drafts for the outside facts JS6 found.

Usage:
  .venv/bin/python docs/calibration/2026-10-19_outside_facts/compare.py
Writes compare.json next to this file and prints the tables.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "2026-10-19_judge_severity" / "results.json"
NEW = HERE / "results.json"
# The outside facts found in the JS6 drafts (hand labels D10, D14/D20, D16/D19, D17).
OUTSIDE = {"Kansas City": r"Kansas City", "an age": r"\b(?:late|early|mid)[- ](?:twenties|thirties|"
           r"forties|fifties|sixties)\b|\b\d{2}[- ]year[- ]old\b",
           "Marta": r"\bMarta\b", "late <relative>": r"\blate (?:grand)?(?:mother|father|"
           r"husband|wife|brother|sister)\b"}


def rows(path):
    out = []
    for r in json.loads(path.read_text(encoding="utf-8"))["d"]:
        claims = r.get("claims") or []
        n = len(claims) if isinstance(claims, list) else 0
        flags = r.get("flags", 0)
        flags = len(flags) if isinstance(flags, list) else flags
        out.append({"talk": r["talk"], "k": r["k"], "claims": n, "flags": flags,
                    "pct": round(100 * (n - flags) / n) if n else None,
                    "flagged": [c["claim"] for c in claims if c.get("label") != "entailed"],
                    "draft": r.get("draft", ""), "transcript_sha": r.get("transcript_sha")})
        assert len(out[-1]["flagged"]) == flags, (r["talk"], r["k"])  # P6: count = claims
    return out


def main():
    old, new = rows(OLD), rows(NEW)
    assert [(o["talk"], o["k"]) for o in old] == [(n["talk"], n["k"]) for n in new]
    same_src = all(o["transcript_sha"] == n["transcript_sha"] for o, n in zip(old, new))
    print(f"same transcripts in both runs: {same_src}\n")
    print(f"{'talk':40} k  old flags/claims  %   new flags/claims  %")
    for o, n in zip(old, new):
        print(f"{o['talk'][:40]:40} {o['k']}  {o['flags']:>3}/{o['claims']:<3}  {o['pct']:>4}"
              f"   {n['flags']:>3}/{n['claims']:<3}  {n['pct']:>4}")
    tot = lambda rs, key: sum(r[key] for r in rs)  # noqa: E731
    for name, rs in (("old", old), ("new", new)):
        c, f = tot(rs, "claims"), tot(rs, "flags")
        print(f"{name}: {f} flags in {c} claims, {round(100 * (c - f) / c)}% supported; "
              f"{sum(1 for r in rs if r['flags'])} of {len(rs)} drafts with a flag")
    print("\nnew flags:")
    for n in new:
        for c in n["flagged"]:
            print(f"  [{n['talk'][:30]} #{n['k']}] {c}")
    hits = {}
    for name, rs in (("old", old), ("new", new)):
        hits[name] = {label: sum(len(re.findall(rx, r["draft"])) for r in rs)
                      for label, rx in OUTSIDE.items()}
    print("\noutside facts found by text search (old -> new):")
    for label in OUTSIDE:
        print(f"  {label}: {hits['old'][label]} -> {hits['new'][label]}")
    (HERE / "compare.json").write_text(json.dumps(
        {"same_transcripts": same_src, "old": [{k: v for k, v in r.items() if k != "draft"}
                                               for r in old],
         "new": [{k: v for k, v in r.items() if k != "draft"} for r in new],
         "outside_fact_hits": hits}, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
