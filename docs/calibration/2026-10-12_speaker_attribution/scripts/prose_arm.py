"""Extra prose_real repeats per arm (old = HEAD prompt, no note; new = current)."""
import importlib.util, json, sys
from pathlib import Path
from unittest.mock import patch
REPO = Path("/Users/davemini2/ProjectsLocal/Projects/trans-summary"); sys.path.insert(0, str(REPO))
import faithfulness_judge as fj, transcript_utils as tu, judge_recalibration as jr
from transcript_utils import resolve_anthropic_key, get_anthropic_client
SP = Path(__file__).parent; arm, rep = sys.argv[1], sys.argv[2]
client = get_anthropic_client(resolve_anthropic_key())
if arm == "old":
    spec = importlib.util.spec_from_file_location("old_fj", SP / "old_fj.py"); old = importlib.util.module_from_spec(spec)
    sys.modules["old_fj"] = old; spec.loader.exec_module(old)
    with patch.object(fj, "_JUDGE_INSTRUCTIONS", old._JUDGE_INSTRUCTIONS), patch.object(tu, "has_speaker_labels", lambda t: True):
        out = jr.prose_real(client, "claude-sonnet-5-5")
else:
    out = jr.prose_real(client, "claude-sonnet-5-5")
(SP / f"prose_{arm}_{rep}.json").write_text(json.dumps(out, indent=1))
print(arm, rep, sum(1 for v in out.values() for l in v.values() if l != "entailed"), "of", sum(len(v) for v in out.values()))
