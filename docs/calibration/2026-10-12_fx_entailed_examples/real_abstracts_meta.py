"""FX: the 3 real-abstract checks with the gate's recording metadata, N runs, using the
faithfulness judge of the checkout given (old or new prompt).
Usage: python real_abstracts_meta.py CHECKOUT OUT.json N"""
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import faithfulness_judge as fj, release_gate as rg
from transcript_utils import resolve_anthropic_key, get_anthropic_client
FIX = Path("/Users/davemini2/ProjectsLocal/Projects/trans-summary/tests/fixtures")
WR = FIX / "where_roots" / "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid"
CASES = [("roots_bowen", FIX / "roots_bowen_test/formatted.md", FIX / "roots_bowen_test/abstract-generated.md", "PASS", None, "Roots of Bowen TEST - Mike Kerr - 2026-07015"),
         ("where_roots", WR / f"{WR.name} - formatted.md", WR / f"{WR.name} - abstract-generated.md", "FAIL", "Malorni", WR.name),
         ("dave_g", FIX / "dave_g_test2/formatted.md", FIX / "dave_g_test2/abstract-generated.md", "FAIL", "nubbin", "TEST FILE 2 - DAVE G - 2026-07-14")]
c = get_anthropic_client(resolve_anthropic_key())
runs = []
for i in range(int(sys.argv[3])):
    run = []
    for label, src, art, expect, must, base in CASES:
        r = fj.judge_artifact(art.read_text(), rg.with_recording_metadata(base, src.read_text()), c)
        flagged = [x.claim for x in r.unfaithful]
        ok = r.status == expect and (must is None or any(must in f for f in flagged))
        run.append({"artifact": label, "status": r.status, "ok": ok, "flagged": flagged})
        print(i + 1, label, r.status, ok, [f[:80] for f in flagged], flush=True)
    runs.append(run)
Path(sys.argv[2]).write_text(json.dumps({"prompt_sha": hashlib.sha256(fj._JUDGE_INSTRUCTIONS.encode()).hexdigest()[:12], "runs": runs}, indent=1))
