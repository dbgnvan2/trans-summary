from unittest.mock import patch

import release_gate
import ts_gui


def _make_gui(logs=None):
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = "Sample"
    gui.logger = None
    gui.log = (lambda *_a, **_k: logs.append(" ".join(str(x) for x in _a))) if logs is not None else (lambda *_a, **_k: None)
    return gui


def test_web_generation_uses_full_page_and_pdf():
    gui = _make_gui()
    allow = release_gate.GateDecision(release_gate.Decision.ALLOW, [], [])

    with patch("release_gate.run_gate", return_value=allow) as mock_gate, \
         patch("ts_gui.pipeline.generate_simple_webpage", return_value=True) as mock_simple, \
         patch("ts_gui.pipeline.generate_webpage", return_value=True) as mock_full, \
         patch("ts_gui.pipeline.generate_pdf", return_value=True) as mock_pdf, \
         patch("ts_gui.transcript_validate_webpage.validate_webpage", return_value=True) as mock_validate:
        success = gui._run_web_pdf_generation()

    assert success is True
    mock_gate.assert_called_once_with("Sample", None)
    mock_simple.assert_not_called()
    mock_pdf.assert_called_once_with("Sample")
    mock_full.assert_called_once_with("Sample")
    mock_validate.assert_called_once_with("Sample")


def test_web_generation_halts_on_gate_block_and_reports_reason():
    """A release-gate BLOCK must surface its real reason and skip web/PDF entirely
    (previously both generators failed opaquely)."""
    logs = []
    gui = _make_gui(logs=logs)
    verdict = release_gate.Verdict(
        "faithfulness", release_gate.Status.FAIL,
        "check failed in summary-generated, overview, blog",
    )
    block = release_gate.GateDecision(
        release_gate.Decision.BLOCK, [verdict], [verdict],
    )

    with patch("release_gate.run_gate", return_value=block), \
         patch("ts_gui.pipeline.generate_webpage") as mock_full, \
         patch("ts_gui.pipeline.generate_pdf") as mock_pdf:
        success = gui._run_web_pdf_generation()

    assert success is False
    mock_full.assert_not_called()
    mock_pdf.assert_not_called()
    assert any("BLOCKED" in l for l in logs)
    assert any("faithfulness" in l for l in logs)
    assert any("summary-generated" in l for l in logs)


# --- R1 (review G1): the GUI BLOCK path must apply the gate's side effects ---

def _block_decision():
    verdict = release_gate.Verdict(
        "faithfulness", release_gate.Status.FAIL, "check failed in blog",
    )
    return release_gate.GateDecision(release_gate.Decision.BLOCK, [verdict], [verdict])


def _project(tmp_path, monkeypatch):
    import config

    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    proj = tmp_path / "Sample"
    proj.mkdir()
    return proj, config


def test_r1a_gui_block_quarantines_stale_bundle(tmp_path, monkeypatch):
    """A BLOCK in the webpdf stage moves a previous ALLOW run's bundle aside."""
    proj, config = _project(tmp_path, monkeypatch)
    stale = [proj / f"Sample{s}" for s in
             (config.SUFFIX_WEBPAGE, config.SUFFIX_WEBPAGE_SIMPLE, config.SUFFIX_PDF)]
    for f in stale:
        f.write_text("old", encoding="utf-8")

    gui = _make_gui()
    with patch("release_gate.run_gate", return_value=_block_decision()):
        assert gui._run_web_pdf_generation() is False

    for f in stale:
        assert not f.exists(), f"{f.name} still looks current after BLOCK"
        assert f.with_name(f.name + ".blocked-stale").exists()


def test_r1b_gui_block_writes_marker_and_manifest(tmp_path, monkeypatch):
    import json

    proj, config = _project(tmp_path, monkeypatch)
    gui = _make_gui()
    with patch("release_gate.run_gate", return_value=_block_decision()):
        gui._run_web_pdf_generation()

    marker = proj / f"Sample{config.SUFFIX_PUBLISH_BLOCKED}"
    assert marker.exists()
    assert "faithfulness" in marker.read_text(encoding="utf-8")
    manifest = json.loads((proj / f"Sample{config.SUFFIX_RUN_MANIFEST}").read_text(encoding="utf-8"))
    assert json.dumps(manifest).count("BLOCK") >= 1


def test_r1c_gui_allow_does_not_quarantine(tmp_path, monkeypatch):
    """ALLOW leaves the bundle in place for the generators to overwrite."""
    proj, config = _project(tmp_path, monkeypatch)
    page = proj / f"Sample{config.SUFFIX_WEBPAGE}"
    page.write_text("current", encoding="utf-8")
    allow = release_gate.GateDecision(release_gate.Decision.ALLOW, [], [])

    gui = _make_gui()
    with patch("release_gate.run_gate", return_value=allow), \
         patch("ts_gui.pipeline.generate_webpage", return_value=True), \
         patch("ts_gui.pipeline.generate_pdf", return_value=True), \
         patch("ts_gui.transcript_validate_webpage.validate_webpage", return_value=True):
        assert gui._run_web_pdf_generation() is True

    assert page.exists()
    assert not (proj / f"Sample{config.SUFFIX_PUBLISH_BLOCKED}").exists()
