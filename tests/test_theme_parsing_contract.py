"""P19 producer→consumer contract tests for the theme parsers.

Purpose: Guarantee that the two theme consumers read the format the extraction
         stage actually writes (bold-numbered `**N. Title**` blocks), verified
         against the REAL KCFC artifacts — not an idealized synthetic fixture.
Spec:    TODO.md#p19-contract-audit-findings (A1, A2, A3)
Tests:   this file

Background (the bug these tests lock down):
  The real `structural-themes.md` / `interpretive-themes.md` artifacts wrap their
  themes as bold-numbered blocks:

      ### Structural Themes (3 total)      <- scaffolding header, NOT a theme
      **1. Parental Over-Functioning ...** <- real theme
      **Description:** ...
      ...
      ### Summary Paragraph                <- scaffolding header, NOT a theme

  Both parsers used to gate on `"###" in text` first, so they captured the
  scaffolding header as the theme *name* and mashed every real theme into one
  description blob — returning 1 theme (abstract) / 2 junk entries (summary) from
  a 3-/7-theme file and reporting success. Classic P19 zero/wrong-count-from-
  non-empty. These tests read the real bytes and assert the true theme counts and
  names, plus that a non-empty artifact never parses to zero themes silently.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from abstract_pipeline import parse_themes_from_extraction  # noqa: E402
from summary_pipeline import parse_themes  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

STRUCTURAL_REAL_NAMES = [
    "Parental Over-Functioning as the Engine of Offspring Under-Functioning",
    "Differentiation of Self as the Mechanism of Change — Moving from Reactive "
    "Fusion to Defined Position",
    "Multigenerational Transmission of Fusion — The Parent's Own Family of Origin "
    "as the Source System",
]

INTERPRETIVE_REAL_NAME_1 = (
    "The Caretaking Trap: How Protecting the Child Produces the Very Helplessness "
    "It Fears"
)

# Scaffolding names that must NEVER surface as a theme name.
SCAFFOLDING_NAMES = {
    "structural themes (3 total)",
    "interpretive / process themes (7 total)",
    "summary paragraph",
    "structural themes analysis",
}


def _read(name: str) -> str:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture
def structural_md() -> str:
    return _read("kcfc_structural-themes.md")


@pytest.fixture
def interpretive_md() -> str:
    return _read("kcfc_interpretive-themes.md")


# ---------------------------------------------------------------------------
# A2/A3 — summary_pipeline.parse_themes must read the real interpretive format
# ---------------------------------------------------------------------------

def test_a2_summary_parses_all_seven_interpretive_themes(interpretive_md):
    """parse_themes returns the 7 real bold-numbered themes, not 2 junk blobs."""
    themes = parse_themes(interpretive_md)
    assert len(themes) == 7, (
        f"expected 7 interpretive themes, got {len(themes)}: "
        f"{[t['name'] for t in themes]}"
    )


def test_a2_summary_theme_names_are_not_scaffolding(interpretive_md):
    """No parsed theme name is a section header / roll-up / summary scaffold."""
    themes = parse_themes(interpretive_md)
    for t in themes:
        assert t["name"].strip().lower() not in SCAFFOLDING_NAMES, (
            f"scaffolding leaked in as a theme name: {t['name']!r}"
        )
        assert not t["name"].lstrip().startswith("#"), (
            f"heading leaked in as a theme name: {t['name']!r}"
        )


def test_a2_summary_first_interpretive_theme_name_and_body(interpretive_md):
    themes = parse_themes(interpretive_md)
    assert themes[0]["name"] == INTERPRETIVE_REAL_NAME_1
    # The description must be the theme's own Description prose, not a 12k blob of
    # all seven themes run together.
    assert "recursive feedback loop" in themes[0]["description"]
    assert len(themes[0]["description"]) < 3000, (
        "first theme description is a run-together blob of every theme (A2)"
    )


def test_a3_summary_parses_structural_bold_numbered_format(structural_md):
    """parse_themes has a path for the real `**N. Title**` format (A3 regression)."""
    themes = parse_themes(structural_md)
    assert len(themes) == 3
    assert [t["name"] for t in themes] == STRUCTURAL_REAL_NAMES


# ---------------------------------------------------------------------------
# A1 — abstract_pipeline.parse_themes_from_extraction must read the real format
# ---------------------------------------------------------------------------

def test_a1_abstract_structural_theme_names_are_real(structural_md):
    """The abstract parser returns real theme names, never the section header."""
    themes = parse_themes_from_extraction(structural_md)
    assert themes, "parser returned zero themes from a non-empty 3-theme artifact"
    names = [t.name for t in themes]
    for n in names:
        assert n.strip().lower() not in SCAFFOLDING_NAMES, (
            f"scaffolding leaked in as a theme name: {n!r}"
        )
    # The abstract keeps the top themes; whatever it keeps must be the real,
    # bold-numbered themes (in document order), not 'Structural Themes (3 total)'.
    assert names[0] == STRUCTURAL_REAL_NAMES[0]


def test_a1_abstract_interpretive_first_theme_is_real(interpretive_md):
    themes = parse_themes_from_extraction(interpretive_md)
    assert themes, "parser returned zero themes from a non-empty 7-theme artifact"
    assert themes[0].name == INTERPRETIVE_REAL_NAME_1
    assert "recursive feedback loop" in themes[0].description


# ---------------------------------------------------------------------------
# P19 loud-failure guarantee — zero-from-non-empty is never a silent success
# ---------------------------------------------------------------------------

def test_p19_summary_zero_from_nonempty_warns(caplog):
    """A non-empty themes doc that parses to nothing must warn, not pass silently."""
    junk = "This document has prose but no theme structure whatsoever.\n" * 3
    import logging

    with caplog.at_level(logging.WARNING):
        themes = parse_themes(junk)
    assert themes == []
    assert any(
        "theme" in rec.message.lower() for rec in caplog.records
    ), "expected a loud warning when non-empty input parses to zero themes"


def test_p19_abstract_zero_from_nonempty_warns(caplog):
    junk = "Plenty of words here, yet not a single parseable theme block.\n" * 3
    import logging

    with caplog.at_level(logging.WARNING):
        themes = parse_themes_from_extraction(junk)
    assert themes == []
    assert any(
        "theme" in rec.message.lower() for rec in caplog.records
    ), "expected a loud warning when non-empty input parses to zero themes"


def test_p19_empty_input_is_benign(structural_md):
    """Genuinely empty input returns [] and must NOT warn (source-absent is benign)."""
    assert parse_themes("") == []
    assert parse_themes_from_extraction("") == []


# ---------------------------------------------------------------------------
# is_scaffolding_theme_name — adversarial: must not drop a REAL theme (P2)
# ---------------------------------------------------------------------------

def test_scaffolding_classifier_rejects_real_scaffolding():
    from transcript_utils import is_scaffolding_theme_name

    for scaffold in [
        "Structural Themes (3 total)",
        "Interpretive / Process Themes (7 total)",
        "Summary Paragraph",
        "# Structural Themes Analysis",
        "## 2021 Webcast Feb – KCFC",
        "",
    ]:
        assert is_scaffolding_theme_name(scaffold), f"should reject scaffold: {scaffold!r}"


def test_scaffolding_classifier_keeps_real_theme_titles():
    """A false-positive silently drops one theme without tripping the P19 guard,
    so real titles that merely *resemble* scaffolding wording must survive."""
    from transcript_utils import is_scaffolding_theme_name

    for real in [
        "Parental Over-Functioning as the Engine of Offspring Under-Functioning",
        "Differentiation of Self as the Mechanism of Change — Moving from Reactive "
        "Fusion to Defined Position",
        "The Caretaking Trap: How Protecting the Child Produces the Very Helplessness "
        "It Fears",
        # Adversarial: real titles whose wording brushes the scaffolding heuristics.
        "Structural Fusion Across Three Generations",
        "Interpretive Reframing of Symptom as Signal",
        "Summarizing Behaviour as a Relational Strategy",
        "The Conclusion the Mother Reaches About Her Own Family",
    ]:
        assert not is_scaffolding_theme_name(real), f"dropped a real theme: {real!r}"


# ---------------------------------------------------------------------------
# extraction validator sibling (learning-qa Finding 1) — an all-scaffolding
# structural file must NOT validate as usable content, and a real one must.
# ---------------------------------------------------------------------------

def test_extraction_validator_rejects_all_scaffolding_structural():
    from extraction_pipeline import _is_valid_section_content

    all_scaffolding = (
        "# Structural Themes Analysis\n"
        "## 2021 Webcast Feb – KCFC\n\n"
        "---\n\n"
        "### Structural Themes (0 total)\n\n"
        "### Summary Paragraph\n"
        "No themes were produced.\n"
    )
    assert not _is_valid_section_content("structural themes", all_scaffolding), (
        "all-scaffolding structural file must not pass content validation (P19 sibling)"
    )


def test_extraction_validator_accepts_real_structural(structural_md):
    from extraction_pipeline import _is_valid_section_content

    assert _is_valid_section_content("structural themes", structural_md)
    assert _is_valid_section_content("interpretive themes", _read("kcfc_interpretive-themes.md"))
