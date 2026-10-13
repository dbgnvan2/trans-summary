"""TE — the theme judge receives only evidence fields. The last theme block ran to
the end of the file, so a document-level paragraph after it ("Summary paragraph",
"Rationale and coverage summary") reached the judge as that theme's evidence.

Spec: docs/calibration_theme_evidence_2026-10-13.md
"""
from pathlib import Path
from unittest.mock import MagicMock

import config
import faithfulness_judge as fj
import release_gate as rg
import transcript_utils as tu

FIXTURES = Path(__file__).parent / "fixtures"

THEMES = """### Structural Themes (2 total)

**1. The Family as One Unit**
**Description:** Kerr treats the family as one emotional unit.
**Key evidence:** "The family is an emotional unit." (Section 2)
**Coverage / role:** Sections 1-4.

---

**2. Anxiety Moves Through the System**
**Description:** Anxiety passes from one member to another.
**Key evidence:** "It is anxiety that is flooding through." (Section 10)
**Coverage / role:** Sections 9-12.

---

**Summary paragraph:** The talk moves from a personal story to the theory and then to
society, and these themes cover all three parts.
"""


def test_te_trailing_document_paragraph_is_not_evidence():
    blocks = tu.parse_theme_blocks_with_evidence(THEMES)
    assert [b[0] for b in blocks] == ["The Family as One Unit", "Anxiety Moves Through the System"]
    assert blocks[-1][2] == 'Key evidence: "It is anxiety that is flooding through." (Section 10)'


def test_te_real_trailing_paragraphs_are_not_evidence():
    """The real files that showed the problem: the last theme's evidence is only its
    Key evidence."""
    for name in ("why_families_structural-themes.md", "beautiful_boy_structural-themes.md",
                 "triangles_lecture_structural-themes.md"):
        blocks = tu.parse_theme_blocks_with_evidence(
            (FIXTURES / "theme_trailing" / name).read_text(encoding="utf-8"))
        assert blocks, name
        for _n, _d, evidence in blocks:
            assert evidence.startswith("Key evidence: ") and "; " not in evidence.split(
                "Key evidence: ", 1)[0], name
            assert "Summary paragraph" not in evidence and "Rationale and coverage" not in evidence
            assert "Why these themes" not in evidence, name


def test_te_key_evidence_kept_for_every_theme():
    for _name, _desc, evidence in tu.parse_theme_blocks_with_evidence(THEMES):
        assert evidence.startswith("Key evidence: ")


def test_te_every_real_fixture_label_is_classified():
    """Contract: every field the judge reads, in every real theme fixture, is either
    evidence or known non-evidence, so a new label is a decision, not an accident.
    Scans the parsed theme blocks (TE review: a raw-text scan missed indented
    list-format fields)."""
    files = [p for p in FIXTURES.rglob("*.md") if "themes" in p.name]
    assert len(files) >= 10
    for f in files:
        assert tu.unclassified_theme_fields(f.read_text(encoding="utf-8")) == [], f.name
    opus = (FIXTURES / "opus_list_themes" / "structural-themes.md").read_text(encoding="utf-8")
    assert len(tu.theme_field_labels(opus)) == 9  # 3 themes x 3 indented fields (raw scan: 1)


def test_te_real_trailing_fields_are_covered_by_fixtures():
    """TE review: each document-level label added to the meta set occurs inside a theme
    block in a real fixture, so removing it from config fails the contract test.
    ("Input note" and "Presenter" sit before the first theme, outside any block.)"""
    trailing = {"summary paragraph", "rationale and coverage summary",
                "why these themes were chosen and how well they cover the presentation"}
    seen = set()
    for f in FIXTURES.rglob("*.md"):
        if "themes" in f.name:
            seen |= {label.lower() for _n, label in
                     tu.theme_field_labels(f.read_text(encoding="utf-8"))}
    assert trailing <= seen, trailing - seen
    assert trailing <= config.THEME_JUDGE_META_LABELS


def test_te_unknown_field_is_still_sent_and_reported():
    """Fail closed: a field in neither list reaches the judge and is listed by
    unclassified_theme_fields (which the gate reports once per file)."""
    text = THEMES.replace("**Coverage / role:** Sections 9-12.",
                          "**Supporting study:** A 1987 survey of 400 families.")
    evidence = tu.parse_theme_blocks_with_evidence(text)[-1][2]
    assert "Supporting study: A 1987 survey of 400 families." in evidence
    assert tu.unclassified_theme_fields(text) == [
        ("Anxiety Moves Through the System", "Supporting study")]
    assert tu.unclassified_theme_fields(THEMES) == []


def test_te_gate_reports_unclassified_fields_once(tmp_path, monkeypatch):
    """TE review (P2): the gate logs one warning per file naming the field and theme,
    and records it in the verdict."""
    base = "Talk - A Person - 2021-01-01"
    proj = tmp_path / base
    proj.mkdir()
    (proj / f"{base}{config.SUFFIX_FORMATTED}").write_text("Kerr said things.", encoding="utf-8")
    (proj / f"{base}{config.SUFFIX_STRUCTURAL_THEMES}").write_text(
        THEMES.replace("**Coverage / role:** Sections 9-12.", "**Supporting study:** x."),
        encoding="utf-8")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "THEME_JUDGE_ENABLED", True)
    monkeypatch.setattr(rg, "_judge_theme_cached",
                        lambda *a, **k: fj.FaithfulnessResult(fj.PASS, "ok"))
    monkeypatch.setattr("transcript_utils.resolve_anthropic_key", lambda: "k")
    monkeypatch.setattr("transcript_utils.get_anthropic_client", lambda k: object())
    logger = MagicMock()
    v = rg.check_theme_grounding(base, logger)
    assert v.items == [{"artifact": "structural-themes.md",
                        "unclassified_fields": ["Anxiety Moves Through the System: Supporting study"]}]
    assert "1 unclassified theme field(s)" in v.detail
    warned = [c.args[0] % c.args[1:] for c in logger.warning.call_args_list]
    assert len(warned) == 1 and "Supporting study (Anxiety Moves Through the System)" in warned[0]


def test_te_evidence_and_meta_sets_do_not_overlap():
    assert not (config.THEME_EVIDENCE_LABELS & config.THEME_JUDGE_META_LABELS)
    assert config.THEME_EVIDENCE_LABELS == frozenset({"key evidence"})
