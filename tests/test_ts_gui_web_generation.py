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
