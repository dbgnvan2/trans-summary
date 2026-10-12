"""D1 — the published Themes section is built from the parsed themes, not the whole
themes file: no file title, rule lines, "(3 total)" headings or "Summary Paragraph".

Spec: docs/plan_todo_triage_2026-10-11.md#D1
"""
import shutil
from pathlib import Path
from unittest.mock import patch

import config
import html_generator as hg
from transcript_utils import parse_bold_numbered_theme_blocks

FIX = Path(__file__).parent / "fixtures"
BASE = "Test Talk - A Person - 2021-01-01"


def _project(tmp_path, fixture_dir):
    proj = tmp_path / BASE
    proj.mkdir()
    for name, suffix in (("structural-themes.md", config.SUFFIX_STRUCTURAL_THEMES),
                         ("interpretive-themes.md", config.SUFFIX_INTERPRETIVE_THEMES)):
        shutil.copy(FIX / fixture_dir / name, proj / f"{BASE}{suffix}")
    with patch.object(config, "PROJECTS_DIR", tmp_path):
        return hg._extract_webpage_metadata(BASE)["themes"]


def _expected_names(fixture_dir):
    return [n for f in ("structural-themes.md", "interpretive-themes.md")
            for n, _ in parse_bold_numbered_theme_blocks((FIX / fixture_dir / f).read_text())]


def _assert_clean(themes, names):
    assert names
    for n in names:
        assert f". {n}**" in themes, n
    assert "\n---" not in themes and not themes.startswith("---")
    assert "total)" not in themes
    assert "Summary Paragraph" not in themes
    assert "Prompt version used" not in themes
    assert themes.count("### Structural Themes") == 1
    assert themes.count("### Interpretive Themes") == 1


def test_d1_bold_format_themes_only(tmp_path):
    themes = _project(tmp_path, "roots_bowen_test")
    _assert_clean(themes, _expected_names("roots_bowen_test"))
    assert "**Key evidence:**" in themes  # the theme's own fields are kept


def test_d1_legacy_h3_format_themes_only(tmp_path):
    themes = _project(tmp_path, "monika_h3_themes")
    _assert_clean(themes, _expected_names("monika_h3_themes"))
    assert "Structural Themes —" not in themes  # the file's own title


def test_d1_page_validator_finds_every_theme(tmp_path):
    """The rendered page still exposes each theme as "<strong>N. Name</strong>",
    which the web-page check (RF.P) reads."""
    from bs4 import BeautifulSoup
    from transcript_utils import markdown_to_html
    themes = _project(tmp_path, "roots_bowen_test")
    soup = BeautifulSoup(markdown_to_html(themes), "html.parser")
    shown = [s.get_text(" ", strip=True) for s in soup.find_all("strong")]
    for i, n in enumerate(_expected_names("roots_bowen_test")):
        assert any(s.endswith(n) and s[0].isdigit() for s in shown), n
