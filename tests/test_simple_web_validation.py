"""RF.O — the Simple Web check reads the page the generator actually writes.

The simple-page reader looked for an older layout (div.content / summary-section /
appendices) that templates/simple_webpage.html stopped producing, so every real
simple page failed with "0 sections, abstract missing, no highlights". These tests
generate real pages with html_generator (real templates) and run the real check.

Spec:  docs/plan_run_fixes_2026-10-09.md#RF.O
"""
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

import config
import html_generator as hg
import transcript_validate_webpage as tvw

FX = Path(__file__).parent / "fixtures" / "where_roots"
BASE = "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid"

_TOPICS = """## Topics

### The Brain and Bowen Theory
Where Bowen's concepts sit in the brain.
*_(~50% of transcript; Sections 1-3)_*

### Emotional Reactivity
How reactivity spreads through relationships.
*_(~50% of transcript; Sections 4-6)_*
"""
_STRUCTURAL = """## Structural Themes

### The Emotional System Has a Biological Base

**Description:** Bowen's concepts are tied to brain networks.
"""
_INTERPRETIVE = """## Interpretive / Process Themes

### Seeing the System Changes the Observer

**Description:** Observation itself shifts emotional position.
"""
# Themes use "### " headings: the source-side reader (extract_topics_themes_metadata)
# does not read the current "**1. Name**" format (adjacent issue, RF.O), and with 0
# source themes the Themes check would be skipped.
_SUMMARY = "Kerr links Bowen theory to brain science. " * 20


@pytest.fixture
def project(tmp_path, monkeypatch):
    dst = tmp_path / "projects"
    shutil.copytree(FX, dst)
    d = dst / BASE
    (d / f"{BASE}{config.SUFFIX_TOPICS}").write_text(_TOPICS, encoding="utf-8")
    (d / f"{BASE}{config.SUFFIX_STRUCTURAL_THEMES}").write_text(_STRUCTURAL, encoding="utf-8")
    (d / f"{BASE}{config.SUFFIX_INTERPRETIVE_THEMES}").write_text(_INTERPRETIVE, encoding="utf-8")
    (d / f"{BASE}{config.SUFFIX_SUMMARY_GEN}").write_text(_SUMMARY, encoding="utf-8")
    monkeypatch.setattr(config, "PROJECTS_DIR", dst)
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    return d


def _generate(project, simple: bool) -> Path:
    gen = hg.generate_simple_webpage if simple else hg.generate_webpage
    with patch("html_generator.release_gate.publish_allowed", return_value=True):
        assert gen(BASE) is True
    suffix = config.SUFFIX_WEBPAGE_SIMPLE if simple else config.SUFFIX_WEBPAGE
    return project / f"{BASE}{suffix}"


def test_rfo1_real_simple_page_passes(project):
    page = _generate(project, simple=True)
    meta = tvw.extract_html_simple_metadata(page)
    assert meta["has_abstract"] and meta["has_summary"]
    assert meta["has_topics"] and meta["has_themes"] and meta["has_key_terms"]
    assert meta["bowen_highlights"] > 0 and meta["emphasis_highlights"] > 0
    n_md, _ = tvw.count_sections_in_formatted(project / f"{BASE}{config.SUFFIX_FORMATTED}")
    assert n_md > 0 and tvw.count_sections_in_html(page)[0] == n_md
    assert tvw.validate_webpage(BASE, simple_mode=True) is True


def test_rfo1_real_full_page_still_passes(project):
    _generate(project, simple=False)
    assert tvw.validate_webpage(BASE) is True


def test_rfo2_simple_page_missing_abstract_fails(project):
    """Adversarial (P7): the page renders, but the abstract body is empty."""
    page = _generate(project, simple=True)
    html = page.read_text(encoding="utf-8")
    start = html.index('<div class="abstract">') + len('<div class="abstract">')
    end = html.index("</div>", start)
    page.write_text(html[:start] + html[end:], encoding="utf-8")
    assert tvw.extract_html_simple_metadata(page)["has_abstract"] is False
    assert tvw.validate_webpage(BASE, simple_mode=True) is False


@pytest.mark.parametrize("heading", ["Key Topics", "Themes"])
def test_rfo2_simple_page_empty_section_fails(project, heading):
    """Adversarial (sweep): the template always renders each section's body <div>,
    so an empty Key Topics / Themes body must fail, not count as present."""
    import re
    page = _generate(project, simple=True)
    html = page.read_text(encoding="utf-8")
    html, n = re.subn(
        rf'(<h2>{heading}</h2>\s*<div class="metadata-section">).*?(</div>\s*</section>)',
        r"\1\2", html, count=1, flags=re.DOTALL)
    assert n == 1
    page.write_text(html, encoding="utf-8")
    key = "has_topics" if heading == "Key Topics" else "has_themes"
    assert tvw.extract_html_simple_metadata(page)[key] is False
    assert tvw.validate_webpage(BASE, simple_mode=True) is False


def test_rfo2_legend_marks_do_not_count_as_highlights(project):
    """Adversarial: transcript highlights stripped, legend marks left in place —
    the page must fail, not pass on the four legend <mark>s."""
    page = _generate(project, simple=True)
    html = page.read_text(encoding="utf-8")
    cut = html.index('<div class="transcript">')
    body = html[cut:]
    import re
    body = re.sub(r"<mark[^>]*>", "", body).replace("</mark>", "")
    page.write_text(html[:cut] + body, encoding="utf-8")
    meta = tvw.extract_html_simple_metadata(page)
    assert meta["bowen_highlights"] == 0 and meta["emphasis_highlights"] == 0
    assert tvw.validate_webpage(BASE, simple_mode=True) is False


def test_rfo2_unrecognised_layout_fails(project):
    """A page whose sections the reader cannot find must fail, never pass empty."""
    page = _generate(project, simple=True)
    html = page.read_text(encoding="utf-8").replace('class="section"', 'class="block"')
    page.write_text(html, encoding="utf-8")
    assert tvw.count_sections_in_html(page)[0] == 0
    assert tvw.validate_webpage(BASE, simple_mode=True) is False


def test_rfo3_bowen_label_stops_at_timestamp():
    title = ("Emphasized: X (92%) | Bowen Reference: Bowen on Anxiety "
             "| Timestamp: 00:09:15")
    assert tvw._title_label(title, "Bowen Reference:") == "Bowen on Anxiety"
    assert tvw._title_label(title, "Emphasized:") == "X (92%)"
    assert tvw._title_label("Bowen Reference: Y", "Emphasized:") == ""


@pytest.mark.parametrize("simple", [True, False])
def test_rfo3_no_bowen_reported_missing_on_real_page(project, simple):
    """Before RF.O every timestamped Bowen label read "X | Timestamp: …" and the
    whole list was reported missing on both layouts."""
    page = _generate(project, simple=simple)
    assert tvw.find_missing_bowen_items(BASE, page) == []
