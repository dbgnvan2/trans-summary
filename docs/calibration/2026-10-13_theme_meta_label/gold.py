"""TM: judge_recalibration (gold, themes, real abstracts, injected) with old or new labels."""
import runpy, sys
from pathlib import Path
from unittest.mock import patch
REPO = Path("/Users/davemini2/ProjectsLocal/Projects/trans-summary"); sys.path.insert(0, str(REPO))
import config
arm, out = sys.argv[1], sys.argv[2]
sys.argv = ["judge_recalibration.py", "--model", "claude-sonnet-5-5", "--repeats", "3", "--out", out]
labels = config.THEME_JUDGE_META_LABELS - {"nested under structural theme(s)"} if arm == "old" else config.THEME_JUDGE_META_LABELS
with patch.object(config, "THEME_JUDGE_META_LABELS", frozenset(labels)):
    runpy.run_path(str(REPO / "judge_recalibration.py"), run_name="__main__")
