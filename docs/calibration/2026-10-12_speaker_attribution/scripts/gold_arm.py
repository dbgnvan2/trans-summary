"""Run judge_recalibration on this checkout's harness; arm 'old' = HEAD judge prompt and
no unlabeled-speakers note (the gate before SA); arm 'new' = current code."""
import importlib.util, runpy, sys
from pathlib import Path
from unittest.mock import patch
REPO = Path("/Users/davemini2/ProjectsLocal/Projects/trans-summary"); sys.path.insert(0, str(REPO))
import faithfulness_judge as fj, transcript_utils as tu
SP = Path(__file__).parent; arm, out = sys.argv[1], sys.argv[2]
sys.argv = ["judge_recalibration.py", "--model", "claude-sonnet-5-5", "--repeats", "3", "--prose-real", "--out", out]
if arm == "old":
    spec = importlib.util.spec_from_file_location("old_fj", SP / "old_fj.py"); old = importlib.util.module_from_spec(spec)
    sys.modules["old_fj"] = old; spec.loader.exec_module(old)
    assert "SPEAKER ATTRIBUTION" not in old._JUDGE_INSTRUCTIONS
    with patch.object(fj, "_JUDGE_INSTRUCTIONS", old._JUDGE_INSTRUCTIONS), patch.object(tu, "has_speaker_labels", lambda t: True):
        runpy.run_path(str(REPO / "judge_recalibration.py"), run_name="__main__")
else:
    runpy.run_path(str(REPO / "judge_recalibration.py"), run_name="__main__")
