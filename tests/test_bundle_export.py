"""Tests for the MD-collection bundle export.

Spec: docs/spec_bundle_export_2026-07-16.md
"""

import re
from unittest.mock import MagicMock, patch

import pytest

import config
import bundle_export
import ts_gui


BASE = "Sample Title - Author - 2025-01-01"
# Every candidate suffix attr across all sections (transcript has two).
SECTION_ATTRS = [a for s in config.BUNDLE_SECTIONS for a in s["suffix_attrs"]]
# The suffix each section resolves to when all candidates are present (the first).
FIRST_ATTRS = [s["suffix_attrs"][0] for s in config.BUNDLE_SECTIONS]
HEADINGS = [s["heading"] for s in config.BUNDLE_SECTIONS]


def _make_project(tmp_path, suffix_attrs, base=BASE):
    proj = tmp_path / base
    proj.mkdir(parents=True, exist_ok=True)
    for attr in suffix_attrs:
        suffix = getattr(config, attr)
        (proj / f"{base}{suffix}").write_text(f"body-of-{attr}", encoding="utf-8")
    return proj


# --- BE.2: combine sections in configured order -----------------------------

def test_be2_combines_sections_in_config_order(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    _make_project(tmp_path, SECTION_ATTRS)
    md, included, missing_req, missing_opt, empty = bundle_export._build_combined_markdown(BASE)

    positions = [md.index(f"# {h}") for h in HEADINGS]
    assert positions == sorted(positions), "sections not in configured order"
    assert included == HEADINGS
    assert missing_req == [] and missing_opt == [] and empty == []
    for attr in FIRST_ATTRS:  # each section resolves to its first candidate
        assert f"body-of-{attr}" in md


# --- BE.3: missing OPTIONAL section surfaced, not silent (P2) ----------------

def test_be3_missing_optional_surfaced_not_silent(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    attrs = [a for s in config.BUNDLE_SECTIONS if s["key"] != "topics" for a in s["suffix_attrs"]]
    _make_project(tmp_path, attrs)
    md, included, missing_req, missing_opt, empty = bundle_export._build_combined_markdown(BASE)

    assert "Topics" in missing_opt
    assert "Topics" not in included
    assert "# Topics" not in md
    assert missing_req == [] and empty == []


def test_be3_present_but_empty_section_excluded_not_shipped_blank(tmp_path, monkeypatch):
    """P19: an optional artifact that exists but is empty is excluded from the
    bundle and surfaced (empty_present), never shipped as a blank section."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    proj = _make_project(tmp_path, SECTION_ATTRS)
    # blank out the optional Topics artifact
    (proj / f"{BASE}{config.SUFFIX_TOPICS}").write_text("   \n\n", encoding="utf-8")
    md, included, missing_req, missing_opt, empty = bundle_export._build_combined_markdown(BASE)

    assert "Topics" in empty
    assert "Topics" not in included
    assert "# Topics" not in md
    assert missing_req == []  # optional-empty is not fatal


def test_be3_present_but_empty_required_is_fatal(tmp_path, monkeypatch):
    """A REQUIRED section present-but-empty aborts the bundle (treated as
    missing_required), not shipped blank."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    proj = _make_project(tmp_path, SECTION_ATTRS)
    # both transcript candidates present-but-empty -> the required section resolves
    # to nothing and aborts.
    (proj / f"{BASE}{config.SUFFIX_FORMATTED}").write_text("   \n", encoding="utf-8")
    (proj / f"{BASE}{config.SUFFIX_YAML}").write_text("---\nTitle: x\n---\n", encoding="utf-8")
    with patch("bundle_export.release_gate.publish_allowed", return_value=True), \
         patch("bundle_export._render_pdf_weasyprint") as mpdf, \
         patch("bundle_export._render_docx_pandoc") as mdocx:
        ok = bundle_export.export_bundle(BASE, fmt="both")
    assert ok is False
    mpdf.assert_not_called()
    mdocx.assert_not_called()


def test_be3_export_logs_n_of_m(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    attrs = [a for s in config.BUNDLE_SECTIONS if s["key"] != "topics" for a in s["suffix_attrs"]]
    _make_project(tmp_path, attrs)
    n_included = len(config.BUNDLE_SECTIONS) - 1  # all sections except Topics
    logger = MagicMock()
    with patch("bundle_export.release_gate.publish_allowed", return_value=True), \
         patch("bundle_export._render_pdf_weasyprint", return_value=True), \
         patch("bundle_export._render_docx_pandoc", return_value=True):
        bundle_export.export_bundle(BASE, fmt="both", logger=logger)
    logged = " ".join(str(c.args[0]) % tuple(c.args[1:]) if len(c.args) > 1 else str(c.args[0])
                       for c in logger.info.call_args_list if c.args)
    assert f"{n_included} of {len(config.BUNDLE_SECTIONS)} included" in logged
    assert "Topics" in logged  # the skipped optional is named


# --- BE.4: missing REQUIRED section / nothing found -> honest failure --------

def test_be4_missing_required_aborts_before_render(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    attrs = [a for s in config.BUNDLE_SECTIONS if not s["required"] for a in s["suffix_attrs"]]
    _make_project(tmp_path, attrs)  # required transcript absent
    with patch("bundle_export.release_gate.publish_allowed", return_value=True), \
         patch("bundle_export._render_pdf_weasyprint") as mpdf, \
         patch("bundle_export._render_docx_pandoc") as mdocx:
        ok = bundle_export.export_bundle(BASE, fmt="both")
    assert ok is False
    mpdf.assert_not_called()
    mdocx.assert_not_called()


def test_be4_all_missing_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    (tmp_path / BASE).mkdir(parents=True)
    with patch("bundle_export.release_gate.publish_allowed", return_value=True):
        ok = bundle_export.export_bundle(BASE, fmt="both")
    assert ok is False


# --- BE.5: fail closed on a publish BLOCK -----------------------------------

def test_be5_fails_closed_on_block(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    _make_project(tmp_path, SECTION_ATTRS)
    with patch("bundle_export.release_gate.publish_allowed", return_value=False), \
         patch("bundle_export._render_pdf_weasyprint") as mpdf, \
         patch("bundle_export._render_docx_pandoc") as mdocx:
        ok = bundle_export.export_bundle(BASE, fmt="both")
    assert ok is False
    mpdf.assert_not_called()
    mdocx.assert_not_called()


def test_be_partial_success_returns_false_but_logs_written_format(tmp_path, monkeypatch):
    """F2: fmt='both' where PDF renders but DOCX fails returns False (not every
    requested format produced) yet logs the partial success so the written PDF
    isn't presented as a total failure."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    _make_project(tmp_path, SECTION_ATTRS)
    logger = MagicMock()
    with patch("bundle_export.release_gate.publish_allowed", return_value=True), \
         patch("bundle_export._render_pdf_weasyprint", return_value=True), \
         patch("bundle_export._render_docx_pandoc", return_value=False):
        ok = bundle_export.export_bundle(BASE, fmt="both", logger=logger)
    assert ok is False
    warned = " ".join(
        str(c.args[0]) % tuple(c.args[1:]) if len(c.args) > 1 else str(c.args[0])
        for c in logger.warning.call_args_list if c.args
    )
    assert "partial success" in warned.lower()
    assert "PDF" in warned and "DOCX" in warned


def test_be_invalid_fmt_rejected_before_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    with patch("bundle_export.release_gate.publish_allowed", return_value=True) as mgate:
        ok = bundle_export.export_bundle(BASE, fmt="xml")
    assert ok is False
    mgate.assert_not_called()


# --- BE.6: DOCX via pandoc (hardened) ---------------------------------------

def test_be6_docx_invokes_pandoc(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    _make_project(tmp_path, SECTION_ATTRS)
    fake = MagicMock(returncode=0, stderr="")
    with patch("bundle_export.release_gate.publish_allowed", return_value=True), \
         patch("bundle_export.subprocess.run", return_value=fake) as mrun:
        ok = bundle_export.export_bundle(BASE, fmt="docx")
    assert ok is True
    cmd = mrun.call_args.args[0]
    assert cmd[0] == "pandoc"
    assert cmd[-1].endswith(config.SUFFIX_BUNDLE_DOCX)
    assert mrun.call_args.kwargs.get("timeout") == bundle_export.PANDOC_TIMEOUT_SECONDS


def test_be6_pandoc_missing_reports_error_no_partial_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    _make_project(tmp_path, SECTION_ATTRS)
    with patch("bundle_export.release_gate.publish_allowed", return_value=True), \
         patch("bundle_export.subprocess.run", side_effect=FileNotFoundError()):
        ok = bundle_export.export_bundle(BASE, fmt="docx")
    assert ok is False
    assert not (tmp_path / BASE / f"{BASE}{config.SUFFIX_BUNDLE_DOCX}").exists()


def test_be6_pandoc_nonzero_exit_cleans_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    _make_project(tmp_path, SECTION_ATTRS)
    out = tmp_path / BASE / f"{BASE}{config.SUFFIX_BUNDLE_DOCX}"

    def _fake_run(*a, **k):
        out.write_bytes(b"partial")  # pandoc wrote a partial file then failed
        return MagicMock(returncode=1, stderr="boom")

    with patch("bundle_export.release_gate.publish_allowed", return_value=True), \
         patch("bundle_export.subprocess.run", side_effect=_fake_run):
        ok = bundle_export.export_bundle(BASE, fmt="docx")
    assert ok is False
    assert not out.exists()  # partial removed


# --- BE.7: PDF via WeasyPrint -----------------------------------------------

def test_be7_pdf_written_via_weasyprint(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    _make_project(tmp_path, SECTION_ATTRS)
    fake_html = MagicMock()
    weasy = pytest.importorskip("weasyprint")
    with patch("bundle_export.release_gate.publish_allowed", return_value=True), \
         patch.object(weasy, "HTML", return_value=fake_html) as mHTML:
        ok = bundle_export.export_bundle(BASE, fmt="pdf")
    assert ok is True
    mHTML.assert_called_once()
    fake_html.write_pdf.assert_called_once()


# --- BE.8: CLI base-name resolution -----------------------------------------

def test_be8_cli_resolve_base_name_strips_suffixes():
    import transcript_bundle
    assert transcript_bundle.resolve_base_name(f"{BASE}{config.SUFFIX_YAML}") == BASE
    assert transcript_bundle.resolve_base_name(f"{BASE}{config.SUFFIX_FORMATTED}") == BASE
    assert transcript_bundle.resolve_base_name(f"{BASE}.txt") == BASE
    assert transcript_bundle.resolve_base_name(BASE) == BASE


# --- BE.9: post-run dialog exports a user-selected subset -------------------

def test_be9_build_markdown_honors_section_subset(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    _make_project(tmp_path, SECTION_ATTRS)
    subset = [s for s in config.BUNDLE_SECTIONS if s["key"] in ("transcript", "bowen")]
    md, included, missing_req, missing_opt, empty = bundle_export._build_combined_markdown(
        BASE, sections=subset
    )
    assert included == ["Transcript (Format/YAML)", "Bowen References"]
    assert "# Topics" not in md and "# Emphasis" not in md


def test_be9_run_bundle_export_builds_subset_and_threads():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = BASE
    gui.logger = object()
    gui.log = MagicMock()
    gui.run_task_in_thread = MagicMock()

    gui._run_bundle_export(["transcript", "bowen"], "pdf")

    gui.run_task_in_thread.assert_called_once()
    args = gui.run_task_in_thread.call_args.args
    assert args[0] is ts_gui.pipeline.export_bundle
    assert args[1] == BASE            # base_name
    assert args[2] == "pdf"           # fmt
    passed_sections = args[3]
    assert [s["key"] for s in passed_sections] == ["transcript", "bowen"]


def test_be9_run_bundle_export_no_sections_warns():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = BASE
    gui.logger = object()
    gui.log = MagicMock()
    gui.run_task_in_thread = MagicMock()
    with patch("ts_gui.messagebox.showwarning") as mwarn:
        gui._run_bundle_export([], "pdf")
    mwarn.assert_called_once()
    gui.run_task_in_thread.assert_not_called()


def test_be9_dialog_builds_section_and_format_controls():
    import inspect
    src = inspect.getsource(ts_gui.TranscriptProcessorGUI.open_bundle_dialog)
    assert "BUNDLE_SECTIONS" in src
    assert "Radiobutton" in src and "fmt_var" in src
    assert "_run_bundle_export" in src


# --- BE.10: bundle run-stage uses the default format ------------------------

def test_be10_run_stage_bundle_uses_default_format():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = BASE
    gui.logger = object()
    with patch("ts_gui.pipeline.export_bundle", return_value=True) as mexport:
        ok = gui._run_stage_bundle()
    assert ok is True
    assert mexport.call_args.kwargs.get("fmt") == config.BUNDLE_DEFAULT_FORMAT


# --- BE.11: reduced heading sizes (main = h1, section = h2) -----------------

def test_be11_title_is_h1_sections_are_h2(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    _make_project(tmp_path, SECTION_ATTRS)
    md, included, *_ = bundle_export._build_combined_markdown(BASE)
    assert md.lstrip().startswith(f"# {BASE}")            # main title is h1
    assert len(re.findall(r"(?m)^# ", md)) == 1           # exactly one h1
    assert len(re.findall(r"(?m)^## ", md)) == len(included)  # each section is h2


def test_be11_pdf_injects_reduced_heading_css(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    _make_project(tmp_path, SECTION_ATTRS)
    weasy = pytest.importorskip("weasyprint")
    captured = {}

    class FakeHTML:
        def __init__(self, string=None):
            captured["html"] = string

        def write_pdf(self, path):
            pass

    with patch("bundle_export.release_gate.publish_allowed", return_value=True), \
         patch.object(weasy, "HTML", FakeHTML):
        ok = bundle_export.export_bundle(BASE, fmt="pdf")
    assert ok is True
    assert bundle_export.BUNDLE_PDF_CSS in captured["html"]
    assert "18pt" in captured["html"] and "14pt" in captured["html"]  # h1 main, h2 section


def test_be11_docx_uses_reduced_heading_reference_doc(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    _make_project(tmp_path, SECTION_ATTRS)
    fake = MagicMock(returncode=0, stderr="")
    with patch("bundle_export.release_gate.publish_allowed", return_value=True), \
         patch("bundle_export.subprocess.run", return_value=fake) as mrun:
        bundle_export.export_bundle(BASE, fmt="docx")
    cmd = mrun.call_args.args[0]
    assert "--reference-doc" in cmd
    assert bundle_export._BUNDLE_REFERENCE_DOCX.exists()


def test_be11_reference_docx_has_reduced_heading_sizes():
    """The committed reference doc must carry the reduced heading sizes (main=
    Heading1 32 half-pt=16pt, section=Heading2 26 half-pt=13pt)."""
    import zipfile
    ref = bundle_export._BUNDLE_REFERENCE_DOCX
    assert ref.exists()
    xml = zipfile.ZipFile(ref).read("word/styles.xml").decode("utf-8")
    for style_id, expected in (("Heading1", "32"), ("Heading2", "26")):
        m = re.search(r'w:styleId="' + style_id + r'"[^>]*>(.*?)</w:style>', xml, re.S)
        assert m and f'<w:sz w:val="{expected}"' in m.group(1)


def test_be10_stage_outputs_bundle_tracks_default_format():
    """P19/P4: STAGE_OUTPUTS['bundle'] is derived from BUNDLE_DEFAULT_FORMAT, so
    the 'exists' status can't drift from what _run_stage_bundle writes."""
    expected = {
        "pdf": ["SUFFIX_BUNDLE_PDF"],
        "docx": ["SUFFIX_BUNDLE_DOCX"],
        "both": ["SUFFIX_BUNDLE_DOCX", "SUFFIX_BUNDLE_PDF"],
    }[config.BUNDLE_DEFAULT_FORMAT]
    assert ts_gui.STAGE_OUTPUTS["bundle"] == expected
    assert ts_gui._bundle_output_suffix_attrs() == expected
