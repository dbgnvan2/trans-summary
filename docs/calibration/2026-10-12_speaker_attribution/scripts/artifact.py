"""SA5: whole-artifact judging (the gate's judge_artifact, with CF confirmation) of
the Kerr 2026-09-13 summary, blog, overview and abstract, old vs new prompt+source."""
import importlib.util, json, sys
from pathlib import Path
from unittest.mock import patch
REPO = Path("/Users/davemini2/ProjectsLocal/Projects/trans-summary"); sys.path.insert(0, str(REPO))
import config, release_gate, faithfulness_judge as fj
from transcript_utils import resolve_anthropic_key, get_anthropic_client
SP = Path(sys.argv[1]); RUNS = int(sys.argv[2])
spec = importlib.util.spec_from_file_location("old_fj", SP / "old_fj.py"); old = importlib.util.module_from_spec(spec); sys.modules["old_fj"] = old; spec.loader.exec_module(old)
OLD, NEW = old._JUDGE_INSTRUCTIONS, fj._JUDGE_INSTRUCTIONS
base = "Why Families Repeat the Same Patterns - Michael Kerr - 2026-09-13"
proj = Path("/Users/davemini2/projects") / base
live = (proj / f"{base} - formatted.md").read_text(encoding="utf-8")
new_src = release_gate.with_recording_metadata(base, live)
old_src = new_src.replace(config.UNLABELED_SPEAKERS_NOTE + "\n", "")
arts = {s.strip(" -"): (proj / f"{base}{s}").read_text(encoding="utf-8")
        for s in config.FAITHFULNESS_ARTIFACT_SUFFIXES if (proj / f"{base}{s}").exists()}
client = get_anthropic_client(resolve_anthropic_key())
rows = []
for r in range(RUNS):
    for cond, instr, src in [c for c in (("old", OLD, old_src), ("new", NEW, new_src)) if c[0] in sys.argv[3].split(",")]:
        for name, text in arts.items():
            with patch.object(fj, "_JUDGE_INSTRUCTIONS", instr):
                res = fj.judge_artifact(text, src, client)
            rows.append({"run": r + 1, "cond": cond, "artifact": name, "status": res.status,
                         "flags": [c.claim for c in res.unfaithful],
                         "overturned": list(res.overturned or [])})
            print(cond, r + 1, name, res.status, len(res.unfaithful), len(res.overturned or []), flush=True)
    (SP / "artifact.json").write_text(json.dumps(rows, indent=1))
