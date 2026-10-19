#!/usr/bin/env python3
"""Join the hand labels (hand_labels.json) with the JS6 severity outcomes (results.json).

The labels were written from blind_flags.md before results.json was read. This script
finds each labelled claim in parts c, d and e by its exact text and reports:
- WRONG-labelled claims judged only NOT QUITE RIGHT (ship criterion d, part d drafts;
  parts c and e reported the same way);
- NOT QUITE RIGHT-labelled claims downgraded, n of m;
- drafts failing old vs new (part d), part e statuses, part c injected outcomes;
- part f agreement with the review's policy labels (not a ship criterion).
No API calls. Writes join.json.

Usage: .venv/bin/python docs/calibration/2026-10-19_judge_severity/join_labels.py
Spec: docs/plan_judge_severity_2026-10-19.md (JS6)
"""
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
NQR, WRONG = "not_quite_right", "wrong"
INJECTED_KEYS = ("1998 Georgetown", "his father who", "two seconds later", "third book")


def appearances(results: dict):
    """(part, where, claim record) for every judged claim in parts c, d and e."""
    for n, run in enumerate(results["c"]["runs"], 1):
        for c in run["claims"]:
            if c.get("severity"):
                yield "c", f"c run {n}", c
    for d in results["d"]:
        for c in d.get("claims", []):
            if c.get("severity"):
                yield "d", f"{d['talk'][:40]} #{d['k']}", c
    for n, run in enumerate(results["e"]["runs"], 1):
        for a in run["artifacts"]:
            for c in a["claims"]:
                if c.get("severity"):
                    yield "e", f"e check {n}", c


def main():
    results = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    labels = json.loads((HERE / "hand_labels.json").read_text(encoding="utf-8"))["labels"]
    by_claim = {lab["claim"]: lab for lab in labels}
    seen, unlabelled, injected = {}, [], []
    for part, where, c in appearances(results):
        if part == "c" and any(k in c["claim"] for k in INJECTED_KEYS):
            injected.append({"where": where, "claim": c["claim"][:60], "severity": c["severity"]})
            continue
        lab = by_claim.get(c["claim"])
        if lab is None:
            unlabelled.append({"where": where, "claim": c["claim"]})
            continue
        seen.setdefault(lab["id"], []).append(
            {"where": where, "severity": c["severity"], "type": c.get("type"),
             "votes": [(v["severity"], v.get("type"), v.get("evidence_found")) for v in c.get("votes", [])]})

    rows = []
    for lab in labels:
        apps = seen.get(lab["id"], [])
        down = sum(a["severity"] == NQR for a in apps)
        rows.append({"id": lab["id"], "label": lab["label"], "borderline": lab["borderline"],
                     "type": lab["type"], "judged": len(apps), "downgraded": down,
                     "judge_types": sorted({a["type"] for a in apps if a["type"]}),
                     "appearances": apps})
    wrong_down = [r for r in rows if r["label"] == "WRONG" and r["downgraded"]]
    nqr = [r for r in rows if r["label"] != "WRONG"]
    nqr_apps = sum(r["judged"] for r in nqr)
    nqr_down_apps = sum(r["downgraded"] for r in nqr)
    nqr_down_ids = [r["id"] for r in nqr if r["downgraded"]]

    drafts = [{"draft": f"{d['talk'][:40]} #{d['k']}", "flags": d.get("flags"),
               "old": d.get("old"), "new": d.get("new"), "error": d.get("error")}
              for d in results["d"]]
    e_runs = [{"check": n, "old": r["old_status"], "new": r["status"]}
              for n, r in enumerate(results["e"]["runs"], 1)]

    f_conf = Counter()
    f_wrong_down = []
    for c in results["f"]["claims"]:
        for n, run in enumerate(c["runs"], 1):
            f_conf[(c["policy"], run["severity"])] += 1
            if c["policy"] == WRONG and run["severity"] == NQR:
                f_wrong_down.append(f"{c['id']} run {n}")

    out = {
        "labels": Counter(lab["label"] for lab in labels),
        "unlabelled_judged_claims": unlabelled,
        "injected_c": injected,
        "wrong_labelled_downgraded": [{k: r[k] for k in ("id", "borderline", "type", "judged",
                                                         "downgraded", "appearances")}
                                      for r in wrong_down],
        "nqr_downgraded_appearances": f"{nqr_down_apps} of {nqr_apps}",
        "nqr_downgraded_claims": f"{len(nqr_down_ids)} of {len(nqr)}",
        "nqr_downgraded_ids": nqr_down_ids,
        "rows": rows,
        "drafts": drafts,
        "drafts_failing_old": sum(d["old"] == "FAIL" for d in drafts),
        "drafts_failing_new": sum(d["new"] == "FAIL" for d in drafts),
        "e_runs": e_runs,
        "f_confusion_policy_vs_judged": {f"{p} -> {s}": n for (p, s), n in sorted(f_conf.items())},
        "f_policy_wrong_downgraded": f_wrong_down,
    }
    (HERE / "join.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print("labels:", dict(out["labels"]), "| unlabelled judged claims:", len(unlabelled))
    print("injected (c):", Counter(i["severity"] for i in injected))
    print("WRONG-labelled claims downgraded:", [(r["id"], f"{r['downgraded']} of {r['judged']}")
                                               for r in wrong_down] or "none")
    print("NQR-labelled downgraded: appearances", out["nqr_downgraded_appearances"],
          "| claims", out["nqr_downgraded_claims"], out["nqr_downgraded_ids"])
    for r in rows:
        print(f"  {r['id']:>4} {r['label']:<16} {'b' if r['borderline'] else ' '} "
              f"judged {r['judged']:>2} downgraded {r['downgraded']:>2} judge types {r['judge_types']}")
    print("drafts failing: old", out["drafts_failing_old"], "new", out["drafts_failing_new"],
          "of", len(drafts))
    for d in drafts:
        print(f"  {d['draft']}: flags {d['flags']} old {d['old']} new {d['new']}"
              + (f" error {d['error']}" if d["error"] else ""))
    print("part e:", [(e["old"], e["new"]) for e in e_runs])
    print("part f policy vs judged:", out["f_confusion_policy_vs_judged"])
    print("part f policy-WRONG downgraded:", f_wrong_down or "none")
    print("saved join.json")


if __name__ == "__main__":
    main()
