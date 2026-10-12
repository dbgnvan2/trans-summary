"""C2: release_gate.check_topic_term_faithfulness (current code, with CF) on real
projects, REPEATS fresh runs each (fresh LOGS_DIR -> no judge cache).
Usage: python c2_topic_term.py OUT_DIR PROJECT_DIR [PROJECT_DIR...]"""
import json, logging, shutil, sys
from pathlib import Path
sys.path.insert(0, "/Users/davemini2/ProjectsLocal/Projects/trans-summary")
import config, release_gate as rg
REPEATS = 2
out = Path(sys.argv[1]); dirs = [Path(p) for p in sys.argv[2:]]
rows = []
for r in range(REPEATS):
    work = out / f"r{r + 1}"
    for d in dirs:
        dst = work / "projects" / d.name
        if not dst.exists():
            dst.mkdir(parents=True)
            for f in d.iterdir():
                if f.suffix == ".md" or f.name.endswith((".txt",)):
                    shutil.copy(f, dst / f.name)
        config.PROJECTS_DIR = config.settings.PROJECTS_DIR = work / "projects"
        config.LOGS_DIR = config.settings.LOGS_DIR = work / "logs"
        rg._FAITHFULNESS_CACHE.clear()
        v = rg.check_topic_term_faithfulness(d.name, logging.getLogger("c2"))
        flagged = [u for it in v.items for u in it.get("unfaithful", [])]
        over = [o for it in v.items for o in (it.get("overturned") or [])]
        row = {"run": r + 1, "project": d.name, "status": str(v.status), "detail": v.detail,
               "flagged": flagged, "overturned": [o.get("claim", "")[:150] for o in over]}
        rows.append(row); print(json.dumps(row)[:400], flush=True)
        (out / "results.json").write_text(json.dumps(rows, indent=2))
