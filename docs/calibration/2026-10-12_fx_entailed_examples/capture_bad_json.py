"""Judge where_roots N times; record every reply that fails to parse (raw text).
Usage: python capture_bad_json.py CHECKOUT OUT.json N"""
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import faithfulness_judge as fj, release_gate as rg, judge_recalibration as jr
from transcript_utils import resolve_anthropic_key, get_anthropic_client
c = get_anthropic_client(resolve_anthropic_key())
bad = []
orig = fj._extract_json_array
def spy(text):
    try:
        return orig(text)
    except Exception as e:
        bad.append({"error": str(e), "reply": text})
        raise
fj._extract_json_array = spy
label, src, art, expect, must, base = [r for r in jr.REAL_ABSTRACTS if r[0] == "where_roots"][0]
statuses = []
for i in range(int(sys.argv[3])):
    r = fj.judge_artifact(art.read_text(), rg.with_recording_metadata(base, src.read_text()), c, model="claude-sonnet-5-5")
    statuses.append(r.status); print(i + 1, r.status, len(bad), flush=True)
Path(sys.argv[2]).write_text(json.dumps({"sha": __import__("hashlib").sha256(fj._JUDGE_INSTRUCTIONS.encode()).hexdigest()[:12], "statuses": statuses, "bad": bad}, indent=1))
