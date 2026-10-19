#!/usr/bin/env python3
"""WO6: each text-search hit for an outside fact (compare.OUTSIDE) in the old (JS6) and
new summary drafts, with whether the matched text is in that talk's transcript and
whether the judge flagged the claim that holds it. compare.py counts the raw hits; a
hit that is in the transcript (e.g. "41-year-old") is not an outside fact.

Needs the KCFC transcripts on the external disk (measure_severity.KCFC).

Usage:
  .venv/bin/python docs/calibration/2026-10-19_outside_facts/outside_fact_hits.py
"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, "docs/calibration/2026-10-19_outside_facts")
from compare import OUTSIDE
src = Path("docs/calibration/2026-10-19_judge_severity/measure_severity.py").read_text()
ns = {"Path": Path, "ROOT": Path.cwd()}
for name in ("PROSE", "KCFC"):
    exec(re.search(rf"^{name} = .*$", src, re.M).group(0), ns)
exec(re.search(r"^DRAFT_TALKS = \[.*?\]", src, re.M | re.S).group(0), ns)
dirs = {p.name.removesuffix("_valid"): p for p in ns["DRAFT_TALKS"]}
for run in ("old", "new"):
    f = (Path("docs/calibration/2026-10-19_judge_severity/results.json") if run == "old"
         else Path("docs/calibration/2026-10-19_outside_facts/results.json"))
    for r in json.loads(f.read_text())["d"]:
        d = dirs.get(r["talk"]) or next(p for k, p in dirs.items() if k.startswith(r["talk"][:30]))
        t = next(d.glob("* - formatted.md")).read_text(encoding="utf-8")
        flagged = " ".join(c["claim"] for c in r.get("claims") or [] if c.get("label") != "entailed")
        for label, rx in OUTSIDE.items():
            for m in re.finditer(rx, r["draft"]):
                ctx = " ".join(r["draft"][max(0, m.start()-60):m.end()+40].split())
                print(f"{run} | {r['talk'][:28]} #{r['k']} | {label} | in source: "
                      f"{bool(re.search(re.escape(m.group(0)), t, re.I))} | flagged: {m.group(0) in flagged and any(m.group(0) in c['claim'] for c in r.get('claims') or [] if c.get('label') != 'entailed')} | {ctx}")
