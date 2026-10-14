"""Hash every theme parser output for each theme fixture (ST.7 snapshot).

snapshot.json was made with the code before ST (commit ab31244), from a git worktree:
    python make_snapshot.py <worktree> tests/fixtures > snapshot.json
tests/test_structured_themes_st.py::test_st7_legacy_fixtures_unchanged recomputes it
with the current code (``snapshot``) and compares.
"""
import hashlib, json, sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, sys.argv[1])

import artifact_contracts as ac
import faithfulness_judge as fj
import transcript_utils as tu


def snapshot(fixtures: Path) -> dict:
    out = {}
    for path in sorted(fixtures.rglob("*themes*.md")):
        out[str(path.relative_to(fixtures))] = _hashes(path)
    return out


def _hashes(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    kind = "structural" if "structural" in path.name else "interpretive"
    items = ac.codec("themes").parse_markdown(text, kind)["items"]
    results = {
        "judge_blocks": tu.parse_theme_blocks_with_evidence(text),
        "judge_input": fj.with_theme_evidence(items, text),
        "page_blocks": tu.theme_display_blocks(text),
        "trimmed": tu.trimmed_theme_notes(text),
        "unclassified": tu.unclassified_theme_fields(text),
        "prompt_text": tu.themes_for_prompt(text),
        "codec_items": items,
    }
    return {k: hashlib.sha256(json.dumps(v, ensure_ascii=False).encode()).hexdigest()[:16]
            for k, v in results.items()}


if __name__ == "__main__":
    print(json.dumps(snapshot(Path(sys.argv[2])), indent=1, sort_keys=True))
