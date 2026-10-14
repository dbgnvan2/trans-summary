"""Side-by-side theme read for ST.9: the same talks' themes from several end-to-end
runs, one column per run, with word counts.

    python side_by_side.py out.html "Run 5 (old)=<run5 dir>" "Run 6 (ST)=<run6 dir>" ...

Each run dir is an e2e_run.py --out folder (projects/<talk>/<talk> - *-themes.md).
"""
import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import transcript_utils as tu  # noqa: E402


def _body_html(body: str) -> str:
    out, in_list = [], False
    for line in body.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{html.escape(line[2:])}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        m = re.match(r"\*\*([^*]+?):\*\*\s*(.*)", line)
        if m:
            out.append(f"<p><b>{html.escape(m.group(1))}:</b> {html.escape(m.group(2))}</p>")
        else:
            out.append(f"<p>{html.escape(line)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _column(path: Path) -> tuple:
    text = path.read_text(encoding="utf-8")
    blocks = tu.theme_display_blocks(text)
    parsed = tu.parse_theme_blocks_with_evidence(text)
    desc_words = [len(d.split()) for _n, d, _e in parsed]
    all_words = [len(b.split()) for _n, _t, b in blocks]
    items = []
    for (number, name, body), (_n, desc, _e) in zip(blocks, parsed):
        items.append(
            f"<div class='theme'><h4>{html.escape(str(number))}. {html.escape(name)}</h4>"
            f"<div class='desc'>{html.escape(desc)}</div>"
            f"<details><summary>All fields ({len(body.split())} words)</summary>"
            f"{_body_html(body)}</details></div>")
    stats = (f"{len(blocks)} themes · description {sum(desc_words) // max(len(desc_words), 1)} "
             f"words avg · theme {sum(all_words) // max(len(all_words), 1)} words avg")
    return stats, "\n".join(items)


def main(out: str, runs: list) -> None:
    runs = [(label, Path(folder)) for label, folder in (r.split("=", 1) for r in runs)]
    talks = sorted(p.name for p in (runs[0][1] / "projects").iterdir() if p.is_dir())
    sections = []
    for talk in talks:
        for kind in ("structural", "interpretive"):
            cols = []
            for label, folder in runs:
                f = folder / "projects" / talk / f"{talk} - {kind}-themes.md"
                if not f.exists():
                    cols.append(f"<div class='col'><h3>{html.escape(label)}</h3><p>missing</p></div>")
                    continue
                stats, items = _column(f)
                cols.append(f"<div class='col'><h3>{html.escape(label)}</h3>"
                            f"<p class='stats'>{stats}</p>{items}</div>")
            sections.append(f"<section><h2>{html.escape(talk)} — {kind} themes</h2>"
                            f"<div class='grid' style='--n:{len(runs)}'>{''.join(cols)}</div></section>")
    page = TEMPLATE.replace("{{SECTIONS}}", "\n".join(sections))
    Path(out).write_text(page, encoding="utf-8")


TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Theme Side-by-Side</title>
<style>
:root{--bg:#fbfaf7;--fg:#1f1f1c;--muted:#6b6a64;--card:#ffffff;--line:#e3e1da;--accent:#2f5d8a}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#171716;--fg:#e8e6e0;--muted:#a3a198;--card:#21211f;--line:#34332f;--accent:#8cb4e0}}
:root[data-theme="dark"]{--bg:#171716;--fg:#e8e6e0;--muted:#a3a198;--card:#21211f;--line:#34332f;--accent:#8cb4e0}
body{background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,system-ui,sans-serif;margin:0;padding:24px 16px}
h1{font-size:22px;margin:0 0 6px} .intro{color:var(--muted);max-width:70ch;margin:0 0 24px}
h2{font-size:17px;margin:32px 0 12px;border-bottom:1px solid var(--line);padding-bottom:6px}
h3{font-size:14px;margin:0 0 4px;color:var(--accent)} h4{font-size:14px;margin:0 0 6px}
.grid{display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr));gap:14px}
@media (max-width:900px){.grid{grid-template-columns:1fr}}
.col{min-width:0} .stats{color:var(--muted);font-size:12px;margin:0 0 10px}
.theme{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin-bottom:10px}
.desc{font-size:14px} details{margin-top:6px;font-size:13px} summary{cursor:pointer;color:var(--muted)}
details p{margin:6px 0} ul{margin:4px 0 4px 18px;padding:0}
</style></head><body>
<h1>Theme side-by-side</h1>
<p class="intro">The same three public talks: run 5 with the old free-form prompts, runs 6 and 7 with
structured output (ST). Each theme shows its description; open "All fields" for the evidence and the
other fields as published. Look for: are the new themes as good, as specific and as well supported?</p>
{{SECTIONS}}
</body></html>"""

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
