"""Throwaway: topic/key-term check + TF.5 on whichever checkout is the cwd.
argv: out.json logs_dir"""
import hashlib, json, logging, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
import config, release_gate as rg
config.LOGS_DIR = Path(sys.argv[2]); config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
log = logging.getLogger("tt"); logging.basicConfig(level=logging.ERROR)
out = {"prompt_sha": hashlib.sha256(__import__("faithfulness_judge")._JUDGE_INSTRUCTIONS.encode()).hexdigest()[:12],
       "topic_term": {}, "tf5": {}}
PR = Path("tests/fixtures/prose_real").resolve()
config.PROJECTS_DIR = PR
for talk in sorted(p.name for p in PR.iterdir() if p.is_dir()):
    if not any((PR / talk / f"{talk}{s}").exists() for s in config.TOPIC_TERM_FAITHFULNESS_SUFFIXES):
        continue
    v = rg.check_topic_term_faithfulness(talk, log)
    out["topic_term"][talk] = {"status": str(v.status), "detail": v.detail, "items": v.items}
    print(talk[:40], v.status, v.detail[:120], flush=True)
config.PROJECTS_DIR = Path("/Users/davemini2/projects")
base = "Why Families Repeat the Same Patterns - Michael Kerr - 2026-09-13"
files = {}
for s in config.FAITHFULNESS_ARTIFACT_SUFFIXES:
    f = config.PROJECTS_DIR / base / f"{base}{s}"
    if f.exists():
        files[f.name] = {"path": str(f), "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
                         "mtime": f.stat().st_mtime}
v = rg.check_faithfulness(base, log)
out["tf5"] = {"status": str(v.status), "detail": v.detail, "items": v.items, "files": files}
print("TF.5", v.status, v.detail[:150])
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str))
