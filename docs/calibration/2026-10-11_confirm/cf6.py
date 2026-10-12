"""Throwaway: the Kerr project's faithfulness check N times, fresh cache each run.
argv: out.json logs_root N   (run from the checkout whose prompt is being tested)"""
import csv, hashlib, json, logging, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
import config, release_gate as rg, faithfulness_judge as fj
logging.basicConfig(level=logging.ERROR)
base = "Why Families Repeat the Same Patterns - Michael Kerr - 2026-09-13"
config.PROJECTS_DIR = Path("/Users/davemini2/projects")
files = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
         for s in config.FAITHFULNESS_ARTIFACT_SUFFIXES
         if (f := config.PROJECTS_DIR / base / f"{base}{s}").exists()}
runs = []
for i in range(int(sys.argv[3])):
    config.LOGS_DIR = Path(sys.argv[2]) / f"run{i}"; config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    rg._FAITHFULNESS_CACHE.clear() if hasattr(rg, "_FAITHFULNESS_CACHE") else None
    v = rg.check_faithfulness(base, logging.getLogger("tf5"))
    cost = 0.0
    p = config.LOGS_DIR / "token_usage.csv"
    if p.exists():
        for r in csv.reader(p.open()):
            try: cost += float(r[-1])
            except (ValueError, IndexError): pass
    flagged = [(it["artifact"], c) for it in (v.items or []) for c in it.get("unfaithful", [])]
    over = [(it["artifact"], o["claim"]) for it in (v.items or []) for o in it.get("overturned", [])]
    runs.append({"status": str(v.status), "flagged": flagged, "overturned": over, "cost": round(cost, 4)})
    print(i + 1, v.status, round(cost, 3), "flagged:", [c[:70] for _, c in flagged], "overturned:", [c[:70] for _, c in over], flush=True)
Path(sys.argv[1]).write_text(json.dumps({"prompt_sha": hashlib.sha256(fj._JUDGE_INSTRUCTIONS.encode()).hexdigest()[:12],
                                         "files": files, "runs": runs}, indent=1))
