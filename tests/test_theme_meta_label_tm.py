"""TM — the interpretive-themes field "Nested under structural theme(s)" is meta, not
evidence. 21 of 25 real interpretive files use that label (the prompt names it), but
only "nested under structural themes" was in config.THEME_JUDGE_META_LABELS, so the
field reached the theme judge as evidence.

Spec: docs/calibration_theme_meta_label_2026-10-13.md
"""
from pathlib import Path

import config
import release_gate
import transcript_utils as tu

BLOCK = """**1. The Family as One Unit**
**Description:** Kerr treats the family as a single emotional unit.
**Nested under structural theme(s):** Theme 2, Theme 3
**Key evidence:** "The family is an emotional unit."
**Lens fuel value:** High
"""


def test_tm_parenthesised_label_is_not_evidence():
    evidence = tu._extract_theme_evidence(BLOCK)
    assert "Nested under" not in evidence
    assert "Key evidence: \"The family is an emotional unit.\"" in evidence


def test_tm_older_label_still_excluded():
    old = BLOCK.replace("structural theme(s)", "structural themes")
    assert "Nested under" not in tu._extract_theme_evidence(old)


def test_tm_real_files_send_no_nested_under_field():
    """Every real interpretive fixture: no theme's evidence carries the field, and
    every theme still carries its Key evidence."""
    files = list((Path(__file__).parent / "fixtures").rglob("*interpretive-themes.md"))
    assert len(files) >= 5
    for f in files:
        blocks = tu.parse_theme_blocks_with_evidence(f.read_text(encoding="utf-8"))
        for _name, _desc, evidence in blocks:
            assert "nested under" not in evidence.lower(), f.name


def test_tm_cache_key_changes_with_the_label_set():
    from unittest.mock import patch

    import faithfulness_judge as fj
    before = release_gate._judge_logic_version(fj._THEME_JUDGE_INSTRUCTIONS)
    with patch.object(config, "THEME_JUDGE_META_LABELS",
                      config.THEME_JUDGE_META_LABELS - {"nested under structural theme(s)"}):
        assert release_gate._judge_logic_version(fj._THEME_JUDGE_INSTRUCTIONS) != before
    assert config.JUDGE_LOGIC_VERSION >= "2026-10-13"
