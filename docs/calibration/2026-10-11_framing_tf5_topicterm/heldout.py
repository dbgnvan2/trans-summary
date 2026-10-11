"""Throwaway: held-out check — overviews and summaries of the three fixture talks that
did not shape the prompt, judged as the gate does (transcript + filename metadata),
N runs, no cache. argv: out.json logs_dir N"""
import hashlib, json, logging, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
import config, release_gate as rg, faithfulness_judge as fj
from transcript_utils import get_anthropic_client, resolve_anthropic_key
logging.basicConfig(level=logging.ERROR)
config.LOGS_DIR = Path(sys.argv[2]); config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
client = get_anthropic_client(resolve_anthropic_key())
PR = Path("tests/fixtures/prose_real").resolve(); config.PROJECTS_DIR = PR
talks = ["Societal Emotional Process - Michael Kerr - 2021-12-12_v-valid",
         "Systems Biology Meets Bowen Theory Rethinking Cancer - Michael Kerr - 2021-06-25_20260718_155038",
         "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid"]
out = {"prompt_sha": hashlib.sha256(fj._JUDGE_INSTRUCTIONS.encode()).hexdigest()[:12], "runs": []}
for i in range(int(sys.argv[3])):
    run = {}
    for t in talks:
        src = rg._source_with_metadata(t)
        for suf in (" - overview.md", " - summary-generated.md"):
            f = PR / t / f"{t}{suf}"
            if not f.exists(): continue
            r = fj.judge_artifact(f.read_text(), src, client)
            run[f.name] = {"status": r.status, "flagged": [[c.label, c.claim] for c in r.unfaithful]}
    out["runs"].append(run)
    print(i + 1, {k[-28:]: (v["status"], len(v["flagged"])) for k, v in run.items()}, flush=True)
Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
