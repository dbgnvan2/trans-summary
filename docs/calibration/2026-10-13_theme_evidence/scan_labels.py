"""Scan theme files for field labels and for themes whose judge input TE changes.
Folders: ~/projects, ~/transcripts, the CrucialX9 KCFC and BTA folders, tests/fixtures."""
import collections, sys
from pathlib import Path
from unittest.mock import patch
REPO = Path(__file__).resolve().parents[3]; sys.path.insert(0, str(REPO))
import config, transcript_utils as tu
ROOTS = [Path.home() / "projects", Path.home() / "transcripts",
         Path("/Volumes/CrucialX9/1 MY DISK/KCFC ALL/projects"),
         Path("/Volumes/CrucialX9/1 MY DISK/BTA ALL ======================="), REPO / "tests/fixtures"]
TE_ADDED = {"rationale and coverage summary", "summary paragraph", "input note", "presenter",
            "why these themes were chosen and how well they cover the presentation"}
files = sorted({p for r in ROOTS if r.exists() for p in r.rglob("*themes*.md")})
labels, changed, themes = collections.Counter(), [], 0
for f in files:
    t = f.read_text(errors="ignore")
    labels.update(m.group(1).strip().lower() for m in tu._THEME_FIELD_RE.finditer(t))
    new = tu.parse_theme_blocks_with_evidence(t); themes += len(new)
    with patch.object(config, "THEME_JUDGE_META_LABELS", frozenset(config.THEME_JUDGE_META_LABELS - TE_ADDED)):
        old = tu.parse_theme_blocks_with_evidence(t)
    if any(a != b for (_, _, a), (_, _, b) in zip(old, new)):
        changed.append(f.name)
print(len(files), "files,", themes, "themes; input changed in:", changed)
for label, n in labels.most_common():
    print(n, label)
