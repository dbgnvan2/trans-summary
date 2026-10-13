"""SA5 targeted: role-attributed claims, old vs new judge prompt, unlabeled live vs labelled fixture."""
import importlib.util, json, sys
from pathlib import Path
from unittest.mock import patch
REPO = Path("/Users/davemini2/ProjectsLocal/Projects/trans-summary"); sys.path.insert(0, str(REPO))
import config, release_gate, faithfulness_judge as fj
from transcript_utils import resolve_anthropic_key, get_anthropic_client
SP = Path(sys.argv[1]); RUNS = int(sys.argv[2])
spec = importlib.util.spec_from_file_location("old_fj", SP / "old_fj.py"); old = importlib.util.module_from_spec(spec); sys.modules["old_fj"] = old; spec.loader.exec_module(old)
OLD, NEW = old._JUDGE_INSTRUCTIONS, fj._JUDGE_INSTRUCTIONS
assert OLD != NEW and "SPEAKER ATTRIBUTION" not in OLD
base = "Why Families Repeat the Same Patterns - Michael Kerr - 2026-09-13"
live = (Path("/Users/davemini2/projects") / base / f"{base} - formatted.md").read_text(encoding="utf-8")
labelled = next((REPO / "tests/fixtures/prose_real").glob("Why Families*/*formatted.md")).read_text(encoding="utf-8")
new_live = release_gate.with_recording_metadata(base, live)
old_live = new_live.replace(config.UNLABELED_SPEAKERS_NOTE + "\n", "")
assert config.UNLABELED_SPEAKERS_NOTE in new_live and config.UNLABELED_SPEAKERS_NOTE not in old_live
lab_src = release_gate.with_recording_metadata(base, labelled)
assert config.UNLABELED_SPEAKERS_NOTE not in lab_src
CLAIMS = {
 "U1": "The interviewer observes that most people drift into blaming or self-blaming and cannot see the anxiety flooding through the system.",
 "U2": "The interviewer describes self-differentiation as a scale from no self to pseudo-self to solid self.",
 "U3": "The interviewer reads this as anxiety in the academic field, and Kerr agrees.",
 "U4": "The interviewer observes that staying neutral is easier outside one's own family, where \"you know exactly when they poke you.\"",
 "U5": "The interviewer cites rising divorce rates and youth criminality in the early 1990s.",
 "A1": "The interviewer cites a 1987 survey of 400 families showing that most parents repeat their own parents' mistakes.",
 "A2": "The interviewer says Kerr later moved his practice to Australia to open a clinic there.",
}
ids = list(CLAIMS); claims = [CLAIMS[i] for i in ids]
client = get_anthropic_client(resolve_anthropic_key())
conds = {"old_unlabeled": (OLD, old_live), "new_unlabeled": (NEW, new_live),
         "old_labelled": (OLD, lab_src), "new_labelled": (NEW, lab_src)}
out = {c: {i: [] for i in ids} for c in conds}
for r in range(RUNS):
    for c, (instr, src) in conds.items():
        with patch.object(fj, "_JUDGE_INSTRUCTIONS", instr):
            vs = fj.judge_claims(claims, src, client)
        for i, v in zip(ids, vs):
            out[c][i].append(v.label)
    print(f"run {r+1} done", flush=True)
    (SP / "targeted.json").write_text(json.dumps(out, indent=1))
for c in conds:
    print(c, {i: "".join(l[0].upper() for l in out[c][i]) for i in ids})
