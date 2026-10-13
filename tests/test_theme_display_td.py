"""TD — the published Themes section showed the model's closing notes ("Summary
paragraph", "Rationale and coverage summary", "Why these themes were chosen…") as part
of the last theme, because the last theme block runs to the end of the file.

Spec: docs/plan_theme_display_2026-10-13.md
"""
import shutil
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

import config
import html_generator as hg
import transcript_utils as tu

FIX = Path(__file__).parent / "fixtures"
TRAILING = FIX / "theme_trailing"
BASE = "Test Talk - A Person - 2021-01-01"
NOTES = ("Summary paragraph", "Rationale and coverage summary", "Why these themes were chosen",
         "These three themes", "These seven themes")


def _page_themes(tmp_path, structural_fixture):
    proj = tmp_path / BASE
    proj.mkdir(parents=True)
    shutil.copy(TRAILING / structural_fixture, proj / f"{BASE}{config.SUFFIX_STRUCTURAL_THEMES}")
    shutil.copy(FIX / "roots_bowen_test" / "interpretive-themes.md",
                proj / f"{BASE}{config.SUFFIX_INTERPRETIVE_THEMES}")
    with patch.object(config, "PROJECTS_DIR", tmp_path):
        return hg._extract_webpage_metadata(BASE)["themes"]


def test_td1_trailing_notes_not_published(tmp_path):
    for name in ("why_families_structural-themes.md", "beautiful_boy_structural-themes.md",
                 "triangles_lecture_structural-themes.md"):
        themes = _page_themes(tmp_path / name[:5], name)
        html = tu.markdown_to_html(themes)
        for note in NOTES:
            assert note not in themes and note not in html, (name, note)


def test_td1_unlabeled_closing_note_not_published():
    """TD review: the Why Families interpretive file ends with an unlabeled note after
    theme 7 ("These seven themes break the three structural anchors…")."""
    text = (TRAILING / "why_families_interpretive-themes.md").read_text(encoding="utf-8")
    blocks = tu.theme_display_blocks(text)
    assert len(blocks) == 7
    assert "These seven themes" in text
    assert all("These seven themes" not in body for _n, _name, body in blocks)
    assert "**Key evidence:**" in blocks[-1][2]


def test_td1_last_theme_keeps_its_own_fields(tmp_path):
    """UI contract: the last theme still shows its title, Description, Key evidence and
    Coverage / role; only the document-level notes after it are gone."""
    for name in ("why_families_structural-themes.md", "beautiful_boy_structural-themes.md",
                 "triangles_lecture_structural-themes.md"):
        text = (TRAILING / name).read_text(encoding="utf-8")
        blocks = tu.theme_display_blocks(text)
        assert len(blocks) == 3, name
        body = blocks[-1][2]
        assert body.startswith("**Description:**"), name
        assert "**Key evidence:**" in body and "**Coverage / role:**" in body, name
        soup = BeautifulSoup(tu.markdown_to_html(_page_themes(tmp_path / ("p" + name[:5]), name)),
                             "html.parser")
        shown = [s.get_text(" ", strip=True) for s in soup.find_all("strong")]
        assert any(s.startswith("3.") and blocks[-1][1] in s for s in shown), name


def test_td2_no_document_field_remains_in_any_fixture():
    """No published theme in any fixture still carries a document-level field."""
    for f in FIX.rglob("*.md"):
        if "themes" not in f.name:
            continue
        for _num, _name, body in tu.theme_display_blocks(f.read_text(encoding="utf-8")):
            for m in tu._THEME_FIELD_RE.finditer(body):
                assert m.group(1).strip().lower() not in config.THEME_DOCUMENT_LEVEL_LABELS


def test_td2_tail_cut_keeps_a_prefix():
    block = ("**Description:** A theme.\n**Key evidence:** \"Quote.\"\n\n"
             "**Summary paragraph:** Notes about all themes.")
    assert tu._theme_own_text(block) == "**Description:** A theme.\n**Key evidence:** \"Quote.\""
    assert tu._theme_own_text("**Description:** A theme.") == "**Description:** A theme."


def test_td2_document_label_inside_a_theme_drops_only_that_field():
    """TD review (P2): a document-level label with theme fields after it removes only
    that field; the theme's Key evidence and Coverage stay, and it is reported."""
    block = ("**Description:** A theme.\n**Presenter:** Michael Kerr\n"
             "**Key evidence:** \"Quote.\"\n**Coverage / role:** Sections 1-3.")
    own, notes = tu._theme_own_text_report(block)
    assert own == ("**Description:** A theme.\n**Key evidence:** \"Quote.\"\n"
                   "**Coverage / role:** Sections 1-3.")
    assert notes == ["document-level field 'Presenter' inside the theme"]


def test_td2_multi_paragraph_last_field_is_kept():
    """TD re-review (P2): a last field that spans paragraphs keeps them all — Key
    evidence bullets separated by blank lines, a two-paragraph Description — even
    when followed by closing prose. Only a theme-level meta field (one paragraph in
    real files) has its later paragraphs dropped."""
    for block in ("**Description:** A theme.\n**Key evidence:**\n\n- \"q1\"\n\n- \"q2\"\n\n- \"q3\"",
                  "**Description:** First paragraph.\n\nSecond paragraph of the description.",
                  "**Description:** A theme.\n**Key evidence:** \"q\"\n\nA second evidence paragraph."):
        assert tu._theme_own_text(block, last=True) == block, block
    meta_last = "**Description:** A theme.\n**Lens fuel value:** High.\n\nThese themes cover the talk."
    assert tu._theme_own_text(meta_last, last=True) == "**Description:** A theme.\n**Lens fuel value:** High."
    assert tu._theme_own_text(meta_last) == meta_last  # not the last theme: nothing dropped


def test_td2_rule_lines_are_not_closing_notes():
    """TD re-review: a trailing "---" rule is not counted or reported as a dropped note."""
    block = "**Description:** A theme.\n**Lens fuel value:** High.\n\n---\n"
    own, notes = tu._theme_own_text_report(block, last=True)
    assert notes == []


def test_td2_h3_trailing_heading_not_published():
    """TD review: a legacy H3 file's unnumbered closing heading stayed in the last theme."""
    text = ("### 1. First Theme\n**Description:** One.\n**Key evidence:** \"a\"\n\n"
            "### 2. Second Theme\n**Description:** Two.\n**Key evidence:** \"b\"\n\n"
            "### Rationale and coverage\n\nWhy these two themes.\n")
    blocks = tu.theme_display_blocks(text)
    assert [b[1] for b in blocks] == ["First Theme", "Second Theme"]
    assert "Rationale" not in blocks[-1][2] and "Why these two" not in blocks[-1][2]


def test_td3_page_and_judge_list_the_same_themes():
    """TD re-review (P6): a block whose only content is a document-level field is not
    a theme for either the page or the judge (before, the page published it with an
    empty body and the judge never saw it)."""
    text = ("**1. A**\n**Description:** First theme.\n**Key evidence:** \"a\"\n\n"
            "**2. B**\n**Summary paragraph:** Notes about the themes.\n")
    assert [b[1] for b in tu.theme_display_blocks(text)] == ["A"]
    assert [b[0] for b in tu.parse_theme_blocks_with_evidence(text)] == ["A"]


def test_td3_judge_reads_the_published_text():
    """For every fixture theme, the judge's description and evidence are what the
    published body gives."""
    for f in FIX.rglob("*.md"):
        if "themes" not in f.name:
            continue
        text = f.read_text(encoding="utf-8")
        page = {name: body for _n, name, body in tu.theme_display_blocks(text)}
        for name, desc, evidence in tu.parse_theme_blocks_with_evidence(text):
            assert tu._extract_theme_description(page[name]) == desc, (f.name, name)
            assert tu._extract_theme_evidence(page[name]) == evidence, (f.name, name)


def test_td4_gate_reports_left_out_notes_once(tmp_path, monkeypatch):
    """TD re-review (P2): what was left out is reported once per file by the gate."""
    import release_gate as rg
    import faithfulness_judge as fj
    from unittest.mock import MagicMock
    base = "Talk - A Person - 2021-01-01"
    proj = tmp_path / base
    proj.mkdir()
    (proj / f"{base}{config.SUFFIX_FORMATTED}").write_text("Kerr said things.", encoding="utf-8")
    shutil.copy(TRAILING / "why_families_interpretive-themes.md",
                proj / f"{base}{config.SUFFIX_INTERPRETIVE_THEMES}")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "THEME_JUDGE_ENABLED", True)
    monkeypatch.setattr(rg, "_judge_theme_cached", lambda *a, **k: fj.FaithfulnessResult(fj.PASS, "ok"))
    monkeypatch.setattr("transcript_utils.resolve_anthropic_key", lambda: "k")
    monkeypatch.setattr("transcript_utils.get_anthropic_client", lambda k: object())
    logger = MagicMock()
    rg.check_theme_grounding(base, logger)
    infos = [c.args[0] % c.args[1:] for c in logger.info.call_args_list]
    left_out = [m for m in infos if "left out" in m]
    assert len(left_out) == 1 and "unlabeled paragraph" in left_out[0]


def test_td3_document_labels_are_non_evidence():
    assert config.THEME_DOCUMENT_LEVEL_LABELS <= config.THEME_JUDGE_META_LABELS
