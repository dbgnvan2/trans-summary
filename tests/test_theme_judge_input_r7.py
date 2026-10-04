"""R7 (review F3): the theme judge sees the whole published theme block.

Spec: docs/plan_review_fixes_2026-10-04.md#R7
"""
import glob
import json
import os

import artifact_contracts as ac
import faithfulness_judge as fj
import transcript_utils as tu

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")

THEMES = """### Structural Themes (1 total)

---

**1. A Real Theme Title**

**Description:** The talk argues that the family is an emotional unit.

**Key evidence:**
- Luciano Malorni's 1975 twin study (Section 4)
- Repeated emphasis on the family unit (Section 6)

**Coverage / role:** Anchors 60% of the lecture.

**Lens fuel value:** High.

---
"""


def _judged_prompt_text(themes_md):
    items = fj.with_theme_evidence(
        ac.codec("themes").parse_markdown(themes_md, "structural")["items"], themes_md)
    blocks = fj.build_theme_judge_prompt(items, "source text")
    return "".join(b["text"] if isinstance(b, dict) else str(b) for b in blocks)


def test_r7a_key_evidence_included():
    text = _judged_prompt_text(THEMES)
    assert "Luciano Malorni's 1975 twin study" in text
    assert "family is an emotional unit" in text


def test_r7b_meta_labels_excluded():
    text = _judged_prompt_text(THEMES)
    assert "Anchors 60%" not in text
    assert "Lens fuel" not in text


def test_r7a_judge_artifact_passes_evidence_to_judge(monkeypatch):
    seen = {}

    def fake_judge(themes, source, client, **_k):
        seen["themes"] = themes
        return [fj.ClaimVerdict(t["name"], fj.GROUNDED, "") for t in themes]

    monkeypatch.setattr(fj, "judge_themes", fake_judge)
    res = fj.judge_themes_artifact(THEMES, "source", "structural", client=object())
    assert res.status == fj.PASS
    assert "Malorni" in seen["themes"][0]["evidence"]


def test_r7c_gold_has_key_evidence_cases():
    gold = json.load(open(os.path.join(FIX, "theme_gold", "gold.json"), encoding="utf-8"))
    cases = [u for u in gold["ungrounded_themes"] if u.get("evidence")]
    assert len(cases) >= 2
    for case in cases:
        src_dir = gold["sources"][case["source"]].split("/")[0]
        real = {n for n, _d, _e in tu.parse_theme_blocks_with_evidence(
            open(os.path.join(FIX, src_dir, "structural-themes.md"), encoding="utf-8").read())}
        assert case["name"] in real, "evidence-only case must reuse a REAL theme"


# Theme counts before R7 (codec items per real themes file, 2026-10-04).
def test_r7d_theme_counts_unchanged():
    files = sorted(glob.glob(os.path.join(FIX, "*", "*themes.md"))
                   + glob.glob(os.path.join(FIX, "prose_real", "*", "*themes.md")))
    assert files
    for f in files:
        md = open(f, encoding="utf-8").read()
        kind = "interpretive" if "interpretive" in f else "structural"
        n_codec = len(ac.codec("themes").parse_markdown(md, kind)["items"])
        n_full = len(tu.parse_theme_blocks_with_evidence(md))
        assert n_codec == n_full == len(tu.parse_bold_numbered_theme_blocks(md)), f
        assert n_codec > 0, f
