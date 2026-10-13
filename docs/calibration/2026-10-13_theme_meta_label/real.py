"""TM: theme grounding on public talks, old vs new THEME_JUDGE_META_LABELS, fresh cache each check."""
import json, sys, tempfile
from pathlib import Path
from unittest.mock import patch
REPO = Path("/Users/davemini2/ProjectsLocal/Projects/trans-summary"); sys.path.insert(0, str(REPO))
import config, release_gate as rg
OLD = frozenset(config.THEME_JUDGE_META_LABELS - {"nested under structural theme(s)"})
assert "nested under structural theme(s)" in config.THEME_JUDGE_META_LABELS
PR = REPO / "tests/fixtures/prose_real"
MOVED = Path("/Users/davemini2/transcripts/source - MOVED/projects")
PROJECTS = [
    (Path("/Users/davemini2/projects"), "Why Families Repeat the Same Patterns - Michael Kerr - 2026-09-13"),
    (PR, "Societal Emotional Process - Michael Kerr - 2021-12-12_v-valid"),
    (PR, "Systems Biology Meets Bowen Theory Rethinking Cancer - Michael Kerr - 2021-06-25_20260718_155038"),
    (PR, "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid"),
    (MOVED, "Monika Baege and Michael Kerr interview - Michael Kerr - 2010-09-23"),
    (MOVED, "Beautiful Boy Review - Kathleen Kerr - 20260409_182707_v-valid"),
]
runs, out = int(sys.argv[2]), []
for r in range(runs):
    for arm in ("old", "new"):
        labels = OLD if arm == "old" else config.THEME_JUDGE_META_LABELS
        for root, base in PROJECTS:
            with tempfile.TemporaryDirectory() as tmp, patch.object(config, "THEME_JUDGE_META_LABELS", labels), \
                    patch.object(config, "PROJECTS_DIR", root), patch.object(config, "LOGS_DIR", Path(tmp)):
                rg._THEME_JUDGE_CACHE.clear()
                v = rg.check_theme_grounding(base)
            out.append({"run": r + 1, "arm": arm, "base": base[:40], "status": str(v.status),
                        "detail": v.detail[:200], "items": v.items})
            print(r + 1, arm, base[:30], v.status, v.detail[:120], flush=True)
        Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str))
