"""T1 — the themes parser reads the third real producer format, ``N. **Title**`` with
indented fields (Opus 5.5, 2026-10-12, Kerr "Why Families Repeat the Same Patterns").
The file parsed to zero themes, so the release gate blocked the run.

Spec: docs/plan_todo_triage_2026-10-11.md#T1
"""
from pathlib import Path

import artifact_contracts as ac
import html_generator as hg
from transcript_utils import (
    parse_bold_numbered_theme_blocks,
    parse_theme_blocks_with_evidence,
    theme_display_blocks,
)

FX = Path(__file__).parent / "fixtures"
REAL = (FX / "opus_list_themes" / "structural-themes.md").read_text(encoding="utf-8")
NAMES = ["The Family as an Emotional System, Not Individual Fault",
         "Chronic Anxiety as the Invisible Driver, from Family to Body to Society",
         "Differentiation of Self: Changing Self While Staying in the System"]


def test_t1_real_list_format_parses():
    themes = parse_theme_blocks_with_evidence(REAL)
    assert [n for n, _d, _e in themes] == NAMES
    for _n, desc, evidence in themes:
        assert desc and "Key evidence" not in desc and "Coverage" not in desc
        assert evidence.startswith("Key evidence:")


def test_t1_codec_accepts_the_real_file():
    obj = ac.codec("themes").parse_markdown(REAL, "structural")
    assert len(obj["items"]) == 3


def test_t1_published_section_uses_the_parsed_themes():
    md = hg._themes_markdown(REAL)
    assert md.count("**1. ") == 1 and md.count("**3. ") == 1
    assert "Rationale and Coverage" not in md and "(3 total)" not in md
    assert "**Description:**" in md


def test_t1_existing_formats_unchanged():
    for name in ("roots_bowen_test/structural-themes.md", "monika_h3_themes/structural-themes.md",
                 "kcfc_interpretive-themes.md"):
        text = (FX / name).read_text(encoding="utf-8")
        assert parse_bold_numbered_theme_blocks(text), name


def test_t1_indented_numbered_line_inside_a_theme_is_not_a_theme():
    """Adversarial: a numbered bold line inside a theme's body (indented) must not
    split the theme."""
    text = ("1. **Theme A**\n   **Description:** Body of A.\n"
            "   1. **Not a theme** an inner list item\n\n"
            "2. **Theme B**\n   **Description:** Body of B.\n")
    assert [n for n, _ in parse_bold_numbered_theme_blocks(text)] == ["Theme A", "Theme B"]


def test_t1_bold_format_wins_when_both_appear():
    """A bold-format file is read as bold format; the list pattern is a fallback."""
    text = ("**1. Theme A**\n**Description:** Body of A with a list:\n"
            "1. **Step one** of something\n\n**2. Theme B**\n**Description:** Body of B.\n")
    assert [n for n, _ in parse_bold_numbered_theme_blocks(text)] == ["Theme A", "Theme B"]


def test_t1_display_blocks_for_list_format():
    blocks = theme_display_blocks(REAL)
    assert [b[1] for b in blocks] == NAMES
    assert blocks[0][2].startswith("**Description:**")


import pytest  # noqa: E402


@pytest.mark.parametrize("attr, split_at", [
    ("PROMPT_STRUCTURAL_THEMES_FILENAME", "If you identify only"),
    ("PROMPT_INTERPRETIVE_THEMES_FILENAME", "After the list"),
])
def test_t2_theme_prompts_name_the_parsed_layout(attr, split_at):
    """T2 (+ review sibling): both theme prompts name the parsed layout and their own
    examples parse; the old examples used an inline list layout no parser reads."""
    import config
    prompt = (config.PROMPTS_DIR / getattr(config, attr)).read_text(encoding="utf-8")
    assert "`**N. Title**`" in prompt and "numbered list or table" not in prompt
    marker = "Example output structure:" if "Example output structure:" in prompt else "Example structure:"
    example = prompt.split(marker, 1)[1].split(split_at, 1)[0]
    filled = example.replace("...", "Text.")
    names = [n for n, _ in parse_bold_numbered_theme_blocks(filled)]
    assert names[:2] == ["Title of Theme 1", "Title of Theme 2"], names


def test_t2_structural_prompt_example_parses():
    """T2: the structural-themes prompt names the parsed layout, and its own example
    parses (the old example used the list layout Opus copied)."""
    import config
    from transcript_utils import extract_section
    prompt = (config.PROMPTS_DIR / config.PROMPT_STRUCTURAL_THEMES_FILENAME).read_text(encoding="utf-8")
    assert "`**N. Title**`" in prompt and "numbered list or table" not in prompt
    example = prompt.split("Example output structure:", 1)[1].split("If you identify only", 1)[0]
    filled = example.replace("2–4 sentences.", "A description of the theme.").replace("...", "Text.")
    names = [n for n, _ in parse_bold_numbered_theme_blocks(filled)]
    assert names[:2] == ["Title of Theme 1", "Title of Theme 2"]


def test_t3_self_check_failure_is_reported_in_the_run_log(tmp_path, monkeypatch):
    """T3: a saved artifact that fails its format check is reported through the run's
    logger (the GUI log), not only the separate artifact_contracts log file."""
    from unittest.mock import MagicMock
    import config
    import extraction_pipeline as ep
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    logger = MagicMock()
    ep._save_summary("# Structural Themes\n\nSome prose that is not a theme list at all.\n",
                     "Talk - A Person - 2021-01-01 - yaml.md", "structural-themes", logger=logger)
    msgs = [c.args[0] % c.args[1:] for c in logger.error.call_args_list]
    assert any("format check" in m and "structural-themes" in m for m in msgs)


def test_t3_every_save_in_the_pipeline_passes_the_run_logger():
    """P5: all _save_summary calls pass the run logger."""
    import re as _re
    src = (Path(__file__).resolve().parent.parent / "extraction_pipeline.py").read_text(encoding="utf-8")
    calls = _re.findall(r"_save_summary\((.*?)\)", src.split("def _save_summary", 1)[1], _re.DOTALL)
    assert calls and all("logger=logger" in c for c in calls), [c for c in calls if "logger=logger" not in c]


def test_t1_numbered_bold_rationale_items_are_not_themes():
    """Review (P7): a Rationale section written as `1. **X**` items after the themes
    must not add themes. List-format items need a **Description:** field."""
    import re as _re
    text = _re.sub(r"(?m)^- \*\*(Kerr's personal life story|Societal regression)\*\*",
                   lambda m: "1. **" + m.group(1) + "**", REAL)
    assert "1. **Kerr's personal life story**" in text
    assert [n for n, _ in parse_bold_numbered_theme_blocks(text)] == NAMES
    obj = ac.codec("themes").parse_markdown(text, "structural")
    assert len(obj["items"]) == 3
    # the same, laid out like a theme (title alone on its line, prose below)
    tail = ("\n1. **Kerr's personal life story**\n   Treated as evidence across all three themes.\n"
            "2. **Societal regression**\n   Folded into Theme 2.\n")
    assert [n for n, _ in parse_bold_numbered_theme_blocks(REAL + tail)] == NAMES


def test_t1_mixed_indentation_keeps_fields_apart():
    """Review (P2): a continuation line at column 0, or sub-bullets indented less than
    the fields, must not fold Key evidence into the description."""
    text = ("1. **Theme A**\n   **Description:** Body of A.\nwrapped continuation.\n"
            "   **Key evidence:**\n - Sec 1.\n   **Coverage / role:** Most of it.\n\n"
            "2. **Theme B**\n   **Description:** Body of B.\n   **Key evidence:** Sec 2.\n")
    themes = parse_theme_blocks_with_evidence(text)
    assert [t[0] for t in themes] == ["Theme A", "Theme B"]
    assert "Key evidence" not in themes[0][1] and themes[0][2].startswith("Key evidence: - Sec 1.")


def test_t1_theme_body_is_in_the_judge_cache_key():
    """Review (P6): _theme_body decides what the theme judge sees."""
    import release_gate
    import transcript_utils as tu
    assert tu._theme_body in release_gate._judge_input_functions()
