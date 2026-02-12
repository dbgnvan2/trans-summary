from unittest.mock import patch

import ts_gui


def test_web_generation_uses_simple_mode_only():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = "Sample"
    gui.log = lambda *_args, **_kwargs: None

    with patch("ts_gui.pipeline.generate_simple_webpage", return_value=True) as mock_simple, \
         patch("ts_gui.pipeline.generate_webpage", return_value=True) as mock_full, \
         patch("ts_gui.pipeline.generate_pdf", return_value=True) as mock_pdf, \
         patch("ts_gui.transcript_validate_webpage.validate_webpage", return_value=True) as mock_validate:
        success = gui._run_web_pdf_generation()

    assert success is True
    mock_simple.assert_called_once_with("Sample")
    mock_pdf.assert_called_once_with("Sample")
    mock_full.assert_not_called()
    mock_validate.assert_called_once_with("Sample", simple_mode=True)
