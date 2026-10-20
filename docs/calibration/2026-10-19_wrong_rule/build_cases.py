"""Collect hand-labelled flagged claims whose source transcript is on this machine.

Sources (all from the repo, read only):
  docs/calibration/2026-10-19_judge_severity/hand_labels.json  (D*, C*, E* hand labels)
  docs/calibration/2026-10-19_judge_severity/results.json       (part c injected W1-W4,
                                                                 part d drafts, part f review)
Transcripts are found by content: a file whose sha256 prefix matches the one the
calibration recorded. The repo's test fixtures are always searched; pass more folders
(e.g. the projects folders on davemini2) to find the rest.

Usage: python build_cases.py [EXTRA_DIR ...]      -> writes cases.json next to this script
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CAL = REPO / "docs/calibration/2026-10-19_judge_severity"
OUT = HERE / "cases.json"

res = json.loads((CAL / "results.json").read_text())
hand = json.loads((CAL / "hand_labels.json").read_text())["labels"]

# Transcripts available here, keyed by the 12-char sha prefix the calibration records.
by_sha = {}
for root in [REPO / "tests/fixtures", *map(Path, sys.argv[1:])]:
    for p in root.rglob("*"):
        if p.suffix in (".md", ".txt") and p.is_file() and p.stat().st_size > 5000:
            by_sha.setdefault(hashlib.sha256(p.read_bytes()).hexdigest()[:12], str(p))

cases, missing = [], []


def add(cid, claim, label, typ, borderline, sha, origin, talk):
    src = by_sha.get(sha)
    row = {"id": cid, "claim": claim, "label": label, "type": typ,
           "borderline": borderline, "transcript": src, "talk": talk, "origin": origin}
    (cases if src else missing).append(row)


# Part d: drafts judged on six talks; hand labels D*.
claim_talk = {}
for run in res["d"]:
    for c in run.get("claims", []):
        claim_talk[c["claim"].strip()] = (run["transcript_sha"], run["talk"])
for x in hand:
    if not x["id"].startswith("D"):
        continue
    hit = next((v for k, v in claim_talk.items() if x["claim"][:60] in k or k[:60] in x["claim"]), None)
    if hit:
        add(x["id"], x["claim"], x["label"], x["type"], x["borderline"], hit[0], "d", hit[1])

# Part c: Why Families summary; hand labels C* plus the four injected WRONG claims.
c_sha = res["c"]["transcript_sha"]
for x in hand:
    if x["id"].startswith("C"):
        add(x["id"], x["claim"], x["label"], x["type"], x["borderline"], c_sha, "c", "Why Families")
inj = None
for run in res["c"]["runs"]:
    if isinstance(run, dict) and run.get("injected"):
        inj = run["injected"]
        break
for typ, v in (inj or {}).items():
    add("INJ-" + typ, v["claim"], "WRONG", typ, False, c_sha, "c-injected", "Why Families")

# Part f: the 43-flag review of 2026-10-18 runs.
shas = res["f"]["source_shas"]
for x in res["f"]["claims"]:
    label = "WRONG" if x["review"] == "wrong" else "NOT QUITE RIGHT"
    add(x["id"], x["claim"], label, x.get("review_type", ""), False,
        shas.get(x["section"], ""), "f", x["section"])

OUT.write_text(json.dumps({"cases": cases, "missing": missing}, indent=1))
from collections import Counter
print("available:", len(cases), Counter(c["label"] for c in cases))
print("missing (transcript not here):", len(missing), Counter(c["talk"][:30] for c in missing))
