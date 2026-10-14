"""TP: compare the theme text the generation prompts received (the section as loaded)
with themes_for_prompt's text, on every real theme file. Local reads only.

Every removed non-blank line is one of: scaffolding (heading, '---'), the theme's
header line (rewritten as **N. Name**), preamble before the first theme, a closing note
after the last theme's own text, or INSIDE a theme (reported in full: should only be a
document-level field). Every prompt line must come from the original or be a header.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/Users/davemini2/ProjectsLocal/Projects/trans-summary")
import extraction_pipeline as ep  # noqa: E402
import transcript_utils as tu  # noqa: E402

ROOTS = [Path.home() / "projects", Path.home() / "transcripts",
         Path("/Volumes/CrucialX9/1 MY DISK/KCFC ALL"),
         Path("/Volumes/CrucialX9/1 MY DISK/BTA ALL ======================="),
         Path("/Users/davemini2/ProjectsLocal/Projects/trans-summary/tests/fixtures")]
NAMES = {"structural": ["Structural Themes"],
         "interpretive": ["Interpretive Themes", "Themes", "Key Themes", "Interpretive / Process Themes"]}

files = sorted({p for r in ROOTS if r.exists() for p in r.rglob("*themes.md")
                if "structural" in p.name or "interpretive" in p.name})
totals = {"files": 0, "themes": 0, "unchanged": 0, "passed_through": 0, "trailing": 0,
          "preamble": 0, "inside": 0, "added": 0}
inside, added, changed = [], [], []
for f in files:
    kind = "structural" if "structural" in f.name else "interpretive"
    content = tu.strip_yaml_frontmatter(f.read_text(encoding="utf-8", errors="replace"))
    loaded = ep._extract_first_section(content, NAMES[kind]) or content.strip()
    prompt = tu.themes_for_prompt(loaded)
    blocks = tu.theme_display_blocks(loaded)
    totals["files"] += 1
    totals["themes"] += len(blocks)
    if prompt == loaded:
        totals["passed_through" if not blocks else "unchanged"] += 1
        continue
    orig = [ln.strip() for ln in loaded.splitlines()]
    plines = {ln.strip() for ln in prompt.splitlines()}
    headers = {f"**{n}. {name}**" for n, name, _b in blocks}
    names = [name for _n, name, _b in blocks]
    body_lines = [ln.strip() for _n, _nm, b in blocks for ln in b.splitlines() if ln.strip()]
    first_hdr = next((i for i, ln in enumerate(orig) if names and names[0] in ln), 0)
    last_body = max((i for i, ln in enumerate(orig) if ln and ln in body_lines), default=len(orig))
    file_trailing = []
    for i, ln in enumerate(orig):
        if not ln or ln in plines or ln == "---" or ln.startswith("#"):
            continue
        if any(nm in ln for nm in names) and len(ln) < 200 and i <= last_body:
            continue  # the theme's own header line, rewritten as **N. Name**
        if i < first_hdr:
            totals["preamble"] += 1
        elif i > last_body:
            totals["trailing"] += 1
            file_trailing.append(ln[:90])
        else:
            totals["inside"] += 1
            inside.append((str(f)[-90:], ln[:160]))
    for ln in plines:
        if ln and ln not in set(orig) and ln not in headers:
            totals["added"] += 1
            added.append((str(f)[-90:], ln[:160]))
    changed.append({"file": str(f)[-110:], "themes": len(blocks),
                    "trailing_removed": file_trailing[:4]})
print(json.dumps(totals))
print("files with removed closing notes:")
for c in changed:
    if c["trailing_removed"]:
        print(" ", c["file"], "|", c["trailing_removed"][:2])
print("INSIDE removals:", len(inside))
for x in inside[:40]:
    print("  ", x)
print("ADDED lines:", len(added))
for x in added[:20]:
    print("  ", x)
