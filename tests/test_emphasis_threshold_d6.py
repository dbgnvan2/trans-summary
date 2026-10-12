"""D6 — the Emphasis validator uses the release gate's verbatim test, so it cannot
report a quote as a "partial match" (pass) that the gate will block.

Measured 2026-10-12 on 752 real quotes (33 projects): the gate passed 696; 24 more
scored 0.80-0.95 ("partial", validator pass) but failed the gate's word coverage.
The gate's 0.80 head/tail threshold is kept: 0.95 would reject 4 real near-verbatim
quotes to catch 2 (see docs/plan_todo_triage_2026-10-11.md#D6).
"""
import logging
import shutil
from pathlib import Path

import pytest

import config
import validation_pipeline as vp

FX = Path(__file__).parent / "fixtures" / "where_roots"
BASE = "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid"


@pytest.fixture
def cloned_run(tmp_path, monkeypatch):
    dst = tmp_path / "projects"
    shutil.copytree(FX, dst)
    monkeypatch.setattr(config, "PROJECTS_DIR", dst)
    return dst / BASE


def test_d6_one_changed_word_fails_validator_like_the_gate(cloned_run, caplog):
    proj = cloned_run
    fmt = proj / f"{BASE}{config.SUFFIX_FORMATTED}"
    scored = proj / f"{BASE}{config.SUFFIX_EMPHASIS_SCORED}"
    lines = scored.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith('"Einstein had his theory'):
            words = line.strip().strip('"').split()
            words[len(words) // 2] = "never"  # one word changed mid-quote
            altered = " ".join(words)
            lines[i] = f'"{altered}"'
            break
    else:
        pytest.fail("anchor quote not found in fixture")
    scored.write_text("\n".join(lines))
    src = fmt.read_text()
    ok, ends, cov = vp.quote_is_verbatim_for_gate(altered, src)
    assert not ok and vp._emphasis_quote_found_ratio(altered, src) >= config.EMPHASIS_QUOTE_PARTIAL_RATIO
    with caplog.at_level(logging.ERROR):
        assert vp.validate_emphasis_items(fmt, fmt, logging.getLogger("t")) is False
    assert any("NOT FOUND" in r.message for r in caplog.records)


def test_d6_real_run_still_passes(monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", FX)
    fmt = FX / BASE / f"{BASE}{config.SUFFIX_FORMATTED}"
    assert vp.validate_emphasis_items(fmt, fmt, logging.getLogger("t")) is True


def test_d6_gate_threshold_kept():
    assert config.EMPHASIS_QUOTE_PARTIAL_RATIO == 0.80


def test_d6_standalone_cli_runs_and_uses_gate_test(cloned_run, capsys):
    """Sweep: transcript_validate_emphasis crashed on 3-tuple items (scored file
    present) and used a 15-word head match; it now uses the gate's test and
    reports failure through its return value / exit code."""
    import transcript_validate_emphasis as tve
    fmt = cloned_run / f"{BASE}{config.SUFFIX_FORMATTED}"
    assert tve.validate_emphasis_items(BASE, fmt) is True
    scored = cloned_run / f"{BASE}{config.SUFFIX_EMPHASIS_SCORED}"
    lines = scored.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith('"Einstein had his theory'):
            words = line.strip().strip('"').split()
            words[len(words) // 2] = "never"
            lines[i] = '"' + " ".join(words) + '"'
            break
    scored.write_text("\n".join(lines))
    assert tve.validate_emphasis_items(BASE, fmt) is False
    assert "NOT FOUND" in capsys.readouterr().out
